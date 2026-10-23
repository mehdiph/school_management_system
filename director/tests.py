"""
The director panel: the school's daily attendance at a glance.

* the home page on a school day (before and after the grace), on
  Thursday / Friday, on a full or partial closure, on a weekday without
  lessons, before daily attendance starts and without data;
* the classes without attendance today, with and without a supporter;
* today's absent students by class, late on its own line;
* frequent absences at and around the threshold, with each student's days;
* the attendance page: periods, clamping at the cutoff (archived
  per-session records never mix in), the daily points (a holiday is never
  zero), the class labels and their thresholds;
* the branch filter, the execution redirect, and locked query counts.

The fixture is ``analytics.tests.Fixture`` (year 1405; class A in branch A
has math at bells 1 and 2 on Sundays, class B in branch B physics at bell
1; bell 1 ends at 08:15) with daily attendance from Sunday 12 Mehr
(``DAILY_FROM_SUNDAY_2``). "Now" is set by each test.
"""

from unittest import mock

from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from analytics.tests import DAILY_FROM_SUNDAY_2, SUNDAY_1, SUNDAY_2, Fixture, J, at
from attendance.models import DailyAttendance, DailyAttendanceSheet, SessionAttendance
from core.testing import (
    make_assignment,
    make_class_subject,
    make_enrollment,
    make_schedule,
    make_school_class,
    make_student,
    make_subject,
    make_supervisor,
    make_teacher_profile,
    make_user,
)
from scheduling.models import ClassSchedule
from school.models import AcademicYear
from supervisor.models import SupervisorClass

from . import selectors

MONDAY = J(1405, 7, 13)
WEDNESDAY = J(1405, 7, 15)
THURSDAY = J(1405, 7, 16)
FRIDAY = J(1405, 7, 17)
SUNDAY_3 = J(1405, 7, 19)
SUNDAY_4 = J(1405, 7, 26)
END_OF_MEHR = J(1405, 7, 29)    # a Wednesday

ABSENT, EXCUSED, LATE, PRESENT = "absent", "excused", "late", "present"


@DAILY_FROM_SUNDAY_2
class DirectorPageTestCase(Fixture):
    def setUp(self):
        self.client.force_login(make_user(User.Roles.DIRECTOR))
        self.ali = self.enroll("علی", "رضایی")
        self.sara = self.enroll("سارا", "محمدی")
        self.maryam = self.enroll("مریم", "کریمی")
        self.reza = self.enroll("رضا", "اکبری")

    def now(self, day, hour=12, minute=0):
        patcher = mock.patch("django.utils.timezone.now", return_value=at(day, hour, minute))
        patcher.start()
        self.addCleanup(patcher.stop)

    def enroll(self, first_name, last_name, school_class=None):
        enrollment = make_enrollment(make_student(), school_class or self.class_a)
        user = enrollment.student.user
        user.first_name, user.last_name = first_name, last_name
        user.save()
        return enrollment

    def supporter(self, school_class, first_name="زهرا", last_name="احمدی"):
        supervisor = make_supervisor(school_class.branch, school_class.grade)
        supervisor.user.first_name, supervisor.user.last_name = first_name, last_name
        supervisor.user.save()
        SupervisorClass.objects.create(supervisor=supervisor, school_class=school_class)
        return supervisor

    def sheet(self, day, *entries, school_class=None):
        """A daily sheet: ``entries`` are ``(enrollment, status[, description])``."""

        sheet = DailyAttendanceSheet.objects.create(
            school_class=school_class or self.class_a, date=day, taken_by=make_user(User.Roles.SUPERVISOR),
        )
        DailyAttendance.objects.bulk_create(
            DailyAttendance(sheet=sheet, student_enrollment=entry[0], status=entry[1],
                            description=entry[2] if len(entry) > 2 else "")
            for entry in entries
        )
        return sheet

    def get(self, name, **params):
        response = self.client.get(reverse(f"director:{name}"), params)
        self.assertEqual(response.status_code, 200)
        return response


# ----------------------------------------------------------------------
# Home: today
# ----------------------------------------------------------------------

class HomeSchoolDayTests(DirectorPageTestCase):
    def setUp(self):
        super().setUp()
        self.supporter(self.class_a)
        self.sheet(
            SUNDAY_2,
            (self.ali, ABSENT, "بیمار است"), (self.sara, EXCUSED, "نامه‌ی پزشک"),
            (self.maryam, LATE, "۸:۴۵"), (self.reza, PRESENT),
        )

    def test_today_in_sentences(self):
        self.now(SUNDAY_2, 10)

        response = self.get("dashboard")

        self.assertEqual(response.context["summary"], {
            "due": 2, "recorded": 1, "pending": 0, "absences": 2, "excused": 1, "late": 1,
        })
        self.assertContains(response, "امروز ۲ دانش‌آموز غایب هستند (۱ نفر موجه).")
        self.assertContains(response, "۱ نفر تأخیر داشتند.")
        self.assertContains(response, "حضور و غیاب ۱ از ۲ کلاس ثبت شده است.")
        for technical in ("نرخ", "کلاس-روز", "زنگ مورد انتظار", "دوره‌ی قبل", "↑", "↓"):
            self.assertNotContains(response, technical)

    def test_missing_classes_with_and_without_a_supporter(self):
        self.now(SUNDAY_2, 10)

        missing = self.get("dashboard").context["missing"]
        self.assertEqual([(row["school_class"], row["supporters"]) for row in missing], [(self.class_b, "")])
        self.assertContains(self.get("dashboard"), "پشتیبان ندارد")

        self.supporter(self.class_b, "مینا", "صادقی")
        response = self.get("dashboard")
        self.assertEqual(response.context["missing"][0]["supporters"], "مینا صادقی")
        self.assertContains(response, "پشتیبان: مینا صادقی")

    def test_todays_absent_students_by_class_late_apart(self):
        self.now(SUNDAY_2, 10)

        response = self.get("dashboard")
        [group] = response.context["absent_by_class"]

        self.assertEqual(group["school_class"], self.class_a)
        self.assertEqual([(r.student_enrollment, r.status) for r in group["absent"]],
                         [(self.ali, ABSENT), (self.sara, EXCUSED)])
        self.assertEqual([r.student_enrollment for r in group["late"]], [self.maryam])
        self.assertEqual(group["excused"], 1)
        self.assertContains(response, "بیمار است")
        self.assertContains(response, "نامه‌ی پزشک")
        self.assertContains(response, "با تأخیر:")

    def test_everything_recorded(self):
        self.now(SUNDAY_2, 10)
        self.sheet(SUNDAY_2, (self.enroll("نیما", "نوری", self.class_b), PRESENT), school_class=self.class_b)

        response = self.get("dashboard")

        self.assertEqual(response.context["missing"], [])
        self.assertContains(response, "حضور و غیاب همه‌ی کلاس‌ها ثبت شده است.")


class HomeGraceTests(DirectorPageTestCase):
    def test_before_the_first_bell_is_over_nothing_is_missing(self):
        self.now(SUNDAY_2, 8, 29)       # bell 1 ends at 08:15: due from 08:30

        response = self.get("dashboard")

        self.assertEqual(response.context["missing"], [])
        self.assertEqual(response.context["summary"]["pending"], 2)
        self.assertContains(response, "هنوز حضور و غیاب هیچ کلاسی ثبت نشده است.")
        self.assertContains(response, "۲ کلاس هنوز وقت دارد")

    def test_after_the_grace_they_are(self):
        self.now(SUNDAY_2, 8, 30)

        response = self.get("dashboard")

        self.assertEqual([row["school_class"] for row in response.context["missing"]],
                         [self.class_a, self.class_b])
        self.assertEqual(response.context["summary"]["pending"], 0)


class HomeHolidayTests(DirectorPageTestCase):
    def test_thursday_and_friday(self):
        for day, name in ((THURSDAY, "پنج‌شنبه"), (FRIDAY, "جمعه")):
            with self.subTest(day=name):
                self.now(day)
                response = self.get("dashboard")
                self.assertEqual(response.context["holiday"]["reason"], f"امروز {name} است؛ مدرسه تعطیل است.")
                self.assertEqual(response.context["holiday"]["next_school_day"], SUNDAY_3.togregorian())
                self.assertContains(response, "روز کلاسی بعدی: یکشنبه ۱۹ مهر ۱۴۰۵")
                self.assertNotIn("missing", response.context)

    def test_a_closure_of_the_whole_school(self):
        self.closure(SUNDAY_3, title="تاسوعا")
        self.now(SUNDAY_3, 10)

        response = self.get("dashboard")

        self.assertEqual(response.context["holiday"]["reason"], "امروز تعطیل است: تاسوعا.")
        self.assertEqual(response.context["holiday"]["next_school_day"], SUNDAY_4.togregorian())

    def test_a_partial_closure_is_a_school_day(self):
        self.closure(SUNDAY_3, branches=[self.branch_b], title="اردو")
        self.now(SUNDAY_3, 10)

        response = self.get("dashboard")

        self.assertNotIn("holiday", response.context)
        self.assertEqual(response.context["summary"]["due"], 1)
        self.assertEqual([row["school_class"] for row in response.context["missing"]], [self.class_a])
        self.assertContains(response, "۱ کلاس امروز تعطیل است (اردو).")

    def test_a_weekday_without_lessons(self):
        self.now(MONDAY)

        response = self.get("dashboard")

        self.assertEqual(response.context["holiday"]["reason"], "امروز کلاسی در برنامه نیست.")

    def test_before_daily_attendance_starts(self):
        self.now(J(1405, 7, 8))         # a Tuesday before the cutoff

        response = self.get("dashboard")

        self.assertFalse(response.context["is_daily"])
        self.assertContains(response, "حضور و غیاب روزانه از یکشنبه ۱۲ مهر ۱۴۰۵ شروع می‌شود.")

    def test_next_holiday(self):
        self.closure(SUNDAY_4, title="اردوی پایه", grades=[self.grade])
        self.now(SUNDAY_2, 10)

        response = self.get("dashboard")

        self.assertEqual(response.context["next_holiday"]["event"].title, "اردوی پایه")
        self.assertTrue(response.context["next_holiday"]["is_partial"])
        self.assertContains(response, "تعطیلی بعدی: یکشنبه ۲۶ مهر ۱۴۰۵، اردوی پایه (بخشی از کلاس‌ها).")

    def test_no_next_holiday(self):
        self.now(SUNDAY_2, 10)

        self.assertContains(self.get("dashboard"), "تا دو ماه آینده تعطیلی‌ای در تقویم آموزشی ثبت نشده است.")


class HomeEmptyTests(DirectorPageTestCase):
    def test_no_data(self):
        self.now(SUNDAY_2, 13)

        response = self.get("dashboard")

        self.assertEqual(response.context["summary"]["recorded"], 0)
        self.assertEqual(response.context["absent_by_class"], [])
        self.assertEqual(response.context["frequent"]["rows"], [])
        self.assertContains(response, "هنوز حضور و غیاب هیچ کلاسی ثبت نشده است.")

    def test_without_a_current_academic_year(self):
        AcademicYear.objects.update(is_current=False)
        self.now(SUNDAY_2, 10)

        self.assertContains(self.get("dashboard"), "سال تحصیلی جاری تعریف نشده است.")
        self.assertContains(self.get("attendance"), "سال تحصیلی جاری تعریف نشده است.")


class BranchFilterTests(DirectorPageTestCase):
    def test_one_branch(self):
        self.now(SUNDAY_2, 10)

        response = self.get("dashboard", branch=self.branch_b.pk)

        self.assertEqual([row["school_class"] for row in response.context["missing"]], [self.class_b])
        self.assertEqual(response.context["summary"]["due"], 1)
        self.assertEqual([row["school_class"] for row in self.get("attendance", branch=self.branch_b.pk)
                          .context["classes"]], [self.class_b])

    def test_an_unknown_branch_is_reported_and_not_applied(self):
        self.now(SUNDAY_2, 10)

        response = self.get("dashboard", branch=9999)

        self.assertIsNone(response.context["filters"].branch)
        self.assertEqual(response.context["summary"]["due"], 2)
        self.assertContains(response, "همه‌ی شعبه‌ها نمایش داده شده است.")

    def test_links_keep_the_branch(self):
        self.now(SUNDAY_2, 10)

        response = self.get("attendance", branch=self.branch_a.pk)

        self.assertEqual(response.context["director_query"], f"branch={self.branch_a.pk}")
        self.assertContains(response, f'href="{reverse("director:dashboard")}?branch={self.branch_a.pk}"')
        self.assertContains(response, f"?branch={self.branch_a.pk}&amp;period=week")


# ----------------------------------------------------------------------
# Frequent absences
# ----------------------------------------------------------------------

class FrequentAbsenceTests(DirectorPageTestCase):
    def setUp(self):
        super().setUp()
        # Ali: 3 days (one excused); Sara: 2 days; Maryam: 1 day and late once.
        self.sheet(SUNDAY_2, (self.ali, ABSENT, "بیمار"), (self.sara, ABSENT), (self.maryam, ABSENT))
        self.sheet(SUNDAY_3, (self.ali, ABSENT), (self.sara, ABSENT), (self.maryam, LATE, "۸:۴۰"))
        self.sheet(SUNDAY_4, (self.ali, EXCUSED, "سفر"), (self.sara, PRESENT))
        self.now(END_OF_MEHR)

    def names(self, response):
        return [row["name"] for row in response.context["frequent"]["rows"]]

    def test_at_the_threshold(self):
        response = self.get("dashboard")
        [row] = response.context["frequent"]["rows"]

        self.assertEqual(row["name"], "علی رضایی")
        self.assertEqual((row["absences"], row["excused"], row["late"]), (3, 1, 0))
        self.assertContains(response, "۳ روز غایب (۱ روز موجه)")

    def test_around_the_threshold(self):
        with override_settings(DIRECTOR_FREQUENT_ABSENCE_DAYS=2):
            self.assertEqual(self.names(self.get("dashboard")), ["علی رضایی", "سارا محمدی"])
        with override_settings(DIRECTOR_FREQUENT_ABSENCE_DAYS=4):
            self.assertEqual(self.names(self.get("dashboard")), [])

    def test_a_students_days(self):
        with override_settings(DIRECTOR_FREQUENT_ABSENCE_DAYS=1):
            response = self.get("attendance")
        rows = {row["name"]: row for row in response.context["frequent"]["rows"]}

        self.assertEqual(
            [(r.date, r.status, r.description) for r in rows["علی رضایی"]["days"]],
            [(SUNDAY_4.togregorian(), EXCUSED, "سفر"), (SUNDAY_3.togregorian(), ABSENT, ""),
             (SUNDAY_2.togregorian(), ABSENT, "بیمار")],
        )
        # late days are listed with the absences, never counted as one
        self.assertEqual([r.status for r in rows["مریم کریمی"]["days"]], [LATE, ABSENT])
        self.assertEqual(rows["مریم کریمی"]["absences"], 1)
        self.assertContains(response, "یکشنبه ۲۶ مهر ۱۴۰۵")
        self.assertContains(response, "سفر")

    def test_the_same_list_on_the_attendance_page_for_the_month(self):
        self.assertEqual(self.names(self.get("attendance")), ["علی رضایی"])
        self.assertIsNone(self.get("attendance", period="today").context["frequent"])
        self.assertContains(self.get("attendance", period="today"), "«این هفته» یا «این ماه»")


# ----------------------------------------------------------------------
# Attendance page
# ----------------------------------------------------------------------

class AttendancePageTests(DirectorPageTestCase):
    def test_the_month_is_clamped_to_the_cutoff_with_a_note(self):
        self.now(END_OF_MEHR)

        response = self.get("attendance")
        filters = response.context["filters"]

        self.assertEqual((filters.period, filters.start, filters.end, filters.clamped),
                         ("month", SUNDAY_2.togregorian(), END_OF_MEHR.togregorian(), True))
        self.assertContains(response, "حضور و غیاب روزانه از ۱۲ مهر ۱۴۰۵ ثبت می‌شود؛")

    def test_archived_per_session_records_never_mix_in(self):
        held = self.session(self.math, SUNDAY_1, self.bell_1)
        SessionAttendance.objects.create(session=held, student_enrollment=self.ali, status=ABSENT)
        self.sheet(SUNDAY_2, (self.ali, PRESENT))
        self.now(END_OF_MEHR)

        response = self.get("attendance")

        self.assertEqual(response.context["totals"]["absences"], 0)
        self.assertNotIn(SUNDAY_1.togregorian(), [p["date"] for p in response.context["daily"]["points"]])

    def test_a_period_entirely_before_the_cutoff_is_empty(self):
        self.now(J(1405, 7, 8))

        response = self.get("attendance")

        self.assertTrue(response.context["filters"].is_empty)
        self.assertContains(response, "این بازه هنوز روزی از آن ندارد")

    def test_periods(self):
        self.now(J(1405, 7, 21))        # Tuesday 21 Mehr

        week = self.get("attendance", period="week").context["filters"]
        today = self.get("attendance", period="today").context["filters"]
        unknown = self.get("attendance", period="year", grade=1, date_from="1405-07-01")

        self.assertEqual((week.start, week.clamped), (J(1405, 7, 18).togregorian(), False))   # Saturday
        self.assertEqual((today.start, today.end), (J(1405, 7, 21).togregorian(),) * 2)
        self.assertEqual(unknown.context["filters"].period, "month")
        self.assertFalse(unknown.context["form"].errors)

    def test_daily_points_mark_holidays_instead_of_zero(self):
        self.sheet(SUNDAY_2, (self.ali, ABSENT), (self.sara, EXCUSED), (self.maryam, LATE))
        self.sheet(SUNDAY_2, (self.enroll("نیما", "نوری", self.class_b), ABSENT), school_class=self.class_b)
        self.closure(SUNDAY_3, title="تاسوعا")
        self.sheet(SUNDAY_4, (self.ali, PRESENT))
        self.now(END_OF_MEHR)

        points = {p["date"]: p for p in self.get("attendance").context["daily"]["points"]}

        sunday_2, sunday_3, sunday_4 = (points[d.togregorian()] for d in (SUNDAY_2, SUNDAY_3, SUNDAY_4))
        self.assertEqual((sunday_2["kind"], sunday_2["absences"], sunday_2["excused"], sunday_2["late"]),
                         ("recorded", 3, 1, 1))
        self.assertEqual((sunday_3["kind"], sunday_3["absences"], sunday_3["closure"]), ("closed", None, "تاسوعا"))
        self.assertEqual((sunday_4["kind"], sunday_4["absences"], sunday_4["missing"]), ("recorded", 0, 1))
        self.assertEqual(points[MONDAY.togregorian()]["kind"], "no_lessons")
        self.assertNotIn(THURSDAY.togregorian(), points)

    def test_a_day_with_lessons_and_no_sheet_is_a_gap(self):
        self.now(SUNDAY_2, 10)

        [point] = [p for p in self.get("attendance", period="today").context["daily"]["points"]]

        self.assertEqual((point["kind"], point["absences"], point["missing"]), ("missing", None, 2))

    def test_class_rows(self):
        self.supporter(self.class_a)
        # class A: 2 of 4 records absent (one excused) -> 50% -> red
        self.sheet(SUNDAY_2, (self.ali, ABSENT), (self.sara, EXCUSED), (self.maryam, LATE), (self.reza, PRESENT))
        self.now(WEDNESDAY)

        rows = {row["school_class"]: row for row in self.get("attendance").context["classes"]}

        a, b = rows[self.class_a], rows[self.class_b]
        self.assertEqual((a["absences"], a["excused"], a["late"], a["share"], a["level"]), (2, 1, 1, 50, "high"))
        self.assertEqual(a["level_badge"], ("danger", "غیبت زیاد"))
        self.assertEqual(a["recording"], ("success", "همه ثبت شده"))
        self.assertEqual(a["supporters"], "زهرا احمدی")
        self.assertEqual((b["level"], b["missing"], b["supporters"]), (None, 1, ""))
        self.assertEqual(b["recording"], ("danger", "۱ روز ثبت نشده"))

    def test_a_class_still_in_time_or_without_lessons(self):
        self.now(SUNDAY_2, 8)
        rows = self.get("attendance", period="today").context["classes"]
        self.assertEqual({row["recording"] for row in rows}, {("", "هنوز وقت دارد")})

        self.now(MONDAY)
        rows = self.get("attendance", period="today").context["classes"]
        self.assertEqual({row["recording"] for row in rows}, {("", "کلاسی نداشته")})


class AbsenceLevelTests(DirectorPageTestCase):
    def test_thresholds(self):
        cases = ((0, 0, None), (0, 20, "good"), (1, 21, "good"), (1, 20, "attention"),
                 (19, 199, "attention"), (2, 20, "high"), (5, 20, "high"))
        for absences, total, level in cases:
            with self.subTest(absences=absences, total=total):
                self.assertEqual(selectors.absence_level(absences, total)[0], level)

    def test_thresholds_come_from_the_settings(self):
        with override_settings(DIRECTOR_CLASS_ABSENCE_YELLOW=1, DIRECTOR_CLASS_ABSENCE_RED=3):
            self.assertEqual(selectors.absence_level(1, 50)[0], "attention")
            self.assertEqual(selectors.absence_level(3, 100)[0], "high")


# ----------------------------------------------------------------------
# Execution: deferred until curriculum budgeting
# ----------------------------------------------------------------------

class ExecutionRedirectTests(DirectorPageTestCase):
    def test_the_execution_page_redirects_home(self):
        url = reverse("director:execution")
        home = reverse("director:dashboard")

        self.assertRedirects(self.client.get(url), home, status_code=302, fetch_redirect_response=False)
        self.assertRedirects(self.client.get(url, {"branch": self.branch_a.pk, "view": "teachers"}),
                             f"{home}?branch={self.branch_a.pk}", fetch_redirect_response=False)
        self.assertRedirects(self.client.get(url, {"branch": "x"}), home, fetch_redirect_response=False)


# ----------------------------------------------------------------------
# Query counts
# ----------------------------------------------------------------------

class QueryCountTests(DirectorPageTestCase):
    """
    Every page runs a fixed number of queries: adding classes, each with
    its supporter, timetable, students, sheets, absences and late records
    (and frequent absentees), must not add any.
    """

    def add_data(self, n):
        for _ in range(n):
            school_class = make_school_class(self.branch_a, self.grade, self.year)
            self.supporter(school_class)
            cs = make_class_subject(
                school_class, make_subject(), make_assignment(make_teacher_profile(), self.branch_a, self.year),
                J(1405, 7, 1), J(1406, 3, 31),
            )
            make_schedule(cs, ClassSchedule.DayChoices.SUNDAY, self.bell_1)
            students = [make_enrollment(make_student(), school_class) for _ in range(3)]
            for day in (SUNDAY_2, SUNDAY_3, SUNDAY_4):
                self.sheet(day, (students[0], ABSENT, "x"), (students[1], LATE), (students[2], EXCUSED),
                           school_class=school_class)

    def counts(self):
        self.client.get(reverse("director:dashboard"))      # warm the session / user caches
        counts = {}
        for name, params in (("dashboard", {}), ("attendance", {}), ("attendance", {"branch": self.branch_a.pk})):
            with self.assertNumQueries(self.locked[(name, bool(params))]) as context:
                response = self.client.get(reverse(f"director:{name}"), params)
            self.assertEqual(response.status_code, 200)
            counts[(name, bool(params))] = len(context.captured_queries)
        return counts

    #: 7 overhead (session, user and its 3 profiles, the footer's 2) + year,
    #: branches and classes, then -- dashboard (20): the calendar (1 + 3
    #: prefetches), this month's student tallies and the frequent
    #: absentees' days, today's timetable, sheets, supporters and absences;
    #: attendance (19): the timetable, the calendar (1 + 3), the sheets,
    #: the supporters, the student tallies and the frequent absentees' days.
    locked = {("dashboard", False): 20, ("attendance", False): 19, ("attendance", True): 19}

    def test_query_counts_do_not_grow_with_data(self):
        # Events on Mondays (no lessons) in each page's range, so the calendar's prefetches run.
        self.closure(J(1405, 7, 20), title="تعطیلی")    # this month, before today
        self.closure(J(1405, 7, 27), title="تعطیلی")    # the next holiday
        self.now(SUNDAY_4, 10)
        self.add_data(1)
        first = self.counts()
        self.add_data(3)
        self.assertEqual(self.counts(), first)
