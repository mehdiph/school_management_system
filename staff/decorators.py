from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.utils import role_dashboard


def get_teacher_profile(user):
    """``user``'s TeacherProfile, or None (no Staff row, or not a teacher)."""

    staff = getattr(user, 'staff_profile', None)
    return getattr(staff, 'teacher_profile', None)


def teacher_required(view):
    """
    For teacher-panel pages: logged-out users go to the login page,
    everyone who is not a teacher goes to their own dashboard (same rule
    as after login), and the view gets ``request.teacher_profile``.
    Mirrors ``student.decorators.student_required``.
    """

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        profile = get_teacher_profile(request.user)
        if profile is not None and request.user.role == 'teacher':
            request.teacher_profile = profile
            return view(request, *args, **kwargs)

        target = role_dashboard(request.user)
        if target == 'core:dashboard':
            # role is "teacher" but no Staff/TeacherProfile row: redirecting
            # to the teacher dashboard would loop forever.
            raise PermissionDenied('پروفایل معلم برای این حساب ثبت نشده است.')
        return redirect(target)

    return wrapper
