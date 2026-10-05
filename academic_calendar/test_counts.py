"""
Holiday (HL) sessions are excluded from every session count and number,
in every panel: one class subject with two held sessions and one holiday
between them must count as two everywhere.
"""

from datetime import datetime

import jdatetime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.profile import teacher_overview
from core.selectors import build_teacher_dashboard
from core.testing import (
    make_academic_year,
    make_assignment,
    make_bell,
    make_branch,
    make_calendar_event,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_school_class,
    make_student,
    make_subject,
    make_supervisor,
    make_teacher_profile,
)
from report.selectors import ReportScope, build_class_report, build_grade_report
from supervisor.models import SupervisorClass
from supervisor.selectors import (
    SessionFilters,
    SupervisorDashboardSelector,
    SupervisorSessionsSelector,
    SupervisorTeachersSelector,
)
from teaching.models import SchoolSession, SessionContent

J = jdatetime.date
NOW = timezone.make_aware(datetime(2026, 10, 20, 12, 0))   # 1405/07/28


class ExcludedCountTests(TestCase):

    def setUp(self):
        self.year = make_academic_year(start_date=J(1405, 7, 1), end_date=J(1406, 6, 31))
        branch, grade = make_branch(), make_grade()
        self.teacher = make_teacher_profile()
        self.school_class = make_school_class(branch, grade, self.year)
        self.class_subject = make_class_subject(
            self.school_class, make_subject(), make_assignment(self.teacher, branch, self.year),
            start_date=J(1405, 7, 1), end_date=J(1406, 3, 31),
        )
        bell = make_bell(1)
        event = make_calendar_event(self.year, J(1405, 7, 13))

        def session(day, **fields):
            row = SchoolSession.objects.create(
                class_subject=self.class_subject, date=J(1405, 7, day), bell=bell, **fields
            )
            if not fields:
                SessionContent.objects.create(session=row, title='t', content='c', homework='h')
            return row

        self.first = session(12)
        # the latest row by date, and with a NULL number (sorted first by
        # "-session_number" on Postgres): it must still never count
        self.holiday = session(26, status=SchoolSession.Status.HOLIDAY, calendar_event=event,
                               is_auto_created=True)
        self.second = session(19)
        make_calendar_event(self.year, J(1405, 7, 26))

        self.supervisor = make_supervisor(branch, grade)
        SupervisorClass.objects.create(supervisor=self.supervisor, school_class=self.school_class)

    def test_teacher_dashboard(self):
        data = build_teacher_dashboard(self.teacher, now=NOW)

        self.assertEqual(data['total_sessions'], 2)
        self.assertNotIn(self.holiday, [row['session'] for row in data['recent_sessions']])

    def test_teacher_profile(self):
        self.assertEqual(teacher_overview(self.teacher)['sessions_this_year'], 2)

    def test_teacher_session_list_lists_but_does_not_count_the_holiday(self):
        self.client.force_login(self.teacher.staff.user)

        response = self.client.get(reverse('teaching:session_list', args=[self.class_subject.pk]))

        self.assertEqual(response.context['session_count'], 2)
        self.assertEqual(len(response.context['sessions']), 3)

    def test_student_session_list(self):
        student = make_student()
        make_enrollment(student, self.school_class)
        self.client.force_login(student.user)

        response = self.client.get(reverse('student:sessions'))

        self.assertEqual(response.context['class_subjects'][0].session_count, 2)

    def test_supervisor_dashboard(self):
        selector = SupervisorDashboardSelector(self.supervisor)

        self.assertEqual(selector.summary()['sessions_count'], 2)
        stats = selector.session_statistics()
        self.assertEqual(stats['total_sessions'], 2)
        self.assertNotIn(SchoolSession.Status.HOLIDAY, stats['by_status'])
        self.assertNotIn(self.holiday, list(selector.recent_sessions()))

    def test_supervisor_sessions_page(self):
        selector = SupervisorSessionsSelector(self.supervisor, today=NOW.date())
        filters = SessionFilters(academic_year=self.year)

        row = selector.summary_rows(filters).get()
        self.assertEqual((row.session_count, row.delivered_count, row.empty_count), (2, 2, 0))
        self.assertEqual(row.last_date, J(1405, 7, 19))
        self.assertEqual(selector.kpis(filters)['session_count'], 2)

    def test_supervised_teachers_page(self):
        teacher = SupervisorTeachersSelector(self.supervisor, today=NOW.date()).teachers(self.year).get()

        self.assertEqual(teacher.session_count, 2)
        self.assertEqual(teacher.last_session_date, J(1405, 7, 19))

    def test_class_report(self):
        report = build_class_report(ReportScope(self.teacher.staff.user), self.school_class)

        subject = report['subjects'][0]
        self.assertEqual(subject['session_count'], 2)
        self.assertEqual(report['total_sessions'], 2)
        self.assertEqual(subject['last_date'], J(1405, 7, 19))

    def test_reports_list_the_holiday_with_its_reason(self):
        scope = ReportScope(self.teacher.staff.user)

        rows = build_class_report(scope, self.school_class)['subjects'][0]['sessions']
        holiday = [row for row in rows if row['is_holiday']]
        self.assertEqual(len(holiday), 1)
        self.assertEqual(holiday[0]['number'], 'تعطیل')
        self.assertTrue(holiday[0]['content'].startswith('تعطیل: '))

        grade = build_grade_report(scope, self.year)
        sessions = grade['grades_data'][0]['classes'][0]['sessions']
        self.assertEqual(sum(1 for row in sessions if row['is_holiday']), 1)
