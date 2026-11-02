from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from student.decorators import student_required
from student.selectors import current_enrollment

from . import selectors, services
from .models.event import Tab


@student_required
@never_cache
def online_page(request):
    """«کلاس‌ها و آزمون‌های آنلاین»: personal links and credentials, so never cached."""

    tab = request.GET.get("tab", Tab.TODAY)
    if tab not in Tab.values:
        raise Http404
    context = selectors.online_page(request.user.student_profile, tab)
    template = "online_classes/_page_list.html" if request.GET.get("partial") == "1" else "online_classes/online_page.html"
    return render(request, template, context)


@student_required
@require_POST
def dismiss_announcement(request, pk):
    """
    A plain form, so it works without JS. Outside the student's audience or
    display window is a 404; a banner that may not be closed is a 403.
    """

    profile = request.user.student_profile
    announcement = get_object_or_404(selectors.live_announcements(current_enrollment(profile)), pk=pk)
    if not announcement.can_be_dismissed:
        return HttpResponse(status=403)
    services.dismiss(announcement, profile)
    if request.GET.get("partial") == "1":
        return HttpResponse(status=204)
    return redirect("student:dashboard")
