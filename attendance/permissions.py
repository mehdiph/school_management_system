"""
Who may see archived per-session attendance, and who may take daily
attendance.

Archived attendance of a ``SchoolSession`` (read-only):

* the teacher of the session's class subject;
* a supervisor whose ``SupervisorScope`` covers the session's class;
* a superuser, or a staff admin with ``attendance.view_sessionattendance``
  who may see the class's branch (``core.services.access``).

Daily attendance of a ``SchoolClass`` (recording and editing):

* the grade supporter whose ``SupervisorScope`` covers the class;
* a superuser, or a staff admin with
  ``attendance.change_dailyattendancesheet`` who may see the class's branch.

Teachers do not take daily attendance.
"""

from core.services import access
from staff.decorators import get_teacher_profile
from supervisor.models import SupervisorProfile


def is_session_teacher(user, session):
    teacher = get_teacher_profile(user)
    return (
        teacher is not None
        and session.class_subject.teacher_assignment.teacher_id == teacher.pk
    )


def is_class_supervisor(user, school_class):
    """Is ``user`` a supervisor whose scope includes ``school_class``?"""

    try:
        supervisor = user.supervisor_profile
    except SupervisorProfile.DoesNotExist:
        return False

    # Imported here: supervisor.selectors imports attendance.services.
    from supervisor.selectors import SupervisorScope

    return SupervisorScope(supervisor).classes().filter(pk=school_class.pk).exists()


def _is_branch_admin(user, school_class, permission, request=None):
    return (
        user.is_staff
        and user.has_perm(permission)
        and access.has_branch_access(user, school_class.branch_id, request=request)
    )


def can_view_session_attendance(user, session, request=None):
    if not user.is_authenticated:
        return False

    if user.is_superuser or is_session_teacher(user, session):
        return True

    school_class = session.class_subject.school_class
    return is_class_supervisor(user, school_class) or _is_branch_admin(
        user, school_class, 'attendance.view_sessionattendance', request
    )


def can_record_daily_attendance(user, school_class, request=None):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return is_class_supervisor(user, school_class) or _is_branch_admin(
        user, school_class, 'attendance.change_dailyattendancesheet', request
    )
