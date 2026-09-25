"""
Tests for recording class sessions (teaching app): the two session
forms, and the create / edit / list views -- including that a teacher
only ever reaches the class subjects of their own TeacherAssignment.
"""

import jdatetime
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_class_subject,
    make_grade,
    make_school_class,
    make_subject,
    make_superuser,
    make_teacher_profile,
    make_user,
)
from school.models import ClassSubject
from teaching.forms import SchoolSessionForm, SessionContentForm
from teaching.models import SchoolSession, SessionContent
from teaching.views import DUPLICATE_SESSION_MESSAGE, SESSIONS_PER_PAGE, _save_session

CONTENT_DATA = {
    'title': 'جمع اعداد چند رقمی',
    'content': 'جمع ستونی با انتقال رقم',
    'homework': 'تمرین‌های صفحه ۱۲',
}


def make_class_subject_for(teacher):
    branch = make_branch()
    year = make_academic_year()
    school_class = make_school_class(branch, make_grade(), year)
    assignment = make_assignment(teacher, branch, year)
    # runs from 1403-07-01 to 1404-03-31
    return make_class_subject(school_class, make_subject(), assignment)


def make_session(class_subject, date, with_content=True, **content):
    session = SchoolSession.objects.create(class_subject=class_subject, date=date)
    if with_content:
        SessionContent.objects.create(session=session, **{**CONTENT_DATA, **content})
    return session


def post_data(class_subject, date='1403-08-01', **overrides):
    return {
        'class_subject': class_subject.pk,
        'date': date,
        'status': SchoolSession.Status.HELD,
        **CONTENT_DATA,
        **overrides,
    }


# ----------------------------------------------------------------------
# Forms
# ----------------------------------------------------------------------

class SessionContentFormTests(TestCase):

    def test_valid_without_activity_and_notes(self):
        form = SessionContentForm(data=CONTENT_DATA)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['activity'], '')
        self.assertEqual(form.cleaned_data['notes'], '')

    def test_activity_and_notes_are_optional_and_last(self):
        form = SessionContentForm()

        self.assertFalse(form.fields['activity'].required)
        self.assertFalse(form.fields['notes'].required)
        self.assertEqual(
            list(form.fields),
            ['title', 'content', 'homework', 'activity', 'notes'],
        )

    def test_required_fields_have_persian_messages(self):
        form = SessionContentForm(data={})

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['title'], ['عنوان درس را وارد کنید.'])
        self.assertEqual(form.errors['content'], ['مطالب تدریس شده را بنویسید.'])
        self.assertEqual(
            form.errors['homework'],
            ['تکالیف منزل را بنویسید؛ اگر تکلیفی ندادید، بنویسید «ندارد».'],
        )
        self.assertNotIn('activity', form.errors)
        self.assertNotIn('notes', form.errors)

    def test_title_too_long_has_persian_message(self):
        form = SessionContentForm(data={**CONTENT_DATA, 'title': 'ا' * 256})

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['title'], ['عنوان درس نباید بیشتر از ۲۵۵ حرف باشد.'])


class SchoolSessionFormTests(TestCase):

    def test_required_fields_have_persian_messages(self):
        form = SchoolSessionForm(data={})

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['class_subject'], ['درس کلاس را انتخاب کنید.'])
        self.assertEqual(form.errors['date'], ['تاریخ جلسه را وارد کنید.'])

    def test_invalid_date_has_persian_message(self):
        form = SchoolSessionForm(data={'date': 'دیروز', 'status': 'HD'})

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['date'],
            ['تاریخ جلسه معتبر نیست؛ آن را از تقویم انتخاب کنید.'],
        )

    def test_date_in_persian_digits_is_accepted(self):
        # the date picker writes Persian digits into the field
        class_subject = make_class_subject_for(make_teacher_profile())
        form = SchoolSessionForm(data={
            'class_subject': class_subject.pk,
            'date': '۱۴۰۳-۰۸-۰۱',
            'status': 'HD',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['date'], jdatetime.date(1403, 8, 1))

    def test_class_subject_outside_the_given_queryset_is_rejected(self):
        own = make_class_subject_for(make_teacher_profile())
        other = make_class_subject_for(make_teacher_profile())
        form = SchoolSessionForm(
            data=post_data(other),
            class_subjects=ClassSubject.objects.filter(pk=own.pk),
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['class_subject'],
            ['درس کلاس انتخاب‌شده معتبر نیست؛ دوباره انتخاب کنید.'],
        )

    def test_next_session_numbers(self):
        first = make_class_subject_for(make_teacher_profile())
        second = make_class_subject_for(make_teacher_profile())
        make_session(first, jdatetime.date(1403, 8, 1))
        make_session(first, jdatetime.date(1403, 8, 2))

        numbers = SchoolSessionForm().next_session_numbers()

        self.assertEqual(numbers[first.pk], 3)
        self.assertEqual(numbers[second.pk], 1)


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------

class SessionViewTestCase(TestCase):

    def setUp(self):
        self.teacher = make_teacher_profile()
        self.class_subject = make_class_subject_for(self.teacher)
        self.client.force_login(self.teacher.staff.user)

        self.other_class_subject = make_class_subject_for(make_teacher_profile())

    def form_url(self, class_subject=None):
        return reverse('teaching:session_form', args=[(class_subject or self.class_subject).pk])

    def list_url(self, class_subject=None):
        return reverse('teaching:session_list', args=[(class_subject or self.class_subject).pk])


class CreateSessionViewTests(SessionViewTestCase):

    def test_login_required(self):
        self.client.logout()

        response = self.client.get(self.form_url())

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.form_url()}",
            fetch_redirect_response=False,
        )

    def test_get_shows_next_session_number_and_only_own_class_subjects(self):
        make_session(self.class_subject, jdatetime.date(1403, 8, 1))

        response = self.client.get(self.form_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'جلسه شماره ۲')
        choices = [pk for pk, _ in response.context['session_form'].fields['class_subject'].choices if pk]
        self.assertEqual([choice.value for choice in choices], [self.class_subject.pk])

    def test_form_marks_optional_fields(self):
        response = self.client.get(self.form_url())

        self.assertContains(response, '(اختیاری)', count=2)
        self.assertContains(response, '«فعالیت‌های کلاسی» و «نکات و عملکرد دانش‌آموزان»')

    def test_other_teachers_class_subject_is_not_found(self):
        response = self.client.get(self.form_url(self.other_class_subject))

        self.assertEqual(response.status_code, 404)

    def test_user_without_teacher_profile_is_not_found(self):
        self.client.force_login(make_user('teacher'))

        response = self.client.get(self.form_url())

        self.assertEqual(response.status_code, 404)

    def test_superuser_can_record_for_any_class_subject(self):
        self.client.force_login(make_superuser())

        response = self.client.get(self.form_url(self.other_class_subject))

        self.assertEqual(response.status_code, 200)

    def test_post_without_activity_and_notes_creates_session(self):
        response = self.client.post(self.form_url(), post_data(self.class_subject))

        session = SchoolSession.objects.get(class_subject=self.class_subject)
        self.assertRedirects(
            response,
            reverse('attendance:attendance_form', args=[session.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(session.session_number, 1)
        self.assertEqual(session.session_contents.title, CONTENT_DATA['title'])
        self.assertEqual(session.session_contents.activity, '')
        self.assertEqual(session.session_contents.notes, '')

    def test_posting_another_teachers_class_subject_is_rejected(self):
        response = self.client.post(self.form_url(), post_data(self.other_class_subject))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SchoolSession.objects.exists())
        self.assertContains(response, 'درس کلاس انتخاب‌شده معتبر نیست')

    def test_invalid_post_keeps_values_and_shows_accessible_errors(self):
        long_text = 'مطالب بسیار طولانی تدریس شده ' * 20

        response = self.client.post(
            self.form_url(),
            post_data(self.class_subject, title='', content=long_text, notes='یادداشت من'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SchoolSession.objects.exists())
        # nothing the teacher typed is lost
        self.assertContains(response, long_text.strip())
        self.assertContains(response, 'یادداشت من')
        # summary, linked to the field
        self.assertContains(response, 'لطفاً موارد زیر را اصلاح کنید')
        self.assertContains(response, 'href="#id_title"')
        # the field itself: aria-invalid + described by its error message
        self.assertContains(response, 'aria-invalid="true"', count=1)
        self.assertContains(response, 'aria-describedby="id_title_helptext id_title_error"')
        self.assertContains(response, 'id="id_title_error"')
        self.assertContains(response, 'عنوان درس را وارد کنید.')

    def test_date_order_error_from_save_is_shown_on_the_date_field(self):
        make_session(self.class_subject, jdatetime.date(1403, 9, 1))

        # earlier than session 1, so SchoolSession.save() refuses it
        response = self.client.post(self.form_url(), post_data(self.class_subject, date='1403-08-01'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SchoolSession.objects.count(), 1)
        self.assertEqual(SessionContent.objects.count(), 1)
        self.assertEqual(
            response.context['session_form'].errors['date'],
            ['تاریخ این جلسه نباید قبل از جلسه 1 باشد.'],
        )

    def test_date_outside_class_subject_range_has_persian_message(self):
        response = self.client.post(self.form_url(), post_data(self.class_subject, date='1402-01-01'))

        self.assertEqual(
            response.context['session_form'].errors['date'],
            ['تاریخ جلسه قبل از تاریخ شروع درس است.'],
        )

    def test_duplicate_session_number_race_has_persian_message(self):
        form = SchoolSessionForm(data=post_data(self.class_subject))
        form.is_valid()
        # another request grabbed number 1 between is_valid() and save()
        make_session(self.class_subject, jdatetime.date(1403, 8, 1))
        form.instance.session_number = 1

        content_form = SessionContentForm(data=CONTENT_DATA)
        content_form.is_valid()

        self.assertIsNone(_save_session(form, content_form))
        self.assertEqual(form.non_field_errors(), [DUPLICATE_SESSION_MESSAGE])
        self.assertEqual(SessionContent.objects.count(), 1)


class UpdateSessionViewTests(SessionViewTestCase):

    def test_edit_own_session(self):
        session = make_session(self.class_subject, jdatetime.date(1403, 8, 1))

        response = self.client.post(
            reverse('teaching:update_session', args=[session.pk]),
            post_data(self.class_subject, title='عنوان تازه', activity=''),
        )

        self.assertRedirects(
            response,
            reverse('attendance:attendance_form', args=[session.pk]),
            fetch_redirect_response=False,
        )
        session.session_contents.refresh_from_db()
        self.assertEqual(session.session_contents.title, 'عنوان تازه')

    def test_get_shows_existing_number(self):
        make_session(self.class_subject, jdatetime.date(1403, 8, 1))
        session = make_session(self.class_subject, jdatetime.date(1403, 8, 2))

        response = self.client.get(reverse('teaching:update_session', args=[session.pk]))

        self.assertContains(response, 'ویرایش جلسه درسی')
        self.assertContains(response, 'جلسه شماره ۲')

    def test_session_without_content_can_be_completed(self):
        session = make_session(self.class_subject, jdatetime.date(1403, 8, 1), with_content=False)

        response = self.client.post(
            reverse('teaching:update_session', args=[session.pk]),
            post_data(self.class_subject),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SessionContent.objects.get().session, session)

    def test_other_teachers_session_is_not_found(self):
        session = make_session(self.other_class_subject, jdatetime.date(1403, 8, 1))

        response = self.client.get(reverse('teaching:update_session', args=[session.pk]))

        self.assertEqual(response.status_code, 404)

    def test_missing_session_is_not_found(self):
        response = self.client.get(reverse('teaching:update_session', args=[999999]))

        self.assertEqual(response.status_code, 404)


class SessionListViewTests(SessionViewTestCase):

    def test_empty_state(self):
        response = self.client.get(self.list_url())

        self.assertContains(response, 'هنوز جلسه‌ای ثبت نشده است')
        self.assertContains(response, self.form_url())

    def test_cards_show_persian_date_status_and_content(self):
        make_session(
            self.class_subject,
            jdatetime.date(1403, 8, 1),
            homework='حل تمرین ۳',
        )

        response = self.client.get(self.list_url())

        self.assertContains(response, 'سه‌شنبه ۱ آبان ۱۴۰۳')
        self.assertContains(response, 'جلسه ۱')
        self.assertContains(response, 'sl-status--hd')
        self.assertContains(response, 'برگزار شده')
        self.assertContains(response, CONTENT_DATA['title'])
        self.assertContains(response, 'حل تمرین ۳')
        self.assertContains(response, 'تعداد کل: ۱ جلسه')

    def test_session_without_content_is_listed(self):
        make_session(self.class_subject, jdatetime.date(1403, 8, 1), with_content=False)

        response = self.client.get(self.list_url())

        self.assertContains(response, 'محتوای این جلسه ثبت نشده است.')

    def test_paginated(self):
        start = jdatetime.date(1403, 8, 1)
        for day in range(SESSIONS_PER_PAGE + 3):
            make_session(self.class_subject, start + jdatetime.timedelta(days=day))

        response = self.client.get(self.list_url())

        self.assertEqual(len(response.context['sessions']), SESSIONS_PER_PAGE)
        self.assertContains(response, 'صفحه ۱ از ۲')
        self.assertContains(response, 'href="?page=2"')

        response = self.client.get(self.list_url(), {'page': 2})
        self.assertEqual(len(response.context['sessions']), 3)

    def _queries_for_page(self, page):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.list_url(), {'page': page})
        return len(queries)

    def test_list_query_does_not_grow_with_sessions(self):
        start = jdatetime.date(1403, 8, 1)
        make_session(self.class_subject, start)
        self.client.get(self.list_url())  # warm the site-settings cache
        few = self._queries_for_page(1)

        for day in range(1, 8):
            make_session(self.class_subject, start + jdatetime.timedelta(days=day))

        self.assertEqual(self._queries_for_page(1), few)

    def test_other_teachers_list_is_not_found(self):
        response = self.client.get(self.list_url(self.other_class_subject))

        self.assertEqual(response.status_code, 404)
