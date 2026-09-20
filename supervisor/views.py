from django.shortcuts import render

from .permissions import require_supervisor
from .selectors import SupervisorAttendanceSelector, SupervisorDashboardSelector


@require_supervisor
def dashboard(request):
    """
    Supervisor dashboard.

    All business/query logic lives in SupervisorDashboardSelector; the
    view only wires the authenticated supervisor to it and renders the
    result. The global topbar's date/time come from
    core.context_processors.topbar (shared by every dashboard), not
    from this view.
    """

    selector = SupervisorDashboardSelector(request.supervisor)
    context = selector.get_dashboard_data()

    return render(request, "supervisor/dashboard.html", context)


@require_supervisor
def attention_list(request):
    """
    Full list of the supervisor's "needs attention" items (classes whose
    scheduled slot ended today without a registered session).

    Unlike the dashboard's inline section, this page can be filtered
    down to a single class -- useful once a supervisor oversees more
    than a handful of classes. The filter only narrows the already
    scoped list returned by the selector, so it can't be used to see
    anything outside the supervisor's own classes.
    """

    selector = SupervisorDashboardSelector(request.supervisor)
    items = selector.attention_items()
    classes = selector.scope.classes().order_by("section")

    selected_class_id = request.GET.get("class", "")
    if selected_class_id:
        try:
            class_id = int(selected_class_id)
        except ValueError:
            class_id = None

        if class_id is not None:
            items = [
                item for item in items
                if item["school_class"].id == class_id
            ]

    context = {
        "attention_items": items,
        "classes": classes,
        "selected_class_id": selected_class_id,
    }

    return render(request, "supervisor/attention_list.html", context)


@require_supervisor
def attendance(request):
    """
    Supervisor's per-class attendance page: the latest registered
    session for the selected class, its attendance rows and summary.

    All querying lives in ``SupervisorAttendanceSelector``; this view
    only reads GET params and renders. ``class`` is the only param the
    selector uses -- a tampered/foreign id simply fails to resolve
    (see ``SupervisorAttendanceSelector.resolve_class``) and falls back
    to the supervisor's first allowed class, it never raises or leaks
    another class's data.

    ``status``/``search`` are *not* used to filter the queryset: class
    rosters are small (a handful to ~30 students), so filtering them in
    the browser (see attendance.js) avoids a DB round trip per
    keystroke/click for no real benefit. They're only read here to
    preserve the toolbar's state across a page reload (e.g. the
    "بروزرسانی" button) or a shared link.
    """

    selector = SupervisorAttendanceSelector(request.supervisor)

    requested_class_id = request.GET.get("class")
    try:
        class_id = int(requested_class_id) if requested_class_id else None
    except ValueError:
        class_id = None

    context = selector.get_attendance_page_data(class_id)
    context["current_status"] = request.GET.get("status", "all")
    context["search_query"] = request.GET.get("search", "")

    return render(request, "supervisor/attendance.html", context)
