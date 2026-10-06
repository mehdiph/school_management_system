"""
The academic calendar: which days and slots are closed, and the holiday
sessions that mirror them.

This module is the only place that decides whether a class is held on a
date. Views, selectors and templates ask it (``is_working_day``,
``is_closed``, ``Closures``, ``get_slots``); none of them computes a
holiday on its own.

Rules
-----
* Thursday and Friday are never working days, and dates outside the
  academic year are not either (``is_working_day``). An event whose range
  covers a Thursday or Friday simply has no effect on those days.
* A ``CalendarEvent`` closes the slots of the classes in its scope:
  same academic year, ``branches`` / ``grades`` (empty = all), and
  ``bells`` (empty = the whole day).
* For every expected slot (``get_slots``) that an active event closes,
  ``sync_cancelled_sessions`` makes sure a ``SchoolSession`` with status
  ``HOLIDAY`` exists for exactly that slot (class subject + date + bell),
  linked to the event and flagged ``is_auto_created``. Two bells of one
  subject on a closed day are two holiday sessions.
* A held (or any non-holiday) session already recorded for a closed slot
  is never touched: it is reported as a conflict.
* Holiday sessions no slot needs any more (event deactivated or edited,
  timetable changed, class subject deactivated) are removed -- but only
  auto-created ones without attendance or content.

Dates: functions accept ``datetime.date`` or ``jdatetime.date`` (what
``jDateField`` holds) and work in Gregorian internally.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import jdatetime
from django.db import transaction
from django.db.models import Q

from scheduling.models import ClassSchedule
from scheduling.utils import DateBeforeAcademicYearError, get_week_cycle, persian_weekday
from school.models import AcademicYear, ClassSubject

from .models import CalendarEvent

#: ``persian_weekday`` values (Saturday=0) of the weekend.
THURSDAY = 5
FRIDAY = 6
WEEKEND = frozenset({THURSDAY, FRIDAY})


# ----------------------------------------------------------------------
# Dates
# ----------------------------------------------------------------------

def to_gregorian(value):
    """``date`` / ``datetime`` / ``jdatetime.date`` -> ``datetime.date``."""

    if isinstance(value, (jdatetime.date, jdatetime.datetime)):
        value = value.togregorian()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Expected a date, got {value!r}")


def to_jalali(value):
    """``date`` / ``jdatetime.date`` -> ``jdatetime.date`` (for jDateField lookups)."""

    if isinstance(value, jdatetime.date):
        return value
    return jdatetime.date.fromgregorian(date=to_gregorian(value))


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_jalali_date(value):
    """
    ``"1405/07/01"`` / ``"1405-7-1"`` (Persian, Arabic or Latin digits) ->
    ``jdatetime.date``; ``ValueError`` when it is not a valid Jalali date.
    """

    text = str(value or "").strip().translate(_DIGITS).replace("-", "/")
    parts = text.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"not a Jalali date: {value!r}")
    year, month, day = (int(part) for part in parts)
    return jdatetime.date(year, month, day)  # raises ValueError when invalid


def date_range(start, end):
    """Every Gregorian day from ``start`` to ``end``, both inclusive."""

    day, end = to_gregorian(start), to_gregorian(end)
    while day <= end:
        yield day
        day += timedelta(days=1)


def is_weekend(value):
    """Thursday or Friday."""

    return persian_weekday(to_gregorian(value)) in WEEKEND


def academic_year_for(value):
    """The academic year ``value`` falls in (the current one wins a tie), or None."""

    day = to_jalali(value)
    return (
        AcademicYear.objects
        .filter(start_date__lte=day, end_date__gte=day)
        .order_by("-is_current", "-start_date")
        .first()
    )


def _in_year(day, academic_year):
    return (
        to_gregorian(academic_year.start_date) <= day <= to_gregorian(academic_year.end_date)
    )


def is_working_day(value, academic_year=None):
    """
    True unless ``value`` is a Thursday or Friday, or outside the academic
    year (``academic_year``, else the year containing it).
    """

    day = to_gregorian(value)
    if is_weekend(day):
        return False
    if academic_year is None:
        return academic_year_for(day) is not None
    return _in_year(day, academic_year)


def get_week_type(value, academic_year=None):
    """
    ``ClassSchedule.WeekTypeChoices.WEEK_ONE`` / ``WEEK_TWO`` for ``value``
    (see ``scheduling.utils.get_week_cycle``), or None before the academic
    year starts / when no year contains it.
    """

    academic_year = academic_year or academic_year_for(value)
    if academic_year is None:
        return None
    try:
        return get_week_cycle(value, academic_year)
    except DateBeforeAcademicYearError:
        return None


# ----------------------------------------------------------------------
# Events and closures
# ----------------------------------------------------------------------

def get_events(start, end, branch=None, grade=None, academic_year=None, include_inactive=False):
    """
    Events with at least one day in ``start``..``end`` whose scope includes
    ``branch`` / ``grade`` (an empty scope includes everything), with
    their scope prefetched. Active ones only unless ``include_inactive``.
    """

    events = CalendarEvent.objects.overlapping(to_jalali(start), to_jalali(end))
    if not include_inactive:
        events = events.active()
    if academic_year is not None:
        events = events.filter(academic_year=academic_year)
    if branch is not None:
        events = events.filter(Q(branches=branch) | Q(branches__isnull=True))
    if grade is not None:
        events = events.filter(Q(grades=grade) | Q(grades__isnull=True))
    return (
        events.distinct()
        .select_related("academic_year")
        .prefetch_related("branches", "grades", "bells")
        .order_by("start_date", "pk")
    )


@dataclass(frozen=True)
class _Scope:
    event: CalendarEvent
    year_id: int
    start: date
    end: date
    branch_ids: frozenset
    grade_ids: frozenset
    bell_ids: frozenset

    @classmethod
    def of(cls, event):
        return cls(
            event=event,
            year_id=event.academic_year_id,
            start=to_gregorian(event.start_date),
            end=to_gregorian(event.end_date),
            branch_ids=frozenset(b.pk for b in event.branches.all()),
            grade_ids=frozenset(g.pk for g in event.grades.all()),
            bell_ids=frozenset(b.pk for b in event.bells.all()),
        )

    def covers(self, day, school_class, bell_id=None):
        """
        Does the event close ``school_class`` on ``day`` -- at ``bell_id``,
        or, with ``bell_id=None``, for the whole day?
        """

        if not (self.start <= day <= self.end) or is_weekend(day):
            # Thursday / Friday are not working days: no event has any
            # effect on them.
            return False
        if school_class.year_id != self.year_id:
            return False
        if self.branch_ids and school_class.branch_id not in self.branch_ids:
            return False
        if self.grade_ids and school_class.grade_id not in self.grade_ids:
            return False
        if bell_id is None:
            return not self.bell_ids
        return not self.bell_ids or bell_id in self.bell_ids


class Closures:
    """
    The active events of a date range, loaded once (two queries) and
    answered in memory -- for pages that check many cells, so they never
    query per cell. ``event_for`` returns the event closing a slot, the
    earliest-starting one when several overlap.
    """

    def __init__(self, events):
        self.scopes = [_Scope.of(event) for event in events]

    @classmethod
    def between(cls, start, end, academic_year=None, branch=None, grade=None):
        return cls(get_events(start, end, branch=branch, grade=grade, academic_year=academic_year))

    def event_for(self, value, school_class, bell=None):
        day = to_gregorian(value)
        bell_id = getattr(bell, "pk", bell)
        for scope in self.scopes:
            if scope.covers(day, school_class, bell_id):
                return scope.event
        return None

    def is_closed(self, value, school_class, bell=None):
        return self.event_for(value, school_class, bell) is not None

    def events(self, start, end):
        """The loaded events with at least one day in ``start``..``end``, by start date."""

        start, end = to_gregorian(start), to_gregorian(end)
        return [
            scope.event for scope in sorted(self.scopes, key=lambda s: (s.start, s.event.pk))
            if scope.start <= end and scope.end >= start
        ]

    def days(self, start=None, end=None):
        """The working days (Saturday..Wednesday) at least one event covers, sorted."""

        start = to_gregorian(start) if start else None
        end = to_gregorian(end) if end else None
        days = set()
        for scope in self.scopes:
            first = max(scope.start, start) if start else scope.start
            last = min(scope.end, end) if end else scope.end
            days.update(day for day in date_range(first, last) if not is_weekend(day))
        return sorted(days)


def closing_event(value, school_class, bell=None):
    """The active event that closes ``school_class`` on ``value`` (at ``bell``), or None."""

    return Closures.between(value, value, academic_year=school_class.year_id).event_for(
        value, school_class, bell
    )


def is_closed(value, school_class, bell=None):
    """
    Is ``school_class`` closed on ``value``? With ``bell``: at that bell
    (a whole-day closure or one whose bell scope includes it). Without:
    for the whole day (an event with no bell scope). Thursday, Friday and
    days outside the class's academic year are not working days at all;
    ask ``is_working_day`` for those.
    """

    return closing_event(value, school_class, bell) is not None


# ----------------------------------------------------------------------
# Expected slots
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class ExpectedSlot:
    """One lesson the timetable plans: a class subject at a bell on a date."""

    class_subject: ClassSubject
    date: date          # Gregorian
    bell: object        # scheduling.Bell
    schedule: ClassSchedule

    @property
    def key(self):
        return (self.class_subject.pk, self.date, self.bell.pk)


def get_slots(start, end, days=None, **filters):
    """
    The slots the timetable plans from ``start`` to ``end`` (both
    inclusive): ``[ExpectedSlot, ...]`` ordered by date, bell, class.

    A ``ClassSchedule`` row gives a slot on a date when the date is a
    working day of its class's academic year (never Thursday/Friday), its
    weekday and rotation week (``get_week_type``; BOTH matches either)
    match, its class subject and class are active, the class subject is
    teaching on that date (``start_date``..``end_date``) and its bell is
    active. Closures are *not* removed: see ``Closures``.

    ``days`` narrows the dates to that subset; ``filters`` are extra
    ``ClassSchedule`` lookups (e.g. ``class_subject__in=...``,
    ``class_subject__teacher_assignment__teacher=...``). One query.
    """

    start, end = to_gregorian(start), to_gregorian(end)
    wanted = (
        sorted(d for d in (to_gregorian(day) for day in days) if start <= d <= end)
        if days is not None else list(date_range(start, end))
    )
    wanted = [day for day in wanted if not is_weekend(day)]
    if not wanted:
        return []

    first, last = to_jalali(wanted[0]), to_jalali(wanted[-1])
    schedules = (
        ClassSchedule.objects.filter(**filters)
        .filter(
            class_subject__is_active=True,
            class_subject__school_class__is_active=True,
            class_subject__start_date__lte=last,
            class_subject__end_date__gte=first,
            class_subject__school_class__year__start_date__lte=last,
            class_subject__school_class__year__end_date__gte=first,
            bell__is_active=True,
        )
        .exclude(day_of_week=ClassSchedule.DayChoices.THURSDAY)
        .select_related(
            "bell",
            "class_subject__subject",
            "class_subject__school_class__year",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
            "class_subject__teacher_assignment__teacher__staff__user",
        )
    )

    by_weekday = defaultdict(list)
    for schedule in schedules:
        by_weekday[schedule.day_of_week].append(schedule)

    week_types = {}
    both = ClassSchedule.WeekTypeChoices.BOTH
    slots = []
    for day in wanted:
        for schedule in by_weekday.get(persian_weekday(day), ()):
            class_subject = schedule.class_subject
            year = class_subject.school_class.year
            if not _in_year(day, year):
                continue
            if not (
                to_gregorian(class_subject.start_date) <= day <= to_gregorian(class_subject.end_date)
            ):
                continue
            key = (year.pk, day)
            if key not in week_types:
                week_types[key] = get_week_type(day, year)
            week_type = week_types[key]
            if week_type is None or schedule.week_type not in (week_type, both):
                continue
            slots.append(ExpectedSlot(class_subject, day, schedule.bell, schedule))

    slots.sort(key=lambda s: (s.date, s.bell.order, s.class_subject.pk))
    return slots


def match_sessions(slot_keys, sessions):
    """
    Which recorded session fills which slot: ``{slot key: session}``.

    ``slot_keys`` are ``(class_subject_id, Gregorian date, bell_id)``
    tuples (``ExpectedSlot.key``) in teaching order -- by date, then bell
    order; ``sessions`` are anything with ``pk``, ``class_subject_id``,
    ``date``, ``bell_id``, ``status`` and ``session_number``.

    A session with a bell fills exactly its own slot. A legacy session
    recorded before sessions had a bell fills that day's first slot (in
    bell order) no session with a bell fills, several of them in their
    number order: the count fallback. Holiday rows always have a bell, so
    a bell-less holiday is ignored. Sessions that fill no slot are simply
    not in the result.

    This is the one place the fallback is written: the calendar sync and
    conflicts, the supervisor's missing-session list, the teacher's
    lessons of today and the analytics engine all call it.
    """

    slot_keys = list(slot_keys)
    wanted = set(slot_keys)
    matched = {}
    legacy = defaultdict(list)          # (class subject, date) -> bell-less sessions

    for session in sessions:
        day = to_gregorian(session.date)
        if session.bell_id is not None:
            key = (session.class_subject_id, day, session.bell_id)
            if key in wanted:
                matched[key] = session
        elif session.status != "HL":
            legacy[(session.class_subject_id, day)].append(session)

    if legacy:
        free = defaultdict(list)
        for key in slot_keys:
            if key not in matched:
                free[key[:2]].append(key)
        for day_key, rows in legacy.items():
            rows = sorted(rows, key=lambda s: (s.session_number or 0, s.pk))
            for key, session in zip(free.get(day_key, ()), rows):
                matched[key] = session

    return matched


def count_open_slots(ranges):
    """
    ``{class_subject_id: (start, end)}`` -> ``{class_subject_id: n}``: how
    many expected slots (``get_slots``) each class subject has in its own
    range that no active event closes -- what "sessions the timetable
    planned" means once holidays are taken out. Two bells of the same
    subject on one day are two. Fixed number of queries.
    """

    ranges = {
        pk: (to_gregorian(start), to_gregorian(end))
        for pk, (start, end) in ranges.items()
        if start is not None and end is not None and to_gregorian(start) <= to_gregorian(end)
    }
    counts = {pk: 0 for pk in ranges}
    if not ranges:
        return counts

    start = min(r[0] for r in ranges.values())
    end = max(r[1] for r in ranges.values())
    closures = Closures.between(start, end)
    for slot in get_slots(start, end, class_subject_id__in=list(ranges)):
        first, last = ranges[slot.class_subject.pk]
        if first <= slot.date <= last and not closures.is_closed(
            slot.date, slot.class_subject.school_class, slot.bell
        ):
            counts[slot.class_subject.pk] += 1
    return counts


# ----------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Conflict:
    """A non-holiday session recorded for a slot an active event closes."""

    session: object      # teaching.SchoolSession
    event: CalendarEvent
    date: date
    bell: object         # scheduling.Bell, or None for a legacy session without one


@dataclass
class SyncResult:
    created: int = 0
    removed: int = 0
    updated: int = 0
    #: Holiday sessions no event needs any more, kept because they have
    #: attendance or content.
    kept: int = 0
    conflicts: list = field(default_factory=list)

    def __add__(self, other):
        return SyncResult(
            created=self.created + other.created,
            removed=self.removed + other.removed,
            updated=self.updated + other.updated,
            kept=self.kept + other.kept,
            conflicts=self.conflicts + other.conflicts,
        )


@dataclass
class _Plan:
    closed: dict            # slot key -> (ExpectedSlot, CalendarEvent)
    by_slot: dict           # slot key -> SchoolSession
    legacy_taken: set       # slot keys a bell-less session is counted against
    holidays: list          # existing auto holiday sessions in range
    conflicts: list


def _plan(start, end, class_subject_ids=None, academic_year=None):
    """Everything the sync (and the conflicts page) needs, read only."""

    from teaching.models import SchoolSession

    start, end = to_gregorian(start), to_gregorian(end)
    closures = Closures.between(start, end, academic_year=academic_year)

    in_range = SchoolSession.objects.filter(
        date__gte=to_jalali(start), date__lte=to_jalali(end)
    )
    filters = {}
    if class_subject_ids is not None:
        in_range = in_range.filter(class_subject_id__in=class_subject_ids)
        filters["class_subject_id__in"] = class_subject_ids
    if academic_year is not None:
        in_range = in_range.filter(class_subject__school_class__year=academic_year)
        filters["class_subject__school_class__year"] = academic_year

    # Only days with an event or an existing holiday row can change, so
    # only the sessions of those days are loaded -- not a whole year's.
    holiday_days = {
        to_gregorian(day) for day in
        in_range.filter(status=SchoolSession.Status.HOLIDAY, is_auto_created=True)
        .order_by().values_list("date", flat=True).distinct()
    }
    days = set(closures.days(start, end)) | holiday_days
    if not days:
        return _Plan(closed={}, by_slot={}, legacy_taken=set(), holidays=[], conflicts=[])

    sessions = list(
        in_range.filter(date__in=sorted(to_jalali(day) for day in days)).select_related(
            "bell",
            "calendar_event",
            "class_subject__subject",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
            "class_subject__teacher_assignment__teacher__staff__user",
        )
    )
    holidays = [
        s for s in sessions
        if s.status == SchoolSession.Status.HOLIDAY and s.is_auto_created
    ]
    slots = get_slots(start, end, days=days, **filters)

    by_slot = {
        (session.class_subject_id, to_gregorian(session.date), session.bell_id): session
        for session in sessions
        if session.bell_id is not None
    }
    # A legacy session (recorded before sessions had a bell) fills that
    # day's slots in bell order: match_sessions' count fallback.
    legacy_taken = {
        key: session
        for key, session in match_sessions([slot.key for slot in slots], sessions).items()
        if session.bell_id is None
    }

    closed, conflicts = {}, []
    for slot in slots:
        event = closures.event_for(slot.date, slot.class_subject.school_class, slot.bell)
        if event is None:
            continue
        closed[slot.key] = (slot, event)
        session = by_slot.get(slot.key) or legacy_taken.get(slot.key)
        if session is not None and session.status != SchoolSession.Status.HOLIDAY:
            conflicts.append(Conflict(session=session, event=event, date=slot.date, bell=slot.bell))

    return _Plan(
        closed=closed,
        by_slot=by_slot,
        legacy_taken=set(legacy_taken),
        holidays=holidays,
        conflicts=conflicts,
    )


def sync_cancelled_sessions(start, end, event=None, class_subjects=None, academic_year=None):
    """
    Makes the holiday sessions from ``start`` to ``end`` match the active
    events, idempotently, and returns a ``SyncResult``:

    * ``created`` -- holiday sessions added for closed slots that had none;
    * ``updated`` -- holiday sessions moved to another event (the one that
      closed them was deactivated, another still does);
    * ``removed`` -- auto-created holiday sessions no slot needs any more,
      deleted because they have no attendance and no content;
    * ``kept`` -- such sessions kept because they do have some;
    * ``conflicts`` -- non-holiday sessions recorded for closed slots,
      left as they are.

    ``event`` narrows the range to that event's dates (all events still
    apply there); ``class_subjects`` (ids or objects) and
    ``academic_year`` narrow what is looked at. Running it twice changes
    nothing the second time.

    Holiday rows are written with ``bulk_create`` (they take no number,
    and every value is checked here); the affected class subjects are
    locked first, so a teacher recording a session for the same slot at
    the same moment waits for the sync and then gets the duplicate-slot
    error.
    """

    from teaching.models import SchoolSession

    start, end = to_gregorian(start), to_gregorian(end)
    if event is not None:
        start = max(start, to_gregorian(event.start_date))
        end = min(end, to_gregorian(event.end_date))
    if start > end:
        return SyncResult()

    class_subject_ids = None
    if class_subjects is not None:
        class_subject_ids = sorted({getattr(cs, "pk", cs) for cs in class_subjects})
        if not class_subject_ids:
            return SyncResult()

    with transaction.atomic():
        lock = ClassSubject.objects.select_for_update().order_by("pk")
        if class_subject_ids is not None:
            lock = lock.filter(pk__in=class_subject_ids)
        elif academic_year is not None:
            lock = lock.filter(school_class__year=academic_year)
        else:
            lock = lock.filter(
                school_class__year__start_date__lte=to_jalali(end),
                school_class__year__end_date__gte=to_jalali(start),
            )
        list(lock.values_list("pk", flat=True))

        plan = _plan(start, end, class_subject_ids, academic_year)
        result = SyncResult(conflicts=plan.conflicts)

        to_create = []
        for key, (slot, closing) in plan.closed.items():
            session = plan.by_slot.get(key)
            if session is None and key not in plan.legacy_taken:
                to_create.append(SchoolSession(
                    class_subject=slot.class_subject,
                    date=to_jalali(slot.date),
                    bell=slot.bell,
                    status=SchoolSession.Status.HOLIDAY,
                    calendar_event=closing,
                    is_auto_created=True,
                    session_number=None,
                ))
            elif (
                session is not None
                and session.status == SchoolSession.Status.HOLIDAY
                and session.calendar_event_id != closing.pk
            ):
                session.calendar_event = closing
                SchoolSession.objects.filter(pk=session.pk).update(calendar_event=closing)
                result.updated += 1

        if to_create:
            SchoolSession.objects.bulk_create(to_create)
            result.created = len(to_create)

        stale = [
            session.pk for session in plan.holidays
            if (session.class_subject_id, to_gregorian(session.date), session.bell_id)
            not in plan.closed
        ]
        if stale:
            removable = SchoolSession.objects.filter(
                pk__in=stale,
                attendances__isnull=True,
                session_contents__isnull=True,
            ).values_list("pk", flat=True)
            removable = list(removable)
            SchoolSession.objects.filter(pk__in=removable).delete()
            result.removed = len(removable)
            result.kept = len(stale) - len(removable)

    return result


def find_conflicts(start=None, end=None, academic_year=None, event=None):
    """
    Non-holiday sessions recorded for slots an active event closes (read
    only), for the admin's conflicts page. Defaults to the whole of
    ``academic_year`` (else the current year), or ``event``'s range.
    """

    if event is not None:
        academic_year = event.academic_year
        start = start or event.start_date
        end = end or event.end_date
    if academic_year is None:
        academic_year = AcademicYear.objects.filter(is_current=True).first()
        if academic_year is None:
            return []
    start = start or academic_year.start_date
    end = end or academic_year.end_date

    conflicts = _plan(start, end, academic_year=academic_year).conflicts
    if event is not None:
        conflicts = [c for c in conflicts if c.event.pk == event.pk]
    return conflicts


def event_impact(event):
    """``(holiday sessions linked to event, its conflicts)`` -- shown after saving it."""

    if not event.is_active:
        return event.sessions.count(), []
    return event.sessions.count(), find_conflicts(event=event)


# ----------------------------------------------------------------------
# Writes that must be followed by a sync
# ----------------------------------------------------------------------

def _event_range(event):
    return to_gregorian(event.start_date), to_gregorian(event.end_date)


def sync_event(event, previous_range=None):
    """
    Re-syncs everything ``event`` affects (now, and before an edit:
    ``previous_range`` = its old ``(start, end)``). Call after the event
    *and its many-to-many scope* are saved -- the admin calls it from
    ``save_related``.
    """

    ranges = [_event_range(event)]
    if previous_range is not None:
        ranges.append(tuple(to_gregorian(d) for d in previous_range))
    start = min(r[0] for r in ranges)
    end = max(r[1] for r in ranges)
    return sync_cancelled_sessions(start, end, academic_year=event.academic_year)


def deactivate_event(event):
    """Soft-deletes ``event`` and removes the holiday sessions only it needed."""

    with transaction.atomic():
        event.is_active = False
        event.save(update_fields=["is_active", "updated_at"])
        return sync_event(event)


def create_closure(*, academic_year, title, start_date, end_date=None, event_type=None,
                   branches=(), grades=(), bells=(), description="", created_by=None):
    """Creates an event with its scope and syncs it, in one transaction."""

    with transaction.atomic():
        event = CalendarEvent(
            academic_year=academic_year,
            title=title,
            event_type=event_type or CalendarEvent.EventType.UNPLANNED_CLOSURE,
            start_date=start_date,
            end_date=end_date or start_date,
            description=description,
            created_by=created_by,
        )
        event.full_clean()
        event.save()
        event.branches.set(branches)
        event.grades.set(grades)
        event.bells.set(bells)
        return event, sync_event(event)


def import_events(plan, created_by=None):
    """
    Creates every row of a valid ``importer.ImportPlan`` and syncs the
    sessions of the whole imported range, in one transaction: if anything
    fails, nothing is saved. Returns ``(events, SyncResult)``.
    """

    if not plan.is_valid:
        raise ValueError("Only a plan without errors can be imported.")

    with transaction.atomic():
        events = []
        for row in plan.rows:
            event = CalendarEvent(
                academic_year=plan.academic_year,
                title=row.title,
                event_type=row.event_type,
                start_date=row.start_date,
                end_date=row.end_date,
                description=row.description,
                created_by=created_by,
            )
            event.full_clean()
            event.save()
            event.branches.set(row.branches)
            event.grades.set(row.grades)
            event.bells.set(row.bells)
            events.append(event)

        result = sync_cancelled_sessions(
            min(row.start_date for row in plan.rows),
            max(row.end_date for row in plan.rows),
            academic_year=plan.academic_year,
        )
    return events, result


def sync_class_subjects(class_subject_ids):
    """
    Re-syncs the holiday sessions of these class subjects over their
    academic years, after a timetable or class subject change. Only days
    that have an event or an existing holiday session are looked at.
    """

    class_subject_ids = sorted(set(class_subject_ids) - {None})
    if not class_subject_ids:
        return SyncResult()

    result = SyncResult()
    years = AcademicYear.objects.filter(
        schoolclass__class_subjects__pk__in=class_subject_ids
    ).distinct()
    for year in years:
        ids = list(
            ClassSubject.objects.filter(pk__in=class_subject_ids, school_class__year=year)
            .values_list("pk", flat=True)
        )
        result += sync_cancelled_sessions(
            year.start_date, year.end_date, class_subjects=ids, academic_year=year
        )
    return result
