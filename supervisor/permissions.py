from django.core.exceptions import PermissionDenied
from .models.supervisor_profile import SupervisorProfile
from functools import wraps
    
from functools import wraps

from django.core.exceptions import PermissionDenied

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

        if request.branch.pk != supervisor.branch_id:
            raise PermissionDenied

        request.supervisor = supervisor

        return view_func(request, *args, **kwargs)

    return wrapper