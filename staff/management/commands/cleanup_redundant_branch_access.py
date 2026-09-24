"""
Reports (and optionally removes) ``BranchAccess`` rows that no longer
carry any information.

Since ``core.services.access`` derives a teacher's branches from their
active assignments, an explicit ``BranchAccess`` row for a branch the
staff member already teaches in grants nothing extra -- it is leftover
double data entry from before that change.

Rows flagged ``is_default=True`` are always kept: that flag is real
information (which branch to preselect) that no assignment can replace.

Nothing is deleted unless ``--apply`` is passed.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.services.access import active_teacher_assignments
from staff.models import BranchAccess
from staff.models.teacher_assignment import TeacherAssignment


class Command(BaseCommand):
    help = (
        "Finds BranchAccess rows already covered by an active teacher "
        "assignment (same staff + branch) and that are not the staff "
        "member's default branch. Dry-run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually delete the redundant rows (inside a "
                "transaction). Without this flag the command only "
                "prints what it would remove."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Default mode: only print the report. Kept explicit for clarity.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        if apply_changes and options["dry_run"]:
            self.stderr.write(
                self.style.ERROR("--apply and --dry-run are mutually exclusive.")
            )
            return

        redundant = self.find_redundant()

        if not redundant:
            self.stdout.write(
                self.style.SUCCESS("No redundant BranchAccess rows found.")
            )
            return

        self.stdout.write(
            f"Found {len(redundant)} redundant BranchAccess row(s):"
        )

        for row in redundant:
            self.stdout.write(
                f"  - id={row.pk} staff={row.staff} "
                f"(personnel_code={row.staff.personnel_code}) "
                f"branch={row.branch}"
            )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run: nothing was deleted. Re-run with --apply to "
                    "remove these rows."
                )
            )
            return

        with transaction.atomic():
            deleted_count, _ = (
                BranchAccess.objects
                .filter(pk__in=[row.pk for row in redundant])
                .delete()
            )

        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted_count} BranchAccess row(s).")
        )

    def find_redundant(self):
        """
        ``BranchAccess`` rows whose (staff, branch) pair is already
        granted by an active teacher assignment, excluding default rows.

        Two queries total, regardless of how many rows exist.
        """

        covered_pairs = set(
            active_teacher_assignments(
                TeacherAssignment.objects.all()
            ).values_list("teacher__staff_id", "branch_id")
        )

        if not covered_pairs:
            return []

        return [
            row
            for row in (
                BranchAccess.objects
                .filter(is_default=False)
                .select_related("staff", "staff__user", "branch")
                .order_by("staff__user__last_name", "branch__name", "pk")
            )
            if (row.staff_id, row.branch_id) in covered_pairs
        ]
