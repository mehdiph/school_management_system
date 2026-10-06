"""
The metric definitions of ``analytics`` (docs/apps/analytics.md), each
pinned by a test: what is an expected slot, what fills it, what is lost
to a closure, what is made up, the rates, and the teaching days and
comparison period.

The fixture: academic year 1405 (1 Mehr = Wednesday 23 Sep 2026), two
branches with one class each. ``math`` (branch A) has two bells every
Sunday, ``physics`` (branch B) one. Unless a test says otherwise,
metrics are computed as of Wednesday 15 Mehr (7 Oct) at noon, over the
year so far: the Sundays 5 and 12 Mehr.
"""

from datetime import date, datetime, time

import jdatetime
from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone

from academic_calendar import services as calendar
from attendance.models import Attendance
from core.testing import (
    make_academic_year,
    make_assignment,
    make_bell,
    make_branch,
    make_calendar_event,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_schedule,
    make_school_class,
    make_student,
    make_subject,
    make_teacher_profile,
)
from scheduling.models import ClassSchedule
from teaching.models import SchoolSession, SessionContent

from . import definitions, metrics, periods
from .engine import CONFLICT, FILLS, PENDING, compute
from .scope import AnalyticsScope, as_of_for

J = jdatetime.date
SUNDAY_1 = J(1405, 7, 5)        # 27 Sep
SUNDAY_2 = J(1405, 7, 12)       # 4 Oct
THURSDAY = J(1405, 7, 9)        # 1 Oct
WEDNESDAY = J(1405, 7, 15)      # 7 Oct


def at(day, hour=12, minute=0):
    day = day.togregorian() if isinstance(day, jdatetime.date) else day
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


AS_OF = at(WEDNESDAY)


class Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year = make_academic_year(J(1405, 7, 1), J(1406, 3, 31))
        cls.grade = make_grade()
        cls.branch_a = make_branch(order=1)
        cls.branch_b = make_branch(order=2)
        cls.class_a = make_school_class(cls.branch_a, cls.grade, cls.year)
        cls.class_b = make_school_class(cls.branch_b, cls.grade, cls.year)
        teacher = make_teacher_profile()
        cls.teacher = teacher
        cls.math = make_class_subject(
            cls.class_a, make_subject(), make_assignment(teacher, cls.branch_a, cls.year),
            J(1405, 7, 1), J(1406, 3, 31),
        )
        cls.physics_teacher = make_teacher_profile()
        cls.physics = make_class_subject(
            cls.class_b, make_subject(), make_assignment(cls.physics_teacher, cls.branch_b, cls.year),
            J(1405, 7, 1), J(1406, 3, 31),
        )
        cls.bell_1 = make_bell(1)       # 07:30-08:15
        cls.bell_2 = make_bell(2)       # 08:30-09:15
        cls.bell_3 = make_bell(3)
        make_schedule(cls.math, ClassSchedule.DayChoices.SUNDAY, cls.bell_1)
        make_schedule(cls.math, ClassSchedule.DayChoices.SUNDAY, cls.bell_2)
        make_schedule(cls.physics, ClassSchedule.DayChoices.SUNDAY, cls.bell_1)

    def scope(self, start=None, end=None, as_of=AS_OF, **kwargs):
        return AnalyticsScope.build(self.year, start, end, as_of=as_of, **kwargs)

    def total(self, scope=None, **kwargs):
        result = compute(scope or self.scope())
        return metrics.total(result, **kwargs)

    def session(self, class_subject, day, bell=None, status=SchoolSession.Status.HELD):
        return SchoolSession.objects.create(class_subject=class_subject, date=day, bell=bell, status=status)

    def content(self, session):
        SessionContent.objects.create(session=session, title="t", content="c", homework="ندارد")

    def closure(self, day, **scope):
        event = make_calendar_event(self.year, day, **scope)
        calendar.sync_cancelled_sessions(day, day)
        return event


class ExpectedSlotTests(Fixture):
    def test_every_bell_is_its_own_slot_and_nothing_recorded_is_unregistered(self):
        breakdown = self.total()

        # math: 2 Sundays x 2 bells, physics: 2 Sundays x 1 bell
        self.assertEqual(breakdown.expected, 6)
        self.assertEqual(breakdown.unregistered, 6)
        self.assertEqual(breakdown.execution_rate, 0)

    def test_held_cancelled_and_unregistered(self):
        self.session(self.math, SUNDAY_1, self.bell_1)
        self.session(self.math, SUNDAY_1, self.bell_2, SchoolSession.Status.CANCELED)

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual(
            (breakdown.expected, breakdown.held, breakdown.cancelled, breakdown.unregistered),
            (4, 1, 1, 2),
        )
        self.assertEqual(breakdown.execution_rate, 25)

    def test_a_legacy_session_without_bell_fills_the_first_free_bell(self):
        self.session(self.math, SUNDAY_1)                     # no bell

        result = compute(self.scope())
        outcomes = {(o.date, o.bell_id): o.outcome for o in result.outcomes if o.class_subject_id == self.math.pk}

        sunday = SUNDAY_1.togregorian()
        self.assertEqual(outcomes[(sunday, self.bell_1.pk)], "held")
        self.assertEqual(outcomes[(sunday, self.bell_2.pk)], "unregistered")

    def test_two_legacy_sessions_fill_both_bells_and_a_bell_session_keeps_its_own(self):
        self.session(self.math, SUNDAY_1, self.bell_1, SchoolSession.Status.CANCELED)
        self.session(self.math, SUNDAY_1)                     # takes bell 2, the free one
        self.session(self.math, SUNDAY_2)
        self.session(self.math, SUNDAY_2)

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual((breakdown.held, breakdown.cancelled, breakdown.unregistered), (3, 1, 0))

    def test_thursday_is_never_expected(self):
        # A legacy Thursday timetable row, written past the model's guard
        # (new ones are refused).
        schedule = make_schedule(self.math, ClassSchedule.DayChoices.SUNDAY, self.bell_3)
        QuerySet.update(
            ClassSchedule.objects.filter(pk=schedule.pk), day_of_week=ClassSchedule.DayChoices.THURSDAY
        )

        result = compute(self.scope())

        self.assertFalse([o for o in result.outcomes if o.date == THURSDAY.togregorian()])
        self.assertEqual(metrics.total(result).expected, 6)

    def test_future_dates_are_never_expected(self):
        scope = self.scope(end=J(1406, 3, 31))

        self.assertEqual(scope.end, AS_OF.date())
        self.assertEqual(self.total(scope).expected, 6)

        # As of Saturday 11 Mehr only the first Sunday has passed.
        self.assertEqual(self.total(self.scope(as_of=at(J(1405, 7, 11)))).expected, 3)

    def test_a_slot_of_today_is_expected_once_its_bell_ended_plus_the_grace(self):
        def expected(hour, minute):
            return self.total(self.scope(as_of=at(SUNDAY_2, hour, minute))).expected

        # bell 1 ends 08:15 -> expected from 08:30; bell 2 ends 09:15 -> 09:30
        self.assertEqual(expected(8, 29), 3)        # only the first Sunday
        self.assertEqual(expected(8, 30), 5)        # + bell 1 of math and physics
        self.assertEqual(expected(9, 30), 6)

    def test_a_session_recorded_in_a_slot_not_over_yet_is_pending(self):
        session = self.session(self.math, SUNDAY_2, self.bell_2, SchoolSession.Status.COMPENSATORY)

        result = compute(self.scope(as_of=at(SUNDAY_2, 9)))
        row = next(r for r in result.sessions if r.pk == session.pk)
        breakdown = metrics.total(result)

        self.assertEqual(row.role, PENDING)
        self.assertEqual((breakdown.compensatory, breakdown.outside_timetable), (0, 0))
        self.assertEqual(breakdown.delivered, 1)

    def test_as_of_for_a_past_day_is_the_end_of_that_day(self):
        self.assertEqual(as_of_for(date(2026, 9, 27)).time(), time.max)
        self.assertEqual(as_of_for(None).date(), timezone.localdate())


class ClosureTests(Fixture):
    def test_a_closed_slot_is_not_expected_and_its_holiday_is_lost_to_the_closure(self):
        self.closure(SUNDAY_2)

        breakdown = self.total()

        self.assertEqual(breakdown.expected, 3)          # the first Sunday only
        self.assertEqual(breakdown.lost_to_closures, 3)  # 2 math bells + 1 physics
        self.assertEqual(breakdown.unregistered, 3)

    def test_a_branch_closure_affects_only_that_branch(self):
        self.closure(SUNDAY_2, branches=[self.branch_a])

        by_branch = metrics.breakdowns(compute(self.scope()), metrics.by_branch)

        self.assertEqual((by_branch[self.branch_a.pk].expected, by_branch[self.branch_a.pk].lost_to_closures), (2, 2))
        self.assertEqual((by_branch[self.branch_b.pk].expected, by_branch[self.branch_b.pk].lost_to_closures), (2, 0))

    def test_a_partial_closure_closes_only_its_bells(self):
        self.closure(SUNDAY_2, bells=[self.bell_2])

        breakdown = self.total()

        self.assertEqual((breakdown.expected, breakdown.lost_to_closures), (5, 1))

    def test_a_session_recorded_in_a_closed_slot_is_a_conflict_not_held(self):
        held = self.session(self.math, SUNDAY_2, self.bell_1)
        self.closure(SUNDAY_2, branches=[self.branch_a])     # keeps the held session

        result = compute(self.scope())
        breakdown = metrics.total(result, where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual([c.session.pk for c in result.conflicts], [held.pk])
        self.assertEqual(next(r for r in result.sessions if r.pk == held.pk).role, CONFLICT)
        self.assertEqual((breakdown.expected, breakdown.held, breakdown.conflicts), (2, 0, 1))
        self.assertEqual(breakdown.lost_to_closures, 1)      # bell 2 only
        self.assertEqual(breakdown.delivered, 1)             # it was still taught

    def test_a_holiday_left_on_a_reopened_slot_is_still_not_expected(self):
        event = self.closure(SUNDAY_2, branches=[self.branch_a])
        type(event).objects.filter(pk=event.pk).update(is_active=False)   # no sync

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual((breakdown.expected, breakdown.lost_to_closures), (2, 2))


class CompensatoryTests(Fixture):
    def test_compensatory_sessions_are_not_expected_and_feed_makeup_coverage(self):
        self.closure(SUNDAY_2, branches=[self.branch_a])                        # 2 HL
        self.session(self.math, SUNDAY_1, self.bell_1, SchoolSession.Status.CANCELED)  # 1 CD
        self.session(self.math, THURSDAY, self.bell_1, SchoolSession.Status.COMPENSATORY)
        self.session(self.math, J(1405, 7, 14), self.bell_3, SchoolSession.Status.COMPENSATORY)

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual(breakdown.expected, 2)
        self.assertEqual(breakdown.compensatory, 2)
        self.assertEqual(round(breakdown.makeup_coverage), 67)     # 2 / (2 HL + 1 CD)
        self.assertEqual(breakdown.delivered, 2)

    def test_a_compensatory_session_in_an_expected_slot_counts_as_held(self):
        session = self.session(self.math, SUNDAY_1, self.bell_1, SchoolSession.Status.COMPENSATORY)

        result = compute(self.scope())
        breakdown = metrics.total(result, where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual(next(r for r in result.sessions if r.pk == session.pk).role, FILLS)
        self.assertEqual((breakdown.held, breakdown.compensatory), (1, 0))
        self.assertIsNone(breakdown.makeup_coverage)              # nothing lost

    def test_held_sessions_outside_the_timetable_are_counted_apart(self):
        self.session(self.math, SUNDAY_1, self.bell_3)            # no slot at bell 3

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual((breakdown.held, breakdown.outside_timetable, breakdown.delivered), (0, 1, 1))


class ContentAndAttendanceTests(Fixture):
    def test_content_and_attendance_rates(self):
        held = self.session(self.math, SUNDAY_1, self.bell_1)
        compensatory = self.session(self.math, THURSDAY, self.bell_1, SchoolSession.Status.COMPENSATORY)
        cancelled = self.session(self.math, SUNDAY_1, self.bell_2, SchoolSession.Status.CANCELED)
        self.content(held)
        self.content(cancelled)             # never part of the content rate

        students = [make_enrollment(make_student(), self.class_a) for _ in range(3)]
        statuses = [Attendance.AttendanceStatus.PRESENT, Attendance.AttendanceStatus.LATE,
                    Attendance.AttendanceStatus.ABSENT]
        for enrollment, status in zip(students, statuses):
            Attendance.objects.create(session=held, student_enrollment=enrollment, status=status)
        Attendance.objects.create(
            session=cancelled, student_enrollment=students[0], status=Attendance.AttendanceStatus.ABSENT
        )

        breakdown = self.total(where=lambda cs: cs.pk == self.math.pk)

        self.assertEqual(breakdown.delivered, 2)
        self.assertEqual(breakdown.content_rate, 50)
        self.assertEqual(breakdown.attendance_recorded_rate, 50)
        self.assertEqual((breakdown.attendance_total, breakdown.absent, breakdown.late), (3, 1, 1))
        self.assertEqual(round(breakdown.attendance_rate), 67)       # present + late
        self.assertEqual(round(breakdown.late_rate), 33)
        self.assertEqual(compensatory.status, "JB")

    def test_rates_without_data_are_none(self):
        breakdown = metrics.Breakdown()

        for name in ("execution_rate", "makeup_coverage", "content_rate",
                     "attendance_recorded_rate", "attendance_rate", "late_rate"):
            self.assertIsNone(getattr(breakdown, name), name)

    def test_the_queryset_and_the_engine_agree(self):
        session = self.session(self.math, SUNDAY_1, self.bell_1)
        for status in (Attendance.AttendanceStatus.PRESENT, Attendance.AttendanceStatus.LATE,
                       Attendance.AttendanceStatus.ABSENT, Attendance.AttendanceStatus.ABSENT):
            Attendance.objects.create(
                session=session, student_enrollment=make_enrollment(make_student(), self.class_a),
                status=status,
            )

        counts = Attendance.objects.delivered().status_counts()

        self.assertEqual(counts["rate"], definitions.rounded(self.total().attendance_rate))
        self.assertEqual(counts["rate"], 50)


class GroupingTests(Fixture):
    def test_breakdowns_by_branch_teacher_and_day_add_up(self):
        self.session(self.math, SUNDAY_1, self.bell_1)
        self.session(self.physics, SUNDAY_2, self.bell_1)
        result = compute(self.scope())

        by_branch = metrics.breakdowns(result, metrics.by_branch)
        by_day = metrics.breakdowns(result, metrics.by_day)
        by_teacher = metrics.breakdowns(result, metrics.by_teacher)

        self.assertEqual(sum((b for b in by_branch.values()), metrics.Breakdown()), metrics.total(result))
        self.assertEqual(sorted(by_day), [SUNDAY_1.togregorian(), SUNDAY_2.togregorian()])
        self.assertEqual(by_teacher[self.teacher.pk].held, 1)
        self.assertEqual(by_teacher[self.physics_teacher.pk].held, 1)

    def test_a_date_window_narrows_slots_and_sessions(self):
        self.session(self.math, SUNDAY_1, self.bell_1)
        result = compute(self.scope())

        second = SUNDAY_2.togregorian()
        breakdown = metrics.total(result, start=second, end=second)

        self.assertEqual((breakdown.expected, breakdown.held), (3, 0))

    def test_a_scope_of_explicit_class_subjects(self):
        breakdown = self.total(self.scope(class_subjects=[self.physics]))

        self.assertEqual(breakdown.expected, 2)


class PeriodTests(Fixture):
    def closures(self):
        return calendar.Closures.between(self.year.start_date, self.year.end_date, academic_year=self.year)

    def units(self, branches=None):
        branches = branches or [self.branch_a, self.branch_b]
        return periods.units(self.year, [b.pk for b in branches], [self.grade.pk])

    def test_teaching_days_skip_thursday_friday_and_full_day_closures(self):
        days = periods.teaching_days(self.year, J(1405, 7, 1), WEDNESDAY, self.closures(), self.units())

        # 1 Mehr (Wed), then two Saturday..Wednesday weeks
        self.assertEqual(len(days), 11)
        self.assertNotIn(THURSDAY.togregorian(), days)

    def test_a_branch_closure_removes_the_day_for_that_branch_only(self):
        make_calendar_event(self.year, SUNDAY_2, branches=[self.branch_a])
        make_calendar_event(self.year, J(1405, 7, 13), bells=[self.bell_2])   # partial: no effect
        closures = self.closures()

        def count(branches=None):
            return len(periods.teaching_days(self.year, J(1405, 7, 1), WEDNESDAY, closures, self.units(branches)))

        self.assertEqual(count([self.branch_a]), 10)
        self.assertEqual(count([self.branch_b]), 11)
        self.assertEqual(count(), 11)        # branch B is open: still a school day
        self.assertEqual(
            periods.closed_days(self.year, J(1405, 7, 1), WEDNESDAY, closures, self.units([self.branch_a])),
            [SUNDAY_2.togregorian()],
        )

    def test_the_previous_period_has_as_many_teaching_days(self):
        closures = self.closures()

        # Sat 11 .. Wed 15 Mehr: 5 days -> Sat 4 .. Wed 8 Mehr
        self.assertEqual(
            periods.previous_period(self.year, J(1405, 7, 11).togregorian(), WEDNESDAY.togregorian(), closures, self.units()),
            (J(1405, 7, 4).togregorian(), J(1405, 7, 8).togregorian(), True),
        )

        # A closure in the previous week pushes it back past the weekend.
        make_calendar_event(self.year, J(1405, 7, 6))
        self.assertEqual(
            periods.previous_period(self.year, J(1405, 7, 11).togregorian(), WEDNESDAY.togregorian(), self.closures(), self.units()),
            (J(1405, 7, 1).togregorian(), J(1405, 7, 8).togregorian(), True),
        )

    def test_the_previous_period_is_incomplete_at_the_start_of_the_year(self):
        start, end, complete = periods.previous_period(
            self.year, J(1405, 7, 4).togregorian(), WEDNESDAY.togregorian(), self.closures(), self.units()
        )

        self.assertEqual((start, end, complete), (J(1405, 7, 1).togregorian(), J(1405, 7, 1).togregorian(), False))
        self.assertIsNone(periods.previous_period(
            self.year, J(1405, 7, 1).togregorian(), J(1405, 7, 1).togregorian(), self.closures(), self.units()
        ))

    def test_presets(self):
        today = WEDNESDAY.togregorian()

        self.assertEqual(periods.period_range(periods.TODAY, today, self.year), (today, today))
        self.assertEqual(periods.period_range(periods.WEEK, today, self.year), (J(1405, 7, 11).togregorian(), today))
        self.assertEqual(periods.period_range(periods.MONTH, today, self.year), (J(1405, 7, 1).togregorian(), today))
        self.assertEqual(periods.period_range(periods.YEAR, today, self.year), (J(1405, 7, 1).togregorian(), today))
        self.assertIsNone(periods.period_range(periods.CUSTOM, today, self.year))
