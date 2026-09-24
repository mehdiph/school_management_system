"""
Tests for the ``BranchAccess`` constraints and for the
``cleanup_redundant_branch_access`` management command.

The command exists because the old "select the branch twice" workflow
left behind ``BranchAccess`` rows that an active teacher assignment now
grants anyway. It must be conservative: never touch a default-branch
row, never touch a row no assignment covers, and never delete anything
unless ``--apply`` was passed.
"""

from datetime import timedelta
from io import StringIO

import jdatetime
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_branch_access,
    make_staff,
    make_teacher_profile,
)
from staff.models import BranchAccess, TeacherAssignment


def today():
    return jdatetime.date.fromgregorian(date=timezone.localdate())


class BranchAccessConstraintTests(TestCase):

    def setUp(self):
        self.staff = make_staff(role=User.Roles.ACCOUNTANT)
        self.branch = make_branch()
        self.other_branch = make_branch()

    def test_staff_and_branch_pair_is_unique(self):
        make_branch_access(self.staff, self.branch)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_branch_access(self.staff, self.branch)

    def test_only_one_default_branch_per_staff(self):
        make_branch_access(self.staff, self.branch, is_default=True)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_branch_access(
                    self.staff, self.other_branch, is_default=True
                )

    def test_several_non_default_rows_are_allowed(self):
        make_branch_access(self.staff, self.branch, is_default=True)
        make_branch_access(self.staff, self.other_branch, is_default=False)

        self.assertEqual(
            BranchAccess.objects.filter(staff=self.staff).count(), 2
        )

    def test_two_staff_members_may_each_have_a_default(self):
        other_staff = make_staff(role=User.Roles.IT)

        make_branch_access(self.staff, self.branch, is_default=True)
        make_branch_access(other_staff, self.branch, is_default=True)

        self.assertEqual(
            BranchAccess.objects.filter(is_default=True).count(), 2
        )


class CleanupRedundantBranchAccessTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.other_branch = make_branch()
        self.current_year = make_academic_year(is_current=True)
        self.old_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "cleanup_redundant_branch_access", *args, stdout=out, stderr=out
        )
        return out.getvalue()

    # -- dry run ------------------------------------------------------

    def test_dry_run_reports_but_deletes_nothing(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        redundant = make_branch_access(teacher.staff, self.branch)

        output = self.run_command()

        self.assertIn("Found 1 redundant", output)
        self.assertIn(f"id={redundant.pk}", output)
        self.assertIn("Dry run", output)
        self.assertTrue(BranchAccess.objects.filter(pk=redundant.pk).exists())

    def test_explicit_dry_run_flag_behaves_the_same(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        redundant = make_branch_access(teacher.staff, self.branch)

        output = self.run_command("--dry-run")

        self.assertIn("Dry run", output)
        self.assertTrue(BranchAccess.objects.filter(pk=redundant.pk).exists())

    # -- apply --------------------------------------------------------

    def test_apply_deletes_the_redundant_row(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        redundant = make_branch_access(teacher.staff, self.branch)

        output = self.run_command("--apply")

        self.assertIn("Deleted 1", output)
        self.assertFalse(BranchAccess.objects.filter(pk=redundant.pk).exists())

    def test_apply_and_dry_run_together_are_refused(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        redundant = make_branch_access(teacher.staff, self.branch)

        output = self.run_command("--apply", "--dry-run")

        self.assertIn("mutually exclusive", output)
        self.assertTrue(BranchAccess.objects.filter(pk=redundant.pk).exists())

    # -- what must be kept --------------------------------------------

    def test_default_rows_are_never_removed(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        default_row = make_branch_access(
            teacher.staff, self.branch, is_default=True
        )

        output = self.run_command("--apply")

        self.assertIn("No redundant", output)
        self.assertTrue(
            BranchAccess.objects.filter(pk=default_row.pk).exists()
        )

    def test_row_for_a_different_branch_is_kept(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        extra_row = make_branch_access(teacher.staff, self.other_branch)

        self.run_command("--apply")

        self.assertTrue(BranchAccess.objects.filter(pk=extra_row.pk).exists())

    def test_row_covered_only_by_an_ended_assignment_is_kept(self):
        teacher = make_teacher_profile()
        make_assignment(
            teacher,
            self.branch,
            self.current_year,
            end_date=today() - timedelta(days=1),
        )
        row = make_branch_access(teacher.staff, self.branch)

        self.run_command("--apply")

        self.assertTrue(BranchAccess.objects.filter(pk=row.pk).exists())

    def test_row_covered_only_by_a_past_year_assignment_is_kept(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.old_year)
        row = make_branch_access(teacher.staff, self.branch)

        self.run_command("--apply")

        self.assertTrue(BranchAccess.objects.filter(pk=row.pk).exists())

    def test_row_covered_only_by_a_terminated_assignment_is_kept(self):
        teacher = make_teacher_profile()
        make_assignment(
            teacher,
            self.branch,
            self.current_year,
            status=TeacherAssignment.AssignmentStatus.TERMINATED,
        )
        row = make_branch_access(teacher.staff, self.branch)

        self.run_command("--apply")

        self.assertTrue(BranchAccess.objects.filter(pk=row.pk).exists())

    def test_non_teaching_staff_rows_are_kept(self):
        staff = make_staff(role=User.Roles.ACCOUNTANT)
        # Somebody has to teach somewhere, or the command short-circuits
        # before it ever looks at BranchAccess rows.
        make_assignment(
            make_teacher_profile(), self.branch, self.current_year
        )
        row = make_branch_access(staff, self.branch)

        self.run_command("--apply")

        self.assertTrue(BranchAccess.objects.filter(pk=row.pk).exists())

    def test_nothing_to_do_is_reported(self):
        output = self.run_command()

        self.assertIn("No redundant", output)
