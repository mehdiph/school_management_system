"""
Tests for the academic calendar service (academic_calendar.services), its
timetable signals and its management commands.

Calendar used throughout (academic year 1405/07/01 = Wed 2026-09-23):

* rotation week 1 ("هفته اول"): 1405/07/01 .. 07/10 (the partial first
  days are merged into the first full week), week 2: 07/11 .. 07/17,
  week 1 again: 07/18 .. 07/24, week 2: 07/25 .. 07/30 (Mehr has 30 days);
* 07/12 is a Sunday, 07/16 a Thursday, 07/17 a Friday, 07/18 a Saturday.
"""

import csv
import io
import tempfile
from datetime import date

import jdatetime
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import QuerySet
from django.test import TestCase

from academic_calendar import services
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

J = jdatetime.date
Day = ClassSchedule.DayChoices
Week = ClassSchedule.WeekTypeChoices

SUNDAY = J(1405, 7, 12)      # rotation week 2
THURSDAY = J(1405, 7, 16)
FRIDAY = J(1405, 7, 17)
SATURDAY = J(1405, 7, 18)    # rotation week 1


class CalendarTestCase(TestCase):

    def setUp(self):
        self.year = make_academic_year(start_date=J(1405, 7, 1), end_date=J(1406, 6, 31))
        self.branch = make_branch()
        self.grade = make_grade()
        self.teacher = make_teacher_profile()
        self.assignment = make_assignment(self.teacher, self.branch, self.year)
        self.school_class = make_school_class(self.branch, self.grade, self.year)
        self.math = self.class_subject()
        self.bell_1, self.bell_2, self.bell_3 = make_bell(1), make_bell(2), make_bell(3)

    def class_subject(self, school_class=None, start=J(1405, 7, 1), end=J(1406, 3, 31)):
        return make_class_subject(
            school_class or self.school_class, make_subject(), self.assignment,
            start_date=start, end_date=end,
        )

    def event(self, start, end=None, **kwargs):
        return make_calendar_event(self.year, start, end, **kwargs)

    def sync(self, start=J(1405, 7, 1), end=J(1405, 7, 30), **kwargs):
        return services.sync_cancelled_sessions(start, end, **kwargs)

    def holidays(self, **filters):
        return sorted(
            (s.class_subject_id, s.date, s.bell.order)
            for s in SchoolSession.objects.holidays().filter(**filters).select_related('bell')
        )


class WorkingDayTests(CalendarTestCase):

    def test_thursday_friday_and_outside_the_year_are_not_working_days(self):
        self.assertTrue(services.is_working_day(SUNDAY))
        self.assertTrue(services.is_working_day(SATURDAY, academic_year=self.year))
        self.assertFalse(services.is_working_day(THURSDAY))
        self.assertFalse(services.is_working_day(FRIDAY))
        self.assertFalse(services.is_working_day(J(1405, 6, 30)))       # before the year
        self.assertFalse(services.is_working_day(SUNDAY.togregorian().replace(year=2030)))

    def test_week_type_follows_the_rotation(self):
        self.assertEqual(services.get_week_type(J(1405, 7, 5)), Week.WEEK_ONE)
        self.assertEqual(services.get_week_type(SUNDAY), Week.WEEK_TWO)
        self.assertEqual(services.get_week_type(SATURDAY), Week.WEEK_ONE)
        self.assertIsNone(services.get_week_type(J(1405, 6, 1)))

    def test_parse_jalali_date(self):
        self.assertEqual(services.parse_jalali_date('۱۴۰۵/۰۷/۱۲'), SUNDAY)
        self.assertEqual(services.parse_jalali_date('1405-7-12'), SUNDAY)
        for bad in ('', '1405/13/01', '1405/07', 'فردا'):
            with self.assertRaises(ValueError):
                services.parse_jalali_date(bad)


class ClosureTests(CalendarTestCase):

    def test_scope_branch_grade_and_bell(self):
        other_branch_class = make_school_class(make_branch(), self.grade, self.year)
        other_grade_class = make_school_class(self.branch, make_grade(), self.year)

        self.event(SUNDAY, branches=[self.branch], grades=[self.grade], bells=[self.bell_3])

        self.assertTrue(services.is_closed(SUNDAY, self.school_class, self.bell_3))
        self.assertFalse(services.is_closed(SUNDAY, self.school_class, self.bell_1))
        # a bell scope is not a whole-day closure
        self.assertFalse(services.is_closed(SUNDAY, self.school_class))
        self.assertFalse(services.is_closed(SUNDAY, other_branch_class, self.bell_3))
        self.assertFalse(services.is_closed(SUNDAY, other_grade_class, self.bell_3))

    def test_empty_scope_means_everything(self):
        self.event(SUNDAY)
        other = make_school_class(make_branch(), make_grade(), self.year)

        self.assertTrue(services.is_closed(SUNDAY, other))
        self.assertTrue(services.is_closed(SUNDAY, other, self.bell_2))

    def test_inactive_events_and_other_years_do_not_close(self):
        self.event(SUNDAY, is_active=False)
        later_year = make_academic_year(start_date=J(1406, 7, 1), is_current=False)
        make_calendar_event(later_year, J(1406, 7, 5))

        self.assertFalse(services.is_closed(SUNDAY, self.school_class))

    def test_events_have_no_effect_on_thursday_and_friday(self):
        event = self.event(SUNDAY, SATURDAY)

        self.assertEqual(services.closing_event(J(1405, 7, 15), self.school_class), event)
        self.assertFalse(services.is_closed(THURSDAY, self.school_class))
        self.assertFalse(services.is_closed(FRIDAY, self.school_class))
        self.assertEqual(
            services.Closures([event]).days(),
            [d.togregorian() for d in (SUNDAY, J(1405, 7, 13), J(1405, 7, 14), J(1405, 7, 15), SATURDAY)],
        )

    def test_get_events_filters_scope(self):
        mine = self.event(SUNDAY, branches=[self.branch])
        everyone = self.event(SUNDAY)
        self.event(SUNDAY, branches=[make_branch()])

        self.assertEqual(
            list(services.get_events(SUNDAY, SUNDAY, branch=self.branch)), [mine, everyone]
        )


class SlotTests(CalendarTestCase):

    def test_slots_follow_weekday_week_type_and_teaching_window(self):
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SATURDAY, self.bell_2, Week.WEEK_TWO)
        ended = self.class_subject(end=J(1405, 7, 11))
        make_schedule(ended, Day.SUNDAY, self.bell_2)

        slots = services.get_slots(SUNDAY, SATURDAY)

        self.assertEqual(
            [(s.class_subject, s.date, s.bell) for s in slots],
            [(self.math, SUNDAY.togregorian(), self.bell_1)],
        )
        # Saturday 07/11 is week 2: the week-2 slot is there
        self.assertEqual(
            [(s.date, s.bell) for s in services.get_slots(J(1405, 7, 11), J(1405, 7, 11))],
            [(date(2026, 10, 3), self.bell_2)],
        )

    def test_inactive_class_subject_class_and_bell_have_no_slots(self):
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        self.math.is_active = False
        self.math.save()

        self.assertEqual(services.get_slots(SUNDAY, SUNDAY), [])


class SyncTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SUNDAY, self.bell_2)

    def test_same_subject_two_bells_gives_two_holiday_sessions(self):
        event = self.event(SUNDAY)

        result = self.sync()

        self.assertEqual(result.created, 2)
        self.assertEqual(self.holidays(), [(self.math.pk, SUNDAY, 1), (self.math.pk, SUNDAY, 2)])
        session = SchoolSession.objects.holidays().first()
        self.assertEqual(session.calendar_event, event)
        self.assertTrue(session.is_auto_created)
        self.assertIsNone(session.session_number)

    def test_sync_is_idempotent(self):
        self.event(SUNDAY)
        self.sync()

        again = self.sync()

        self.assertEqual((again.created, again.removed, again.updated), (0, 0, 0))
        self.assertEqual(SchoolSession.objects.count(), 2)

    def test_range_over_thursday_and_friday_skips_them(self):
        thursday_cs = self.class_subject()
        make_schedule(thursday_cs, Day.SATURDAY, self.bell_1)
        # a legacy Thursday slot, written past the model's guard
        QuerySet.update(ClassSchedule.objects.filter(class_subject=thursday_cs), day_of_week=Day.THURSDAY)
        self.event(SUNDAY, SATURDAY)

        self.sync()

        days = {d for _, d, _ in self.holidays()}
        self.assertEqual(days, {SUNDAY})   # math has Sunday slots only
        self.assertFalse(SchoolSession.objects.filter(class_subject=thursday_cs).exists())

    def test_bell_scope_closes_only_those_bells(self):
        self.event(SUNDAY, bells=[self.bell_2])

        self.sync()

        self.assertEqual(self.holidays(), [(self.math.pk, SUNDAY, 2)])

    def test_branch_and_grade_scope(self):
        other_class = make_school_class(make_branch(), self.grade, self.year)
        other = self.class_subject(school_class=other_class)
        make_schedule(other, Day.SUNDAY, self.bell_3)
        self.event(SUNDAY, branches=[other_class.branch])

        self.sync()

        self.assertEqual(self.holidays(), [(other.pk, SUNDAY, 3)])

    def test_week_type_is_respected(self):
        week_one = self.class_subject()
        make_schedule(week_one, Day.SATURDAY, self.bell_1, Week.WEEK_ONE)
        # 07/11 (week 2) and 07/18 (week 1) are both Saturdays
        self.event(J(1405, 7, 11), SATURDAY)

        self.sync()

        self.assertEqual(
            [d for cs, d, _ in self.holidays() if cs == week_one.pk], [SATURDAY]
        )

    def test_class_subject_date_range_is_respected(self):
        late = self.class_subject(start=J(1405, 7, 13))
        make_schedule(late, Day.SUNDAY, self.bell_3)
        self.event(SUNDAY, SATURDAY)
        make_schedule(late, Day.SATURDAY, self.bell_3)

        self.sync()

        self.assertEqual([d for cs, d, _ in self.holidays() if cs == late.pk], [SATURDAY])

    def test_retroactive_closure_never_overwrites_a_held_session(self):
        held = SchoolSession.objects.create(class_subject=self.math, date=SUNDAY, bell=self.bell_1)
        event = self.event(SUNDAY)

        result = self.sync()

        held.refresh_from_db()
        self.assertEqual((held.status, held.session_number), (SchoolSession.Status.HELD, 1))
        self.assertEqual([c.session for c in result.conflicts], [held])
        self.assertEqual(result.conflicts[0].event, event)
        # the other bell is still cancelled
        self.assertEqual(self.holidays(), [(self.math.pk, SUNDAY, 2)])
        self.assertEqual([c.session for c in services.find_conflicts(academic_year=self.year)], [held])

    def test_legacy_session_without_bell_takes_the_first_slot(self):
        legacy = SchoolSession.objects.create(class_subject=self.math, date=SUNDAY)
        self.event(SUNDAY)

        result = self.sync()

        self.assertEqual([c.session for c in result.conflicts], [legacy])
        self.assertEqual(self.holidays(), [(self.math.pk, SUNDAY, 2)])

    def test_held_numbering_is_not_affected(self):
        SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 5), bell=self.bell_1)
        self.event(SUNDAY)
        self.sync()
        later = SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 19), bell=self.bell_1)

        self.assertEqual(later.session_number, 2)
        self.assertEqual(SchoolSession.objects.counted().filter(class_subject=self.math).count(), 2)


class DeactivationTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SUNDAY, self.bell_2)
        self.event_ = self.event(SUNDAY)
        self.sync()

    def test_deactivating_removes_the_auto_sessions(self):
        result = services.deactivate_event(self.event_)

        self.assertEqual(result.removed, 2)
        self.assertFalse(SchoolSession.objects.exists())
        self.event_.refresh_from_db()
        self.assertFalse(self.event_.is_active)

    def test_sessions_with_content_or_attendance_are_kept(self):
        with_content, with_attendance = SchoolSession.objects.holidays().order_by('bell__order')
        SessionContent.objects.create(session=with_content, title='t', content='c', homework='h')
        enrollment = make_enrollment(make_student(), self.school_class)
        # Attendance.save() refuses holidays; old data may still have some
        Attendance.objects.bulk_create([
            Attendance(session=with_attendance, student_enrollment=enrollment)
        ])

        result = services.deactivate_event(self.event_)

        self.assertEqual((result.removed, result.kept), (0, 2))
        self.assertEqual(SchoolSession.objects.count(), 2)

    def test_another_event_still_covering_takes_the_sessions_over(self):
        second = self.event(SUNDAY, title='آلودگی هوا')

        result = services.deactivate_event(self.event_)

        self.assertEqual((result.removed, result.updated), (0, 2))
        self.assertEqual(
            set(SchoolSession.objects.values_list('calendar_event', flat=True)), {second.pk}
        )

    def test_editing_the_range_moves_the_sessions(self):
        make_schedule(self.math, Day.MONDAY, self.bell_1)
        previous = (self.event_.start_date, self.event_.end_date)
        self.event_.start_date = self.event_.end_date = J(1405, 7, 13)
        self.event_.save()

        result = services.sync_event(self.event_, previous_range=previous)

        self.assertEqual((result.created, result.removed), (1, 2))
        self.assertEqual(self.holidays(), [(self.math.pk, J(1405, 7, 13), 1)])


class TimetableChangeTests(CalendarTestCase):
    """Holiday sessions follow the timetable (academic_calendar.signals)."""

    def setUp(self):
        super().setUp()
        self.slot = make_schedule(self.math, Day.SUNDAY, self.bell_1)
        self.event(SUNDAY)
        self.sync()

    def test_new_slot_on_a_closed_day_is_cancelled_too(self):
        with self.captureOnCommitCallbacks(execute=True):
            make_schedule(self.math, Day.SUNDAY, self.bell_2)

        self.assertEqual(self.holidays(), [(self.math.pk, SUNDAY, 1), (self.math.pk, SUNDAY, 2)])

    def test_moving_or_deleting_a_slot_removes_its_holiday(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.slot.day_of_week = Day.MONDAY
            self.slot.save()

        self.assertEqual(self.holidays(), [])

        with self.captureOnCommitCallbacks(execute=True):
            self.slot.day_of_week = Day.SUNDAY
            self.slot.save()
        self.assertEqual(len(self.holidays()), 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.slot.delete()
        self.assertEqual(self.holidays(), [])

    def test_deactivating_the_class_subject_removes_its_holidays(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.math.is_active = False
            self.math.save()

        self.assertEqual(self.holidays(), [])

    def test_bulk_create_from_the_timetable_editor_syncs(self):
        with self.captureOnCommitCallbacks(execute=True):
            ClassSchedule.objects.bulk_create([
                ClassSchedule(class_subject=self.math, day_of_week=Day.SUNDAY, bell=self.bell_3,
                              week_type=Week.BOTH),
            ])

        self.assertEqual(len(self.holidays()), 2)


class ThursdaySlotTests(CalendarTestCase):

    def test_new_thursday_slots_are_refused_on_every_write_path(self):
        with self.assertRaises(ValidationError):
            make_schedule(self.math, Day.THURSDAY, self.bell_1)
        with self.assertRaises(ValidationError):
            ClassSchedule.objects.bulk_create([
                ClassSchedule(class_subject=self.math, day_of_week=Day.THURSDAY, bell=self.bell_1)
            ])
        row = make_schedule(self.math, Day.SUNDAY, self.bell_1)
        with self.assertRaises(ValidationError):
            ClassSchedule.objects.filter(pk=row.pk).update(day_of_week=Day.THURSDAY)
        row.day_of_week = Day.THURSDAY
        with self.assertRaises(ValidationError):
            ClassSchedule.objects.bulk_update([row], ['day_of_week'])

    def test_a_legacy_thursday_slot_can_still_be_edited(self):
        row = make_schedule(self.math, Day.SUNDAY, self.bell_1)
        QuerySet.update(ClassSchedule.objects.filter(pk=row.pk), day_of_week=Day.THURSDAY)
        row.refresh_from_db()

        row.bell = self.bell_2
        row.save()


class CommandTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SUNDAY, self.bell_2)

    def run_command(self, name, *args):
        out = io.StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def test_sync_command_dry_run_then_real(self):
        self.event(SUNDAY)

        output = self.run_command('sync_calendar_sessions', '--from', '1405/07/01', '--to', '1405/07/30', '--dry-run')
        self.assertIn('created=2', output)
        self.assertFalse(SchoolSession.objects.exists())

        self.run_command('sync_calendar_sessions', '--year', str(self.year.pk))
        self.assertEqual(SchoolSession.objects.holidays().count(), 2)

        output = self.run_command('sync_calendar_sessions')
        self.assertIn('created=0 removed=0', output)

    def test_backfill_matches_unambiguous_sessions_only(self):
        # two sessions, two Sunday slots: matched in order
        first = SchoolSession.objects.create(class_subject=self.math, date=SUNDAY)
        second = SchoolSession.objects.create(class_subject=self.math, date=SUNDAY)
        # one session for two Monday... slots: none on Monday at all
        monday = SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 13))
        # one session for the two Sunday slots of week 1: ambiguous
        ambiguous = SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 19))

        with tempfile.NamedTemporaryFile(suffix='.csv') as report:
            output = self.run_command('backfill_session_bells', '--csv', report.name)
            rows = {int(r['session_id']): r for r in csv.DictReader(open(report.name, encoding='utf-8-sig'))}

        self.assertIn('Dry run', output)
        self.assertFalse(SchoolSession.objects.filter(bell__isnull=False).exists())
        self.assertEqual(rows[first.pk]['bell_id'], str(self.bell_1.pk))
        self.assertEqual(rows[second.pk]['bell_id'], str(self.bell_2.pk))
        self.assertEqual(rows[monday.pk]['result'], 'left_null')
        self.assertIn('زنگی در برنامه ندارد', rows[monday.pk]['reason'])
        self.assertIn('مبهم', rows[ambiguous.pk]['reason'])

        self.run_command('backfill_session_bells', '--apply')

        first.refresh_from_db()
        second.refresh_from_db()
        ambiguous.refresh_from_db()
        self.assertEqual((first.bell, second.bell, ambiguous.bell), (self.bell_1, self.bell_2, None))
