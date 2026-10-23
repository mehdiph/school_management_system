"""
The slot engine: what the timetable expected in a scope, what happened in
each expected slot, and every session of the scope -- computed once, in a
fixed number of queries, and then grouped any way a page needs
(``analytics.metrics``).

One pass:

1. ``ClassSubject`` rows of the scope, with everything a label needs
   (one query) -- the dimension table every grouping reads.
2. The expected slots (``academic_calendar.services.get_slots``, one
   query): never Thursday/Friday, only active class subjects of active
   classes on the dates they are taught.
3. Every session of the scope in the range, as plain rows, with whether it
   has content and its archived attendance tallies (one query).
4. Sessions are matched to slots with ``match_sessions`` -- over *all*
   slots, closed ones included, exactly as the calendar sync does, so a
   legacy bell-less session on a closed slot is a conflict for both.

Then each slot gets one outcome:

* a slot an active event closes is not expected: it is lost to the
  closure (its ``HL`` session is counted as such), and a non-holiday
  session recorded in it is a conflict (exactly the calendar's
  ``find_conflicts``);
* a slot of today whose bell has not ended (plus the registration grace)
  is not expected yet, whatever was recorded in it;
* a slot holding a holiday row that no event closes any more (the sync
  has not run since an event changed) is treated the same way;
* otherwise it is expected, and **held** (an ``HD`` session -- or a
  ``JB`` one: the class met in its regular slot), **cancelled** (``CD``)
  or **unregistered** (no session).

Each session also gets a ``role``: it ``FILLS`` an expected slot, is in a
``CONFLICT`` slot, is ``PENDING`` (today's slot not over yet), or fills no
slot at all (``""``): a compensatory session made up elsewhere, or an
``HD`` / ``CD`` session outside the timetable (legacy data).

Attendance comes from ``attendance.services``, which reads the teacher's
per-session archive before ``settings.ATTENDANCE_DAILY_START_DATE`` and
the supporters' daily sheets from it on:

* before the cutoff, each delivered session ``takes_attendance`` and
  carries its own tallies;
* from the cutoff on, attendance belongs to a class and a day: one
  ``ClassDayRow`` per **expected class-day** (a day on which the class has
  at least one expected slot -- open, and for today over plus the grace)
  and per day with a sheet, with the sheet's tallies (one query).
"""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import DateField, Exists, OuterRef
from django.db.models.functions import Cast

from academic_calendar import services as calendar
from attendance import services as attendance
from school.models import ClassSubject
from teaching.models import SchoolSession, SessionContent

from .definitions import (
    CANCELLED,
    DELIVERED_STATUSES,
    HOLIDAY,
    slot_deadline,
)

HELD_SLOT = "held"
CANCELLED_SLOT = "cancelled"
UNREGISTERED_SLOT = "unregistered"

FILLS = "fills"
CONFLICT = "conflict"
PENDING = "pending"

#: What every grouping and label needs from a class subject.
CLASS_SUBJECT_RELATED = (
    "subject",
    "school_class__grade",
    "school_class__branch",
    "teacher_assignment__teacher__staff__user",
)


@dataclass(slots=True)
class SessionRow:
    """One ``SchoolSession`` of the scope, as the metrics need it."""

    pk: int
    class_subject_id: int
    date: date              # Gregorian
    bell_id: int | None
    status: str
    session_number: int | None
    has_content: bool
    attendance_total: int = 0
    absent: int = 0
    late: int = 0
    role: str = ""
    # a delivered session before the cutoff: attendance was taken in it
    takes_attendance: bool = False


@dataclass(slots=True)
class ClassDayRow:
    """Daily attendance of one class on one day (from the cutoff on)."""

    school_class_id: int
    date: date              # Gregorian
    expected: bool = False  # the class had an expected slot that day
    has_sheet: bool = False
    total: int = 0
    absent: int = 0
    late: int = 0
    excused: int = 0


@dataclass(slots=True)
class SlotOutcome:
    """An expected slot and what happened in it."""

    class_subject_id: int
    date: date
    bell_id: int
    outcome: str
    session: SessionRow | None = None


@dataclass(slots=True)
class ConflictSlot:
    """A non-holiday session recorded for a slot an active event closes."""

    class_subject_id: int
    date: date
    bell: object
    session: SessionRow
    event: object


@dataclass
class EngineResult:
    scope: object
    class_subjects: dict = field(default_factory=dict)
    outcomes: list = field(default_factory=list)
    sessions: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    class_days: list = field(default_factory=list)

    @property
    def classes(self):
        """``{pk: SchoolClass}`` of the scope's class subjects."""

        return {cs.school_class_id: cs.school_class for cs in self.class_subjects.values()}


def _deadline(day, bell):
    """When a slot of ``day`` at ``bell`` stops being "not over yet"."""

    return slot_deadline(day, bell.end_time)


def load_class_subjects(scope):
    """``{pk: ClassSubject}`` of the scope, labels joined in (one query)."""

    return {
        cs.pk: cs
        for cs in ClassSubject.objects.filter(**scope.class_subject_filter())
        .select_related(*CLASS_SUBJECT_RELATED)
        .defer(*calendar.UNUSED_JALALI_FIELDS)
    }


def session_rows(scope, with_attendance=True):
    """
    Every session of the scope in its range (holidays included): one
    query, plus one for the archived attendance tallies of the range's
    part before the cutoff (none when it is all after). The tallies are a
    separate grouped aggregate over the attendance records rather than a
    join on the sessions: on a year of a whole school (a million records)
    that is about twice as fast.
    """

    in_range = {
        "date__gte": calendar.to_jalali(scope.start),
        "date__lte": calendar.to_jalali(scope.end),
        **scope.class_subject_filter("class_subject__"),
    }
    sessions = (
        SchoolSession.objects.filter(**in_range)
        .order_by()
        .annotate(
            # Read as a plain (Gregorian) date: a jDateField value becomes a
            # jdatetime.date, whose constructor queries the locale -- the
            # slowest part of reading a year of sessions.
            day=Cast("date", output_field=DateField()),
            has_content=Exists(SessionContent.objects.filter(session=OuterRef("pk"))),
        )
        .values_list("pk", "class_subject_id", "day", "bell_id", "status", "session_number", "has_content")
    )
    rows = [SessionRow(*values) for values in sessions]

    cutoff = attendance.daily_start()
    for row in rows:
        row.takes_attendance = row.status in DELIVERED_STATUSES and row.date < cutoff

    if with_attendance and rows:
        by_pk = {row.pk: row for row in rows}
        tallies = attendance.session_tallies(
            scope.start, scope.end, **scope.class_subject_filter("session__class_subject__")
        )
        for session_id, total, absent, late in tallies:
            row = by_pk.get(session_id)
            if row is not None:
                row.attendance_total, row.absent, row.late = total, absent, late
    return rows


def class_day_rows(scope, result):
    """
    Daily attendance per class and day, from the cutoff on: every expected
    class-day (a day with at least one expected slot of the class in
    ``result.outcomes``) and every day with a sheet -- today's sheet is
    taken in the morning, before any slot of the day is expected -- with
    the sheet's tallies. One query (none before the cutoff).
    """

    cutoff = attendance.daily_start()
    class_subjects = result.class_subjects
    rows = {}
    for outcome in result.outcomes:
        if outcome.date >= cutoff:
            class_id = class_subjects[outcome.class_subject_id].school_class_id
            if (class_id, outcome.date) not in rows:
                rows[(class_id, outcome.date)] = ClassDayRow(class_id, outcome.date, expected=True)

    class_ids = {cs.school_class_id for cs in class_subjects.values()}
    for class_id, day, total, absent, late, excused in attendance.class_day_tallies(
        scope.start, scope.end, class_ids
    ):
        row = rows.get((class_id, day))
        if row is None:
            row = rows[(class_id, day)] = ClassDayRow(class_id, day)
        row.has_sheet = True
        row.total, row.absent, row.late, row.excused = total, absent, late, excused
    return sorted(rows.values(), key=lambda row: (row.date, row.school_class_id))


def compute(scope, *, closures=None, with_attendance=True, class_subjects=None):
    """
    The ``EngineResult`` of ``scope``; without attendance (no archived
    tallies, no class-days) when ``with_attendance`` is False. ``closures`` (a
    ``calendar.Closures`` covering the range) and ``class_subjects`` (from
    :func:`load_class_subjects`) can be passed in when the caller already
    has them, so a page that needs them elsewhere loads them once.
    """

    if class_subjects is None:
        class_subjects = load_class_subjects(scope)
    result = EngineResult(scope=scope, class_subjects=class_subjects)
    if scope.is_empty:
        return result

    slots = calendar.get_slots(
        scope.start, scope.end, **scope.class_subject_filter("class_subject__")
    )
    if closures is None:
        closures = calendar.Closures.between(scope.start, scope.end, academic_year=scope.year)
    result.sessions = session_rows(scope, with_attendance)
    matched = calendar.match_sessions([slot.key for slot in slots], result.sessions)

    for slot in slots:
        session = matched.get(slot.key)
        cs_id = slot.class_subject.pk

        # Closed first: a closed slot is never expected, and a session in
        # it is a conflict at once -- as find_conflicts reports it.
        event = closures.event_for(slot.date, slot.class_subject.school_class, slot.bell)
        if event is not None:
            if session is not None and session.status != HOLIDAY:
                session.role = CONFLICT
                result.conflicts.append(ConflictSlot(cs_id, slot.date, slot.bell, session, event))
            continue

        if slot.date == scope.today and scope.as_of < _deadline(slot.date, slot.bell):
            if session is not None:
                session.role = PENDING
            continue

        if session is not None and session.status == HOLIDAY:
            continue

        if session is None:
            outcome = UNREGISTERED_SLOT
        else:
            session.role = FILLS
            outcome = CANCELLED_SLOT if session.status == CANCELLED else HELD_SLOT
        result.outcomes.append(SlotOutcome(cs_id, slot.date, slot.bell.pk, outcome, session))

    if with_attendance:
        result.class_days = class_day_rows(scope, result)
    return result
