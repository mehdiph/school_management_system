from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_safe

from accounts.utils import role_dashboard


def is_director(user):
    """The school director (role «مدیر مدرسه»), or a superuser."""

    return user.is_authenticated and (
        user.is_superuser or user.role == user.Roles.DIRECTOR
    )


def director_required(view):
    """
    For director-panel pages: logged-out users go to the login page,
    everyone else who is not the director goes to their own dashboard
    (the same rule as ``teacher_required`` / ``student_required``).

    The panel is read-only, so only GET / HEAD are accepted: anything
    else is 405, whoever asks. The director needs no profile row: they
    see every active branch, so there is nothing to look up.
    """

    @login_required
    @require_safe
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if is_director(request.user):
            return view(request, *args, **kwargs)
        return redirect(role_dashboard(request.user))

    return wrapper
