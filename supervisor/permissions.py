from functools import wraps

from django.core.exceptions import PermissionDenied

from core.services import access

from .models import SupervisorProfile


def require_supervisor(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            raise PermissionDenied

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
