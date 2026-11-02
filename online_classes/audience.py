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

from django.db.models import Exists, OuterRef, Q

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

def _target_ids(item):
    return {field: set(getattr(item, field).values_list("pk", flat=True)) for field in ALL_TARGET_FIELDS}


def reached_enrollments(item):
    """The current enrolments a saved item reaches, by name (the admin's counts and lists, the import)."""

    targets = _target_ids(item)
    enrollments = StudentEnrollment.objects.current()

    if not item.is_whole_school:
        wanted = Q(student__in=targets["students"]) | Q(school_class__in=targets["classes"])
        if targets["branches"] or targets["grades"]:
            by_group = Q()
            if targets["branches"]:
                by_group &= Q(school_class__branch__in=targets["branches"])
            if targets["grades"]:
                by_group &= Q(school_class__grade__in=targets["grades"])
            wanted |= by_group
        enrollments = enrollments.filter(wanted)

    return (
        enrollments.exclude(student__in=targets["excluded_students"])
        .select_related("student__user", "school_class__grade", "school_class__branch")
        .order_by("student__user__last_name", "student__user__first_name", "pk")
    )


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
