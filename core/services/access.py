"""
Branch access: the single source of truth for "which branches may this
user see?".

A staff member's accessible branches are *derived*, never stored twice:

  * explicit access -- their ``BranchAccess`` rows (mainly for
    non-teaching staff, or extra access granted on top of teaching),
  * teaching access -- the branches of their **active**
    ``TeacherAssignment`` rows in the **current** academic year,
  * supervisor access -- the branch on their ``SupervisorProfile``,
  * student access -- the branches of their active enrolments (kept
    from the original ``BranchService`` behaviour, so student pages
    keep working).

The union of those is what everything in the project must use.
``BranchAccess`` rows are deliberately *not* auto-created from teacher
assignments: a synced row would keep granting access after the
assignment ended or was deleted, which is exactly the drift this module
exists to remove.

Every caller (middleware, context processors, admin, permissions) goes
through this module -- nothing queries ``BranchAccess`` or
``SupervisorProfile.branch`` directly any more.
"""

import jdatetime
from django.db.models import Q
from django.utils import timezone

from school.models import Branch
from staff.models import BranchAccess
from staff.models.teacher_assignment import TeacherAssignment
from student.models.student_enrollment import StudentEnrollment
from supervisor.models.supervisor_profile import SupervisorProfile

#: Where a branch in a user's accessible set came from. Used by the
#: admin's read-only "شعبه‌های مؤثر" field so an admin can see *why*
#: somebody has access to a branch.
SOURCE_EXPLICIT = "explicit"
SOURCE_TEACHING = "teaching"
SOURCE_SUPERVISOR = "supervisor"
SOURCE_STUDENT = "student"

SOURCE_LABELS = {
    SOURCE_EXPLICIT: "دسترسی مستقیم",
    SOURCE_TEACHING: "تدریس",
    SOURCE_SUPERVISOR: "پشتیبانی",
    SOURCE_STUDENT: "تحصیل",
}

#: Deterministic ordering for "the first accessible branch". ``order``
#: is the field the project already uses to sort branches in the UI.
BRANCH_ORDERING = ("order", "id")

#: Attribute used to memoise a user's accessible branch ids on the
#: request. The cached value is stored together with the user's pk, so a
#: request that changes user (login/logout) can never read another
#: user's cached set -- and nothing is cached globally.
_REQUEST_CACHE_ATTR = "_accessible_branch_ids_cache"


def today_jalali():
    """Today as a Jalali date, for comparing against ``jDateField``s."""

    return jdatetime.date.fromgregorian(date=timezone.localdate())


# ----------------------------------------------------------------------
# Building blocks
# ----------------------------------------------------------------------

def active_teacher_assignments(queryset=None):
    """
    Narrows ``queryset`` (default: all assignments) down to the ones
    that currently grant branch access:

      * status is ``ACTIVE``,
      * the academic year is the current one,
      * the assignment has not ended yet.

    This predicate is defined here once; the cleanup management command
    and the admin reuse it so "active assignment" can never drift
    between them.
    """

    if queryset is None:
        queryset = TeacherAssignment.objects.all()

    return queryset.filter(
        status=TeacherAssignment.AssignmentStatus.ACTIVE,
        academic_year__is_current=True,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today_jalali())
    )


def _staff_of(user):
    return getattr(user, "staff_profile", None)


def _supervisor_of(user):
    return getattr(user, "supervisor_profile", None)


def _student_of(user):
    return getattr(user, "student_profile", None)


def get_branch_access_map(user):
    """
    ``{branch_id: {source, ...}}`` for ``user``.

    Only active branches are considered. Superusers are *not* special
    cased here -- see :func:`get_accessible_branch_ids` -- because this
    map answers "where does this person's access come from", which for a
    superuser is "from being a superuser".

    Runs at most four small id-only queries, no matter how many branches
    or assignments exist.
    """

    access_map = {}

    if not user.is_authenticated:
        return access_map

    def add(branch_ids, source):
        for branch_id in branch_ids:
            access_map.setdefault(branch_id, set()).add(source)

    staff = _staff_of(user)

    if staff is not None:
        add(
            BranchAccess.objects
            .filter(staff=staff, branch__is_active=True)
            .values_list("branch_id", flat=True),
            SOURCE_EXPLICIT,
        )

        add(
            active_teacher_assignments(
                TeacherAssignment.objects.filter(
                    teacher__staff=staff,
                    branch__is_active=True,
                )
            ).values_list("branch_id", flat=True),
            SOURCE_TEACHING,
        )

    supervisor = _supervisor_of(user)

    if supervisor is not None and supervisor.branch_id:
        add(
            Branch.objects
            .filter(pk=supervisor.branch_id, is_active=True)
            .values_list("id", flat=True),
            SOURCE_SUPERVISOR,
        )

    student = _student_of(user)

    if student is not None:
        add(
            StudentEnrollment.objects
            .filter(
                student=student,
                status=StudentEnrollment.EnrollmentStatus.ACTIVE,
                school_class__branch__is_active=True,
            )
            .values_list("school_class__branch_id", flat=True),
            SOURCE_STUDENT,
        )

    return access_map


def describe_branch_access(user):
    """
    ``[(Branch, [source label, ...]), ...]`` ordered like the branch
    switcher, for display in the admin.
    """

    access_map = get_branch_access_map(user)

    if not access_map:
        return []

    branches = (
        Branch.objects
        .filter(id__in=access_map.keys())
        .order_by(*BRANCH_ORDERING)
    )

    return [
        (
            branch,
            [
                SOURCE_LABELS[source]
                for source in (
                    SOURCE_EXPLICIT,
                    SOURCE_TEACHING,
                    SOURCE_SUPERVISOR,
                    SOURCE_STUDENT,
                )
                if source in access_map[branch.id]
            ],
        )
        for branch in branches
    ]


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def get_accessible_branch_ids(user, request=None):
    """
    The ids of every branch ``user`` may see, as a ``frozenset``.

    Pass ``request`` where the same user's branches are needed several
    times in one request (admin ``get_queryset`` + every FK dropdown on
    the same page, context processors, ...): the result is memoised on
    that request object only, keyed by the user's pk.
    """

    if request is not None:
        cached = getattr(request, _REQUEST_CACHE_ATTR, None)

        if cached is not None and cached[0] == user.pk:
            return cached[1]

    branch_ids = _compute_accessible_branch_ids(user)

    if request is not None:
        setattr(request, _REQUEST_CACHE_ATTR, (user.pk, branch_ids))

    return branch_ids


def _compute_accessible_branch_ids(user):
    if not user.is_authenticated:
        return frozenset()

    if user.is_superuser:
        return frozenset(
            Branch.objects
            .filter(is_active=True)
            .values_list("id", flat=True)
        )

    return frozenset(get_branch_access_map(user))


def get_accessible_branches(user, request=None):
    """
    Every branch ``user`` may see, as a ``Branch`` queryset.

    Superusers get all active branches.
    """

    if not user.is_authenticated:
        return Branch.objects.none()

    if user.is_superuser:
        return Branch.objects.filter(is_active=True).order_by(*BRANCH_ORDERING)

    return (
        Branch.objects
        .filter(id__in=get_accessible_branch_ids(user, request=request))
        .order_by(*BRANCH_ORDERING)
    )


def has_branch_access(user, branch, request=None):
    """True if ``user`` may see ``branch`` (a ``Branch`` or a pk)."""

    if branch is None:
        return False

    branch_id = getattr(branch, "pk", branch)

    return branch_id in get_accessible_branch_ids(user, request=request)


def get_default_branch(user, request=None):
    """
    The branch to preselect for ``user``:

      1. their ``BranchAccess`` row flagged ``is_default``,
      2. otherwise the branch of their most recent active teacher
         assignment,
      3. otherwise the first accessible branch.

    A supervisor's own branch wins step 3 (it is one of their accessible
    branches), so a supervisor keeps landing on the branch they
    supervise -- which is the only branch their dashboard accepts.
    """

    if not user.is_authenticated:
        return None

    accessible_ids = get_accessible_branch_ids(user, request=request)

    if not accessible_ids:
        return None

    staff = _staff_of(user)

    if staff is not None:
        default_access = (
            BranchAccess.objects
            .select_related("branch")
            .filter(
                staff=staff,
                is_default=True,
                branch_id__in=accessible_ids,
            )
            .first()
        )

        if default_access:
            return default_access.branch

        assignment = (
            active_teacher_assignments(
                TeacherAssignment.objects.filter(
                    teacher__staff=staff,
                    branch_id__in=accessible_ids,
                )
            )
            .select_related("branch")
            .order_by("-academic_year__start_date", "-hire_date", "-id")
            .first()
        )

        if assignment:
            return assignment.branch

    supervisor = _supervisor_of(user)

    if supervisor is not None and supervisor.branch_id in accessible_ids:
        return supervisor.branch

    return (
        Branch.objects
        .filter(id__in=accessible_ids)
        .order_by(*BRANCH_ORDERING)
        .first()
    )
