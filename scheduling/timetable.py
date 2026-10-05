"""
The admin's weekly timetable grid for one class (``SchoolClassAdmin`` ->
"برنامه هفتگی"): what it shows, the teacher-busy hint, and saving the
whole grid in one transaction.

The grid is one row per school day and one column per active bell. A
cell holds either one "every week" entry or a "هفته اول" and/or a
"هفته دوم" entry; each entry is a subject + a ``TeacherAssignment``.
``ClassSubject`` never shows up in the UI: it is looked up (or created)
from ``(class, subject, assignment)`` when saving.

The grid owns the class's schedule rows that are *in effect*: their
class subject is active and their bell is active. Rows on inactive bells
and rows of inactive class subjects are left alone -- unless the grid
re-activates that class subject, in which case its old rows are replaced
by what the grid says.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q

from school.colors import safe_hex
from school.models import ClassSubject, Subject
from staff.models import TeacherAssignment

from .conflicts import (
    ScheduleConflictError,
    Slot,
    class_label,
    find_conflicts,
    lock_for_schedule_change,
    teacher_conflict_message,
)
from .models.bell import Bell
from .models.class_schedule import THURSDAY_MESSAGE, ClassSchedule
from .services import _working_days, persian_digits

WeekType = ClassSchedule.WeekTypeChoices

MSG_INCOMPLETE = "درس و معلم هر دو باید انتخاب شوند."
MSG_BAD_SUBJECT = "این درس قابل انتخاب نیست."
MSG_BAD_TEACHER = "این معلم برای شعبه و سال تحصیلی این کلاس انتساب فعال ندارد."
MSG_BAD_CELL = "این خانه در جدول وجود ندارد."
MSG_MIXED_WEEKS = "یک خانه نمی‌تواند هم «هر هفته» و هم «هفته‌درمیان» باشد."
MSG_DUPLICATE = "این خانه دو بار فرستاده شده است."


def teacher_name(assignment):
    user = assignment.teacher.staff.user
    return user.get_full_name() or user.get_username()


def grid_bells():
    return list(Bell.objects.filter(is_active=True).order_by("order"))


def owned_schedules(school_class):
    """The class's rows the grid shows and replaces (see module docstring)."""

    return (
        ClassSchedule.objects
        .filter(
            class_subject__school_class=school_class,
            class_subject__is_active=True,
            bell__is_active=True,
        )
        .select_related(
            "class_subject__subject",
            "class_subject__teacher_assignment__teacher__staff__user",
        )
    )


def teacher_choices(school_class, include_ids=()):
    """
    Assignments offered in the teacher select: active ones in the
    class's branch and academic year, plus any already used by the
    class (so an existing entry of a teacher on leave still shows).
    """

    assignments = (
        TeacherAssignment.objects
        .filter(branch_id=school_class.branch_id, academic_year_id=school_class.year_id)
        .filter(Q(status=TeacherAssignment.AssignmentStatus.ACTIVE) | Q(pk__in=list(include_ids)))
        .select_related("teacher__staff__user")
    )
    return sorted(assignments, key=lambda a: (teacher_name(a), a.pk))


def subject_choices(include_ids=()):
    return list(Subject.objects.filter(Q(is_active=True) | Q(pk__in=list(include_ids))).order_by("name"))


def load_grid(school_class):
    """Everything the grid page needs, JSON-ready."""

    rows = list(owned_schedules(school_class))
    bells = grid_bells()
    days = _working_days(row.day_of_week for row in rows)
    day_labels = dict(ClassSchedule.DayChoices.choices)
    used_assignments = {row.class_subject.teacher_assignment_id for row in rows}
    used_subjects = {row.class_subject.subject_id for row in rows}

    return {
        "class_label": class_label(school_class),
        "days": [{"value": day, "label": day_labels[day]} for day in days],
        "bells": [
            {
                "id": bell.id,
                "title": bell.title,
                "time": persian_digits(f"{bell.start_time:%H:%M} – {bell.end_time:%H:%M}"),
            }
            for bell in bells
        ],
        "subjects": [
            {"id": s.id, "name": s.name, "color": safe_hex(s.color)}
            for s in subject_choices(used_subjects)
        ],
        "teachers": [
            {
                "id": a.id,
                "name": teacher_name(a)
                if a.status == TeacherAssignment.AssignmentStatus.ACTIVE
                else f"{teacher_name(a)} ({a.get_status_display()})",
            }
            for a in teacher_choices(school_class, used_assignments)
        ],
        "entries": [
            {
                "day": row.day_of_week,
                "bell": row.bell_id,
                "week_type": row.week_type,
                "subject": row.class_subject.subject_id,
                "teacher": row.class_subject.teacher_assignment_id,
            }
            for row in sorted(rows, key=lambda r: (r.day_of_week, r.bell_id, r.week_type))
        ],
        "recent_pairs": _pairs_by_use(rows),
    }


def _pairs_by_use(rows):
    """(subject, assignment) pairs of the class, most used first -- the quick-fill chips."""

    counts = Counter(
        (row.class_subject.subject_id, row.class_subject.teacher_assignment_id) for row in rows
    )
    return [{"subject": s, "teacher": t} for (s, t), _ in counts.most_common()]


def teacher_busy(school_class, assignment):
    """
    Where ``assignment``'s teacher already teaches in *other* classes of
    the same academic year (any branch), as grid coordinates. A hint
    only: ``save_grid`` is what enforces the rules.
    """

    rows = (
        ClassSchedule.objects
        .filter(
            class_subject__is_active=True,
            class_subject__teacher_assignment__teacher_id=assignment.teacher_id,
            class_subject__school_class__year_id=school_class.year_id,
        )
        .exclude(class_subject__school_class=school_class)
        .select_related(
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
        )
        .order_by("day_of_week", "bell__order", "week_type")
    )
    return [
        {
            "day": row.day_of_week,
            "bell": row.bell_id,
            "week_type": row.week_type,
            "message": teacher_conflict_message(
                row.class_subject.school_class,
                None if row.week_type == WeekType.BOTH else row.week_type,
                school_class.branch_id,
            ),
        }
        for row in rows
    ]


# ----------------------------------------------------------------------
# Saving
# ----------------------------------------------------------------------

@dataclass
class SaveResult:
    errors: list = field(default_factory=list)   # [{day, bell, week_type, message}]
    created: int = 0
    updated: int = 0
    deleted: int = 0
    deactivated_class_subjects: list = field(default_factory=list)
    deleted_class_subjects: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


class _Rejected(Exception):
    def __init__(self, errors):
        self.errors = errors


def _error(day, bell, week_type, message):
    return {"day": day, "bell": bell, "week_type": week_type, "message": message}


def _conflict_errors(conflicts):
    errors, seen = [], set()
    for conflict in conflicts:
        slot = conflict.slot
        item = (slot.day_of_week, slot.bell_id, slot.week_type, conflict.message)
        if item not in seen:
            seen.add(item)
            errors.append(_error(*item))
    return errors


def _parse_entries(payload, day_values, bell_ids):
    """
    ``[{day, bell, week_type, subject, teacher}, ...]`` -> ``{(day, bell,
    week_type): (subject_id, assignment_id)}``, or ``_Rejected``.
    """

    if not isinstance(payload, list):
        raise _Rejected([_error(None, None, None, "داده‌ی فرستاده‌شده معتبر نیست.")])

    def as_int(value):
        if isinstance(value, bool):
            raise ValueError
        return None if value in (None, "") else int(value)

    entries, errors = {}, []
    for raw in payload:
        try:
            day, bell, week_type = (as_int(raw.get(k)) for k in ("day", "bell", "week_type"))
            subject, teacher = as_int(raw.get("subject")), as_int(raw.get("teacher"))
        except (AttributeError, TypeError, ValueError):
            raise _Rejected([_error(None, None, None, "داده‌ی فرستاده‌شده معتبر نیست.")])

        if day not in day_values or bell not in bell_ids or week_type not in WeekType.values:
            errors.append(_error(day, bell, week_type, MSG_BAD_CELL))
            continue
        if subject is None and teacher is None:
            continue  # an empty half of an alternating cell
        if subject is None or teacher is None:
            errors.append(_error(day, bell, week_type, MSG_INCOMPLETE))
            continue
        if (day, bell, week_type) in entries:
            errors.append(_error(day, bell, week_type, MSG_DUPLICATE))
            continue
        entries[(day, bell, week_type)] = (subject, teacher)

    for day, bell, week_type in entries:
        if week_type == WeekType.BOTH and any(
            (day, bell, w) in entries for w in (WeekType.WEEK_ONE, WeekType.WEEK_TWO)
        ):
            errors.append(_error(day, bell, week_type, MSG_MIXED_WEEKS))

    if errors:
        raise _Rejected(errors)
    return entries


def save_grid(school_class, payload, can_delete_class_subjects=True):
    """
    Makes the class's timetable match ``payload`` (the whole grid, as
    ``[{day, bell, week_type, subject, teacher}, ...]``), all or nothing.

    Only changed rows are written: per cell, rows that already match are
    kept, the others are updated in place where possible, and the rest
    are deleted or created. The final state is checked against every
    conflict rule before anything is written, with the class and all
    teachers involved locked.

    A ``ClassSubject`` that loses its last schedule row is deactivated
    when it has sessions (its history stays), and deleted otherwise (it
    was only ever a timetable entry) -- or also just deactivated when the
    user may not delete class subjects.
    """

    try:
        with transaction.atomic():
            return _save_grid(school_class, payload, can_delete_class_subjects)
    except _Rejected as rejected:
        return SaveResult(errors=rejected.errors)
    except ScheduleConflictError as error:
        # Only reachable if the final check and a write-path check
        # disagree; the transaction is rolled back either way.
        return SaveResult(errors=_conflict_errors(error.conflicts))


def _save_grid(school_class, payload, can_delete_class_subjects):
    bells = grid_bells()
    year = school_class.year

    # -- 1. Parse ------------------------------------------------------
    # Days: every day the model knows; a Thursday cell is only accepted
    # when it is an unchanged legacy row (checked below).
    entries = _parse_entries(payload, set(ClassSchedule.DayChoices.values), {b.id for b in bells})

    # -- 2. Lock the class, then read what is saved --------------------
    lock_for_schedule_change(class_ids=[school_class.pk])

    owned = list(owned_schedules(school_class))
    class_subjects = {
        (cs.subject_id, cs.teacher_assignment_id): cs
        for cs in ClassSubject.objects.filter(school_class=school_class)
        .select_related("school_class", "teacher_assignment")
    }

    used_assignments = {row.class_subject.teacher_assignment_id for row in owned}
    used_subjects = {row.class_subject.subject_id for row in owned}
    assignments = {a.id: a for a in teacher_choices(school_class, used_assignments)}
    subjects = {s.id: s for s in subject_choices(used_subjects)}

    errors = []
    legacy_thursday = {
        (row.day_of_week, row.bell_id, row.week_type,
         row.class_subject.subject_id, row.class_subject.teacher_assignment_id)
        for row in owned
        if row.day_of_week == ClassSchedule.DayChoices.THURSDAY
    }
    for (day, bell, week_type), (subject_id, assignment_id) in entries.items():
        if (
            day == ClassSchedule.DayChoices.THURSDAY
            and (day, bell, week_type, subject_id, assignment_id) not in legacy_thursday
        ):
            # Only an unchanged legacy Thursday row may stay; see
            # ClassSchedule.check_no_new_thursday.
            errors.append(_error(day, bell, week_type, THURSDAY_MESSAGE))
            continue
        if subject_id not in subjects:
            errors.append(_error(day, bell, week_type, MSG_BAD_SUBJECT))
        elif assignment_id not in assignments:
            errors.append(_error(day, bell, week_type, MSG_BAD_TEACHER))
    if errors:
        raise _Rejected(errors)

    lock_for_schedule_change(
        class_ids=[school_class.pk],
        teacher_ids=[assignments[a].teacher_id for _, a in entries.values()],
    )

    # -- 3. Plan: the class subject behind every entry -----------------
    new_class_subjects, reactivated = [], []

    def class_subject_for(subject_id, assignment_id):
        key = (subject_id, assignment_id)
        cs = class_subjects.get(key)
        if cs is None:
            cs = ClassSubject(
                school_class=school_class,
                subject=subjects[subject_id],
                teacher_assignment=assignments[assignment_id],
                start_date=year.start_date,
                end_date=year.end_date,
                is_active=True,
            )
            class_subjects[key] = cs
            new_class_subjects.append(cs)
        elif not cs.is_active:
            cs.is_active = True
            reactivated.append(cs)
        return cs

    final = {cell: class_subject_for(*pair) for cell, pair in entries.items()}

    # Rows of re-activated class subjects come back into effect with them.
    dormant = list(
        ClassSchedule.objects.filter(class_subject__in=[cs.pk for cs in reactivated])
    )

    # -- 4. Check the final state --------------------------------------
    slots = [
        Slot(class_subject=cs, day_of_week=day, bell_id=bell, week_type=week_type)
        for (day, bell, week_type), cs in final.items()
    ]
    conflicts = find_conflicts(slots, replaced_ids=[r.pk for r in owned + dormant])
    if conflicts:
        raise _Rejected(_conflict_errors(conflicts))

    # -- 5. Diff, cell by cell -----------------------------------------
    # Before _diff(), which re-points updated rows at their new subject.
    previously_used = {row.class_subject_id: row.class_subject for row in owned}
    keep, updates, deletes, creates = _diff(owned, dormant, final)

    # -- 6. Write (order matters, see _diff) ---------------------------
    result = SaveResult(created=len(creates), updated=len(updates), deleted=len(deletes))

    if deletes:
        ClassSchedule.objects.filter(pk__in=[row.pk for row in deletes]).delete()
    for cs in new_class_subjects:
        cs.save()
    if updates:
        ClassSchedule.objects.bulk_update(updates, ["class_subject", "week_type"])
    if creates:
        ClassSchedule.objects.bulk_create(creates)
    for cs in reactivated:
        cs.save(update_fields=["is_active"])

    # -- 7. Class subjects nothing schedules any more ------------------
    in_use = {cs.pk for cs in final.values()}
    for cs_id, cs in previously_used.items():
        if cs_id in in_use or ClassSchedule.objects.filter(class_subject_id=cs_id).exists():
            continue
        if can_delete_class_subjects and not cs.sessions.exists():
            cs.delete()
            result.deleted_class_subjects.append(cs_id)
        else:
            cs.is_active = False
            cs.save(update_fields=["is_active"])
            result.deactivated_class_subjects.append(cs_id)

    return result


def _diff(owned, dormant, final):
    """
    Per cell, match saved rows to the wanted ``{(day, bell, week_type):
    class_subject}``:

    1. same week type and class subject -> keep as is;
    2. same week type -> change the class subject;
    3. same class subject -> change the week type;
    4. anything left over -> change both;
    then delete the saved rows left and create the wanted ones left.

    ``dormant`` rows (of re-activated class subjects) are only kept on
    an exact match, else deleted. Exact matches all come first, so no
    update ever takes a (class_subject, day, week_type, bell) another
    row still holds -- deletes run before updates, updates before
    creates.
    """

    wanted = defaultdict(dict)
    for (day, bell, week_type), cs in final.items():
        wanted[(day, bell)][week_type] = cs

    saved = defaultdict(list)
    for row in owned:
        saved[(row.day_of_week, row.bell_id)].append(row)

    keep, updates, deletes, creates = [], [], [], []

    def take_exact(rows, want):
        left = []
        for row in rows:
            cs = want.get(row.week_type)
            if cs is not None and cs.pk == row.class_subject_id:
                keep.append(row)
                del want[row.week_type]
            else:
                left.append(row)
        return left

    dormant_by_cell = defaultdict(list)
    for row in dormant:
        dormant_by_cell[(row.day_of_week, row.bell_id)].append(row)
    for cell, rows in dormant_by_cell.items():
        deletes.extend(take_exact(rows, wanted[cell]))

    for cell in set(saved) | set(wanted):
        want = wanted[cell]
        rows = take_exact(saved[cell], want)

        left = []
        for row in rows:
            if row.week_type in want:
                row.class_subject = want.pop(row.week_type)
                updates.append(row)
            else:
                left.append(row)

        rows, left = left, []
        for row in rows:
            week_type = next(
                (w for w, cs in want.items() if cs.pk is not None and cs.pk == row.class_subject_id),
                None,
            )
            if week_type is None:
                left.append(row)
            else:
                row.week_type = week_type
                del want[week_type]
                updates.append(row)

        for row in left:
            if want:
                week_type, cs = next(iter(want.items()))
                del want[week_type]
                row.week_type, row.class_subject = week_type, cs
                updates.append(row)
            else:
                deletes.append(row)

        day, bell = cell
        for week_type, cs in want.items():
            creates.append(ClassSchedule(
                class_subject=cs, day_of_week=day, bell_id=bell, week_type=week_type,
            ))

    return keep, updates, deletes, creates
