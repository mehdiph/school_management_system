"""
Attendance as every page and report reads it: the cutoff rule, written once.

Until ``settings.ATTENDANCE_DAILY_START_DATE`` the teacher took attendance
in every session (``SessionAttendance``, now an archive the app never
writes). From that date on the grade supporter takes it once a day per
class (``DailyAttendanceSheet`` / ``DailyAttendance``). Exactly one of them
applies to a date: :func:`split_range` decides which, and every reader
below goes through it, so no page reads the archive after the cutoff or a
daily sheet before it.

Readers
-------
* :func:`get_absences`: the records to follow up (absent, late, excused)
  of a student or of classes over a date range.
* :func:`attendance_counts`: status counts and the attendance rate.
* :func:`student_tallies`: the same counts per student.
* :func:`session_tallies` / :func:`class_day_tallies`: per session
  (archive) and per class and day (daily), for ``analytics.engine``.
* :func:`class_day_statuses`: which classes took their daily attendance
  on which days, and which were due to (the director's panel).

Archived records count only for held and compensatory sessions, as they
always have; every daily record counts. Across the cutoff, an absence is
one missed session before it and one missed day after it. The counts are
added together, never converted.

Writing
-------
* :func:`day_error`: whether a class can have a sheet on a day.
* :func:`save_daily_sheet`: create or edit the sheet of a class and day.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, DateField, Q, QuerySet
from django.db.models.functions import Cast
from django.utils import timezone

from academic_calendar import services as calendar
from analytics.definitions import ABSENT, EXCUSED, LATE, PRESENT, attendance_rate, rounded, slot_deadline
from core.templatetags.jalali_tags import format_jalali
from school.models import SchoolClass
from student.models.student_enrollment import StudentEnrollment

from .models import DailyAttendance, DailyAttendanceSheet, SessionAttendance

#: What a follow-up list shows: every record that is not «حاضر».
FOLLOW_UP_STATUSES = (ABSENT, LATE, EXCUSED)

#: Labels of every status, archive and daily alike.
STATUS_LABELS = dict(DailyAttendance.Status.choices)


# ----------------------------------------------------------------------
# The cutoff
# ----------------------------------------------------------------------

def daily_start():
    """The first day of daily attendance (a Gregorian ``date``)."""

    return settings.ATTENDANCE_DAILY_START_DATE


def is_daily(value):
    """Does ``value`` (Gregorian or Jalali) have daily attendance?"""

    return calendar.to_gregorian(value) >= daily_start()


def split_range(start=None, end=None):
    """
    ``start``..``end`` (inclusive, Gregorian or Jalali, None = unbounded)
    cut at the cutoff: ``(archive part, daily part)``, each a
    ``(start, end)`` pair of Gregorian dates (either may be None =
    unbounded), or None when the range has no day on that side.
    """

    cutoff = daily_start()
    start = calendar.to_gregorian(start) if start else None
    end = calendar.to_gregorian(end) if end else None

    archive = daily = None
    if start is None or start < cutoff:
        archive = (start, end if end is not None and end < cutoff else cutoff - timedelta(days=1))
    if end is None or end >= cutoff:
        daily = (max(start, cutoff) if start is not None else cutoff, end)
    return archive, daily


def _dates(field, part):
    """``part`` (from :func:`split_range`) as ``field`` lookups (Jalali values)."""

    start, end = part
    lookups = {}
    if start is not None:
        lookups[f"{field}__gte"] = calendar.to_jalali(start)
    if end is not None:
        lookups[f"{field}__lte"] = calendar.to_jalali(end)
    return lookups


def _target(target):
    """``(archive Q, daily Q)`` restricting the records to ``target``."""

    if target is None:
        return Q(), Q()
    if isinstance(target, StudentEnrollment):
        return Q(student_enrollment=target), Q(student_enrollment=target)
    if isinstance(target, SchoolClass):
        return Q(session__class_subject__school_class=target), Q(sheet__school_class=target)
    if isinstance(target, QuerySet) and target.model is SchoolClass:
        return (
            Q(session__class_subject__school_class__in=target),
            Q(sheet__school_class__in=target),
        )
    if isinstance(target, QuerySet) and target.model is StudentEnrollment:
        return Q(student_enrollment__in=target), Q(student_enrollment__in=target)
    raise TypeError(f"attendance of what? {target!r}")


def _archive(target, part):
    """Archived records of ``target`` in ``part`` (held and compensatory sessions only)."""

    archive_q, _ = _target(target)
    return SessionAttendance.objects.delivered().filter(archive_q, **_dates("session__date", part))


def _daily(target, part):
    _, daily_q = _target(target)
    return DailyAttendance.objects.filter(daily_q, **_dates("sheet__date", part))


# ----------------------------------------------------------------------
# Readers
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class AbsenceRecord:
    """One record to follow up, from either source."""

    date: date                  # Gregorian
    student_enrollment: StudentEnrollment
    status: str
    description: str
    recorded_at: object         # jdatetime: when it was taken or last changed
    session: object = None      # archive records: the session it was taken in

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def is_daily(self):
        return self.session is None


def get_absences(target, start=None, end=None, statuses=FOLLOW_UP_STATUSES):
    """
    The records of ``target`` (a ``StudentEnrollment``, a ``SchoolClass``
    or a queryset of classes) from ``start`` to ``end`` whose status is in
    ``statuses`` -- by default every record that is not «حاضر» -- as
    ``AbsenceRecord``s, newest day first, then by name. The archive for
    the days before the cutoff, the daily sheets from it on (two queries
    at most).
    """

    archive_part, daily_part = split_range(start, end)
    student = ("student_enrollment__student__user", "student_enrollment__school_class__grade")
    records = []

    if archive_part is not None:
        rows = (
            _archive(target, archive_part)
            .filter(status__in=statuses)
            .select_related(
                *student, "session__class_subject__subject", "session__bell",
            )
        )
        records += [
            AbsenceRecord(
                calendar.to_gregorian(row.session.date), row.student_enrollment, row.status,
                row.description, row.created_at, row.session,
            )
            for row in rows
        ]

    if daily_part is not None:
        rows = _daily(target, daily_part).filter(status__in=statuses).select_related("sheet", *student)
        records += [
            AbsenceRecord(
                calendar.to_gregorian(row.sheet.date), row.student_enrollment, row.status,
                row.description, row.updated_at,
            )
            for row in rows
        ]

    def order(record):
        user = record.student_enrollment.student.user
        bell = record.session.bell.order if record.session is not None and record.session.bell else 0
        return (-record.date.toordinal(), user.last_name, user.first_name, record.student_enrollment.pk, bell)

    return sorted(records, key=order)


def _counts(total=0, present=0, absent=0, late=0, excused=0):
    return {
        "total": total, "present": present, "absent": absent, "late": late, "excused": excused,
        "absences": absent + excused,
        "rate": rounded(attendance_rate(total, absent + excused)),
    }


def attendance_counts(target=None, start=None, end=None):
    """
    ``total`` / ``present`` / ``absent`` / ``late`` / ``excused`` records
    of ``target`` (see :func:`get_absences`; None = everything), their
    ``absences`` (absent + excused) and the rounded attendance ``rate``
    (None without records). One query per side of the cutoff.
    """

    archive_part, daily_part = split_range(start, end)
    totals = dict.fromkeys(("total", "present", "absent", "late", "excused"), 0)
    parts = []
    if archive_part is not None:
        parts.append(_archive(target, archive_part).status_counts())
    if daily_part is not None:
        parts.append(_daily(target, daily_part).status_counts())
    for counts in parts:
        for key in totals:
            totals[key] += counts[key]
    return _counts(**totals)


def session_counts(session):
    """
    The counts of :func:`attendance_counts` for one session, with
    ``daily``: before the cutoff, the session's own archived records
    (``daily`` False); from it on, the daily sheet of its class on its
    date (``daily`` True) -- a session no longer has attendance of its own.
    """

    if is_daily(session.date):
        counts = attendance_counts(session.class_subject.school_class, session.date, session.date)
        counts["daily"] = True
        return counts
    counts = SessionAttendance.objects.filter(session=session).status_counts()
    return {**_counts(**{key: counts[key] for key in ("total", "present", "absent", "late", "excused")}),
            "daily": False}


#: The student fields :func:`student_tallies` returns with the counts.
STUDENT_FIELDS = {
    "first_name": "student_enrollment__student__user__first_name",
    "last_name": "student_enrollment__student__user__last_name",
    "username": "student_enrollment__student__user__username",
    "grade": "student_enrollment__school_class__grade__name",
    "section": "student_enrollment__school_class__section",
    "branch": "student_enrollment__school_class__branch__name",
}


def student_tallies(target=None, start=None, end=None):
    """
    ``{enrollment id: row}``: per student of ``target``, the counts of
    :func:`attendance_counts` (without ``present`` / ``rate``) plus the
    names in ``STUDENT_FIELDS``. One grouped query per side of the cutoff.
    """

    archive_part, daily_part = split_range(start, end)
    queries = []
    if archive_part is not None:
        queries.append(_archive(target, archive_part))
    if daily_part is not None:
        queries.append(_daily(target, daily_part))

    rows = {}
    for records in queries:
        grouped = (
            records.order_by()
            .values("student_enrollment", *STUDENT_FIELDS.values())
            .annotate(
                total=Count("id"),
                absent=Count("id", filter=Q(status=ABSENT)),
                late=Count("id", filter=Q(status=LATE)),
                excused=Count("id", filter=Q(status=EXCUSED)),
            )
        )
        for values in grouped:
            row = rows.setdefault(values["student_enrollment"], {
                **{name: values[field] for name, field in STUDENT_FIELDS.items()},
                "total": 0, "absent": 0, "late": 0, "excused": 0,
            })
            for key in ("total", "absent", "late", "excused"):
                row[key] += values[key]
    for row in rows.values():
        row["absences"] = row["absent"] + row["excused"]
    return rows


def session_tallies(start, end, **lookups):
    """
    ``(session id, total, absent, late)`` per archived session from
    ``start`` to ``end`` (only its part before the cutoff; every status --
    the engine decides which sessions count). ``lookups`` filter the
    records (e.g. ``session__class_subject__school_class__year=...``).
    One grouped query, or none when the range is all after the cutoff.
    """

    archive_part, _ = split_range(start, end)
    if archive_part is None:
        return []
    return (
        SessionAttendance.objects.filter(**_dates("session__date", archive_part), **lookups)
        .order_by()
        .values_list("session_id")
        .annotate(
            total=Count("id"),
            absent=Count("id", filter=Q(status=ABSENT)),
            late=Count("id", filter=Q(status=LATE)),
        )
    )


def class_day_tallies(start, end, class_ids):
    """
    ``(class id, Gregorian day, total, absent, late, excused)`` per daily
    sheet of the classes ``class_ids`` from ``start`` to ``end`` (only its
    part from the cutoff on). A sheet without records is listed with
    zeros: it was taken. One grouped query, or none before the cutoff.
    """

    _, daily_part = split_range(start, end)
    if daily_part is None or not class_ids:
        return []
    return (
        DailyAttendanceSheet.objects.filter(
            school_class_id__in=sorted(class_ids), **_dates("date", daily_part)
        )
        .order_by()
        # A plain DATE: a jDateField value would become a jdatetime object,
        # whose constructor queries the locale (as in analytics.engine).
        .annotate(day=Cast("date", output_field=DateField()))
        .values_list("school_class_id", "day")
        .annotate(
            total=Count("records"),
            absent=Count("records", filter=Q(records__status=ABSENT)),
            late=Count("records", filter=Q(records__status=LATE)),
            excused=Count("records", filter=Q(records__status=EXCUSED)),
        )
    )


# ----------------------------------------------------------------------
# Which days have daily attendance
# ----------------------------------------------------------------------

def _planned(start, end, classes, closures=None):
    """
    ``{(class id, Gregorian day): (closing event or None, deadline or
    None)}``: :func:`planned_class_days` plus, for a day with an open
    slot, when its earliest-ending open slot is over (its bell's end plus
    the registration grace, ``analytics.definitions.slot_deadline``).
    """

    slots = calendar.get_slots(start, end, class_subject__school_class__in=classes)
    if not slots:
        return {}
    if closures is None:
        closures = calendar.Closures.between(start, end)
    days = {}
    for slot in slots:
        school_class = slot.class_subject.school_class
        key = (school_class.pk, slot.date)
        event = closures.event_for(slot.date, school_class, slot.bell)
        if event is None:
            deadline = slot_deadline(slot.date, slot.bell.end_time)
            current = days.get(key)
            if current is None or current[0] is not None or deadline < current[1]:
                days[key] = (None, deadline)
        elif key not in days:
            days[key] = (event, None)
    return days


def planned_class_days(start, end, classes, closures=None):
    """
    ``{(class id, Gregorian day): closing event or None}`` for every day
    from ``start`` to ``end`` on which the weekly timetable plans at least
    one lesson for a class of ``classes`` (a queryset): None when at
    least one of that day's slots is open, else the event that closed the
    first of them. A day missing from the result has no lesson in the
    timetable (no ``ClassSchedule`` slot, Thursday, Friday, outside the
    academic year or the class subjects' dates). Two queries, plus the
    calendar's when there are events.

    The same rule as the analytics engine's expected class-days, which
    starts from the same slots and closures (and additionally waits, for
    today, until the first open bell is over). ``closures`` (covering the
    range) can be passed in when the caller has them already.
    """

    return {key: event for key, (event, _) in _planned(start, end, classes, closures).items()}


@dataclass
class ClassDay:
    """Daily attendance of one class on one day, as :func:`class_day_statuses` sees it."""

    RECORDED = "recorded"       # the sheet is taken
    MISSING = "missing"         # the class was due to have one and has none
    PENDING = "pending"         # today, before its first open bell is over (+ grace)
    CLOSED = "closed"           # every lesson of the day closed by the calendar

    school_class_id: int
    date: date                  # Gregorian
    status: str
    closure: object = None      # the closing CalendarEvent (CLOSED)
    total: int = 0              # the sheet's records (RECORDED)
    absent: int = 0
    late: int = 0
    excused: int = 0

    @property
    def absences(self):
        return self.absent + self.excused

    @property
    def is_due(self):
        """The class has (or will have today) a lesson: it takes attendance."""

        return self.status != self.CLOSED


def class_day_statuses(start, end, classes, as_of=None, closures=None):
    """
    ``{(class id, Gregorian day): ClassDay}`` for the classes ``classes``
    (instances or ids) over the part of ``start``..``end`` from the cutoff
    to today -- every day on which the timetable plans a lesson for the
    class (:func:`planned_class_days`) or the class has a sheet. A
    (class, day) missing from the result had no lesson.

    * a sheet makes the day **recorded** (whatever the timetable says
      now, as on the supervisor's overview);
    * every planned lesson closed by the calendar: **closed**;
    * otherwise the class was due to take attendance: **missing** once
      the day is over or, today, once its first open bell has ended plus
      the registration grace -- the same moment the analytics engine
      starts expecting that class-day -- and **pending** until then.

    ``as_of`` (default now) decides "today". ``closures`` can be passed
    in when the caller has the range's events already. Three queries
    (timetable, sheets, events), none before the cutoff.
    """

    as_of = as_of or timezone.now()
    today = timezone.localtime(as_of).date()
    _, daily_part = split_range(start, end)
    if daily_part is None:
        return {}
    start, end = daily_part[0], min(daily_part[1] or today, today)
    ids = sorted({getattr(c, "pk", c) for c in classes})
    if start > end or not ids:
        return {}

    days = {}
    for (class_id, day), (event, deadline) in _planned(start, end, ids, closures).items():
        if event is not None:
            days[(class_id, day)] = ClassDay(class_id, day, ClassDay.CLOSED, closure=event)
        elif day < today or as_of >= deadline:
            days[(class_id, day)] = ClassDay(class_id, day, ClassDay.MISSING)
        else:
            days[(class_id, day)] = ClassDay(class_id, day, ClassDay.PENDING)

    for class_id, day, total, absent, late, excused in class_day_tallies(start, end, ids):
        days[(class_id, day)] = ClassDay(
            class_id, day, ClassDay.RECORDED, total=total, absent=absent, late=late, excused=excused,
        )
    return days


def day_error(school_class, value, today=None):
    """
    Why ``school_class`` cannot have a daily sheet on ``value``, as a
    Persian message, or None when it can: from the cutoff to today, in
    the class's academic year, on a day its timetable has a lesson that
    the academic calendar did not close.
    """

    day = calendar.to_gregorian(value)
    today = today or timezone.localdate()

    if day < daily_start():
        return (
            f"حضور و غیاب روزانه از {format_jalali(daily_start())} شروع شده است؛ "
            "حضور و غیاب روزهای پیش از آن در هر جلسه ثبت شده و بایگانی است."
        )
    if day > today:
        return "حضور و غیاب روزهای آینده را نمی‌توان ثبت کرد."
    year = school_class.year
    if not calendar.to_gregorian(year.start_date) <= day <= calendar.to_gregorian(year.end_date):
        return "این روز در سال تحصیلی این کلاس نیست."

    days = planned_class_days(day, day, SchoolClass.objects.filter(pk=school_class.pk))
    if (school_class.pk, day) not in days:
        return "این کلاس در این روز طبق برنامه‌ی هفتگی کلاسی ندارد."
    event = days[(school_class.pk, day)]
    if event is not None:
        return f"کلاس در این روز به‌دلیل «{event.title}» تعطیل است."
    return None


# ----------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------

def sheet_enrollments(school_class, sheet=None):
    """
    The students a sheet lists: the class's active enrollments of its
    academic year, plus anyone already recorded on ``sheet`` (a student
    who left after it was taken keeps their record), by name.
    """

    wanted = Q(
        status=StudentEnrollment.EnrollmentStatus.ACTIVE,
        academic_year_id=school_class.year_id,
    )
    if sheet is not None and sheet.pk:
        wanted |= Q(daily_attendances__sheet=sheet)
    return (
        StudentEnrollment.objects.filter(school_class=school_class)
        .filter(wanted)
        .distinct()
        .select_related("student__user")
        .order_by("student__user__last_name", "student__user__first_name", "pk")
    )


@transaction.atomic
def save_daily_sheet(school_class, value, user, entries):
    """
    Create or edit the sheet of ``school_class`` on ``value``:
    ``(sheet, created)``.

    ``entries`` maps an enrollment id to ``(status or None, description or
    None)``; None leaves the value as it is. On a new sheet, a student
    with no status is «حاضر» (the supporter only marks the exceptions).
    One sheet per class and day (``get_or_create`` on the unique pair, so
    two saves never make two sheets); the sheet row is then locked, so
    two edits of one sheet run one after the other. A record changed on
    an existing sheet gets ``updated_by = user``.
    """

    sheet, created = DailyAttendanceSheet.objects.get_or_create(
        school_class=school_class,
        date=calendar.to_jalali(value),
        defaults={"taken_by": user},
    )
    sheet = DailyAttendanceSheet.objects.select_for_update().get(pk=sheet.pk)
    existing = {record.student_enrollment_id: record for record in sheet.records.all()}

    new = []
    for enrollment in sheet_enrollments(school_class, sheet):
        status, description = entries.get(enrollment.pk, (None, None))
        record = existing.get(enrollment.pk)
        if record is None:
            new.append(DailyAttendance(
                sheet=sheet,
                student_enrollment=enrollment,
                status=status or PRESENT,
                description=description or "",
                updated_by=None if created else user,
            ))
            continue

        status = status or record.status
        description = record.description if description is None else description
        if (status, description) != (record.status, record.description):
            record.status, record.description, record.updated_by = status, description, user
            record.save(update_fields=["status", "description", "updated_by", "updated_at"])

    DailyAttendance.objects.bulk_create(new)
    return sheet, created
