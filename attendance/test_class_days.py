"""
``attendance.services.class_day_statuses``: which classes were due to take
their daily attendance on which days, and which did -- what the director's
panel shows. Pinned against the two places that already answered parts of
that question, so there is still one rule:

* the supervisor's daily overview (recorded / missing / closed / no
  lessons, without a grace), and
* the analytics engine's expected class-days (a day is expected once its
  first open bell is over plus the registration grace).

Also: ``planned_class_days`` with preloaded closures, the readers with a
queryset of enrollments, and ``supervisor.selectors.class_supervisors``.

The fixture is ``analytics.tests.Fixture`` (class A in branch A has math at
bells 1 and 2 on Sundays, class B in branch B physics at bell 1; bell 1
ends at 08:15, bell 2 at 09:15) with daily attendance from Sunday 12 Mehr.
"""

from datetime import timedelta

from academic_calendar import services as calendar
from accounts.models import User
from analytics.engine import compute
from analytics.tests import DAILY_FROM_SUNDAY_2, SUNDAY_1, SUNDAY_2, Fixture, J, at
from attendance import services
from attendance.models import DailyAttendanceSheet
from attendance.services import ClassDay
from core.testing import make_grade, make_supervisor, make_user
from student.models.student_enrollment import StudentEnrollment
from supervisor.models import SupervisorClass
from supervisor.selectors import SupervisorAttendanceSelector, class_supervisors

MONDAY = J(1405, 7, 13)         # no lesson in the timetable
WEDNESDAY = J(1405, 7, 15)
THURSDAY = J(1405, 7, 16)
FRIDAY = J(1405, 7, 17)


@DAILY_FROM_SUNDAY_2
class ClassDayStatusTests(Fixture):
    def statuses(self, start, end, as_of, classes=None):
        days = services.class_day_statuses(start, end, classes or [self.class_a, self.class_b], as_of)
        return {(class_id, J.fromgregorian(date=day)): row.status for (class_id, day), row in days.items()}

    def test_due_today_is_pending_until_the_first_bell_is_over_plus_the_grace(self):
        # bell 1 ends at 08:15: due from 08:30
        for hour, minute, expected in ((8, 0, ClassDay.PENDING), (8, 29, ClassDay.PENDING),
                                       (8, 30, ClassDay.MISSING), (13, 0, ClassDay.MISSING)):
            with self.subTest(time=f"{hour}:{minute}"):
                self.assertEqual(
                    self.statuses(SUNDAY_2, SUNDAY_2, at(SUNDAY_2, hour, minute)),
                    {(self.class_a.pk, SUNDAY_2): expected, (self.class_b.pk, SUNDAY_2): expected},
                )

    def test_a_sheet_is_recorded_at_once_with_its_counts(self):
        self.daily(self.class_a, SUNDAY_2, "absent", "excused", "late", "present")

        days = services.class_day_statuses(SUNDAY_2, SUNDAY_2, [self.class_a], at(SUNDAY_2, 8, 0))
        day = days[(self.class_a.pk, SUNDAY_2.togregorian())]

        self.assertEqual(day.status, ClassDay.RECORDED)
        self.assertEqual((day.total, day.absent, day.excused, day.late, day.absences), (4, 1, 1, 1, 2))

    def test_a_partial_closure_waits_for_the_first_open_bell(self):
        # class A's bell 1 is closed: its first open bell (2) ends at 09:15
        self.closure(SUNDAY_2, branches=[self.branch_a], bells=[self.bell_1])

        at_nine = self.statuses(SUNDAY_2, SUNDAY_2, at(SUNDAY_2, 9, 0))
        at_half_past = self.statuses(SUNDAY_2, SUNDAY_2, at(SUNDAY_2, 9, 30))

        self.assertEqual(at_nine[(self.class_a.pk, SUNDAY_2)], ClassDay.PENDING)
        self.assertEqual(at_nine[(self.class_b.pk, SUNDAY_2)], ClassDay.MISSING)
        self.assertEqual(at_half_past[(self.class_a.pk, SUNDAY_2)], ClassDay.MISSING)

    def test_a_full_closure(self):
        event = self.closure(SUNDAY_2, branches=[self.branch_b])

        days = services.class_day_statuses(SUNDAY_2, SUNDAY_2, [self.class_a, self.class_b], at(WEDNESDAY))

        self.assertEqual(days[(self.class_b.pk, SUNDAY_2.togregorian())].status, ClassDay.CLOSED)
        self.assertEqual(days[(self.class_b.pk, SUNDAY_2.togregorian())].closure, event)
        self.assertFalse(days[(self.class_b.pk, SUNDAY_2.togregorian())].is_due)
        self.assertEqual(days[(self.class_a.pk, SUNDAY_2.togregorian())].status, ClassDay.MISSING)

    def test_days_without_lessons_thursday_and_friday_are_not_listed(self):
        for day in (MONDAY, THURSDAY, FRIDAY):
            with self.subTest(day=day):
                self.assertEqual(self.statuses(day, day, at(day, 13)), {})

    def test_a_past_day_has_no_grace(self):
        self.assertEqual(
            set(self.statuses(SUNDAY_2, WEDNESDAY, at(WEDNESDAY, 7, 0)).values()), {ClassDay.MISSING},
        )

    def test_the_range_is_clamped_to_the_cutoff_and_to_today(self):
        # a sheet before the cutoff (refused by the model; bulk_create skips it) is never read
        DailyAttendanceSheet.objects.bulk_create([DailyAttendanceSheet(
            school_class=self.class_a, date=SUNDAY_1, taken_by=make_user(User.Roles.SUPERVISOR),
        )])

        statuses = self.statuses(SUNDAY_1, J(1405, 7, 26), at(WEDNESDAY))

        self.assertEqual({day for _, day in statuses}, {SUNDAY_2})
        self.assertEqual(self.statuses(SUNDAY_1, SUNDAY_1 + timedelta(days=3), at(WEDNESDAY)), {})

    def test_no_classes(self):
        self.assertEqual(services.class_day_statuses(SUNDAY_2, SUNDAY_2, [], at(WEDNESDAY)), {})

    def test_agrees_with_the_supervisors_overview(self):
        """Without the grace (end of day), the same statuses as the supporter sees."""

        supervisor_a = make_supervisor(self.branch_a, self.grade)
        supervisor_b = make_supervisor(self.branch_b, self.grade)
        SupervisorClass.objects.create(supervisor=supervisor_a, school_class=self.class_a)
        SupervisorClass.objects.create(supervisor=supervisor_b, school_class=self.class_b)
        self.daily(self.class_a, SUNDAY_2, "absent")
        self.closure(J(1405, 7, 19), branches=[self.branch_b])
        overview_status = {"recorded": ClassDay.RECORDED, "missing": ClassDay.MISSING,
                           "closed": ClassDay.CLOSED, "no_lessons": None}

        for day in (SUNDAY_2, MONDAY, J(1405, 7, 19)):
            as_of = at(day, 23, 59)
            mine = self.statuses(day, day, as_of)
            for supervisor in (supervisor_a, supervisor_b):
                for row in SupervisorAttendanceSelector(supervisor, today=day.togregorian()).overview(
                    day.togregorian()
                ):
                    with self.subTest(day=day, school_class=row.school_class.pk):
                        self.assertEqual(mine.get((row.school_class.pk, day)), overview_status[row.status])

    def test_agrees_with_the_engines_expected_class_days(self):
        """Missing = the engine's expected class-days without a sheet, at every moment of the day."""

        self.closure(SUNDAY_2, branches=[self.branch_a], bells=[self.bell_1])
        self.daily(self.class_b, SUNDAY_1 + timedelta(days=14), "absent")    # Sunday 19, later

        for as_of in (at(SUNDAY_2, 8, 0), at(SUNDAY_2, 8, 30), at(SUNDAY_2, 9, 15), at(SUNDAY_2, 9, 30),
                      at(WEDNESDAY), at(J(1405, 7, 19), 8, 45)):
            with self.subTest(as_of=as_of):
                result = compute(self.scope(SUNDAY_2, J(1405, 7, 19), as_of=as_of))
                engine_missing = {(r.school_class_id, r.date) for r in result.class_days
                                  if r.expected and not r.has_sheet}
                engine_recorded = {(r.school_class_id, r.date) for r in result.class_days if r.has_sheet}

                days = services.class_day_statuses(
                    SUNDAY_2, J(1405, 7, 19), [self.class_a, self.class_b], as_of,
                )
                self.assertEqual({k for k, d in days.items() if d.status == ClassDay.MISSING}, engine_missing)
                self.assertEqual({k for k, d in days.items() if d.status == ClassDay.RECORDED}, engine_recorded)


@DAILY_FROM_SUNDAY_2
class PlannedClassDaysTests(Fixture):
    def test_preloaded_closures_give_the_same_days(self):
        event = self.closure(SUNDAY_2, branches=[self.branch_b])
        classes = [self.class_a.pk, self.class_b.pk]
        closures = calendar.Closures.between(SUNDAY_2, J(1405, 7, 19))

        self.assertEqual(
            services.planned_class_days(SUNDAY_2, J(1405, 7, 19), classes, closures),
            services.planned_class_days(SUNDAY_2, J(1405, 7, 19), classes),
        )
        self.assertEqual(services.planned_class_days(SUNDAY_2, SUNDAY_2, classes)[
            (self.class_b.pk, SUNDAY_2.togregorian())], event)

    def test_a_day_is_open_when_any_of_its_bells_is(self):
        self.closure(SUNDAY_2, bells=[self.bell_1])

        days = services.planned_class_days(SUNDAY_2, SUNDAY_2, [self.class_a.pk, self.class_b.pk])

        self.assertIsNone(days[(self.class_a.pk, SUNDAY_2.togregorian())])         # bell 2 is open
        self.assertIsNotNone(days[(self.class_b.pk, SUNDAY_2.togregorian())])      # its only bell closed


@DAILY_FROM_SUNDAY_2
class EnrollmentTargetTests(Fixture):
    def test_readers_accept_a_queryset_of_enrollments(self):
        sheet = self.daily(self.class_a, SUNDAY_2, "absent", "late", "present")
        listed, late, _ = [record.student_enrollment for record in sheet.records.order_by("pk")]
        enrollments = StudentEnrollment.objects.filter(pk__in=[listed.pk, late.pk])

        records = services.get_absences(enrollments, SUNDAY_1, SUNDAY_2)
        tallies = services.student_tallies(enrollments, SUNDAY_1, SUNDAY_2)

        self.assertEqual({(r.student_enrollment, r.status) for r in records},
                         {(listed, "absent"), (late, "late")})
        self.assertEqual(set(tallies), {listed.pk, late.pk})
        self.assertEqual(services.attendance_counts(enrollments, SUNDAY_2, SUNDAY_2)["total"], 2)


class ClassSupervisorsTests(Fixture):
    def name(self, profile, first, last):
        profile.user.first_name, profile.user.last_name = first, last
        profile.user.save()
        return profile

    def test_the_supporters_of_each_class(self):
        second = self.name(make_supervisor(self.branch_a, self.grade), "مریم", "کریمی")
        first = self.name(make_supervisor(self.branch_a, self.grade), "زهرا", "احمدی")
        inactive = make_supervisor(self.branch_a, self.grade)
        inactive.user.is_active = False
        inactive.user.save()
        other_grade = make_supervisor(self.branch_a, make_grade())
        for supervisor in (second, first, inactive):
            SupervisorClass.objects.create(supervisor=supervisor, school_class=self.class_a)
        # bypasses clean(): an assignment SupervisorScope would not honour
        SupervisorClass.objects.create(supervisor=other_grade, school_class=self.class_a)

        supervisors = class_supervisors([self.class_a.pk, self.class_b.pk])

        self.assertEqual(supervisors, {self.class_a.pk: [first, second]})

    def test_the_same_classes_as_the_supervisors_scope(self):
        supervisor = make_supervisor(self.branch_a, self.grade)
        SupervisorClass.objects.create(supervisor=supervisor, school_class=self.class_a)
        wrong_branch = make_supervisor(self.branch_b, self.grade)
        SupervisorClass.objects.create(supervisor=wrong_branch, school_class=self.class_a)

        supervisors = class_supervisors([self.class_a.pk])

        self.assertEqual(supervisors, {self.class_a.pk: [supervisor]})
        self.assertNotIn(self.class_a, SupervisorAttendanceSelector(wrong_branch).scope.classes())
