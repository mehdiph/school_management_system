"""
Who an event or an announcement reaches (D2, D3): the only code that reads the
audience fields.

    shown = whole school
            OR the student is listed
            OR the student's class is listed
            OR (a branch or grade is selected
                AND the student's branch matches, if any branches are selected
                AND the student's grade matches, if any grades are selected)
    then remove excluded students (exclusion always wins)

Nothing selected means nobody. Both directions (``visible_to``, one student's
items; ``reached_enrollments``, one item's students) start from the student's
current enrolment, so a class change takes effect on the next page load, and a
test holds them to the same answer. A custom group (Phase 2) is one more
many-to-many on ``AudienceTargets`` and one more term here.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Exists, OuterRef, Q, Subquery

from school.models import SchoolClass
from student.models.student_enrollment import StudentEnrollment

ALL_TARGET_FIELDS = ("branches", "grades", "classes", "students", "excluded_students")


def _rows(model, field, **lookups):
    """The ``field`` many-to-many rows of the outer item, as a subquery."""

    through = getattr(model, field).through
    return through.objects.filter(**{model._meta.model_name: OuterRef("pk"), **lookups})


def _exists(model, field, **lookups):
    return Exists(_rows(model, field, **lookups))


# ----------------------------------------------------------------------
# One student -> their items
# ----------------------------------------------------------------------

def visible_to(queryset, enrollment):
    """Narrows ``queryset`` to the items a current enrolment receives. ``None``: nothing. One query."""

    if enrollment is None:
        return queryset.none()

    model = queryset.model
    school_class = enrollment.school_class
    any_branch = _exists(model, "branches")
    any_grade = _exists(model, "grades")
    in_branch = _exists(model, "branches", branch_id=school_class.branch_id)
    in_grade = _exists(model, "grades", grade_id=school_class.grade_id)

    return queryset.filter(
        Q(is_whole_school=True)
        | Q(_exists(model, "students", studentprofile_id=enrollment.student_id))
        | Q(_exists(model, "classes", schoolclass_id=school_class.pk))
        | (Q(in_branch) & (~Q(any_grade) | Q(in_grade)))
        | (~Q(any_branch) & Q(in_grade))
    ).filter(~_exists(model, "excluded_students", studentprofile_id=enrollment.student_id))


# ----------------------------------------------------------------------
# One item -> its students
# ----------------------------------------------------------------------

def _target_rows(item, field):
    """The item's ``field`` rows as a subquery: nothing is read until the outer query runs."""

    through = getattr(type(item), field).through
    return through.objects.filter(**{type(item)._meta.model_name: item.pk})


def _target_ids(item, field):
    column = getattr(type(item), field).field.m2m_reverse_name()
    return _target_rows(item, field).values(column)


def reached_enrollments(item):
    """
    The current enrolments a saved item reaches (the admin's counts and lists,
    the import). One query: the targets are subqueries, not lists read first.
    """

    enrollments = StudentEnrollment.objects.current()

    if not item.is_whole_school:
        any_branch = Exists(_target_rows(item, "branches"))
        any_grade = Exists(_target_rows(item, "grades"))
        by_group = (
            (Q(any_branch) | Q(any_grade))
            & (~Q(any_branch) | Q(school_class__branch__in=_target_ids(item, "branches")))
            & (~Q(any_grade) | Q(school_class__grade__in=_target_ids(item, "grades")))
        )
        enrollments = enrollments.filter(
            Q(student__in=_target_ids(item, "students"))
            | Q(school_class__in=_target_ids(item, "classes"))
            | by_group
        )

    return (
        enrollments.exclude(student__in=_target_ids(item, "excluded_students"))
        .select_related("student__user", "school_class__grade", "school_class__branch")
        .order_by("student__user__last_name", "student__user__first_name", "pk")
    )


# ----------------------------------------------------------------------
# The admin's summary and lists: aggregated in the database, scoped (D1)
# ----------------------------------------------------------------------

def _scoped(item, branch_ids):
    """``reached_enrollments`` limited to ``branch_ids``; ``None`` means every branch (a superuser)."""

    enrollments = reached_enrollments(item)
    if branch_ids is not None:
        enrollments = enrollments.filter(school_class__branch__in=branch_ids)
    return enrollments


def _has_row(event):
    from .models import OnlineEventAccess  # models import this module

    return Exists(OnlineEventAccess.objects.filter(event=event, student=OuterRef("student_id")))


@dataclass
class ClassCount:
    class_id: int
    grade: str
    section: str
    branch: str
    total: int
    missing: int = 0

    @property
    def label(self):
        return f"{self.grade} {self.section} · {self.branch}"


@dataclass
class Breakdown:
    """Who an item reaches, per class, ordered by grade, section and branch. ``missing``: no access row."""

    classes: list = field(default_factory=list)
    with_access: bool = False

    @property
    def total(self):
        return sum(row.total for row in self.classes)

    @property
    def missing(self):
        return sum(row.missing for row in self.classes)

    @property
    def with_row(self):
        return self.total - self.missing


def breakdown(item, branch_ids=None, event=None):
    """
    One aggregate query, whatever the audience size. ``event``: a personal
    event, to count who has no access row; rows of students outside the
    audience aren't counted.
    """

    counts = {"total": Count("pk")}
    if event is not None:
        counts["missing"] = Count("pk", filter=~Q(_has_row(event)))
    rows = (
        _scoped(item, branch_ids)
        .order_by()
        .values(
            "school_class_id", "school_class__grade__name", "school_class__grade__level", "school_class__section",
            "school_class__branch__name", "school_class__branch__order",
        )
        .annotate(**counts)
        .order_by(
            "school_class__grade__level", "school_class__section", "school_class__branch__order",
            "school_class__branch__name",
        )
    )
    return Breakdown(
        classes=[
            ClassCount(
                class_id=row["school_class_id"],
                grade=row["school_class__grade__name"],
                section=row["school_class__section"],
                branch=row["school_class__branch__name"],
                total=row["total"],
                missing=row.get("missing", 0),
            )
            for row in rows
        ],
        with_access=event is not None,
    )


def students(item, branch_ids=None, event=None):
    """
    The list page's enrolments, ordered by class and name. With ``event``, each
    carries ``access_id`` (its row, or ``None``), so a page costs no query per
    student.
    """

    enrollments = _scoped(item, branch_ids).order_by(
        "school_class__grade__level", "school_class__section", "school_class__branch__order",
        "student__user__last_name", "student__user__first_name", "pk",
    )
    if event is not None:
        from .models import OnlineEventAccess

        enrollments = enrollments.annotate(access_id=Subquery(
            OnlineEventAccess.objects.filter(event=event, student=OuterRef("student_id")).values("pk")[:1]
        ))
    return enrollments


def has_targets(item):
    """False when nothing is selected, which means nobody sees it."""

    return item.is_whole_school or any(getattr(item, field).exists() for field in ALL_TARGET_FIELDS[:4])


# ----------------------------------------------------------------------
# Admin: what a branch-scoped (non-superuser) admin may see and change (D23)
# ----------------------------------------------------------------------

def _student_in_branches(ids):
    return StudentEnrollment.objects.current().filter(
        student=OuterRef("studentprofile_id"), school_class__branch__in=ids
    )


def touching_branches(queryset, branch_ids):
    """Items that reach these branches, whole-school ones included."""

    model = queryset.model
    return queryset.filter(
        Q(is_whole_school=True)
        | Q(_exists(model, "branches", branch__in=branch_ids))
        | Q(_exists(model, "classes", schoolclass__branch__in=branch_ids))
        | (Q(_exists(model, "grades")) & ~Q(_exists(model, "branches")))
        | Q(_exists(model, "students", studentprofile__enrollments__school_class__branch__in=branch_ids))
    )


def touching_grade(queryset, grade_id):
    """Items that reach this grade, whole-school ones and those through a class included."""

    model = queryset.model
    return queryset.filter(
        Q(is_whole_school=True)
        | Q(_exists(model, "grades", grade_id=grade_id))
        | Q(_exists(model, "classes", schoolclass__grade_id=grade_id))
        | (Q(_exists(model, "branches")) & ~Q(_exists(model, "grades")))
        | Q(_exists(model, "students", studentprofile__enrollments__school_class__grade_id=grade_id))
    )


def wholly_within(queryset, branch_ids):
    """
    Items a branch-scoped admin may change: every target inside these branches.
    Never a whole-school item, a grade with no branch (that is every branch),
    or an item with no target at all. ``targets_problems`` is the same rule
    for a form's unsaved values.
    """

    model = queryset.model
    return queryset.filter(
        Q(_exists(model, "branches")) | Q(_exists(model, "classes")) | Q(_exists(model, "students")),
        is_whole_school=False,
    ).filter(
        Q(_exists(model, "branches")) | ~Q(_exists(model, "grades")),
    ).filter(
        ~Exists(_rows(model, "branches").exclude(branch__in=branch_ids)),
        ~Exists(_rows(model, "classes").exclude(schoolclass__branch__in=branch_ids)),
        ~Exists(_rows(model, "students").filter(~Exists(_student_in_branches(branch_ids)))),
        ~Exists(_rows(model, "excluded_students").filter(~Exists(_student_in_branches(branch_ids)))),
    )


def targets_problems(*, is_whole_school, branch_ids, grade_ids, class_ids, student_ids, excluded_ids, allowed):
    """
    ``{field: message}``: what a branch-scoped admin may not select. The same
    rule as ``wholly_within``, for values that aren't saved yet.
    """

    allowed = set(allowed)
    problems = {}

    if is_whole_school:
        problems["is_whole_school"] = "فقط مدیر کل می‌تواند «کل مدرسه» را انتخاب کند."
    if set(branch_ids) - allowed:
        problems["branches"] = "به همه‌ی این شعبه‌ها دسترسی ندارید."
    if grade_ids and not branch_ids:
        problems["branches"] = "پایه به‌تنهایی یعنی همه‌ی شعبه‌ها؛ شعبه را هم انتخاب کنید."
    if class_ids and SchoolClass.objects.filter(pk__in=class_ids).exclude(branch__in=allowed).exists():
        problems["classes"] = "به همه‌ی این کلاس‌ها دسترسی ندارید."

    def outside(ids):
        inside = StudentEnrollment.objects.current().filter(
            student__in=ids, school_class__branch__in=allowed
        ).values_list("student_id", flat=True)
        return set(ids) - set(inside)

    if outside(student_ids):
        problems["students"] = "برخی از این دانش‌آموزان در شعبه‌های شما نیستند."
    if outside(excluded_ids):
        problems["excluded_students"] = "برخی از این دانش‌آموزان در شعبه‌های شما نیستند."
    if not (is_whole_school or branch_ids or grade_ids or class_ids or student_ids):
        problems.setdefault("branches", "حداقل یک شعبه، کلاس یا دانش‌آموز از شعبه‌های خودتان انتخاب کنید.")
    return problems
