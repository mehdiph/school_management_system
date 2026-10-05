"""
Tests for recording class sessions (teaching app): the two session
forms, and the create / edit / list views -- including that a teacher
only ever reaches the class subjects of their own TeacherAssignment.
"""

import jdatetime
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import (
    make_academic_year,
    make_assignment,
    make_bell,
    make_branch,
    make_calendar_event,
    make_class_subject,
    make_schedule,
    make_grade,
    make_school_class,
    make_subject,
    make_superuser,
    make_teacher_profile,
    make_user,
)
from scheduling.models import ClassSchedule
from scheduling.models.bell import Bell
from school.models import ClassSubject
from teaching.forms import SchoolSessionForm, SessionContentForm
from teaching.models import SchoolSession, SessionContent
from teaching.models.school_session import DUPLICATE_SLOT_MESSAGE
from teaching.views import DUPLICATE_SESSION_MESSAGE, SESSIONS_PER_PAGE, _save_session

CONTENT_DATA = {
    'title': 'جمع اعداد چند رقمی',
    'content': 'جمع ستونی با انتقال رقم',
    'homework': 'تمرین‌های صفحه ۱۲',
}


def slot_bell():
    return Bell.objects.filter(order=1).first() or make_bell(1)


def make_class_subject_for(teacher):
    branch = make_branch()
    year = make_academic_year()
    school_class = make_school_class(branch, make_grade(), year)
    assignment = make_assignment(teacher, branch, year)
    # runs from 1403-07-01 to 1404-03-31
    class_subject = make_class_subject(school_class, make_subject(), assignment)
    # every Tuesday (1403-08-01 is one) at bell 1
    make_schedule(class_subject, ClassSchedule.DayChoices.TUESDAY, slot_bell())
    return class_subject


def make_session(class_subject, date, with_content=True, **content):
    session = SchoolSession.objects.create(class_subject=class_subject, date=date)
    if with_content:
        SessionContent.objects.create(session=session, **{**CONTENT_DATA, **content})
    return session


def post_data(class_subject, date='1403-08-01', **overrides):
    return {
        'class_subject': class_subject.pk,
        'date': date,
        'bell': slot_bell().pk,
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
            'bell': slot_bell().pk,
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

    def test_earlier_date_is_inserted_and_later_sessions_renumbered(self):
        later = make_session(self.class_subject, jdatetime.date(1403, 9, 1))

        response = self.client.post(self.form_url(), post_data(self.class_subject, date='1403-08-01'))

        self.assertEqual(response.status_code, 302)
        earlier = SchoolSession.objects.exclude(pk=later.pk).get()
        later.refresh_from_db()
        self.assertEqual((earlier.session_number, later.session_number), (1, 2))

    def test_date_outside_class_subject_range_has_persian_message(self):
        response = self.client.post(self.form_url(), post_data(self.class_subject, date='1402-01-01'))

        self.assertEqual(
            response.context['session_form'].errors['date'],
            ['تاریخ جلسه بیرون از سال تحصیلی این کلاس است.'],
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


# ----------------------------------------------------------------------
# Numbering and slots (SchoolSession model)
# ----------------------------------------------------------------------

class SessionNumberingTests(TestCase):
    """Counted sessions are numbered 1..N in teaching order; holidays never are."""

    def setUp(self):
        self.class_subject = make_class_subject_for(make_teacher_profile())
        self.bell_1, self.bell_2 = slot_bell(), make_bell(2)
        self.event = make_calendar_event(
            self.class_subject.school_class.year, jdatetime.date(1403, 8, 10)
        )

    def create(self, date, bell=None, **fields):
        return SchoolSession.objects.create(
            class_subject=self.class_subject, date=date, bell=bell, **fields
        )

    def numbers(self):
        return list(
            SchoolSession.objects.filter(class_subject=self.class_subject)
            .order_by('date', 'bell__order')
            .values_list('date', 'bell__order', 'session_number')
        )

    def test_same_day_two_bells_are_two_sessions_in_bell_order(self):
        day = jdatetime.date(1403, 8, 1)
        second = self.create(day, self.bell_2)
        first = self.create(day, self.bell_1)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.session_number, second.session_number), (1, 2))

    def test_holiday_has_no_number_and_numbering_stays_continuous(self):
        self.create(jdatetime.date(1403, 8, 1), self.bell_1)
        holiday = self.create(
            jdatetime.date(1403, 8, 10), self.bell_1,
            status=SchoolSession.Status.HOLIDAY, calendar_event=self.event,
        )
        self.create(jdatetime.date(1403, 8, 20), self.bell_1)

        self.assertIsNone(holiday.session_number)
        self.assertEqual([n for *_, n in self.numbers()], [1, None, 2])
        self.assertEqual(SchoolSession.objects.counted().count(), 2)
        self.assertEqual(SchoolSession.objects.holidays().count(), 1)

    def test_registering_a_missed_past_session_renumbers_later_ones(self):
        self.create(jdatetime.date(1403, 8, 1), self.bell_1)
        self.create(jdatetime.date(1403, 8, 20), self.bell_1)

        missed = self.create(jdatetime.date(1403, 8, 5), self.bell_1)

        self.assertEqual(missed.session_number, 2)
        self.assertEqual([n for *_, n in self.numbers()], [1, 2, 3])

    def test_moving_and_deleting_keep_numbers_continuous(self):
        first = self.create(jdatetime.date(1403, 8, 1), self.bell_1)
        self.create(jdatetime.date(1403, 8, 5), self.bell_1)
        third = self.create(jdatetime.date(1403, 8, 9), self.bell_1)

        first.date = jdatetime.date(1403, 8, 30)
        first.save()
        self.assertEqual(first.session_number, 3)

        third.delete()
        self.assertEqual(
            sorted(SchoolSession.objects.values_list('session_number', flat=True)), [1, 2]
        )

    def test_holiday_status_needs_a_calendar_event_and_the_reverse(self):
        with self.assertRaises(ValidationError):
            self.create(jdatetime.date(1403, 8, 1), status=SchoolSession.Status.HOLIDAY)
        with self.assertRaises(ValidationError):
            self.create(jdatetime.date(1403, 8, 1), calendar_event=self.event)

    def test_one_session_per_slot(self):
        self.create(jdatetime.date(1403, 8, 1), self.bell_1)

        with self.assertRaisesMessage(ValidationError, DUPLICATE_SLOT_MESSAGE):
            self.create(jdatetime.date(1403, 8, 1), self.bell_1)

        # the same subject at another bell, and legacy rows without a bell,
        # are not the same slot
        self.create(jdatetime.date(1403, 8, 1), self.bell_2)
        self.create(jdatetime.date(1403, 8, 1))
        self.create(jdatetime.date(1403, 8, 1))
        self.assertEqual(SchoolSession.objects.count(), 4)
