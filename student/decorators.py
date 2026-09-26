from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.utils import role_dashboard


def student_required(view):
    """
    For pages that read ``request.user.student_profile``: logged-out
    users go to the login page, everyone who is not a student goes to
    their own dashboard (same rule as after login).
    """

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if hasattr(request.user, 'student_profile'):
            return view(request, *args, **kwargs)

        target = role_dashboard(request.user)
        if target == 'student:dashboard':
            # role is "student" but no StudentProfile row: redirecting
            # to the student dashboard would loop forever.
            raise PermissionDenied('پروفایل دانش‌آموزی برای این حساب ثبت نشده است.')
        return redirect(target)

    return wrapper
