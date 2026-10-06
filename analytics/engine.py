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
   has content and its attendance tallies (one query).
4. Sessions are matched to slots with ``match_sessions`` -- over *all*
   slots, closed ones included, exactly as the calendar sync does, so a
   legacy bell-less session on a closed slot is a conflict for both.

Then each slot gets one outcome:

* a slot of today whose bell has not ended (plus the registration grace)
  is not expected yet, whatever was recorded in it;
* a slot an active event closes is not expected: it is lost to the
  closure (its ``HL`` session is counted as such), and a non-holiday
  session recorded in it is a conflict;
* a slot holding a holiday row that no event closes any more (the sync
  has not run since an event changed) is treated the same way;
* otherwise it is expected, and **held** (an ``HD`` session -- or a
  ``JB`` one: the class met in its regular slot), **cancelled** (``CD``)
  or **unregistered** (no session).

Each session also gets a ``role``: it ``FILLS`` an expected slot, is in a
``CONFLICT`` slot, is ``PENDING`` (today's slot not over yet), or fills no
slot at all (``""``): a compensatory session made up elsewhere, or an
``HD`` / ``CD`` session outside the timetable (legacy data).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from academic_calendar import services as calendar
from school.models import ClassSubject
from teaching.models import SchoolSession, SessionContent

from .definitions import (
    ABSENT,
    CANCELLED,
    HOLIDAY,
    LATE,
    REGISTRATION_GRACE_MINUTES,
)

HELD_SLOT = "held"
CANCELLED_SLOT = "cancelled"
UNREGISTERED_SLOT = "unregistered"

FILLS = "fills"
CONFLICT = "conflict"
PENDING = "pending"

REGISTRATION_GRACE = timedelta(minutes=REGISTRATION_GRACE_MINUTES)

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


def _deadline(day, bell):
    """When a slot of ``day`` at ``bell`` stops being "not over yet"."""

    end = datetime.combine(day, bell.end_time)
    return timezone.make_aware(end, timezone.get_default_timezone()) + REGISTRATION_GRACE


def load_class_subjects(scope):
    """``{pk: ClassSubject}`` of the scope, labels joined in (one query)."""

    return {
        cs.pk: cs
        for cs in ClassSubject.objects.filter(**scope.class_subject_filter())
        .select_related(*CLASS_SUBJECT_RELATED)
    }


def session_rows(scope, with_attendance=True):
    """Every session of the scope in its range (holidays included), one query."""

    sessions = (
        SchoolSession.objects.filter(
            date__gte=calendar.to_jalali(scope.start),
            date__lte=calendar.to_jalali(scope.end),
            **scope.class_subject_filter("class_subject__"),
        )
        .order_by()
        .annotate(has_content=Exists(SessionContent.objects.filter(session=OuterRef("pk"))))
    )
    fields = ["pk", "class_subject_id", "date", "bell_id", "status", "session_number", "has_content"]
    if with_attendance:
        sessions = sessions.annotate(
            attendance_total=Count("attendances"),
            absent=Count("attendances", filter=Q(attendances__status=ABSENT)),
            late=Count("attendances", filter=Q(attendances__status=LATE)),
        )
        fields += ["attendance_total", "absent", "late"]

    rows = []
    for values in sessions.values_list(*fields):
        row = SessionRow(*values)
        row.date = calendar.to_gregorian(row.date)
        rows.append(row)
    return rows


def compute(scope, *, closures=None, with_attendance=True, class_subjects=None):
    """
    The ``EngineResult`` of ``scope``. ``closures`` (a
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

        if slot.date == scope.today and scope.as_of < _deadline(slot.date, slot.bell):
            if session is not None:
                session.role = PENDING
            continue

        event = closures.event_for(slot.date, slot.class_subject.school_class, slot.bell)
        if event is not None:
            if session is not None and session.status != HOLIDAY:
                session.role = CONFLICT
                result.conflicts.append(ConflictSlot(cs_id, slot.date, slot.bell, session, event))
            continue

        if session is not None and session.status == HOLIDAY:
            continue

        if session is None:
            outcome = UNREGISTERED_SLOT
        else:
            session.role = FILLS
            outcome = CANCELLED_SLOT if session.status == CANCELLED else HELD_SLOT
        result.outcomes.append(SlotOutcome(cs_id, slot.date, slot.bell.pk, outcome, session))

    return result
