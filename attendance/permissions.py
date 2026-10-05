"""
Who may open and save the attendance page of a ``SchoolSession``.

The page writes attendance for a whole class, so it is never public:

* the teacher of the session's class subject;
* a supervisor whose ``SupervisorScope`` covers the session's class;
* a superuser, or a staff admin with ``attendance.change_attendance``
  who may see the class's branch (``core.services.access``).
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


def can_manage_attendance(user, session, request=None):
    if not user.is_authenticated:
        return False

    if user.is_superuser or is_session_teacher(user, session):
        return True

    school_class = session.class_subject.school_class

    try:
        supervisor = user.supervisor_profile
    except SupervisorProfile.DoesNotExist:
        supervisor = None

    if supervisor is not None:
        # Imported here: supervisor.selectors imports attendance.models.
        from supervisor.selectors import SupervisorScope

        if SupervisorScope(supervisor).classes().filter(pk=school_class.pk).exists():
            return True

    return (
        user.is_staff
        and user.has_perm('attendance.change_attendance')
        and access.has_branch_access(user, school_class.branch_id, request=request)
    )
