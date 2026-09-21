"""
Tests for the supervisor dashboard selector layer.

There are no shared factories/fixtures elsewhere in the project (every
app's tests.py is still a stub), so this module defines small, explicit
helper functions instead. Each helper takes every value it needs as an
argument -- nothing is hidden in class-level defaults -- so test bodies
stay easy to audit against the assertions they make.
"""

import jdatetime
from datetime import date, datetime, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from attendance.models.attendance import Attendance
from school.models import AcademicYear, Branch, ClassSubject, Grade, SchoolClass, Subject
from scheduling.models.bell import Bell
from scheduling.models.class_schedule import ClassSchedule
from staff.models.staff import Staff
from staff.models.teacher_assignment import TeacherAssignment
from staff.models.teacher_profile import TeacherProfile
from student.models.student_enrollment import StudentEnrollment
from student.models.student_profile import StudentProfile
from supervisor.models.supervisor_class import SupervisorClass
from supervisor.models.supervisor_profile import SupervisorProfile
from supervisor.selectors import SupervisorDashboardSelector, SupervisorScope
from teaching.models.school_session import SchoolSession

User = get_user_model()

_counter = 0


def _unique(prefix):
    global _counter
    _counter += 1
    return f"{prefix}{_counter}"



def make_user(role):
    username = _unique("user")
    return User.objects.create_user(
        username=username,
        password="test-pass-123",
        first_name=username,
        last_name=role,
        role=role,
        phone_number="09120000000",
    )


def make_branch():
    code = _unique("branch")
    return Branch.objects.create(name=code, code=code)


def make_grade(level=None):
    if level is None:
        global _counter
        _counter += 1
        level = _counter
    return Grade.objects.create(name=f"پایه {level}", level=level)


def make_academic_year(start_date, end_date=None, is_current=True, is_active=True):
    if end_date is None:
        end_date = start_date.replace(year=start_date.year + 1)
    return AcademicYear.objects.create(
        title=_unique("year"),
        start_date=start_date,
        end_date=end_date,
        is_current=is_current,
        is_active=is_active,
    )


def make_subject():
    slug = _unique("subject")
    return Subject.objects.create(name=slug, slug=slug)


def make_school_class(branch, grade, year, is_active=True):
    return SchoolClass.objects.create(
        year=year,
        grade=grade,
        branch=branch,
        section=_unique("section"),
        is_active=is_active,
    )


def make_teacher(branch, academic_year, status=TeacherAssignment.AssignmentStatus.ACTIVE):
    """
    Creates a full teacher chain (User -> Staff -> TeacherProfile) plus a
    TeacherAssignment in the given branch/year, and returns
    (teacher_profile, assignment).
    """

    user = make_user(User.Roles.TEACHER)
    staff = Staff.objects.create(
        user=user,
        personnel_code=_unique("pc"),
        national_code=_unique("nc")[:10],
        gender=Staff.Gender.MALE,
        hire_date=jdatetime.date(1400, 1, 1),
    )
    teacher = TeacherProfile.objects.create(staff=staff)
    assignment = TeacherAssignment.objects.create(
        teacher=teacher,
        branch=branch,
        academic_year=academic_year,
        hire_date=jdatetime.date(1400, 1, 1),
        status=status,
    )
    return teacher, assignment


def make_class_subject(school_class, subject, teacher_assignment, start_date, end_date, is_active=True):
    return ClassSubject.objects.create(
        school_class=school_class,
        subject=subject,
        teacher_assignment=teacher_assignment,
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
    )


def make_supervisor(branch, grade):
    user = make_user(User.Roles.SUPERVISOR)
    return SupervisorProfile.objects.create(user=user, branch=branch, grade=grade)


def assign_class(supervisor, school_class):
    """
    Bypasses SupervisorClass.clean() on purpose: it lets tests build the
    "cross branch/grade" rows needed to prove SupervisorScope's own
    defensive filtering (not just the admin-form-level validation) is
    what keeps a supervisor's data isolated.
    """

    return SupervisorClass.objects.create(supervisor=supervisor, school_class=school_class)


def make_student():
    user = make_user(User.Roles.STUDENT)
    return StudentProfile.objects.create(user=user, student_code=_unique("std"))


def make_enrollment(student, school_class, status=StudentEnrollment.EnrollmentStatus.ACTIVE, enrollment_date=None):
    if enrollment_date is None:
        enrollment_date = jdatetime.date(1402, 7, 1)
    return StudentEnrollment.objects.create(
        student=student,
        school_class=school_class,
        enrollment_date=enrollment_date,
        status=status,
    )


def make_session(class_subject, session_date, status=SchoolSession.Status.HELD):
    return SchoolSession.objects.create(
        class_subject=class_subject,
        date=session_date,
        status=status,
    )


def make_attendance(session, enrollment, status=Attendance.AttendanceStatus.PRESENT):
    return Attendance.objects.create(
        session=session,
        student_enrollment=enrollment,
        status=status,
    )


def make_bell(start_time, end_time):
    global _counter
    _counter += 1
    return Bell.objects.create(
        title=f"bell{_counter}",
        order=_counter,
        start_time=start_time,
        end_time=end_time,
    )


def make_schedule(class_subject, day_of_week, bell, week_type=ClassSchedule.WeekTypeChoices.BOTH):
    return ClassSchedule.objects.create(
        class_subject=class_subject,
        day_of_week=day_of_week,
        week_type=week_type,
        bell=bell,
    )


def aware(gregorian_date, hour, minute):
    tz = timezone.get_default_timezone()
    return timezone.make_aware(
        datetime(gregorian_date.year, gregorian_date.month, gregorian_date.day, hour, minute),
        tz,
    )


# A fixed range that comfortably brackets every jalali date used below,
# so ClassSubject.start_date/end_date never rejects a session/schedule.
WIDE_START = jdatetime.date(1400, 1, 1)
WIDE_END = jdatetime.date(1410, 1, 1)


class SupervisorScopeIsolationTests(TestCase):
    """
    Items 1-4: a supervisor's data must never leak outside their
    assigned classes, branch, or grade.
    """

    def setUp(self):
        self.branch = make_branch()
        self.other_branch = make_branch()
        self.grade = make_grade()
        self.other_grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))

        self.supervisor = make_supervisor(self.branch, self.grade)

        self.own_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, self.own_class)

        _, assignment = make_teacher(self.branch, self.year)
        self.own_class_subject = make_class_subject(
            self.own_class, make_subject(), assignment, WIDE_START, WIDE_END
        )

    def test_supervisor_sees_only_assigned_classes(self):
        # An existing class in the supervisor's own branch/grade that was
        # never assigned to them must not show up.
        unassigned_class = make_school_class(self.branch, self.grade, self.year)

        classes = SupervisorScope(self.supervisor).classes()

        self.assertIn(self.own_class, classes)
        self.assertNotIn(unassigned_class, classes)

    def test_cannot_see_another_supervisors_classes(self):
        other_supervisor = make_supervisor(self.branch, self.grade)
        other_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(other_supervisor, other_class)

        classes = SupervisorScope(self.supervisor).classes()

        self.assertNotIn(other_class, classes)
        # And the other supervisor's session data must not leak through
        # class_subjects()/sessions() either.
        _, assignment = make_teacher(self.branch, self.year)
        other_class_subject = make_class_subject(
            other_class, make_subject(), assignment, WIDE_START, WIDE_END
        )
        other_session = make_session(other_class_subject, jdatetime.date(1402, 7, 10))

        self.assertNotIn(other_session, SupervisorScope(self.supervisor).sessions())

    def test_branch_isolation(self):
        # A SupervisorClass row pointing at a class from a different
        # branch (bypassing model-level validation) must still be
        # rejected by the scope's own branch filter.
        cross_branch_class = make_school_class(self.other_branch, self.grade, self.year)
        assign_class(self.supervisor, cross_branch_class)

        classes = SupervisorScope(self.supervisor).classes()

        self.assertNotIn(cross_branch_class, classes)

    def test_grade_isolation(self):
        cross_grade_class = make_school_class(self.branch, self.other_grade, self.year)
        assign_class(self.supervisor, cross_grade_class)

        classes = SupervisorScope(self.supervisor).classes()

        self.assertNotIn(cross_grade_class, classes)


class SupervisorDashboardSelectorSummaryTests(TestCase):
    """Items 5-7: summary() counts, with teachers/students deduplicated."""

    def setUp(self):
        self.branch = make_branch()
        self.grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))
        self.supervisor = make_supervisor(self.branch, self.grade)

        self.class_a = make_school_class(self.branch, self.grade, self.year)
        self.class_b = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, self.class_a)
        assign_class(self.supervisor, self.class_b)

        # One teacher teaches a subject in BOTH assigned classes: must
        # be counted once, not twice.
        self.teacher, self.assignment = make_teacher(self.branch, self.year)
        self.cs_a = make_class_subject(
            self.class_a, make_subject(), self.assignment, WIDE_START, WIDE_END
        )
        self.cs_b = make_class_subject(
            self.class_b, make_subject(), self.assignment, WIDE_START, WIDE_END
        )

    def test_summary_counts_are_correct(self):
        selector = SupervisorDashboardSelector(self.supervisor)
        make_session(self.cs_a, jdatetime.date(1402, 7, 1))
        make_session(self.cs_a, jdatetime.date(1402, 7, 8))
        make_session(self.cs_b, jdatetime.date(1402, 7, 1))

        summary = selector.summary()

        self.assertEqual(summary["classes_count"], 2)
        self.assertEqual(summary["sessions_count"], 3)

    def test_teachers_are_counted_uniquely(self):
        # A second teacher teaching a different subject in class_a only.
        other_teacher, other_assignment = make_teacher(self.branch, self.year)
        make_class_subject(
            self.class_a, make_subject(), other_assignment, WIDE_START, WIDE_END
        )

        summary = SupervisorDashboardSelector(self.supervisor).summary()

        # self.teacher (2 class_subjects) + other_teacher (1) = 2 unique
        # teachers, not 3 rows.
        self.assertEqual(summary["teachers_count"], 2)

    def test_deactivated_class_subject_teacher_is_not_counted(self):
        # Reproduces a real bug report: a class_subject is reassigned
        # to a new teacher by deactivating the old ClassSubject row
        # (teacher_assignment is PROTECTed, so the old row is
        # deactivated rather than deleted) and creating a new one. The
        # old teacher must not still count towards "معلم فعال".
        old_teacher, old_assignment = make_teacher(self.branch, self.year)
        old_class_subject = make_class_subject(
            self.class_a, make_subject(), old_assignment, WIDE_START, WIDE_END
        )
        old_class_subject.is_active = False
        old_class_subject.save(update_fields=["is_active"])

        new_teacher, new_assignment = make_teacher(self.branch, self.year)
        make_class_subject(
            self.class_a, make_subject(), new_assignment, WIDE_START, WIDE_END
        )

        summary = SupervisorDashboardSelector(self.supervisor).summary()

        # self.teacher (still active) + new_teacher = 2; old_teacher's
        # only class_subject is inactive, so they don't count.
        self.assertEqual(summary["teachers_count"], 2)

    def test_teacher_with_terminated_assignment_is_not_counted(self):
        # Same bug, different signal: the class_subject itself is still
        # active but the teacher's assignment has ended.
        _, terminated_assignment = make_teacher(
            self.branch, self.year,
            status=TeacherAssignment.AssignmentStatus.TERMINATED,
        )
        make_class_subject(
            self.class_a, make_subject(), terminated_assignment, WIDE_START, WIDE_END
        )

        summary = SupervisorDashboardSelector(self.supervisor).summary()

        # Only self.teacher (active) counts.
        self.assertEqual(summary["teachers_count"], 1)

    def test_students_are_counted_uniquely_and_only_active(self):
        student_1 = make_student()
        student_2 = make_student()
        withdrawn_student = make_student()

        make_enrollment(student_1, self.class_a)
        make_enrollment(student_2, self.class_b)
        make_enrollment(
            withdrawn_student,
            self.class_a,
            status=StudentEnrollment.EnrollmentStatus.WITHDRAWN,
        )

        summary = SupervisorDashboardSelector(self.supervisor).summary()

        self.assertEqual(summary["students_count"], 2)


class SupervisorDashboardSelectorSessionsTests(TestCase):
    """Item 8: recent_sessions() ordering."""

    def test_recent_sessions_are_correctly_ordered(self):
        branch = make_branch()
        grade = make_grade()
        year = make_academic_year(jdatetime.date(1402, 1, 1))
        supervisor = make_supervisor(branch, grade)
        school_class = make_school_class(branch, grade, year)
        assign_class(supervisor, school_class)
        _, assignment = make_teacher(branch, year)
        class_subject = make_class_subject(
            school_class, make_subject(), assignment, WIDE_START, WIDE_END
        )

        # SchoolSession.clean() requires session_number and date to
        # agree on ordering, so create them in chronological order and
        # rely on recent_sessions() to reverse it.
        oldest = make_session(class_subject, jdatetime.date(1402, 6, 1))
        middle = make_session(class_subject, jdatetime.date(1402, 7, 1))
        newest = make_session(class_subject, jdatetime.date(1402, 8, 1))

        sessions = list(
            SupervisorDashboardSelector(supervisor).recent_sessions(limit=5)
        )

        self.assertEqual(sessions, [newest, middle, oldest])


class SupervisorDashboardSelectorAttendanceTests(TestCase):
    """Item 9: attendance_statistics() respects scope."""

    def test_attendance_statistics_respect_scope(self):
        branch = make_branch()
        grade = make_grade()
        year = make_academic_year(jdatetime.date(1402, 1, 1))

        supervisor = make_supervisor(branch, grade)
        school_class = make_school_class(branch, grade, year)
        assign_class(supervisor, school_class)
        _, assignment = make_teacher(branch, year)
        class_subject = make_class_subject(
            school_class, make_subject(), assignment, WIDE_START, WIDE_END
        )
        session = make_session(class_subject, jdatetime.date(1402, 7, 1))

        student_1 = make_student()
        student_2 = make_student()
        enrollment_1 = make_enrollment(student_1, school_class)
        enrollment_2 = make_enrollment(student_2, school_class)

        make_attendance(session, enrollment_1, Attendance.AttendanceStatus.PRESENT)
        make_attendance(session, enrollment_2, Attendance.AttendanceStatus.ABSENT)

        # Data completely outside this supervisor's scope.
        other_supervisor = make_supervisor(make_branch(), make_grade())
        other_class = make_school_class(other_supervisor.branch, other_supervisor.grade, year)
        assign_class(other_supervisor, other_class)
        _, other_assignment = make_teacher(other_supervisor.branch, year)
        other_class_subject = make_class_subject(
            other_class, make_subject(), other_assignment, WIDE_START, WIDE_END
        )
        other_session = make_session(other_class_subject, jdatetime.date(1402, 7, 1))
        other_student = make_student()
        other_enrollment = make_enrollment(other_student, other_class)
        make_attendance(other_session, other_enrollment, Attendance.AttendanceStatus.LATE)

        stats = SupervisorDashboardSelector(supervisor).attendance_statistics()

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["present"], 1)
        self.assertEqual(stats["absent"], 1)
        self.assertEqual(stats["late"], 0)


class SupervisorDashboardSelectorAttentionItemsTests(TestCase):
    """
    Items 10-16: the "Need attention" / missing-session business rule.

    "Now" is frozen via mocking django.utils.timezone.now so the tests
    don't depend on the real wall-clock date/time.
    """

    #: Saturday (see scheduling.utils.get_today_schedule_day's mapping).
    TODAY = date(2024, 1, 6)
    NEXT_WEEK_SAME_DAY = date(2024, 1, 13)

    BELL_START = time(8, 0)
    BELL_END = time(8, 30)  # deadline = 08:45 (30 + 15 minute grace)

    def setUp(self):
        self.branch = make_branch()
        self.grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))
        self.supervisor = make_supervisor(self.branch, self.grade)
        self.school_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, self.school_class)

        _, self.assignment = make_teacher(self.branch, self.year)
        self.class_subject = make_class_subject(
            self.school_class, make_subject(), self.assignment, WIDE_START, WIDE_END
        )
        self.bell = make_bell(self.BELL_START, self.BELL_END)

    def _attention_items_at(self, gregorian_date, hour, minute):
        frozen_now = aware(gregorian_date, hour, minute)
        with patch("supervisor.selectors.timezone.now", return_value=frozen_now):
            return SupervisorDashboardSelector(self.supervisor).attention_items()

    def test_session_registered_on_time_does_not_appear(self):
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, self.bell)
        make_session(
            self.class_subject,
            jdatetime.date.fromgregorian(date=self.TODAY),
        )

        # Well past the 15-minute deadline (08:45); the session already
        # exists, so nothing should be flagged.
        items = self._attention_items_at(self.TODAY, 9, 0)

        self.assertEqual(items, [])

    def test_session_registered_within_grace_period_does_not_appear(self):
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, self.bell)

        # No session registered yet, but we are still inside the grace
        # window (bell ended 08:30, deadline is 08:45).
        items = self._attention_items_at(self.TODAY, 8, 40)

        self.assertEqual(items, [])

    def test_session_not_registered_after_deadline_appears(self):
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, self.bell)

        items = self._attention_items_at(self.TODAY, 9, 0)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["class_subject_id"], self.class_subject.id)
        self.assertEqual(items[0]["title"], "جلسه ثبت نشده")

    def test_scheduled_class_on_another_weekday_does_not_appear(self):
        # Scheduled for Sunday, but "today" (frozen) is Saturday.
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SUNDAY, self.bell)

        items = self._attention_items_at(self.TODAY, 9, 0)

        self.assertEqual(items, [])

    def test_week_type_is_respected(self):
        # A second class_subject/schedule pair so the two week types
        # don't collide on the same schedule row.
        _, other_assignment = make_teacher(self.branch, self.year)
        other_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, other_class)
        other_class_subject = make_class_subject(
            other_class, make_subject(), other_assignment, WIDE_START, WIDE_END
        )

        make_schedule(
            self.class_subject,
            ClassSchedule.DayChoices.SATURDAY,
            self.bell,
            week_type=ClassSchedule.WeekTypeChoices.WEEK_ONE,
        )
        make_schedule(
            other_class_subject,
            ClassSchedule.DayChoices.SATURDAY,
            self.bell,
            week_type=ClassSchedule.WeekTypeChoices.WEEK_TWO,
        )

        # get_current_week_type() looks at the AcademicYear with
        # is_active=True and the latest start_date. Deactivate the
        # setUp() year (it can't just be deleted: SchoolClass/ClassSubject
        # rows PROTECT-reference it transitively) and add a dedicated one
        # whose start_date == TODAY (in jalali) => week index 0 => WEEK_ONE.
        self.year.is_active = False
        self.year.save(update_fields=["is_active"])

        make_academic_year(
            jdatetime.date.fromgregorian(date=self.TODAY),
            is_current=True,
            is_active=True,
        )

        week_one_items = self._attention_items_at(self.TODAY, 9, 0)
        week_one_ids = {item["class_subject_id"] for item in week_one_items}

        self.assertIn(self.class_subject.id, week_one_ids)
        self.assertNotIn(other_class_subject.id, week_one_ids)

        # A week later, same weekday => current week flips to WEEK_TWO.
        week_two_items = self._attention_items_at(self.NEXT_WEEK_SAME_DAY, 9, 0)
        week_two_ids = {item["class_subject_id"] for item in week_two_items}

        self.assertIn(other_class_subject.id, week_two_ids)
        self.assertNotIn(self.class_subject.id, week_two_ids)

    def test_canceled_session_does_not_appear_as_missing(self):
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, self.bell)
        make_session(
            self.class_subject,
            jdatetime.date.fromgregorian(date=self.TODAY),
            status=SchoolSession.Status.CANCELED,
        )

        items = self._attention_items_at(self.TODAY, 9, 0)

        self.assertEqual(items, [])

    def test_duplicate_schedule_occurrences_are_handled_correctly(self):
        # The same class_subject meets twice today, at two different
        # bells, both already overdue. Only one session was registered
        # for today: exactly one occurrence should be reported missing.
        second_bell = make_bell(time(9, 0), time(9, 30))

        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, self.bell)
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, second_bell)

        make_session(
            self.class_subject,
            jdatetime.date.fromgregorian(date=self.TODAY),
        )

        # Past both deadlines (08:45 and 09:45).
        items = self._attention_items_at(self.TODAY, 10, 0)

        matching = [
            item for item in items if item["class_subject_id"] == self.class_subject.id
        ]
        self.assertEqual(len(matching), 1)


class SupervisorDashboardViewTests(TestCase):
    """
    View/template level smoke tests: access control (items 2-4 of the
    manual test checklist) plus a basic check that the dashboard
    actually renders using the selector's data (items 1, 5-8).
    """

    def setUp(self):
        self.branch = make_branch()
        self.grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))
        self.supervisor = make_supervisor(self.branch, self.grade)
        self.url = reverse("supervisor:dashboard")

    def test_anonymous_user_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_non_supervisor_user_is_rejected(self):
        teacher_user = make_user(User.Roles.TEACHER)
        self.client.force_login(teacher_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_supervisor_can_load_own_dashboard(self):
        school_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, school_class)
        _, assignment = make_teacher(self.branch, self.year)
        class_subject = make_class_subject(
            school_class, make_subject(), assignment, WIDE_START, WIDE_END
        )
        make_session(class_subject, jdatetime.date(1402, 7, 1))

        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "supervisor/dashboard.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertEqual(response.context["summary"]["classes_count"], 1)
        self.assertContains(response, "داشبورد پشتیبان")

    def test_dashboard_only_shows_this_supervisors_data(self):
        # A second supervisor's class/session must not affect this
        # supervisor's rendered counters.
        other_supervisor = make_supervisor(make_branch(), make_grade())
        other_class = make_school_class(other_supervisor.branch, other_supervisor.grade, self.year)
        assign_class(other_supervisor, other_class)

        own_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, own_class)

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url)

        self.assertEqual(response.context["summary"]["classes_count"], 1)


class SupervisorAttentionListViewTests(TestCase):
    """
    View/template tests for the standalone "needs attention" page: access
    control, that it reuses the same selector data as the dashboard, and
    that the class filter narrows results without leaking other classes.
    """

    #: Saturday (see scheduling.utils.get_today_schedule_day's mapping).
    TODAY = date(2024, 1, 6)
    BELL_START = time(8, 0)
    BELL_END = time(8, 30)  # deadline = 08:45 (30 + 15 minute grace)

    def setUp(self):
        self.branch = make_branch()
        self.grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))
        self.supervisor = make_supervisor(self.branch, self.grade)
        self.url = reverse("supervisor:attention_list")

        self.class_a = make_school_class(self.branch, self.grade, self.year)
        self.class_b = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, self.class_a)
        assign_class(self.supervisor, self.class_b)

        _, assignment_a = make_teacher(self.branch, self.year)
        self.class_subject_a = make_class_subject(
            self.class_a, make_subject(), assignment_a, WIDE_START, WIDE_END
        )
        _, assignment_b = make_teacher(self.branch, self.year)
        self.class_subject_b = make_class_subject(
            self.class_b, make_subject(), assignment_b, WIDE_START, WIDE_END
        )

        self.bell = make_bell(self.BELL_START, self.BELL_END)
        make_schedule(self.class_subject_a, ClassSchedule.DayChoices.SATURDAY, self.bell)
        make_schedule(self.class_subject_b, ClassSchedule.DayChoices.SATURDAY, self.bell)

    def _get_at(self, gregorian_date, hour, minute, **query):
        frozen_now = aware(gregorian_date, hour, minute)
        with patch("supervisor.selectors.timezone.now", return_value=frozen_now):
            return self.client.get(self.url, query)

    def test_anonymous_user_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_non_supervisor_user_is_rejected(self):
        teacher_user = make_user(User.Roles.TEACHER)
        self.client.force_login(teacher_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_lists_all_overdue_items_in_scope(self):
        self.client.force_login(self.supervisor.user)

        response = self._get_at(self.TODAY, 9, 0)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "supervisor/attention_list.html")
        class_subject_ids = {
            item["class_subject_id"] for item in response.context["attention_items"]
        }
        self.assertEqual(
            class_subject_ids, {self.class_subject_a.id, self.class_subject_b.id}
        )

    def test_class_filter_narrows_to_selected_class(self):
        self.client.force_login(self.supervisor.user)

        response = self._get_at(self.TODAY, 9, 0, **{"class": self.class_a.id})

        class_subject_ids = {
            item["class_subject_id"] for item in response.context["attention_items"]
        }
        self.assertEqual(class_subject_ids, {self.class_subject_a.id})

    def test_class_filter_only_offers_supervisors_own_classes(self):
        other_supervisor = make_supervisor(make_branch(), make_grade())
        other_class = make_school_class(other_supervisor.branch, other_supervisor.grade, self.year)
        assign_class(other_supervisor, other_class)

        self.client.force_login(self.supervisor.user)
        response = self._get_at(self.TODAY, 9, 0)

        offered_class_ids = {c.id for c in response.context["classes"]}
        self.assertEqual(offered_class_ids, {self.class_a.id, self.class_b.id})


class SupervisorAttendanceViewTests(TestCase):
    """
    Attendance page, backed by ``SupervisorAttendanceSelector`` and real
    data end to end. Covers: access control, branch/scope isolation
    (items 1-3), summary counts (items 4-6), the phone-number
    visibility rule (items 7-9), the "no attendance yet" empty state
    (item 10), a tampered/foreign class_id not leaking another class's
    data (item 11), and that status/search are echoed for the
    toolbar's initial state without filtering the queryset (item 12 --
    the actual filtering is client-side, see attendance.js).
    """

    def setUp(self):
        self.branch = make_branch()
        self.other_branch = make_branch()
        self.grade = make_grade()
        self.year = make_academic_year(jdatetime.date(1402, 1, 1))
        self.supervisor = make_supervisor(self.branch, self.grade)
        self.url = reverse("supervisor:attendance")

        self.class_a = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, self.class_a)

        _, assignment = make_teacher(self.branch, self.year)
        self.class_subject = make_class_subject(
            self.class_a, make_subject(), assignment, WIDE_START, WIDE_END
        )
        self.session = make_session(self.class_subject, jdatetime.date(1402, 7, 10))

        self.student_present = make_student()
        self.student_absent = make_student()
        self.student_late = make_student()

        enrollment_present = make_enrollment(self.student_present, self.class_a)
        enrollment_absent = make_enrollment(self.student_absent, self.class_a)
        enrollment_late = make_enrollment(self.student_late, self.class_a)

        make_attendance(self.session, enrollment_present, Attendance.AttendanceStatus.PRESENT)
        make_attendance(self.session, enrollment_absent, Attendance.AttendanceStatus.ABSENT)
        make_attendance(self.session, enrollment_late, Attendance.AttendanceStatus.LATE)

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def test_anonymous_user_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_non_supervisor_user_is_rejected(self):
        teacher_user = make_user(User.Roles.TEACHER)
        self.client.force_login(teacher_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # Item 1: sees own assigned class
    # ------------------------------------------------------------------

    def test_supervisor_sees_own_assigned_class(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": self.class_a.id})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "supervisor/attendance.html")
        self.assertEqual(response.context["selected_class"], self.class_a)

    # ------------------------------------------------------------------
    # Item 2: cannot see a class in the same branch/grade that was
    # never assigned to them
    # ------------------------------------------------------------------

    def test_supervisor_cannot_see_unassigned_class(self):
        unassigned_class = make_school_class(self.branch, self.grade, self.year)

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url, {"class": unassigned_class.id})

        # Falls back to the one class actually in scope instead of the
        # requested (unauthorized) one.
        self.assertEqual(response.context["selected_class"], self.class_a)
        self.assertNotIn(unassigned_class, response.context["classes"])

    # ------------------------------------------------------------------
    # Item 3: cannot see another branch's class
    # ------------------------------------------------------------------

    def test_supervisor_cannot_see_other_branch_class(self):
        other_supervisor = make_supervisor(self.other_branch, make_grade())
        other_class = make_school_class(self.other_branch, other_supervisor.grade, self.year)
        assign_class(other_supervisor, other_class)

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url, {"class": other_class.id})

        self.assertEqual(response.context["selected_class"], self.class_a)
        self.assertNotIn(other_class, response.context["classes"])

    # ------------------------------------------------------------------
    # Items 4-6: summary counts
    # ------------------------------------------------------------------

    def test_summary_counts_are_correct(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": self.class_a.id})

        summary = response.context["summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["present"], 1)
        self.assertEqual(summary["absent"], 1)
        self.assertEqual(summary["late"], 1)

    # ------------------------------------------------------------------
    # Items 7-9: phone number visibility rule
    # ------------------------------------------------------------------

    def test_phone_number_shown_for_absent_student(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": self.class_a.id})

        self.assertContains(response, self.student_absent.user.phone_number)

    def test_phone_number_shown_for_late_student(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": self.class_a.id})

        self.assertContains(response, self.student_late.user.phone_number)

    def test_phone_number_not_shown_for_present_student(self):
        # Give the present student a distinctive phone number so its
        # absence from the page is unambiguous (rather than asserting
        # against an empty string, which is trivially "in" any page).
        self.student_present.user.phone_number = "09999999999"
        self.student_present.user.save(update_fields=["phone_number"])

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url, {"class": self.class_a.id})

        self.assertNotContains(response, "09999999999")

    # ------------------------------------------------------------------
    # Item 10: empty state for a class with no session registered yet
    # ------------------------------------------------------------------

    def test_class_with_no_session_shows_empty_state(self):
        empty_class = make_school_class(self.branch, self.grade, self.year)
        assign_class(self.supervisor, empty_class)

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url, {"class": empty_class.id})

        self.assertEqual(list(response.context["attendance_rows"]), [])
        self.assertContains(response, "هنوز حضور و غیابی ثبت نشده است")
        self.assertEqual(response.context["summary"]["total"], 0)

    # ------------------------------------------------------------------
    # Item 11: a nonexistent/tampered class_id can't be used to reach
    # another class's data -- it just falls back safely.
    # ------------------------------------------------------------------

    def test_nonexistent_class_id_falls_back_safely(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": 999999})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_class"], self.class_a)

    def test_non_numeric_class_id_falls_back_safely(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url, {"class": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_class"], self.class_a)

    # ------------------------------------------------------------------
    # Item 12: status/search are echoed back for the toolbar's initial
    # state, but never used to filter the queryset server-side.
    # ------------------------------------------------------------------

    def test_status_and_search_are_echoed_but_dont_filter_the_queryset(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(
            self.url,
            {"class": self.class_a.id, "status": "absent", "search": "زهرا"},
        )

        self.assertEqual(response.context["current_status"], "absent")
        self.assertEqual(response.context["search_query"], "زهرا")
        # All three rows are still in the context -- filtering happens
        # client-side, not in the queryset.
        self.assertEqual(len(response.context["attendance_rows"]), 3)

    # ------------------------------------------------------------------
    # "Latest session" business rule: a class can have more than one
    # class_subject (subject/teacher); the session shown is whichever
    # is most recently registered, not necessarily the first one.
    # ------------------------------------------------------------------

    def test_shows_attendance_for_the_most_recently_registered_session(self):
        _, other_assignment = make_teacher(self.branch, self.year)
        other_class_subject = make_class_subject(
            self.class_a, make_subject(), other_assignment, WIDE_START, WIDE_END
        )
        newer_session = make_session(other_class_subject, jdatetime.date(1402, 8, 1))
        newer_student = make_student()
        newer_enrollment = make_enrollment(newer_student, self.class_a)
        make_attendance(newer_session, newer_enrollment, Attendance.AttendanceStatus.PRESENT)

        self.client.force_login(self.supervisor.user)
        response = self.client.get(self.url, {"class": self.class_a.id})

        self.assertEqual(response.context["session"], newer_session)
        self.assertEqual(response.context["summary"]["total"], 1)

    # ------------------------------------------------------------------
    # Performance: no N+1. Query count must stay flat as the roster
    # grows -- select_related on attendance_rows() and the DB-side
    # aggregate in summary() are what make that true.
    # ------------------------------------------------------------------

    def test_query_count_does_not_grow_with_roster_size(self):
        self.client.force_login(self.supervisor.user)

        # BranchMiddleware caches the resolved branch in the session on
        # the very first authenticated request (an extra one-time
        # session write) and takes a slightly different query path once
        # that cache exists -- neither is related to this page or its
        # roster size, so warm it up before measuring.
        self.client.get(self.url, {"class": self.class_a.id})

        with CaptureQueriesContext(connection) as small_roster:
            self.client.get(self.url, {"class": self.class_a.id})

        for _ in range(15):
            student = make_student()
            enrollment = make_enrollment(student, self.class_a)
            make_attendance(self.session, enrollment, Attendance.AttendanceStatus.PRESENT)

        with CaptureQueriesContext(connection) as large_roster:
            self.client.get(self.url, {"class": self.class_a.id})

        self.assertEqual(
            len(small_roster.captured_queries),
            len(large_roster.captured_queries),
        )
