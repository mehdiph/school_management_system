"""
The director panel's pages: what each shows for a known fixture, the
alerts and their thresholds, the filters, the empty states, and a locked
number of queries per page.

The fixture is ``analytics.tests.Fixture`` (two branches, Sunday slots in
1405) and "now" is Wednesday 15 Mehr 1405 at noon, like the metric tests.
"""

from unittest import mock

from django.test import override_settings
from django.urls import reverse

from academic_calendar import services as calendar
from analytics.tests import AS_OF, SUNDAY_1, SUNDAY_2, THURSDAY, Fixture, J, at
from attendance.models import Attendance
from core.templatetags.jalali_tags import fa_digits
from core.testing import (
    make_assignment,
    make_calendar_event,
    make_class_subject,
    make_enrollment,
    make_schedule,
    make_school_class,
    make_student,
    make_subject,
    make_teacher_profile,
    make_user,
)
from accounts.models import User
from school.models import AcademicYear
from scheduling.models import ClassSchedule
from teaching.models import SchoolSession

now = mock.patch("django.utils.timezone.now", lambda: AS_OF)


class DirectorPageTestCase(Fixture):
    def setUp(self):
        now.start()
        self.addCleanup(now.stop)
        self.client.force_login(make_user(User.Roles.DIRECTOR))

    def get(self, name, **params):
        response = self.client.get(reverse(f"director:{name}"), params)
        self.assertEqual(response.status_code, 200)
        return response

    def attend(self, session, *statuses, school_class=None):
        for status in statuses:
            Attendance.objects.create(
                session=session,
                student_enrollment=make_enrollment(make_student(), school_class or self.class_a),
                status=status,
            )


P, A, L = (Attendance.AttendanceStatus.PRESENT, Attendance.AttendanceStatus.ABSENT,
           Attendance.AttendanceStatus.LATE)


class DashboardTests(DirectorPageTestCase):
    def kpis(self, response):
        return {kpi.key: kpi for kpi in response.context["kpis"]}

    def test_kpis_for_the_year_so_far(self):
        held = self.session(self.math, SUNDAY_1, self.bell_1)
        self.content(held)
        self.attend(held, P, L, A, P)
        self.session(self.math, SUNDAY_1, self.bell_2, SchoolSession.Status.CANCELED)
        make_enrollment(make_student(), self.class_b)

        response = self.get("dashboard", period="year")
        kpis = self.kpis(response)

        self.assertEqual(kpis["execution_rate"].value, 100 / 6)       # 1 of 6 slots
        self.assertEqual(kpis["attendance_rate"].value, 75)            # late is attended
        self.assertEqual(kpis["content_rate"].value, 100)
        self.assertEqual(kpis["students"].value, 5)
        self.assertEqual(kpis["classes"].value, 2)
        self.assertEqual(kpis["teachers"].value, 2)
        # The year so far has no previous period: no arrow, a note.
        self.assertIsNone(kpis["execution_rate"].delta)
        self.assertEqual(kpis["execution_rate"].note, "بدون دوره‌ی قبلی")
        self.assertContains(response, "۱۷٪")

    def test_counts_have_no_comparison(self):
        kpis = self.kpis(self.get("dashboard", period="week"))

        for key in ("students", "classes", "teachers"):
            self.assertIsNone(kpis[key].delta)
            self.assertFalse(kpis[key].is_rate)

    def test_comparison_with_the_previous_period(self):
        # This week (Sat 11 .. Wed 15 Mehr) has Sunday 12; the previous
        # five teaching days (Sat 4 .. Wed 8) have Sunday 5.
        self.session(self.math, SUNDAY_1, self.bell_1)
        self.session(self.math, SUNDAY_1, self.bell_2)
        self.session(self.physics, SUNDAY_1, self.bell_1)
        self.session(self.math, SUNDAY_2, self.bell_1)

        response = self.get("dashboard", period="week")
        kpi = self.kpis(response)["execution_rate"]

        self.assertEqual(response.context["previous_period"],
                         (J(1405, 7, 4).togregorian(), J(1405, 7, 8).togregorian(), True))
        self.assertEqual((round(kpi.value), round(kpi.previous), kpi.delta), (33, 100, -67))
        self.assertEqual(kpi.direction, "down")
        self.assertContains(response, '<bdi dir="ltr">−۶۷</bdi> واحد')

    def test_an_incomplete_previous_period_shows_no_arrow(self):
        # Sat 4 .. Wed 15 has 10 teaching days; only 1 Mehr comes before.
        kpi = self.kpis(self.get("dashboard", date_from="1405-07-04", date_to="1405-07-15"))["execution_rate"]

        self.assertIsNone(kpi.delta)
        self.assertEqual(kpi.note, "داده‌ی دوره‌ی قبل کافی نیست")

    def test_branches_side_by_side_whatever_the_branch_filter(self):
        self.session(self.math, SUNDAY_1, self.bell_1)

        response = self.get("dashboard", branch=self.branch_b.pk)
        comparison = {c["branch"].pk: c for c in response.context["comparison"]}

        self.assertEqual(comparison[self.branch_a.pk]["breakdown"].held, 1)
        self.assertEqual(comparison[self.branch_b.pk]["breakdown"].held, 0)
        self.assertTrue(comparison[self.branch_b.pk]["is_selected"])
        # The KPIs follow the filter: branch B held nothing.
        self.assertEqual(self.kpis(response)["execution_rate"].value, 0)
        self.assertEqual(self.kpis(response)["classes"].value, 1)

    def test_calendar_summary(self):
        make_calendar_event(self.year, SUNDAY_2, branches=[self.branch_a])
        upcoming = make_calendar_event(self.year, J(1405, 7, 20), title="تعطیلی آینده")
        make_calendar_event(self.year, J(1405, 9, 1), title="بیش از ۳۰ روز بعد")

        summary = self.get("dashboard").context["calendar"]
        summary_a = self.get("dashboard", branch=self.branch_a.pk).context["calendar"]

        self.assertEqual((summary["elapsed"], summary["lost"]), (11, 0))
        self.assertEqual((summary_a["elapsed"], summary_a["lost"]), (10, 1))
        self.assertEqual(summary["upcoming"], [upcoming])
        self.assertGreater(summary["remaining"], 100)

    def test_no_data_yet(self):
        response = self.get("dashboard", period="today")
        kpis = self.kpis(response)

        self.assertIsNone(kpis["execution_rate"].value)
        self.assertIsNone(kpis["attendance_rate"].value)
        self.assertContains(response, "—")

    def test_without_a_current_academic_year(self):
        AcademicYear.objects.update(is_current=False)

        response = self.get("dashboard")

        self.assertContains(response, "سال تحصیلی جاری تعریف نشده است")
        self.assertNotIn("kpis", response.context)

    def test_a_range_in_the_future_is_empty(self):
        response = self.get("dashboard", date_from="1405-09-01", date_to="1405-09-10")

        self.assertTrue(response.context["scope"].is_empty)
        self.assertContains(response, "هیچ روزی از سال تحصیلی تا امروز")


class AlertTests(DirectorPageTestCase):
    def alerts(self, **params):
        return {alert.key: alert for alert in self.get("dashboard", **params).context["alerts"]}

    def test_classes_under_the_attendance_threshold(self):
        # 6 of 7 attended = 86% (not flagged); 5 of 6 = 83% (flagged)
        self.attend(self.session(self.math, SUNDAY_2, self.bell_1), P, P, P, P, P, L, A)
        self.attend(self.session(self.physics, SUNDAY_2, self.bell_1), P, P, P, P, P, A,
                    school_class=self.class_b)

        alert = self.alerts()["attendance"]

        self.assertEqual(alert.count, 1)
        self.assertEqual(alert.items[0]["label"], fa_digits(f"{self.grade.name} {self.class_b.section}"))
        self.assertIn(f"class={self.class_b.pk}", alert.items[0]["url"])
        self.assertIn("period=custom", alert.items[0]["url"])

        with override_settings(DIRECTOR_ALERT_ATTENDANCE_RATE=90):
            self.assertEqual(self.alerts()["attendance"].count, 2)

    def test_attendance_outside_the_window_is_ignored(self):
        # Sunday 5 Mehr is more than 7 teaching days before Wednesday 15.
        self.attend(self.session(self.math, SUNDAY_1, self.bell_1), A, A)

        self.assertEqual(self.alerts()["attendance"].count, 0)

    def test_teachers_with_unregistered_slots(self):
        # Math: Sunday 12 (2 bells) + Monday 13 (1 bell) in the window = 3.
        make_schedule(self.math, ClassSchedule.DayChoices.MONDAY, self.bell_1)

        alert = self.alerts()["unregistered"]

        self.assertEqual(alert.count, 1)
        self.assertIn(self.teacher.staff.user.first_name, alert.items[0]["label"])
        self.assertIn("view=teachers", alert.url)

        self.session(self.math, J(1405, 7, 13), self.bell_1)
        self.assertEqual(self.alerts()["unregistered"].count, 0)

        with override_settings(DIRECTOR_ALERT_UNREGISTERED_SLOTS=2):
            self.assertEqual(self.alerts()["unregistered"].count, 1)

    def test_held_sessions_without_attendance_after_a_day(self):
        self.session(self.math, SUNDAY_1, self.bell_1)                                # old: listed
        self.session(self.math, J(1405, 7, 13), self.bell_3, SchoolSession.Status.COMPENSATORY)  # 2 days: listed
        self.session(self.math, J(1405, 7, 14), self.bell_3, SchoolSession.Status.COMPENSATORY)  # yesterday: not yet
        self.session(self.math, SUNDAY_1, self.bell_2, SchoolSession.Status.CANCELED)  # cancelled: never
        self.attend(self.session(self.physics, SUNDAY_1, self.bell_1), P, school_class=self.class_b)

        alert = self.alerts()["missing_attendance"]

        self.assertEqual(alert.count, 2)
        self.assertIn("#missing", alert.url)
        self.assertEqual(self.alerts(branch=self.branch_b.pk)["missing_attendance"].count, 0)

    def test_conflicts_with_the_calendar(self):
        self.session(self.math, SUNDAY_2, self.bell_1)
        make_calendar_event(self.year, SUNDAY_2, branches=[self.branch_a], title="آلودگی هوا")
        calendar.sync_cancelled_sessions(SUNDAY_2, SUNDAY_2)

        alerts = self.alerts()
        execution = self.get("execution", period="year")

        self.assertEqual(alerts["conflicts"].count, 1)
        self.assertEqual(alerts["conflicts"].items[0]["detail"], "آلودگی هوا")
        self.assertEqual(self.alerts(branch=self.branch_b.pk)["conflicts"].count, 0)
        self.assertEqual(len(execution.context["conflicts"]), 1)
        self.assertContains(execution, "آلودگی هوا")

    def test_no_alerts(self):
        alerts = self.alerts(period="today")

        # math has 2 unregistered slots in the window, physics 1: under 3
        self.assertEqual([a.count for a in alerts.values()], [0, 0, 0, 0])
        self.assertContains(self.get("dashboard"), "ندارد")


class ExecutionTests(DirectorPageTestCase):
    def test_drill_down_branch_grade_class_class_subject(self):
        self.session(self.math, SUNDAY_1, self.bell_1)

        def rows(**params):
            response = self.get("execution", **params)
            return response.context["level"], {r.label: r.breakdown for r in response.context["rows"]}

        level, by_branch = rows()
        self.assertEqual(level, "branch")
        self.assertEqual((by_branch[self.branch_a.name].expected, by_branch[self.branch_a.name].held), (4, 1))

        level, by_grade = rows(branch=self.branch_a.pk)
        self.assertEqual((level, by_grade[self.grade.name].held), ("grade", 1))

        level, by_class = rows(branch=self.branch_a.pk, grade=self.grade.pk)
        self.assertEqual(level, "class")
        self.assertEqual(list(by_class), [fa_digits(f"{self.grade.name} {self.class_a.section}")])

        level, by_subject = rows(branch=self.branch_a.pk, grade=self.grade.pk, **{"class": self.class_a.pk})
        self.assertEqual(level, "class_subject")
        self.assertEqual(by_subject[self.math.subject.name].unregistered, 3)

    def test_teachers_view(self):
        self.session(self.math, SUNDAY_1, self.bell_1)

        response = self.get("execution", view="teachers")
        rows = response.context["teacher_rows"]

        self.assertEqual([r.breakdown.execution_rate for r in rows], [0, 25])   # worst first
        self.assertContains(response, self.math.subject.name)

    def test_same_subject_comparison_marks_the_class_behind(self):
        class_c = make_school_class(self.branch_b, self.grade, self.year)
        teacher = make_teacher_profile()
        lagging = make_class_subject(
            class_c, self.math.subject, make_assignment(teacher, self.branch_b, self.year),
            J(1405, 7, 1), J(1406, 3, 31),
        )
        make_schedule(lagging, ClassSchedule.DayChoices.SUNDAY, self.bell_3)
        for day in (SUNDAY_1, SUNDAY_2):
            self.session(self.math, day, self.bell_1)

        response = self.get("execution", view="subjects", grade=self.grade.pk)
        matrix = response.context["subject_matrix"]
        row = next(r for r in matrix["rows"] if r["subject"] == self.math.subject)
        cells = {c["school_class"].pk: c for c in row["cells"]}

        self.assertEqual(cells[self.class_a.pk]["breakdown"].held, 2)
        self.assertTrue(cells[class_c.pk]["is_behind"])
        self.assertIsNone(cells[self.class_b.pk]["breakdown"])     # no math in class B
        self.assertContains(response, "director-matrix__behind")

    def test_the_subject_comparison_asks_for_a_grade(self):
        response = self.get("execution", view="subjects")

        self.assertIsNone(response.context["subject_matrix"])
        self.assertContains(response, "یک پایه انتخاب کنید")

    def test_a_class_outside_the_scope_is_ignored(self):
        response = self.get("execution", branch=self.branch_b.pk, **{"class": self.class_a.pk})

        self.assertIsNone(response.context["school_class"])
        self.assertEqual(response.context["level"], "grade")

    def test_unknown_view_falls_back(self):
        self.assertEqual(self.get("execution", view="nope").context["view"], "breakdown")


class AttendancePageTests(DirectorPageTestCase):
    def test_trend_marks_closure_days_instead_of_zero(self):
        self.attend(self.session(self.math, SUNDAY_1, self.bell_1), P, A)
        self.attend(self.session(self.math, J(1405, 7, 13), self.bell_3, SchoolSession.Status.COMPENSATORY), P)
        make_calendar_event(self.year, SUNDAY_2, title="تعطیل رسمی")

        trend = self.get("attendance").context["trend"]
        points = {p["date"]: p for p in trend["points"]}

        self.assertEqual(points[SUNDAY_1.togregorian()]["rate"], 50)
        self.assertTrue(points[SUNDAY_2.togregorian()]["closed"])
        self.assertIsNone(points[SUNDAY_2.togregorian()]["rate"])
        self.assertEqual(points[SUNDAY_2.togregorian()]["closure"], "تعطیل رسمی")
        self.assertNotIn(THURSDAY.togregorian(), points)
        self.assertTrue(trend["enough"])
        self.assertEqual(trend["chart"]["closed"].count(True), 1)

    def test_one_day_of_data_is_not_enough_for_a_chart(self):
        self.attend(self.session(self.math, SUNDAY_1, self.bell_1), P)

        response = self.get("attendance")

        self.assertFalse(response.context["trend"]["enough"])
        self.assertNotContains(response, 'id="attendanceTrend"')
        self.assertContains(response, "جدول روزانه")

    def test_empty_state(self):
        response = self.get("attendance")

        self.assertFalse(response.context["trend"]["has_data"])
        self.assertContains(response, "هنوز در این بازه حضور و غیابی ثبت نشده است")

    def test_comparison_and_top_absentees(self):
        session_a = self.session(self.math, SUNDAY_1, self.bell_1)
        session_b = self.session(self.math, SUNDAY_1, self.bell_2)
        often = make_enrollment(make_student(), self.class_a)
        once = make_enrollment(make_student(), self.class_a)
        for session in (session_a, session_b):
            Attendance.objects.create(session=session, student_enrollment=often, status=A)
        Attendance.objects.create(session=session_a, student_enrollment=once, status=A)
        Attendance.objects.create(session=session_b, student_enrollment=once, status=L)

        response = self.get("attendance", branch=self.branch_a.pk)
        absentees = response.context["absentees"]
        rows = {r.label: r.breakdown for r in response.context["rows"]}

        self.assertEqual([(s["absent"], s["absence_rate"]) for s in absentees], [(2, 100), (1, 50)])
        self.assertEqual(absentees[0]["class_label"], fa_digits(f"{self.grade.name} {self.class_a.section}"))
        self.assertEqual(rows[self.grade.name].attendance_total, 4)
        self.assertEqual(round(rows[self.grade.name].attendance_rate), 25)

    def test_missing_attendance_list(self):
        self.session(self.math, SUNDAY_1, self.bell_1)

        response = self.get("attendance")

        self.assertEqual(response.context["missing"]["count"], 1)
        self.assertContains(response, 'id="missing"')


class FormattingTests(DirectorPageTestCase):
    def test_a_rate_is_banded_by_the_value_it_shows(self):
        from director.templatetags.director_tags import percent, rate_level, signed

        self.assertEqual((percent(84.6), rate_level(84.6)), ("۸۵٪", "ok"))
        self.assertEqual((percent(84.4), rate_level(84.4)), ("۸۴٪", "warning"))
        self.assertEqual((rate_level(59.5), rate_level(59.4)), ("warning", "low"))
        self.assertEqual((percent(None), rate_level(None)), ("—", ""))
        self.assertEqual((signed(3), signed(-12), signed(0)), ("+۳", "−۱۲", "۰"))


class FilterTests(DirectorPageTestCase):
    def scope(self, **params):
        return self.get("dashboard", **params).context["scope"]

    def test_presets(self):
        today = AS_OF.date()

        self.assertEqual(self.scope(period="year").start, J(1405, 7, 1).togregorian())
        self.assertEqual(self.scope(period="today").start, today)
        self.assertEqual(self.scope(period="week").start, J(1405, 7, 11).togregorian())
        self.assertEqual(self.scope(period="month").start, J(1405, 7, 1).togregorian())

    def test_every_page_opens_on_this_jalali_month(self):
        # In Aban, "this month" and "since the start of the year" differ.
        aban = at(J(1405, 8, 10))
        with mock.patch("django.utils.timezone.now", lambda: aban):
            self.client.force_login(make_user(User.Roles.DIRECTOR))
            for page in ("dashboard", "execution", "attendance"):
                with self.subTest(page=page):
                    response = self.get(page)
                    self.assertEqual(response.context["filters"].period, "month")
                    self.assertEqual(
                        (response.context["scope"].start, response.context["scope"].end),
                        (J(1405, 8, 1).togregorian(), aban.date()),
                    )
                    self.assertIn("period=month", response.context["director_query"])

            year = self.get("dashboard", period="year")
            self.assertEqual(year.context["scope"].start, J(1405, 7, 1).togregorian())
            # A custom range without dates falls back to this month too.
            self.assertEqual(self.get("dashboard", period="custom").context["filters"].period, "month")

    def test_typed_dates_make_a_custom_range(self):
        response = self.get("dashboard", period="week", date_from="۱۴۰۵/۰۷/۰۴", date_to="1405-07-08")

        self.assertEqual(response.context["filters"].period, "custom")
        self.assertEqual(response.context["scope"].start, J(1405, 7, 4).togregorian())
        self.assertIn("date_from=1405-07-04", response.context["director_query"])

    def test_dates_equal_to_the_preset_keep_it(self):
        response = self.get("dashboard", period="week", date_from="1405-07-11", date_to="1405-07-15")

        self.assertEqual(response.context["filters"].period, "week")

    def test_invalid_input_is_reported_and_not_applied(self):
        response = self.get("dashboard", date_from="1405-13-40", branch="999999", grade="x")

        self.assertEqual(response.context["filters"].branch, None)
        self.assertEqual(response.context["scope"].start, J(1405, 7, 1).togregorian())
        self.assertContains(response, "برخی فیلترها اعمال نشدند")

    def test_end_before_start(self):
        response = self.get("dashboard", date_from="1405-07-10", date_to="1405-07-05")

        self.assertContains(response, "تاریخ پایان نباید قبل از تاریخ شروع باشد")

    def test_links_keep_the_filters(self):
        response = self.get("dashboard", period="week", branch=self.branch_a.pk)

        self.assertContains(response, f'{reverse("director:execution")}?period=week&amp;branch={self.branch_a.pk}')


class QueryCountTests(DirectorPageTestCase):
    """
    Every page runs a fixed number of queries, however many classes,
    sessions and records there are: the second request, after adding a
    class with its timetable, sessions, content and attendance, must not
    run a single extra query.
    """

    PAGES = (
        ("dashboard", {}),
        ("dashboard", {"branch": "A"}),
        ("execution", {}),
        ("execution", {"view": "teachers"}),
        ("execution", {"view": "subjects", "grade": "G"}),
        ("execution", {"class": "C"}),
        ("attendance", {}),
        ("attendance", {"class": "C"}),
    )

    def params(self, params):
        values = {"A": self.branch_a.pk, "G": self.grade.pk, "C": self.class_a.pk}
        return {key: values.get(value, value) for key, value in params.items()}

    def add_data(self, n):
        for _ in range(n):
            school_class = make_school_class(self.branch_a, self.grade, self.year)
            teacher = make_teacher_profile()
            cs = make_class_subject(
                school_class, make_subject(), make_assignment(teacher, self.branch_a, self.year),
                J(1405, 7, 1), J(1406, 3, 31),
            )
            make_schedule(cs, ClassSchedule.DayChoices.SUNDAY, self.bell_3)
            session = self.session(cs, SUNDAY_1, self.bell_3)
            self.content(session)
            self.attend(session, P, A, L, school_class=school_class)
        make_calendar_event(self.year, J(1405, 7, 20))

    def counts(self):
        counts = {}
        for name, params in self.PAGES:
            url = reverse(f"director:{name}")
            self.client.get(url, self.params(params))      # warm per-process caches
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url, self.params(params))
            self.assertEqual(response.status_code, 200)
            counts[(name, tuple(sorted(params.items())))] = len(queries)
        return counts

    def test_query_counts_do_not_grow_with_data(self):
        self.add_data(1)
        before = self.counts()
        self.add_data(5)
        after = self.counts()

        self.assertEqual(after, before)
        # Locked: a new query on a page must be a deliberate change.
        self.assertEqual(before, self.EXPECTED)

    #: overhead (session, user, branch middleware, site footer) 7 +
    #: current year, branches, grades 3 + the year's events 4 + engine 3
    #: (class subjects, slots, sessions) + 1 attendance tallies where the
    #: page shows attendance; the dashboard adds the head counts 5 (its
    #: conflicts and sessions without attendance come from the engine
    #: run); the attendance page adds the top absentees 1.
    EXPECTED = {
        ("dashboard", ()): 23,
        ("dashboard", (("branch", "A"),)): 23,
        ("execution", ()): 17,
        ("execution", (("view", "teachers"),)): 17,
        ("execution", (("grade", "G"), ("view", "subjects"))): 17,
        ("execution", (("class", "C"),)): 17,
        ("attendance", ()): 19,
        ("attendance", (("class", "C"),)): 19,
    }

