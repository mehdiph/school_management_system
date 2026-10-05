"""
Gives sessions recorded before ``SchoolSession.bell`` existed their bell,
where the timetable makes it unambiguous. Dry-run unless ``--apply``.

    python manage.py backfill_session_bells                      # report only
    python manage.py backfill_session_bells --csv report.csv     # ... and save it
    python manage.py backfill_session_bells --apply              # write the bells

For every non-holiday session without a bell, grouped per class subject
and date:

1. the date's weekday and rotation week (``academic_calendar.services``)
   give the *candidate* slots: the class subject's ``ClassSchedule`` rows
   for that weekday in that week (or every week), in bell order -- from
   the timetable as it is *now*, since past timetables are not stored;
2. bells already used by that class subject's sessions on that date are
   taken;
3. when the number of bell-less sessions equals the number of free
   candidates, they are matched in their numbering order to the bells in
   bell order and the session gets that bell;
4. anything else is left NULL with the reason: a Friday, before the
   academic year, no timetable slot that day (e.g. a compensatory
   session), or more / fewer sessions than free slots (e.g. one session
   recorded for a double period).

Sessions left NULL keep working everywhere (they count against that day's
slots in order, see ``academic_calendar.services``); a teacher editing one
picks its bell. After ``--apply``, run ``sync_calendar_sessions``.
"""

import csv
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from academic_calendar.services import get_week_type, to_gregorian
from scheduling.models import ClassSchedule
from scheduling.utils import persian_weekday
from teaching.models import SchoolSession

WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه")

COLUMNS = [
    "session_id", "class_subject_id", "class_subject", "date", "weekday",
    "week_type", "status", "session_number", "candidates", "taken",
    "result", "bell_id", "bell", "reason",
]


def _bells(bells):
    return "، ".join(f"{bell.title} (#{bell.pk})" for bell in bells)


class Command(BaseCommand):
    help = (
        "Matches sessions without a bell to their timetable slot. Dry-run "
        "(a per-session report) unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the bells found (one transaction).")
        parser.add_argument("--csv", dest="csv_path", help="Also write the report to this CSV file (UTF-8).")

    def handle(self, *args, **options):
        rows = self.plan()

        for row in rows:
            line = (
                f"session {row['session_id']} | {row['class_subject']} | {row['date']} "
                f"{row['weekday']} | candidates: {row['candidates'] or '-'}"
            )
            if row["result"] == "assigned":
                self.stdout.write(f"{line} -> {self.style.SUCCESS(row['bell'])}")
            else:
                self.stdout.write(f"{line} -> {self.style.WARNING('NULL')}: {row['reason']}")

        assigned = [row for row in rows if row["result"] == "assigned"]
        self.stdout.write(
            f"\n{len(rows)} session(s) without a bell: {len(assigned)} matched, "
            f"{len(rows) - len(assigned)} left NULL."
        )

        if options["csv_path"]:
            # utf-8-sig so Excel shows the Persian text correctly
            with open(options["csv_path"], "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f"Report written to {options['csv_path']}.")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved. Re-run with --apply to write."))
            return

        with transaction.atomic():
            for row in assigned:
                # update(): the numbers already follow this order, and
                # save() would re-validate legacy rows for nothing.
                SchoolSession.objects.filter(pk=row["session_id"], bell__isnull=True).update(
                    bell_id=row["bell_id"]
                )
        self.stdout.write(self.style.SUCCESS(f"{len(assigned)} bell(s) written."))

    def plan(self):
        sessions = list(
            SchoolSession.objects.counted()
            .filter(bell__isnull=True)
            .select_related(
                "class_subject__subject",
                "class_subject__school_class__year",
                "class_subject__school_class__grade",
                "class_subject__school_class__branch",
                "class_subject__teacher_assignment__teacher__staff__user",
            )
            .order_by("class_subject_id", "date", "session_number", "pk")
        )
        if not sessions:
            return []

        class_subject_ids = {s.class_subject_id for s in sessions}
        schedules = defaultdict(list)
        for schedule in (
            ClassSchedule.objects.filter(class_subject_id__in=class_subject_ids)
            .select_related("bell")
            .order_by("bell__order")
        ):
            schedules[(schedule.class_subject_id, schedule.day_of_week)].append(schedule)

        taken = defaultdict(set)
        for class_subject_id, day, bell_id in (
            SchoolSession.objects.filter(class_subject_id__in=class_subject_ids, bell__isnull=False)
            .values_list("class_subject_id", "date", "bell_id")
        ):
            taken[(class_subject_id, day)].add(bell_id)

        groups = defaultdict(list)
        for session in sessions:
            groups[(session.class_subject_id, session.date)].append(session)

        rows = []
        for (class_subject_id, day), group in groups.items():
            rows.extend(self._match(group, schedules, taken[(class_subject_id, day)]))
        return rows

    @staticmethod
    def _match(group, schedules, taken_bell_ids):
        first = group[0]
        class_subject = first.class_subject
        year = class_subject.school_class.year
        day = to_gregorian(first.date)
        weekday = persian_weekday(day)
        week_type = get_week_type(day, year)

        candidates, reason = [], ""
        if weekday == 6:
            reason = "جمعه: هیچ زنگی در برنامه نیست"
        elif week_type is None:
            reason = "قبل از شروع سال تحصیلی کلاس"
        else:
            candidates = [
                s.bell for s in schedules.get((class_subject.pk, weekday), ())
                if s.week_type in (week_type, ClassSchedule.WeekTypeChoices.BOTH)
            ]
            if not candidates:
                reason = "این درس در این روز و این هفته زنگی در برنامه ندارد (مثلاً جلسه‌ی جبرانی)"

        free = [bell for bell in candidates if bell.pk not in taken_bell_ids]
        taken = [bell for bell in candidates if bell.pk in taken_bell_ids]
        if candidates and not free:
            reason = "همه‌ی زنگ‌های این روز قبلاً جلسه دارند"
        elif candidates and len(free) != len(group):
            reason = (
                f"{len(group)} جلسه‌ی بدون زنگ برای {len(free)} زنگ آزاد: "
                "تطبیق مبهم است"
            )

        matched = dict(zip((s.pk for s in group), free)) if candidates and not reason else {}

        rows = []
        for session in group:
            bell = matched.get(session.pk)
            rows.append({
                "session_id": session.pk,
                "class_subject_id": class_subject.pk,
                "class_subject": str(class_subject),
                "date": session.date.strftime("%Y/%m/%d"),
                "weekday": WEEKDAYS[weekday],
                "week_type": (
                    ClassSchedule.WeekTypeChoices(week_type).label if week_type else ""
                ),
                "status": session.get_status_display(),
                "session_number": session.session_number,
                "candidates": _bells(candidates),
                "taken": _bells(taken),
                "result": "assigned" if bell else "left_null",
                "bell_id": bell.pk if bell else "",
                "bell": bell.title if bell else "",
                "reason": "" if bell else reason,
            })
        return rows
