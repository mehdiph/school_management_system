"""
The slot rules of recording a session (teaching.services.slot_errors),
through the registration page: the weekly schedule's prefill
(?date=&bell=) and the POST, which re-checks everything.

"Today" is fixed at 1405/07/14 (Tue 2026-10-06). Academic year from
1405/07/01; 07/12 is a Sunday (rotation week 2), 07/09 a Thursday,
07/10 a Friday.
"""

from datetime import date
from unittest import mock

import jdatetime
from django.contrib.messages import get_messages
from django.urls import reverse

from academic_calendar.tests import CalendarTestCase, Day
from core.testing import make_calendar_event, make_schedule, make_teacher_profile
from teaching.models import SchoolSession
from teaching.models.school_session import DUPLICATE_SLOT_MESSAGE
from teaching.services import FRIDAY_MESSAGE, FUTURE_DATE_MESSAGE, THURSDAY_MESSAGE

J = jdatetime.date
TODAY = date(2026, 10, 6)

CONTENT = {'title': 'جلسه', 'content': 'مطالب', 'homework': 'ندارد'}


@mock.patch('django.utils.timezone.localdate', lambda *args, **kwargs: TODAY)
class RegistrationRuleTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        # math: Sunday bells 1 and 2 (the same subject twice a day)
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SUNDAY, self.bell_2)
        self.client.force_login(self.teacher.staff.user)
        self.url = reverse('teaching:session_form', args=[self.math.pk])

    def open(self, day, bell, **params):
        return self.client.get(self.url, {'date': day, 'bell': bell.pk, **params})

    def post(self, day, bell, status=SchoolSession.Status.HELD):
        return self.client.post(self.url, {
            'class_subject': self.math.pk, 'date': day, 'bell': bell.pk,
            'status': status, **CONTENT,
        })

    def messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def assert_refused(self, response, message):
        self.assertEqual(response.status_code, 302)
        self.assertTrue(any(message in m for m in self.messages(response)), self.messages(response))

    def assert_form_error(self, response, message):
        self.assertEqual(response.status_code, 200)
        errors = [e for errors in response.context['session_form'].errors.values() for e in errors]
        self.assertIn(message, ' '.join(errors))

    # -- prefill ---------------------------------------------------------

    def test_prefill_fills_class_subject_date_and_bell(self):
        response = self.open('1405-07-12', self.bell_2)

        form = response.context['session_form']
        self.assertEqual(form.initial['class_subject'], self.math)
        self.assertEqual((form.initial['date'], form.initial['bell']), (J(1405, 7, 12), self.bell_2))

    def test_future_date(self):
        response = self.open('1405-07-19', self.bell_1)
        self.assert_refused(response, FUTURE_DATE_MESSAGE)
        self.assertRedirects(
            response, reverse('scheduling:teacher-schedule') + '?week=1405-07-18',
            fetch_redirect_response=False,
        )

        self.assert_form_error(self.post('1405-07-19', self.bell_1), FUTURE_DATE_MESSAGE)
        self.assertFalse(SchoolSession.objects.exists())

    def test_duplicate_slot_but_not_another_bell_of_the_same_day(self):
        self.assertEqual(self.post('1405-07-12', self.bell_1).status_code, 302)

        response = self.open('1405-07-12', self.bell_1)
        self.assert_refused(response, DUPLICATE_SLOT_MESSAGE)
        self.assertTrue(any('update_session' in m or 'مشاهده' in m for m in self.messages(response)))
        self.assert_form_error(self.post('1405-07-12', self.bell_1), DUPLICATE_SLOT_MESSAGE)

        # bell 2 of the same day is its own slot
        self.assertEqual(self.open('1405-07-12', self.bell_2).status_code, 200)
        self.assertEqual(self.post('1405-07-12', self.bell_2).status_code, 302)
        self.assertEqual(
            list(SchoolSession.objects.order_by('bell__order').values_list('session_number', flat=True)),
            [1, 2],
        )

    def test_closed_slot_names_the_event(self):
        make_calendar_event(self.year, J(1405, 7, 12), title='برف سنگین', bells=[self.bell_2])

        self.assert_refused(self.open('1405-07-12', self.bell_2), 'برف سنگین')
        self.assert_form_error(self.post('1405-07-12', self.bell_2), 'برف سنگین')
        # a compensatory session cannot use a closed slot either
        self.assert_form_error(
            self.post('1405-07-12', self.bell_2, SchoolSession.Status.COMPENSATORY), 'برف سنگین'
        )
        # bell 1 is open
        self.assertEqual(self.post('1405-07-12', self.bell_1).status_code, 302)

    def test_another_teachers_class_subject_is_not_found(self):
        self.client.force_login(make_teacher_profile().staff.user)

        self.assertEqual(self.open('1405-07-12', self.bell_1).status_code, 404)

    def test_friday_and_thursday(self):
        self.assert_refused(self.open('1405-07-10', self.bell_1), FRIDAY_MESSAGE)
        self.assert_form_error(
            self.post('1405-07-10', self.bell_1, SchoolSession.Status.COMPENSATORY), FRIDAY_MESSAGE
        )

        self.assert_form_error(self.post('1405-07-09', self.bell_1), THURSDAY_MESSAGE)
        # make-up classes are held on Thursdays, at any bell
        self.assertEqual(
            self.post('1405-07-09', self.bell_3, SchoolSession.Status.COMPENSATORY).status_code, 302
        )

    def test_held_session_needs_a_timetable_slot_compensatory_does_not(self):
        self.assert_form_error(self.post('1405-07-12', self.bell_3), 'برنامه ندارد')
        self.assert_form_error(self.post('1405-07-13', self.bell_1), 'برنامه ندارد')   # Monday

        self.assertEqual(
            self.post('1405-07-13', self.bell_1, SchoolSession.Status.COMPENSATORY).status_code, 302
        )

    def test_outside_the_class_subject_teaching_window(self):
        self.math.start_date = J(1405, 7, 13)
        self.math.save()

        self.assert_refused(self.open('1405-07-12', self.bell_1), 'بازه‌ی تدریس')

    def test_next_is_used_when_local_only(self):
        response = self.open('1405-07-19', self.bell_1, next='/scheduling/teacher/?week=1405-07-11')
        self.assertRedirects(response, '/scheduling/teacher/?week=1405-07-11', fetch_redirect_response=False)

        response = self.open('1405-07-19', self.bell_1, next='https://evil.example/')
        self.assertTrue(response['Location'].startswith(reverse('scheduling:teacher-schedule')))

    def test_holiday_sessions_cannot_be_edited(self):
        event = make_calendar_event(self.year, J(1405, 7, 12), title='تاسوعا')
        holiday = SchoolSession.objects.create(
            class_subject=self.math, date=J(1405, 7, 12), bell=self.bell_1,
            status=SchoolSession.Status.HOLIDAY, calendar_event=event, is_auto_created=True,
        )

        response = self.client.get(reverse('teaching:update_session', args=[holiday.pk]))

        self.assert_refused(response, 'تاسوعا')

    def test_holiday_status_is_never_offered(self):
        response = self.client.get(self.url)

        statuses = [value for value, _ in response.context['session_form'].fields['status'].choices]
        self.assertNotIn(SchoolSession.Status.HOLIDAY, statuses)

    def test_editing_only_the_content_skips_the_slot_rules(self):
        # recorded before its slot was moved to Monday
        self.post('1405-07-12', self.bell_1)
        session = SchoolSession.objects.get()
        from scheduling.models import ClassSchedule
        ClassSchedule.objects.filter(class_subject=self.math, bell=self.bell_1).update(day_of_week=Day.MONDAY)

        response = self.client.post(reverse('teaching:update_session', args=[session.pk]), {
            'class_subject': self.math.pk, 'date': '1405-07-12', 'bell': self.bell_1.pk,
            'status': SchoolSession.Status.HELD, **CONTENT, 'title': 'عنوان تازه',
        })

        self.assertEqual(response.status_code, 302)
