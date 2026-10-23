"""
The supporter's side of daily attendance: which classes have their sheet
on a day (the overview of the attendance page and the dashboard card),
the follow-up list of one class, and the session drawer after the cutoff.

Fixture: ``analytics.tests.Fixture`` (year 1405, class A has math at bells
1 and 2 on Sundays), with the cutoff on Sunday 12 Mehr. The supporter of
branch A also has class C (a lesson at bell 1 on Sundays), class D (no
timetable) and class E (only bell 3 on Sundays, which a calendar event
closes on Sunday 12).
"""

from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from analytics.tests import DAILY_FROM_SUNDAY_2, SUNDAY_1, SUNDAY_2, WEDNESDAY, Fixture, J, at
from attendance import services
from core.testing import (
    make_assignment,
    make_calendar_event,
    make_class_subject,
    make_enrollment,
    make_schedule,
    make_school_class,
    make_student,
    make_subject,
    make_supervisor,
    make_teacher_profile,
)
from scheduling.models import ClassSchedule
from supervisor.models import SupervisorClass
from supervisor.selectors import ClassAttendanceDay, SupervisorAttendanceSelector


@DAILY_FROM_SUNDAY_2
class DailyAttendanceSupervisorTestCase(Fixture):
    def setUp(self):
        self.supervisor = make_supervisor(self.branch_a, self.grade)
        self.class_c = self.make_class(bell=self.bell_1)
        self.class_d = self.make_class(bell=None)
        self.class_e = self.make_class(bell=self.bell_3)
        for school_class in (self.class_a, self.class_c, self.class_d, self.class_e):
            SupervisorClass.objects.create(supervisor=self.supervisor, school_class=school_class)
        make_calendar_event(self.year, SUNDAY_2, bells=[self.bell_3], title="اردو")

        self.ali = make_enrollment(make_student(), self.class_a)
        self.sara = make_enrollment(make_student(), self.class_a)
        self.reza = make_enrollment(make_student(), self.class_a)
        self.ali.student.user.phone_number = "09120000001"
        self.ali.student.user.save()
        services.save_daily_sheet(self.class_a, SUNDAY_2, self.supervisor.user, {
            self.ali.pk: ("absent", None), self.sara.pk: ("excused", "نامه"),
        })

    def make_class(self, bell):
        school_class = make_school_class(self.branch_a, self.grade, self.year)
        if bell is not None:
            cs = make_class_subject(
                school_class, make_subject(),
                make_assignment(make_teacher_profile(), self.branch_a, self.year),
                J(1405, 7, 1), J(1406, 3, 31),
            )
            make_schedule(cs, ClassSchedule.DayChoices.SUNDAY, bell)
        return school_class

    def selector(self, today=WEDNESDAY):
        return SupervisorAttendanceSelector(self.supervisor, today=today.togregorian())

    def statuses(self, day, today=WEDNESDAY):
        return {row.school_class: row.status for row in self.selector(today).overview(day.togregorian())}


class OverviewTests(DailyAttendanceSupervisorTestCase):
    def test_each_class_on_a_daily_day(self):
        self.assertEqual(self.statuses(SUNDAY_2), {
            self.class_a: ClassAttendanceDay.RECORDED,
            self.class_c: ClassAttendanceDay.MISSING,
            self.class_d: ClassAttendanceDay.NO_LESSONS,
            self.class_e: ClassAttendanceDay.CLOSED,
        })

    def test_the_summary_counts_only_classes_with_lessons(self):
        selector = self.selector()
        rows = selector.overview(SUNDAY_2.togregorian())

        summary = selector.summarize(rows)

        self.assertEqual((summary["due"], summary["recorded"]), (2, 1))
        self.assertEqual([row.school_class for row in summary["missing"]], [self.class_c])
        recorded = next(row for row in rows if row.school_class == self.class_a)
        self.assertEqual(recorded.counts, {"total": 3, "absent": 1, "late": 0, "excused": 1})
        closed = next(row for row in rows if row.school_class == self.class_e)
        self.assertEqual(closed.closure.title, "اردو")

    def test_a_day_before_the_cutoff_is_archive(self):
        self.assertEqual(set(self.statuses(SUNDAY_1).values()), {ClassAttendanceDay.ARCHIVE})

    def test_a_day_after_today_is_future(self):
        self.assertEqual(set(self.statuses(SUNDAY_2, today=J(1405, 7, 11)).values()),
                         {ClassAttendanceDay.FUTURE})

    def test_only_the_supervisors_classes(self):
        self.assertNotIn(self.class_b, self.statuses(SUNDAY_2))


class AttendancePageTests(DailyAttendanceSupervisorTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("django.utils.timezone.now", lambda: at(WEDNESDAY))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.supervisor.user)
        self.url = reverse("supervisor:attendance")

    def get(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response

    def test_the_overview_links_every_class_to_its_sheet(self):
        response = self.get(date="1405/07/12")
        sheet = reverse("attendance:daily_sheet", args=[self.class_c.pk])

        self.assertTrue(response.context["is_daily"])
        self.assertContains(response, f'href="{sheet}?date=1405/07/12">ثبت حضور و غیاب')
        self.assertContains(
            response,
            f'href="{reverse("attendance:daily_sheet", args=[self.class_a.pk])}?date=1405/07/12">ویرایش',
        )
        # the one class still missing is highlighted
        self.assertContains(response, "daily-class--missing", count=1)
        self.assertContains(response, "۱ از ۲ کلاس ثبت شده")
        self.assertContains(response, "«اردو»")

    def test_the_follow_up_list_has_everyone_not_present(self):
        response = self.get(date="1405/07/12", **{"class": self.class_a.pk})

        absences = response.context["absences"]
        self.assertEqual({(r.student_enrollment, r.status) for r in absences},
                         {(self.ali, "absent"), (self.sara, "excused")})
        self.assertTrue(all(r.is_daily for r in absences))
        self.assertContains(response, "09120000001")
        self.assertContains(response, 'data-status-filter="excused"')
        self.assertEqual(response.context["summary"]["absences"], 2)

    def test_a_class_without_its_sheet_offers_to_take_it(self):
        response = self.get(date="1405/07/12", **{"class": self.class_c.pk})

        self.assertEqual(response.context["absences"], [])
        self.assertContains(response, "حضور و غیاب این کلاس برای این روز هنوز ثبت نشده است.")

    def test_it_opens_on_today(self):
        response = self.get()

        self.assertEqual(response.context["day"], WEDNESDAY)
        self.assertIsNone(response.context["next_day"])
        self.assertContains(response, "در این روز هیچ کلاسی طبق برنامه‌ی هفتگی کلاس ندارد.")

    def test_an_invalid_date_falls_back_to_today(self):
        response = self.get(date="not-a-date")

        self.assertEqual(response.context["day"], WEDNESDAY)
        self.assertContains(response, "تاریخ واردشده معتبر نیست")

    def test_query_count_does_not_grow_with_the_roster(self):
        params = {"date": "1405/07/12", "class": self.class_a.pk}
        self.client.get(self.url, params)       # warm the branch middleware's session cache
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url, params)

        for _ in range(10):
            enrollment = make_enrollment(make_student(), self.class_a)
            services.save_daily_sheet(self.class_a, SUNDAY_2, self.supervisor.user, {
                enrollment.pk: ("late", None),
            })
        with CaptureQueriesContext(connection) as large:
            self.client.get(self.url, params)

        self.assertEqual(len(small.captured_queries), len(large.captured_queries))


class DashboardCardTests(DailyAttendanceSupervisorTestCase):
    def test_todays_card_names_the_classes_still_missing(self):
        with mock.patch("django.utils.timezone.now", lambda: at(SUNDAY_2, 9)):
            self.client.force_login(self.supervisor.user)
            response = self.client.get(reverse("supervisor:dashboard"))

        card = response.context["daily_attendance"]
        self.assertEqual((card["due"], card["recorded"]), (2, 1))
        self.assertEqual([row.school_class for row in card["missing"]], [self.class_c])
        self.assertContains(response, "حضور و غیاب امروز")
        self.assertContains(response, f"کلاس {self.class_c.section}")
        self.assertContains(response, "stat-card--alert")

    def test_before_the_cutoff_there_is_no_card(self):
        with mock.patch("django.utils.timezone.now", lambda: at(SUNDAY_1, 9)):
            self.client.force_login(self.supervisor.user)
            response = self.client.get(reverse("supervisor:dashboard"))

        self.assertFalse(response.context["daily_attendance"]["is_daily"])
        self.assertNotContains(response, "حضور و غیاب امروز")

    def test_the_attendance_rate_reads_both_sides_of_the_cutoff(self):
        from attendance.models import SessionAttendance

        session = self.session(self.math, SUNDAY_1, self.bell_1)
        SessionAttendance.objects.create(session=session, student_enrollment=self.reza, status="present")

        from supervisor.selectors import SupervisorDashboardSelector

        stats = SupervisorDashboardSelector(self.supervisor).attendance_statistics()

        # 1 archived (present) + 3 daily (present, absent, excused)
        self.assertEqual((stats["total"], stats["absences"], stats["present_rate"]), (4, 2, 50))


class SessionDrawerTests(DailyAttendanceSupervisorTestCase):
    def test_a_session_after_the_cutoff_shows_the_class_sheet_of_that_day(self):
        session = self.session(self.math, SUNDAY_2, self.bell_1)
        self.client.force_login(self.supervisor.user)

        response = self.client.get(
            reverse("supervisor:session_detail", args=[session.pk]), {"partial": "1"}
        )

        attendance = response.context["attendance"]
        self.assertEqual((attendance["daily"], attendance["total"], attendance["excused"]), (True, 3, 1))
        self.assertContains(response, "حضور و غیاب روزانه‌ی کلاس در این روز")
        self.assertContains(response, "غیبت موجه")
