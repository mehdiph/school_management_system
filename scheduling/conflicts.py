"""
Timetable conflict rules -- the one place that decides whether a set of
``ClassSchedule`` slots may coexist.

Two slots clash when all of these hold:

* same academic year, same ``day_of_week`` and same ``Bell`` (bells are
  global, so the same bell is the same time in every branch);
* their week types overlap: "every week" (BOTH) overlaps week 1 and
  week 2; week 1 and week 2 never overlap each other;
* both class subjects are active and their teaching windows
  (``start_date`` .. ``end_date``, ``None`` = open-ended) overlap;
* and either they are in the same class (*class conflict*) or they are
  taught by the same ``TeacherProfile`` (*teacher conflict*). Teachers
  are compared by profile, not by ``TeacherAssignment``: one teacher
  has one assignment per branch, and those still clash.

Every write path goes through here: ``ClassSchedule.clean()`` /
``save()``, the ``ClassScheduleQuerySet`` bulk methods, ``ClassSubject``
(changing a subject's teacher, dates or active flag moves its slots too)
and the admin timetable grid (``scheduling.timetable``).

Writers must call :func:`lock_for_schedule_change` inside their
transaction *before* checking, so two admins saving at once cannot both
pass the check and then both commit: whoever comes second waits for the
first to commit and then sees its rows.
"""

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Q

from .models.class_schedule import ClassSchedule

WeekType = ClassSchedule.WeekTypeChoices

#: Week types each week type shares at least one real week with.
_OVERLAPPING_WEEKS = {
    WeekType.WEEK_ONE: frozenset({WeekType.WEEK_ONE, WeekType.BOTH}),
    WeekType.WEEK_TWO: frozenset({WeekType.WEEK_TWO, WeekType.BOTH}),
    WeekType.BOTH: frozenset({WeekType.WEEK_ONE, WeekType.WEEK_TWO, WeekType.BOTH}),
}

#: ``ClassSchedule`` fields that move a slot in the timetable.
CONFLICT_FIELDS = frozenset({"class_subject", "day_of_week", "week_type", "bell"})

CLASS_CONFLICT = "class"
TEACHER_CONFLICT = "teacher"

#: related rows needed to word a conflict message
SCHEDULE_RELATED = (
    "bell",
    "class_subject__subject",
    "class_subject__school_class__grade",
    "class_subject__school_class__branch",
    "class_subject__teacher_assignment",
)


def overlapping_week_types(week_type):
    return _OVERLAPPING_WEEKS[week_type]


def week_types_overlap(a, b):
    return b in _OVERLAPPING_WEEKS[a]


def date_ranges_overlap(start_a, end_a, start_b, end_b):
    """Inclusive ranges; ``None`` means open-ended on that side."""

    return (
        (start_a is None or end_b is None or start_a <= end_b)
        and (start_b is None or end_a is None or start_b <= end_a)
    )


def class_label(school_class):
    return f"{school_class.grade.name} - {school_class.section}"


def _when(shared_week):
    when = "در همین زنگ"
    if shared_week is not None:
        when += f" ({WeekType(shared_week).label})"
    return when


def class_conflict_message(subject_name, shared_week):
    return f"برای این کلاس {_when(shared_week)} درس «{subject_name}» ثبت شده است."


def teacher_conflict_message(other_class, shared_week, branch_id):
    """"This teacher already teaches in <other_class> at this bell", as seen from ``branch_id``."""

    where = f"کلاس {class_label(other_class)}"
    if other_class.branch_id != branch_id:
        branch = other_class.branch.name
        where += f" ({branch})" if branch.startswith("شعبه") else f" (شعبه {branch})"
    return f"این معلم {_when(shared_week)} در {where} درس دارد."


# ----------------------------------------------------------------------
# Slots and conflicts
# ----------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class Slot:
    """
    One timetable entry as the rules see it, saved or not.

    ``class_subject`` is a (possibly unsaved or modified) ``ClassSubject``
    whose ``school_class`` and ``teacher_assignment`` can be read.
    ``key`` is the caller's own handle, handed back on each ``Conflict``.
    """

    class_subject: object
    day_of_week: int
    bell_id: int
    week_type: int
    schedule_id: int | None = None
    key: object = None

    @classmethod
    def of(cls, schedule, key=None):
        return cls(
            class_subject=schedule.class_subject,
            day_of_week=schedule.day_of_week,
            bell_id=schedule.bell_id,
            week_type=schedule.week_type,
            schedule_id=schedule.pk,
            key=key,
        )

    @property
    def is_active(self):
        return bool(self.class_subject.is_active)

    @property
    def school_class_id(self):
        return self.class_subject.school_class_id

    @property
    def academic_year_id(self):
        return self.class_subject.school_class.year_id

    @property
    def teacher_id(self):
        return self.class_subject.teacher_assignment.teacher_id

    @property
    def time_key(self):
        return (self.academic_year_id, self.day_of_week, self.bell_id)


@dataclass(frozen=True)
class Conflict:
    """``slot`` (being validated) clashes with ``other``."""

    slot: Slot
    other: Slot
    kind: str

    @property
    def shared_week(self):
        """The rotation week both happen in, or None when both are every week."""

        if self.slot.week_type != WeekType.BOTH:
            return self.slot.week_type
        if self.other.week_type != WeekType.BOTH:
            return self.other.week_type
        return None

    @property
    def message(self):
        other = self.other.class_subject
        if self.kind == CLASS_CONFLICT:
            return class_conflict_message(other.subject.name, self.shared_week)
        return teacher_conflict_message(
            other.school_class,
            self.shared_week,
            self.slot.class_subject.school_class.branch_id,
        )

    @property
    def message_with_time(self):
        """``message`` prefixed with the day and bell, for errors away from the grid."""

        day = ClassSchedule.DayChoices(self.slot.day_of_week).label
        from .models.bell import Bell

        bell = Bell.objects.filter(pk=self.slot.bell_id).values_list("title", flat=True).first()
        return f"{day}، زنگ {bell}: {self.message}"


class ScheduleConflictError(ValidationError):
    def __init__(self, conflicts, with_time=False):
        self.conflicts = list(conflicts)
        super().__init__([
            conflict.message_with_time if with_time else conflict.message
            for conflict in self.conflicts
        ])


def _clash(a, b):
    if not week_types_overlap(a.week_type, b.week_type):
        return None

    cs_a, cs_b = a.class_subject, b.class_subject
    if not date_ranges_overlap(cs_a.start_date, cs_a.end_date, cs_b.start_date, cs_b.end_date):
        return None

    if a.school_class_id == b.school_class_id:
        return CLASS_CONFLICT
    if a.teacher_id == b.teacher_id:
        return TEACHER_CONFLICT
    return None


def find_conflicts(slots, replaced_ids=()):
    """
    Every clash of ``slots`` with each other and with the saved
    timetable. One query, however many slots.

    Saved rows whose pk is in ``replaced_ids`` -- or is the
    ``schedule_id`` of one of ``slots`` -- are ignored: the caller is
    replacing them. Inactive class subjects never clash.
    """

    slots = [slot for slot in slots if slot.is_active]
    if not slots:
        return []

    conflicts = []

    # 1. Among the slots themselves -- both directions, so each side
    #    can be pointed at.
    by_time = defaultdict(list)
    for slot in slots:
        by_time[slot.time_key].append(slot)
    for group in by_time.values():
        for i, a in enumerate(group):
            for b in group[:i]:
                kind = _clash(a, b)
                if kind:
                    conflicts.append(Conflict(a, b, kind))
                    conflicts.append(Conflict(b, a, kind))

    # 2. Against what is saved.
    ignored = set(replaced_ids) | {slot.schedule_id for slot in slots if slot.schedule_id}
    saved = (
        ClassSchedule.objects
        .filter(
            class_subject__is_active=True,
            class_subject__school_class__year_id__in={s.academic_year_id for s in slots},
            day_of_week__in={s.day_of_week for s in slots},
            bell_id__in={s.bell_id for s in slots},
        )
        .filter(
            Q(class_subject__school_class_id__in={s.school_class_id for s in slots})
            | Q(class_subject__teacher_assignment__teacher_id__in={s.teacher_id for s in slots})
        )
        .exclude(pk__in=ignored)
        .select_related(*SCHEDULE_RELATED)
    )
    saved_by_time = defaultdict(list)
    for row in saved:
        other = Slot.of(row)
        saved_by_time[other.time_key].append(other)

    for slot in slots:
        for other in saved_by_time[slot.time_key]:
            kind = _clash(slot, other)
            if kind:
                conflicts.append(Conflict(slot, other, kind))

    return conflicts


# ----------------------------------------------------------------------
# Locking
# ----------------------------------------------------------------------

def lock_for_schedule_change(class_ids=(), teacher_ids=()):
    """
    Row-locks the classes and teachers (``TeacherProfile``) whose
    timetables are about to change, until the surrounding transaction
    ends. Any two writes that could produce a clash share a class or a
    teacher, so they queue up here.

    Locks are always taken classes first, each in pk order, so two
    writers can never deadlock. ``FOR NO KEY UPDATE`` (PostgreSQL) does
    not block rows that merely reference the locked ones. A no-op on
    SQLite, which serialises writers anyway.
    """

    from school.models import SchoolClass
    from staff.models import TeacherProfile

    no_key = connection.features.has_select_for_no_key_update

    for model, ids in ((SchoolClass, class_ids), (TeacherProfile, teacher_ids)):
        ids = sorted({pk for pk in ids if pk is not None})
        if ids:
            list(
                model.objects
                .select_for_update(no_key=no_key)
                .filter(pk__in=ids)
                .order_by("pk")
                .values_list("pk", flat=True)
            )


def lock_slots(slots):
    slots = list(slots)
    lock_for_schedule_change(
        class_ids=[slot.school_class_id for slot in slots],
        teacher_ids=[slot.teacher_id for slot in slots],
    )


def check_slots(slots, replaced_ids=(), with_time=False):
    """Lock, then raise ``ScheduleConflictError`` if ``slots`` clash. Call inside a transaction."""

    slots = [slot for slot in slots if slot.is_active]
    lock_slots(slots)
    conflicts = find_conflicts(slots, replaced_ids=replaced_ids)
    if conflicts:
        raise ScheduleConflictError(conflicts, with_time=with_time)


# ----------------------------------------------------------------------
# Write-path helpers
# ----------------------------------------------------------------------

def schedules_as_slots(schedules):
    """
    ``Slot``s for (unsaved or modified) ``ClassSchedule`` objects. A
    class subject already cached on the object is used as is; the others
    are loaded in one query.
    """

    schedules = list(schedules)
    from school.models import ClassSubject

    schedules = [s for s in schedules if s.class_subject_id or ClassSchedule.class_subject.is_cached(s)]
    missing = {
        s.class_subject_id for s in schedules
        if not ClassSchedule.class_subject.is_cached(s)
    }
    loaded = ClassSubject.objects.select_related(
        "school_class", "teacher_assignment"
    ).in_bulk(missing)

    return [
        Slot(
            class_subject=(
                s.class_subject if ClassSchedule.class_subject.is_cached(s)
                else loaded[s.class_subject_id]
            ),
            day_of_week=s.day_of_week,
            bell_id=s.bell_id,
            week_type=s.week_type,
            schedule_id=s.pk,
            key=s,
        )
        for s in schedules
    ]


def class_subject_slots(class_subject):
    """The saved slots of ``class_subject``, judged with its in-memory values."""

    if class_subject.pk is None:
        return []
    return [
        Slot(
            class_subject=class_subject,
            day_of_week=day,
            bell_id=bell_id,
            week_type=week_type,
            schedule_id=pk,
        )
        for pk, day, bell_id, week_type in ClassSchedule.objects
        .filter(class_subject_id=class_subject.pk)
        .values_list("pk", "day_of_week", "bell_id", "week_type")
    ]


_prevalidated = ContextVar("schedule_conflicts_prevalidated", default=False)


@contextmanager
def prevalidated():
    """
    Marks writes inside the block as already checked, for the
    ``QuerySet.update()`` that ``bulk_update()`` issues internally.
    """

    token = _prevalidated.set(True)
    try:
        yield
    finally:
        _prevalidated.reset(token)


def is_prevalidated():
    return _prevalidated.get()
