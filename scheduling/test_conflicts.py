"""
Timetable conflict rules (scheduling.conflicts) on every write path.

Rules under test:
  1. class conflict   -- one class, same day + bell, overlapping weeks
  2. teacher conflict -- one TeacherProfile, even through assignments in
     different branches
  3. week overlap     -- every week overlaps week 1 and week 2; week 1
     and week 2 do not overlap
  4. scope            -- same academic year, active class subjects,
     overlapping teaching windows only
  5. write paths      -- save(), clean(), bulk_create(), bulk_update(),
     QuerySet.update(), ClassSubject changes
  6. concurrency      -- two transactions cannot both add a clashing slot
"""

import threading
from datetime import time

import jdatetime
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F
from django.test import SimpleTestCase, TestCase, TransactionTestCase, skipUnlessDBFeature

from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_grade,
    make_school_class,
    make_subject,
    make_teacher_profile,
)
from school.models import ClassSubject

from .conflicts import ScheduleConflictError, week_types_overlap
from .models.bell import Bell
from .models.class_schedule import ClassSchedule

WEEK_ONE = ClassSchedule.WeekTypeChoices.WEEK_ONE
WEEK_TWO = ClassSchedule.WeekTypeChoices.WEEK_TWO
EVERY_WEEK = ClassSchedule.WeekTypeChoices.BOTH
SAT = ClassSchedule.DayChoices.SATURDAY
SUN = ClassSchedule.DayChoices.SUNDAY

YEAR_START = jdatetime.date(1405, 7, 1)
YEAR_END = jdatetime.date(1406, 3, 31)


class WeekOverlapTests(SimpleTestCase):
    """Rule 3."""

    def test_overlap_table(self):
        expected = {
            (EVERY_WEEK, EVERY_WEEK): True,
            (EVERY_WEEK, WEEK_ONE): True,
            (EVERY_WEEK, WEEK_TWO): True,
            (WEEK_ONE, EVERY_WEEK): True,
            (WEEK_TWO, EVERY_WEEK): True,
            (WEEK_ONE, WEEK_ONE): True,
            (WEEK_TWO, WEEK_TWO): True,
            (WEEK_ONE, WEEK_TWO): False,
            (WEEK_TWO, WEEK_ONE): False,
        }
        for (a, b), overlap in expected.items():
            with self.subTest(a=a, b=b):
                self.assertIs(week_types_overlap(a, b), overlap)


class ConflictFixture:
    """
    Branch A: class_a1, class_a2. Branch B: class_b. One academic year.
    Teacher T teaches in both branches (assignment t_a, t_b); teacher U
    only in A.
    """

    def make_fixture(self):
        self.branch_a = make_branch(name="شعبه-الف")
        self.branch_b = make_branch(name="شعبه-ب")
        self.grade = make_grade()
        self.year = make_academic_year(start_date=YEAR_START, end_date=YEAR_END)

        self.class_a1 = make_school_class(self.branch_a, self.grade, self.year)
        self.class_a2 = make_school_class(self.branch_a, self.grade, self.year)
        self.class_b = make_school_class(self.branch_b, self.grade, self.year)

        self.teacher = make_teacher_profile()
        self.t_a = make_assignment(self.teacher, self.branch_a, self.year)
        self.t_b = make_assignment(self.teacher, self.branch_b, self.year)
        self.other_teacher = make_teacher_profile()
        self.u_a = make_assignment(self.other_teacher, self.branch_a, self.year)

        self.bell_1 = Bell.objects.create(title="اول", order=1, start_time=time(8), end_time=time(8, 45))
        self.bell_2 = Bell.objects.create(title="دوم", order=2, start_time=time(9), end_time=time(9, 45))

    def cs(self, school_class, assignment, start=YEAR_START, end=YEAR_END, is_active=True, name=None):
        subject = make_subject()
        if name:
            subject.name = name
            subject.save()
        return ClassSubject.objects.create(
            school_class=school_class,
            subject=subject,
            teacher_assignment=assignment,
            start_date=start,
            end_date=end,
            is_active=is_active,
        )

    def slot(self, class_subject, day=SAT, bell=None, week_type=EVERY_WEEK):
        return ClassSchedule.objects.create(
            class_subject=class_subject,
            day_of_week=day,
            bell=bell or self.bell_1,
            week_type=week_type,
        )

    def unsaved(self, class_subject, day=SAT, bell=None, week_type=EVERY_WEEK):
        return ClassSchedule(
            class_subject=class_subject,
            day_of_week=day,
            bell=bell or self.bell_1,
            week_type=week_type,
        )


class ClassConflictTests(ConflictFixture, TestCase):
    """Rule 1 (and rule 3 applied to it)."""

    def setUp(self):
        self.make_fixture()
        self.math = self.cs(self.class_a1, self.t_a, name="ریاضی")
        self.art = self.cs(self.class_a1, self.u_a, name="هنر")

    def assert_rejected(self, existing_week, new_week):
        self.slot(self.math, week_type=existing_week)
        with self.assertRaises(ValidationError) as ctx:
            self.slot(self.art, week_type=new_week)
        self.assertIn("برای این کلاس در همین زنگ", " ".join(ctx.exception.messages))
        self.assertIn("ریاضی", " ".join(ctx.exception.messages))
        self.assertEqual(ClassSchedule.objects.count(), 1)

    def test_every_week_vs_every_week(self):
        self.assert_rejected(EVERY_WEEK, EVERY_WEEK)

    def test_every_week_vs_week_one(self):
        self.assert_rejected(EVERY_WEEK, WEEK_ONE)

    def test_week_two_vs_every_week(self):
        self.assert_rejected(WEEK_TWO, EVERY_WEEK)

    def test_week_one_vs_week_one(self):
        self.assert_rejected(WEEK_ONE, WEEK_ONE)

    def test_week_one_and_week_two_share_a_cell(self):
        self.slot(self.math, week_type=WEEK_ONE)
        self.slot(self.art, week_type=WEEK_TWO)
        self.assertEqual(ClassSchedule.objects.count(), 2)

    def test_same_subject_twice_in_one_cell(self):
        self.slot(self.math, week_type=EVERY_WEEK)
        with self.assertRaises(ValidationError):
            self.slot(self.math, week_type=WEEK_ONE)

    def test_other_bell_or_day_is_free(self):
        self.slot(self.math)
        self.slot(self.art, bell=self.bell_2)
        self.slot(self.art, day=SUN)
        self.assertEqual(ClassSchedule.objects.count(), 3)

    def test_editing_a_slot_does_not_clash_with_itself(self):
        row = self.slot(self.math)
        row.week_type = WEEK_ONE
        row.save()
        self.assertEqual(ClassSchedule.objects.get().week_type, WEEK_ONE)

    def test_message_names_the_week_when_only_one_week_clashes(self):
        self.slot(self.math, week_type=WEEK_TWO)
        with self.assertRaises(ValidationError) as ctx:
            self.slot(self.art, week_type=EVERY_WEEK)
        self.assertIn("(هفته دوم)", " ".join(ctx.exception.messages))


class TeacherConflictTests(ConflictFixture, TestCase):
    """Rule 2 (and rule 3 applied to it)."""

    def setUp(self):
        self.make_fixture()

    def test_same_teacher_two_classes_same_branch(self):
        self.slot(self.cs(self.class_a1, self.t_a))
        with self.assertRaises(ValidationError) as ctx:
            self.slot(self.cs(self.class_a2, self.t_a))
        message = " ".join(ctx.exception.messages)
        self.assertIn("این معلم در همین زنگ در کلاس", message)
        self.assertIn(self.class_a1.section, message)

    def test_same_teacher_across_branches_through_different_assignments(self):
        self.slot(self.cs(self.class_a1, self.t_a))
        with self.assertRaises(ValidationError) as ctx:
            self.slot(self.cs(self.class_b, self.t_b))
        message = " ".join(ctx.exception.messages)
        self.assertIn(self.class_a1.section, message)
        self.assertIn("(شعبه-الف)", message)
        self.assertNotIn("شعبه شعبه", message)

    def test_cross_branch_every_week_vs_week_one(self):
        self.slot(self.cs(self.class_a1, self.t_a), week_type=EVERY_WEEK)
        with self.assertRaises(ValidationError):
            self.slot(self.cs(self.class_b, self.t_b), week_type=WEEK_ONE)

    def test_cross_branch_week_one_and_week_two_are_fine(self):
        self.slot(self.cs(self.class_a1, self.t_a), week_type=WEEK_ONE)
        self.slot(self.cs(self.class_b, self.t_b), week_type=WEEK_TWO)
        self.assertEqual(ClassSchedule.objects.count(), 2)

    def test_week_two_vs_every_week(self):
        self.slot(self.cs(self.class_a1, self.t_a), week_type=WEEK_TWO)
        with self.assertRaises(ValidationError) as ctx:
            self.slot(self.cs(self.class_a2, self.t_a), week_type=EVERY_WEEK)
        self.assertIn("(هفته دوم)", " ".join(ctx.exception.messages))

    def test_different_teachers_same_slot_other_classes(self):
        self.slot(self.cs(self.class_a1, self.t_a))
        self.slot(self.cs(self.class_a2, self.u_a))
        self.assertEqual(ClassSchedule.objects.count(), 2)


class ConflictScopeTests(ConflictFixture, TestCase):
    """Rule 4."""

    def setUp(self):
        self.make_fixture()

    def test_other_academic_year_does_not_clash(self):
        old_year = make_academic_year(
            start_date=jdatetime.date(1404, 7, 1), end_date=jdatetime.date(1405, 3, 31), is_current=False
        )
        old_class = make_school_class(self.branch_a, self.grade, old_year)
        old_assignment = make_assignment(self.teacher, self.branch_a, old_year)
        self.slot(self.cs(old_class, old_assignment,
                          start=jdatetime.date(1404, 7, 1), end=jdatetime.date(1405, 3, 31)))

        self.slot(self.cs(self.class_a1, self.t_a))
        self.assertEqual(ClassSchedule.objects.count(), 2)

    def test_inactive_class_subject_does_not_clash(self):
        self.slot(self.cs(self.class_a1, self.t_a, is_active=False))
        self.slot(self.cs(self.class_a2, self.t_a))
        self.slot(self.cs(self.class_a1, self.u_a))
        self.assertEqual(ClassSchedule.objects.count(), 3)

    def test_inactive_new_slot_is_not_checked(self):
        self.slot(self.cs(self.class_a1, self.t_a))
        self.slot(self.cs(self.class_a2, self.t_a, is_active=False))
        self.assertEqual(ClassSchedule.objects.count(), 2)

    def test_disjoint_teaching_windows_do_not_clash(self):
        # First term / second term of the same year.
        self.slot(self.cs(self.class_a1, self.t_a, end=jdatetime.date(1405, 10, 30)))
        self.slot(self.cs(self.class_a2, self.t_a, start=jdatetime.date(1405, 11, 1)))
        self.slot(self.cs(self.class_a1, self.u_a, start=jdatetime.date(1405, 11, 1)))
        self.assertEqual(ClassSchedule.objects.count(), 3)

    def test_touching_teaching_windows_clash(self):
        self.slot(self.cs(self.class_a1, self.t_a, end=jdatetime.date(1405, 11, 1)))
        with self.assertRaises(ValidationError):
            self.slot(self.cs(self.class_a2, self.t_a, start=jdatetime.date(1405, 11, 1)))

    def test_open_ended_window_is_treated_as_overlapping(self):
        from .conflicts import date_ranges_overlap

        d = jdatetime.date
        self.assertTrue(date_ranges_overlap(None, None, d(1405, 1, 1), d(1405, 1, 2)))
        self.assertTrue(date_ranges_overlap(d(1405, 1, 1), None, d(1406, 1, 1), d(1406, 2, 1)))
        self.assertFalse(date_ranges_overlap(d(1405, 1, 1), d(1405, 2, 1), d(1405, 3, 1), None))


class WritePathTests(ConflictFixture, TestCase):
    """Rule 5: paths that skip clean() still check."""

    def setUp(self):
        self.make_fixture()
        self.busy = self.slot(self.cs(self.class_a1, self.t_a))

    def test_bulk_create_against_saved_rows(self):
        with self.assertRaises(ScheduleConflictError) as ctx:
            ClassSchedule.objects.bulk_create([
                self.unsaved(self.cs(self.class_a2, self.u_a), bell=self.bell_2),
                self.unsaved(self.cs(self.class_b, self.t_b)),
            ])
        self.assertIsInstance(ctx.exception, ValidationError)
        self.assertEqual(ClassSchedule.objects.count(), 1)

    def test_bulk_create_within_the_batch(self):
        # Two subjects in one class cell; nothing saved clashes with either.
        with self.assertRaises(ScheduleConflictError):
            ClassSchedule.objects.bulk_create([
                self.unsaved(self.cs(self.class_a2, self.u_a), bell=self.bell_2),
                self.unsaved(self.cs(self.class_a2, self.t_a), bell=self.bell_2, week_type=WEEK_ONE),
            ])
        self.assertEqual(ClassSchedule.objects.count(), 1)

    def test_bulk_create_without_conflicts(self):
        ClassSchedule.objects.bulk_create([
            self.unsaved(self.cs(self.class_a2, self.u_a)),
            self.unsaved(self.cs(self.class_b, self.t_b), bell=self.bell_2),
        ])
        self.assertEqual(ClassSchedule.objects.count(), 3)

    def test_bulk_update_into_a_conflict(self):
        row = self.slot(self.cs(self.class_b, self.t_b), bell=self.bell_2)
        row.bell = self.bell_1
        with self.assertRaises(ScheduleConflictError):
            ClassSchedule.objects.bulk_update([row], ["bell"])
        self.assertEqual(ClassSchedule.objects.get(pk=row.pk).bell, self.bell_2)

    def test_bulk_update_judges_saved_values_of_other_fields(self):
        # In memory the row is stale (says bell_1); only week_type is written.
        row = self.slot(self.cs(self.class_b, self.t_b), bell=self.bell_2)
        stale = ClassSchedule.objects.get(pk=row.pk)
        stale.bell = self.bell_1
        stale.week_type = WEEK_ONE
        ClassSchedule.objects.bulk_update([stale], ["week_type"])
        row.refresh_from_db()
        self.assertEqual((row.bell, row.week_type), (self.bell_2, WEEK_ONE))

    def test_queryset_update_into_a_conflict(self):
        row = self.slot(self.cs(self.class_b, self.t_b), bell=self.bell_2)
        with self.assertRaises(ScheduleConflictError):
            ClassSchedule.objects.filter(pk=row.pk).update(bell=self.bell_1)
        with self.assertRaises(ScheduleConflictError):
            ClassSchedule.objects.filter(pk=row.pk).update(bell_id=self.bell_1.pk)
        self.assertEqual(ClassSchedule.objects.get(pk=row.pk).bell, self.bell_2)

    def test_queryset_update_without_conflict(self):
        row = self.slot(self.cs(self.class_b, self.t_b), bell=self.bell_2)
        ClassSchedule.objects.filter(pk=row.pk).update(week_type=WEEK_TWO)
        self.assertEqual(ClassSchedule.objects.get(pk=row.pk).week_type, WEEK_TWO)

    def test_queryset_update_with_expression_is_refused(self):
        with self.assertRaises(TypeError):
            ClassSchedule.objects.update(day_of_week=F("day_of_week") + 1)

    def test_reactivating_a_class_subject_into_a_conflict(self):
        dormant = self.cs(self.class_b, self.t_b, is_active=False)
        self.slot(dormant)

        dormant.is_active = True
        with self.assertRaises(ValidationError) as ctx:
            dormant.full_clean()
        self.assertIn("شنبه، زنگ اول", " ".join(ctx.exception.messages))
        with self.assertRaises(ValidationError):
            dormant.save()
        self.assertFalse(ClassSubject.objects.get(pk=dormant.pk).is_active)

    def test_changing_a_class_subject_teacher_into_a_conflict(self):
        class_subject = self.cs(self.class_a2, self.u_a)
        self.slot(class_subject)

        class_subject.teacher_assignment = self.t_a
        with self.assertRaises(ValidationError):
            class_subject.save()

    def test_extending_a_teaching_window_into_a_conflict(self):
        class_subject = self.cs(self.class_a2, self.t_a, start=jdatetime.date(1406, 1, 1))
        # busy's window ends 1406/03/31, so it already overlaps; shrink it first.
        ClassSubject.objects.filter(pk=self.busy.class_subject_id).update(end_date=jdatetime.date(1405, 12, 29))
        self.slot(class_subject)

        class_subject.start_date = jdatetime.date(1405, 7, 1)
        with self.assertRaises(ValidationError):
            class_subject.save()

    def test_deactivating_a_class_subject_is_never_blocked(self):
        class_subject = ClassSubject.objects.get(pk=self.busy.class_subject_id)
        class_subject.is_active = False
        with self.assertNumQueries(1):
            class_subject.save()


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentSaveTests(ConflictFixture, TransactionTestCase):
    """
    Rule 6: two admins adding the same teacher to the same bell in two
    classes at the same time. Without the lock both transactions would
    see no conflict and both commit.
    """

    def setUp(self):
        self.make_fixture()
        self.cs_1 = self.cs(self.class_a1, self.t_a)
        self.cs_2 = self.cs(self.class_b, self.t_b)

    def test_second_writer_waits_and_then_sees_the_first(self):
        first_saved = threading.Event()
        release_first = threading.Event()
        second_finished = threading.Event()
        outcome = {}

        def first():
            try:
                with transaction.atomic():
                    self.slot(self.cs_1)
                    first_saved.set()
                    release_first.wait(10)
            finally:
                connection.close()

        def second():
            try:
                first_saved.wait(10)
                try:
                    with transaction.atomic():
                        self.slot(self.cs_2)
                    outcome["second"] = "saved"
                except ValidationError as error:
                    outcome["second"] = error.messages
            finally:
                second_finished.set()
                connection.close()

        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()

        # While the first transaction is open, the second one must block.
        self.assertTrue(first_saved.wait(10))
        self.assertFalse(second_finished.wait(1))
        release_first.set()
        for thread in threads:
            thread.join(10)

        self.assertNotEqual(outcome.get("second"), "saved")
        self.assertIn("این معلم در همین زنگ", " ".join(outcome["second"]))
        self.assertEqual(ClassSchedule.objects.count(), 1)
