from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from core.services import access

from .models import SupervisorProfile


def require_supervisor(view_func):
    """
    For supervisor-panel pages: logged-out users go to the login page
    (like ``teacher_required`` / ``student_required``), anyone else who is
    not a supervisor of the selected branch gets 403, and the view gets
    ``request.supervisor``.
    """

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        try:
            supervisor = request.user.supervisor_profile
        except SupervisorProfile.DoesNotExist:
            raise PermissionDenied

        if request.branch is None:
            raise PermissionDenied

        # The supervisor pages are scoped to the branch the supervisor
        # actually supervises, so the selected branch must be that one --
        # a supervisor who *also* has explicit access to another branch
        # has to switch back before these pages will render.
        if request.branch.pk != supervisor.branch_id:
            raise PermissionDenied

        if not access.has_branch_access(
            request.user, request.branch, request=request
        ):
            raise PermissionDenied

        request.supervisor = supervisor

        return view_func(request, *args, **kwargs)

    return wrapper
