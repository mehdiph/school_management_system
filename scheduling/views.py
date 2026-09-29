from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from staff.decorators import teacher_required

from .pdf import render_schedule_pdf, render_teacher_schedule_pdf
from .services import (
    get_student_weekly_schedule,
    get_teacher_weekly_schedule,
    schedule_pdf_filename,
    teacher_schedule_pdf_filename,
)


def _student_profile(request):
    # No schedule id in the URL on purpose: a student can only ever get
    # their own schedule, there is nothing to tamper with.
    profile = getattr(request.user, "student_profile", None)
    if profile is None:
        raise PermissionDenied("برنامه هفتگی فقط برای دانش‌آموزان در دسترس است.")
    return profile


def _selected_week(request, schedule):
    """?week=1|2 when valid, otherwise the current rotation week."""

    try:
        week = schedule.week(int(request.GET.get("week", "")))
    except ValueError:
        week = None
    return week or schedule.current_week


@login_required
def weekly_schedule(request):
    schedule = get_student_weekly_schedule(_student_profile(request))

    context = {"schedule": schedule}
    if schedule is not None:
        context["selected_week"] = _selected_week(request, schedule)

    return render(request, "scheduling/weekly-schedule.html", context)


@login_required
def weekly_schedule_pdf(request):
    schedule = get_student_weekly_schedule(_student_profile(request))
    if schedule is None:
        return render(request, "scheduling/weekly-schedule.html", {"schedule": None}, status=404)

    response = HttpResponse(render_schedule_pdf(schedule), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{schedule_pdf_filename(schedule)}"'
    return response


# ----------------------------------------------------------------------
# Teacher
# ----------------------------------------------------------------------
# No teacher id in these URLs either: the schedule is always built for
# request.teacher_profile (set by teacher_required), so a teacher can only
# ever see their own.

@teacher_required
def teacher_schedule(request):
    schedule = get_teacher_weekly_schedule(request.teacher_profile)

    context = {"schedule": schedule}
    if schedule is not None and schedule.has_entries:
        context["selected_week"] = _selected_week(request, schedule)
        context["weeks"] = [(week, schedule.summary(week)) for week in schedule.weeks]

    return render(request, "scheduling/teacher-schedule.html", context)


@teacher_required
def teacher_schedule_pdf(request):
    schedule = get_teacher_weekly_schedule(request.teacher_profile)
    if schedule is None or not schedule.has_entries:
        return render(request, "scheduling/teacher-schedule.html", {"schedule": schedule}, status=404)

    response = HttpResponse(render_teacher_schedule_pdf(schedule), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{teacher_schedule_pdf_filename(schedule)}"'
    return response
