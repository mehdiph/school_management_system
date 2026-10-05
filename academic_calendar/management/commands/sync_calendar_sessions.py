"""
Re-syncs the holiday sessions of the academic calendar.

Every write through the admin, the quick-closure form, the Excel import
and the timetable already syncs on its own; this command is for repairs
(e.g. after data was changed directly in the database, or after the
``backfill_session_bells`` command) and for checking what a sync would do.

    python manage.py sync_calendar_sessions                      # the current academic year
    python manage.py sync_calendar_sessions --year 3             # academic year id 3
    python manage.py sync_calendar_sessions --from 1405/07/01 --to 1405/07/30
    python manage.py sync_calendar_sessions --dry-run            # report, roll back

Dates are Jalali (``YYYY/MM/DD``). It runs
``academic_calendar.services.sync_cancelled_sessions`` -- the same code the
admin uses -- and is idempotent: a second run reports no changes.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from school.models import AcademicYear

from academic_calendar.services import parse_jalali_date, sync_cancelled_sessions


class _DryRun(Exception):
    pass


class Command(BaseCommand):
    help = (
        "Creates / removes the holiday (HL) sessions so they match the active "
        "calendar events. Defaults to the current academic year."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="date_from", help="First day, Jalali YYYY/MM/DD.")
        parser.add_argument("--to", dest="date_to", help="Last day, Jalali YYYY/MM/DD.")
        parser.add_argument("--year", type=int, help="AcademicYear id (default: the current year).")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change, then roll everything back.",
        )

    def handle(self, *args, **options):
        year = self._year(options["year"])
        try:
            start = parse_jalali_date(options["date_from"]) if options["date_from"] else year.start_date
            end = parse_jalali_date(options["date_to"]) if options["date_to"] else year.end_date
        except ValueError as error:
            raise CommandError(f"Invalid date: {error}")
        if start > end:
            raise CommandError("--from must not be after --to.")

        self.stdout.write(f"Academic year {year.title}: {start:%Y/%m/%d} .. {end:%Y/%m/%d}")

        try:
            with transaction.atomic():
                result = sync_cancelled_sessions(start, end, academic_year=year)
                if options["dry_run"]:
                    raise _DryRun
        except _DryRun:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))

        self.stdout.write(
            f"created={result.created} removed={result.removed} "
            f"updated={result.updated} kept_with_data={result.kept} "
            f"conflicts={len(result.conflicts)}"
        )
        for conflict in result.conflicts:
            session = conflict.session
            self.stdout.write(
                f"  conflict: session id={session.pk} {session.class_subject} "
                f"{session.date:%Y/%m/%d} bell={conflict.bell} event={conflict.event}"
            )
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Done."))

    @staticmethod
    def _year(year_id):
        if year_id is not None:
            year = AcademicYear.objects.filter(pk=year_id).first()
            if year is None:
                raise CommandError(f"No academic year with id {year_id}.")
            return year
        year = AcademicYear.objects.filter(is_current=True).first()
        if year is None:
            raise CommandError("No current academic year; pass --year.")
        return year
