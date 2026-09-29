from django.shortcuts import render

from staff.decorators import teacher_required

from .selectors import build_teacher_dashboard


@teacher_required
def dashboard(request):
    """
    Dashboard view for teacher.
    """

    return render(
        request,
        "core/dashboard.html",
        build_teacher_dashboard(request.teacher_profile),
    )
