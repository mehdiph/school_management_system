"""
Weekly schedule: calendar rules, the two-week rotation, the data the page
and PDF are built from, and who may see it.

Fixed calendar used throughout (1405 academic year):

    AcademicYear.start_date = 1405/07/01 = Wed 2026-09-23
    rotation anchor         = Sat 2026-09-19  (Saturday on or before it)
    Sat 2026-09-19 .. Fri 09-25  -> week 1
    Sat 2026-09-26 .. Fri 10-02  -> week 2   <- NOW is in here
    Sat 2026-10-03 .. Fri 10-09  -> week 1   (shown as "week 1" while NOW)
"""

from datetime import date, datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import jdatetime
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_school_class,
    make_student,
    make_subject,
    make_teacher_profile,
)
from school.models import AcademicYear
from staff.models import Staff
from student.models.student_enrollment import StudentEnrollment

from .models.bell import Bell
from .models.class_schedule import ClassSchedule
from .pdf import render_schedule_html
from .services import (
    build_weekly_schedule,
    get_current_enrollment,
    get_student_weekly_schedule,
)
from .utils import (
    get_current_week_type,
    get_rotation_anchor,
    get_today_schedule_day,
    persian_weekday,
    week_start,
)

TEHRAN = ZoneInfo("Asia/Tehran")
WEEK_ONE = ClassSchedule.WeekTypeChoices.WEEK_ONE
WEEK_TWO = ClassSchedule.WeekTypeChoices.WEEK_TWO
EVERY_WEEK = ClassSchedule.WeekTypeChoices.BOTH
Day = ClassSchedule.DayChoices

YEAR_START = jdatetime.date(1405, 7, 1)  # Wednesday 2026-09-23
#: Saturday of rotation week 2, 09:10 -> during the second bell.
NOW = datetime(2026, 9, 26, 9, 10, tzinfo=TEHRAN)

FAST_HASHER = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)


def year_starting(start):
    return AcademicYear(title="t", start_date=start, end_date=start.replace(year=start.year + 1))


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


class WeekdayMappingTests(SimpleTestCase):

    def test_persian_week_starts_on_saturday(self):
        # 2026-09-26 is a Saturday.
        saturday = date(2026, 9, 26)
        for offset in range(7):
            with self.subTest(offset=offset):
                self.assertEqual(persian_weekday(saturday + timedelta(days=offset)), offset)

    def test_matches_stored_day_choices(self):
        self.assertEqual(get_today_schedule_day(date(2026, 9, 26)), Day.SATURDAY)
        self.assertEqual(get_today_schedule_day(date(2026, 9, 28)), Day.MONDAY)
        self.assertEqual(get_today_schedule_day(date(2026, 10, 1)), Day.THURSDAY)

    def test_friday_has_no_school_day(self):
        self.assertIsNone(get_today_schedule_day(date(2026, 10, 2)))

    def test_week_start_is_saturday_on_or_before(self):
        self.assertEqual(week_start(date(2026, 9, 26)), date(2026, 9, 26))
        self.assertEqual(week_start(date(2026, 9, 23)), date(2026, 9, 19))
        self.assertEqual(week_start(date(2026, 10, 2)), date(2026, 9, 26))

    def test_today_is_tehran_local_date(self):
        # 21:00 UTC on Friday is already 00:30 Saturday in Tehran.
        utc_friday_night = datetime(2026, 9, 25, 21, 0, tzinfo=ZoneInfo("UTC"))
        with mock.patch("django.utils.timezone.now", return_value=utc_friday_night):
            self.assertEqual(get_today_schedule_day(), Day.SATURDAY)


@override_settings(SCHEDULE_ROTATION_ANCHOR=None)
class RotationWeekTests(SimpleTestCase):

    def setUp(self):
        self.year = year_starting(YEAR_START)

    def week(self, value):
        return get_current_week_type(value, academic_year=self.year)

    def test_anchor_is_saturday_before_year_start(self):
        self.assertEqual(get_rotation_anchor(self.year), date(2026, 9, 19))

    def test_rotation_flips_on_saturday_not_mid_week(self):
        # The year starts on a Wednesday; the first week still ends on Friday.
        self.assertEqual(self.week(date(2026, 9, 22)), WEEK_ONE)
        self.assertEqual(self.week(date(2026, 9, 23)), WEEK_ONE)
        self.assertEqual(self.week(date(2026, 9, 25)), WEEK_ONE)
        self.assertEqual(self.week(date(2026, 9, 26)), WEEK_TWO)
        self.assertEqual(self.week(date(2026, 10, 2)), WEEK_TWO)
        self.assertEqual(self.week(date(2026, 10, 3)), WEEK_ONE)
        self.assertEqual(self.week(date(2026, 10, 10)), WEEK_TWO)

    def test_year_starting_on_saturday(self):
        year = year_starting(jdatetime.date.fromgregorian(date=date(2026, 9, 26)))
        self.assertEqual(get_current_week_type(date(2026, 9, 26), academic_year=year), WEEK_ONE)
        self.assertEqual(get_current_week_type(date(2026, 10, 3), academic_year=year), WEEK_TWO)

    def test_configured_anchor_overrides_year(self):
        # Any day of the intended week-1 works; it snaps to its Saturday.
        with override_settings(SCHEDULE_ROTATION_ANCHOR="2026-09-28"):
            self.assertEqual(get_rotation_anchor(self.year), date(2026, 9, 26))
            self.assertEqual(self.week(date(2026, 9, 26)), WEEK_ONE)
            self.assertEqual(self.week(date(2026, 10, 3)), WEEK_TWO)


# ---------------------------------------------------------------------------
# Schedule data
# ---------------------------------------------------------------------------


class ScheduleFixtureMixin:

    @classmethod
    def setUpTestData(cls):
        cls.branch = make_branch()
        cls.grade = make_grade()
        cls.year = make_academic_year(start_date=YEAR_START, is_current=True)
        cls.school_class = make_school_class(cls.branch, cls.grade, cls.year)
        cls.other_class = make_school_class(cls.branch, cls.grade, cls.year)

        cls.teacher = make_teacher_profile()
        cls.teacher.staff.user.last_name = "رضایی"
        cls.teacher.staff.user.save()
        cls.assignment = make_assignment(cls.teacher, cls.branch, cls.year)

        # Created out of order on purpose: display order is Bell.order.
        cls.bell_2 = Bell.objects.create(title="دوم", order=2, start_time=time(9), end_time=time(9, 45))
        cls.bell_1 = Bell.objects.create(title="اول", order=1, start_time=time(8), end_time=time(8, 45))
        cls.bell_off = Bell.objects.create(
            title="غیرفعال", order=3, start_time=time(10), end_time=time(10, 45), is_active=False
        )

    @classmethod
    def class_subject(cls, name, school_class=None, start=YEAR_START, end=jdatetime.date(1406, 3, 31)):
        subject = make_subject()
        subject.name = name
        subject.color = "#2563eb"
        subject.save()
        return make_class_subject(school_class or cls.school_class, subject, cls.assignment, start, end)

    @staticmethod
    def slot(class_subject, day, bell, week_type=EVERY_WEEK):
        return ClassSchedule.objects.create(
            class_subject=class_subject, day_of_week=day, bell=bell, week_type=week_type
        )

    def build(self, now=NOW):
        return build_weekly_schedule(self.school_class, academic_year=self.year, now=now)


def subjects_on(week, day_value):
    day = next(d for d in week.days if d.value == day_value)
    return [slot.entry.subject if slot.entry else None for slot in day.slots]


@override_settings(SCHEDULE_ROTATION_ANCHOR=None, SCHOOL_WORKING_DAYS=[0, 1, 2, 3, 4])
class WeeklyScheduleServiceTests(ScheduleFixtureMixin, TestCase):

    def test_every_week_entries_appear_in_both_weeks(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1, EVERY_WEEK)
        self.slot(self.class_subject("علوم"), Day.SATURDAY, self.bell_2, WEEK_ONE)
        self.slot(self.class_subject("هنر"), Day.SUNDAY, self.bell_2, WEEK_TWO)

        schedule = self.build()
        week_1, week_2 = schedule.week(1), schedule.week(2)

        self.assertEqual(subjects_on(week_1, Day.SATURDAY), ["ریاضی", "علوم"])
        self.assertEqual(subjects_on(week_2, Day.SATURDAY), ["ریاضی", None])
        self.assertEqual(subjects_on(week_1, Day.SUNDAY), [None, None])
        self.assertEqual(subjects_on(week_2, Day.SUNDAY), [None, "هنر"])

    def test_current_week_and_today(self):
        schedule = self.build()

        self.assertTrue(schedule.week(2).is_current)
        self.assertFalse(schedule.week(1).is_current)
        self.assertEqual(schedule.today_day, Day.SATURDAY)
        # Today is only highlighted in the week being lived now.
        self.assertEqual([d.value for d in schedule.week(2).days if d.is_today], [Day.SATURDAY])
        self.assertEqual([d for d in schedule.week(1).days if d.is_today], [])

    def test_running_bell_is_marked(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_2)
        self.slot(self.class_subject("علوم"), Day.SUNDAY, self.bell_2)

        schedule = self.build()
        now_slots = [
            (week.number, day.value, slot.bell.order)
            for week in schedule.weeks for day in week.days for slot in day.slots if slot.is_now
        ]
        self.assertEqual(now_slots, [(2, Day.SATURDAY, 2)])

    def test_only_active_bells_in_order(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_off)

        schedule = self.build()

        self.assertEqual([b.order for b in schedule.bells], [1, 2])
        self.assertEqual(subjects_on(schedule.week(2), Day.SATURDAY), [None, None])

    def test_inactive_class_subject_is_hidden(self):
        class_subject = self.class_subject("ریاضی")
        class_subject.is_active = False
        class_subject.save()
        self.slot(class_subject, Day.SATURDAY, self.bell_1)

        self.assertEqual(subjects_on(self.build().week(2), Day.SATURDAY), [None, None])

    def test_class_subject_teaching_window_is_per_displayed_week(self):
        # Ended the Friday before this week: gone from both.
        ended = self.class_subject("ختم‌شده", end=jdatetime.date.fromgregorian(date=date(2026, 9, 25)))
        self.slot(ended, Day.SATURDAY, self.bell_1)
        # Starts next week (Sat 2026-10-03): only in week 1, which is shown as next week.
        upcoming = self.class_subject("جدید", start=jdatetime.date.fromgregorian(date=date(2026, 10, 3)))
        self.slot(upcoming, Day.SUNDAY, self.bell_1)

        schedule = self.build()

        self.assertEqual(subjects_on(schedule.week(1), Day.SATURDAY), [None, None])
        self.assertEqual(subjects_on(schedule.week(2), Day.SATURDAY), [None, None])
        self.assertEqual(subjects_on(schedule.week(1), Day.SUNDAY), ["جدید", None])
        self.assertEqual(subjects_on(schedule.week(2), Day.SUNDAY), [None, None])

    def test_other_classes_are_not_included(self):
        self.slot(self.class_subject("دیگری", school_class=self.other_class), Day.SATURDAY, self.bell_1)

        self.assertEqual(subjects_on(self.build().week(2), Day.SATURDAY), [None, None])

    def test_working_days_default_to_saturday_through_wednesday(self):
        days = [d.value for d in self.build().week(1).days]
        self.assertEqual(days, [0, 1, 2, 3, 4])

    def test_thursday_shown_when_configured(self):
        with override_settings(SCHOOL_WORKING_DAYS=[0, 1, 2, 3, 4, 5]):
            days = [d.value for d in self.build().week(1).days]
        self.assertEqual(days, [0, 1, 2, 3, 4, 5])

    def test_day_with_classes_is_never_hidden_by_config(self):
        self.slot(self.class_subject("ریاضی"), Day.THURSDAY, self.bell_1)

        schedule = self.build()

        self.assertIn(Day.THURSDAY, [d.value for d in schedule.week(1).days])
        self.assertEqual(subjects_on(schedule.week(1), Day.THURSDAY), ["ریاضی", None])

    def test_teacher_shown_with_title_and_last_name(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)

        entry = self.build().week(2).days[0].slots[0].entry
        self.assertEqual(entry.teacher, "آقای رضایی")

    def test_invalid_color_in_database_never_reaches_style(self):
        class_subject = self.class_subject("ریاضی")
        type(class_subject.subject).objects.filter(pk=class_subject.subject_id).update(
            color="red;background:url(x)"
        )
        self.slot(class_subject, Day.SATURDAY, self.bell_1)

        entry = self.build().week(2).days[0].slots[0].entry
        self.assertEqual(entry.color, "#d96a30")
        self.assertNotIn("url", entry.style)

    def test_both_weeks_in_constant_queries(self):
        for day in (Day.SATURDAY, Day.SUNDAY, Day.MONDAY):
            self.slot(self.class_subject(f"درس {day}"), day, self.bell_1)

        with self.assertNumQueries(2):  # bells + schedule slots
            self.build()


class FormalNameTests(TestCase):

    def test_titles_by_gender_and_fallbacks(self):
        staff = make_teacher_profile().staff
        staff.user.first_name, staff.user.last_name = "مریم", "حسینی"

        staff.gender = Staff.Gender.FEMALE
        self.assertEqual(staff.formal_name, "خانم حسینی")
        staff.gender = Staff.Gender.MALE
        self.assertEqual(staff.formal_name, "آقای حسینی")
        staff.gender = ""
        self.assertEqual(staff.formal_name, "مریم حسینی")
        staff.gender, staff.user.last_name = Staff.Gender.MALE, ""
        self.assertEqual(staff.formal_name, "مریم")


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


@FAST_HASHER
class CurrentEnrollmentTests(ScheduleFixtureMixin, TestCase):

    def test_uses_current_year_enrollment(self):
        old_year = make_academic_year(start_date=jdatetime.date(1404, 7, 1), is_current=False)
        old_class = make_school_class(self.branch, self.grade, old_year)
        student = make_student()
        make_enrollment(student, old_class)
        current = make_enrollment(student, self.school_class)

        self.assertEqual(get_current_enrollment(student), current)

    def test_schedule_is_the_enrolled_class_only(self):
        student = make_student()
        make_enrollment(student, self.school_class)
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)
        self.slot(self.class_subject("دیگری", school_class=self.other_class), Day.SATURDAY, self.bell_2)

        schedule = get_student_weekly_schedule(student, now=NOW)

        self.assertEqual(schedule.enrollment.school_class, self.school_class)
        self.assertEqual(subjects_on(schedule.week(2), Day.SATURDAY), ["ریاضی", None])

    def test_no_active_enrollment_means_no_schedule(self):
        student = make_student()
        make_enrollment(student, self.school_class, status=StudentEnrollment.EnrollmentStatus.WITHDRAWN)

        self.assertIsNone(get_student_weekly_schedule(student, now=NOW))


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@FAST_HASHER
@override_settings(SCHEDULE_ROTATION_ANCHOR=None)
class WeeklyScheduleViewTests(ScheduleFixtureMixin, TestCase):
    url = reverse("scheduling:weekly-schedule")

    def setUp(self):
        self.student = make_student()
        make_enrollment(self.student, self.school_class)
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)
        self.client.force_login(self.student.user)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def selected_tab(self, response):
        week = response.context["selected_week"]
        return week.number

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url),
            f"{reverse('accounts:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_non_student_is_forbidden(self):
        self.client.force_login(self.teacher.staff.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_defaults_to_current_rotation_week(self):
        response = self.client.get(self.url)

        self.assertEqual(self.selected_tab(response), 2)
        self.assertContains(response, 'id="ws-tab-2"')
        self.assertContains(response, 'aria-selected="true" tabindex="0"', count=1)
        self.assertContains(response, "ریاضی")
        self.assertContains(response, "آقای رضایی")
        self.assertContains(response, 'style="--subject-color: #2563eb; --subject-on: #ffffff;"')

    def test_week_query_parameter(self):
        self.assertEqual(self.selected_tab(self.client.get(self.url, {"week": "1"})), 1)
        self.assertEqual(self.selected_tab(self.client.get(self.url, {"week": "2"})), 2)
        self.assertEqual(self.selected_tab(self.client.get(self.url, {"week": "7"})), 2)
        self.assertEqual(self.selected_tab(self.client.get(self.url, {"week": "x"})), 2)

    def test_no_hardcoded_mobile_content(self):
        response = self.client.get(self.url)

        for leftover in ("خانم حسینی", "آقای تقوی", "عرض مرورگر خود را افزایش دهید"):
            self.assertNotContains(response, leftover)

    def test_student_without_enrollment_gets_empty_state(self):
        other = make_student()
        self.client.force_login(other.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ثبت‌نام فعال ندارید")


@FAST_HASHER
@override_settings(SCHEDULE_ROTATION_ANCHOR=None)
class WeeklySchedulePdfTests(ScheduleFixtureMixin, TestCase):
    url = reverse("scheduling:weekly-schedule-pdf")

    def setUp(self):
        self.student = make_student()
        make_enrollment(self.student, self.school_class)
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1, EVERY_WEEK)
        self.slot(self.class_subject("علوم"), Day.SUNDAY, self.bell_1, WEEK_ONE)

    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(
            self.client.get(self.url),
            f"{reverse('accounts:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_non_student_is_forbidden(self):
        self.client.force_login(self.teacher.staff.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_student_downloads_own_pdf(self):
        self.client.force_login(self.student.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="weekly-schedule-1405.pdf"'
        )
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_one_page_per_week_with_every_week_entries_on_both(self):
        schedule = get_student_weekly_schedule(self.student, now=NOW)

        html = render_schedule_html(schedule)

        self.assertEqual(html.count('class="page"'), 2)
        self.assertIn("برنامه هفتگی – هفته اول", html)
        self.assertIn("برنامه هفتگی – هفته دوم", html)
        self.assertEqual(html.count("ریاضی"), 2)  # every week
        self.assertEqual(html.count("علوم"), 1)   # week 1 only
        self.assertIn(self.student.user.get_full_name(), html)
