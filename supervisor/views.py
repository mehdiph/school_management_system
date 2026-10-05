from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from teaching.models import SchoolSession, SessionContent

from .forms import SessionFilterForm, SessionPeriodForm, TeacherFilterForm
from .permissions import require_supervisor
from .selectors import (
    SupervisorAttendanceSelector,
    SupervisorDashboardSelector,
    SupervisorSessionsSelector,
    SupervisorTeachersSelector,
)


def _is_partial(request):
    """
    ``?partial=1``: the page's JS asks for just the HTML fragment (to put
    into the page / drawer). Without it the same URL is a full page, which
    is what a link opened without JS (or in a new tab) gets.
    """

    return request.GET.get("partial") == "1"


def _period_query(filters):
    """The date range / status of ``filters`` as a query string (for the timeline links)."""

    params = {}
    if filters.date_from:
        params["date_from"] = filters.date_from.strftime("%Y-%m-%d")
    if filters.date_to:
        params["date_to"] = filters.date_to.strftime("%Y-%m-%d")
    if filters.status:
        params["status"] = filters.status
    return urlencode(params)


#: The summary table's sortable columns: (sort key, header, first click
#: sorts descending). Counts and dates are most useful largest/newest first.
SESSION_TABLE_COLUMNS = [
    ("teacher", "معلم", False),
    ("subject", "درس", False),
    ("class", "کلاس", False),
    ("sessions", "جلسات ثبت‌شده", True),
    ("empty", "بدون محتوا", True),
    ("holidays", "تعطیل", True),
    ("first_date", "اولین جلسه", False),
    ("last_date", "آخرین جلسه", True),
]


def _sort_columns(current):
    """Header data for the sortable columns: each one's next ``sort`` value and state."""

    columns = []
    for key, label, descending_first in SESSION_TABLE_COLUMNS:
        if current == key:
            state, next_sort = "ascending", f"-{key}"
        elif current == f"-{key}":
            state, next_sort = "descending", key
        else:
            state, next_sort = "", f"-{key}" if descending_first else key
        columns.append({"key": key, "label": label, "state": state, "next": next_sort})
    return columns


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


@require_supervisor
def training_sessions(request):
    """
    "جلسات آموزشی": per teacher x subject x class, how many sessions were
    recorded, how many lack content, when, and how that compares with the
    timetable -- to judge whether teachers keep pace with the curriculum
    plan. Filters, sorting and paging are all plain GET parameters.
    """

    selector = SupervisorSessionsSelector(request.supervisor)
    form = SessionFilterForm(request.GET, selector=selector)
    filters = form.filters()

    page_obj = Paginator(
        selector.summary_rows(filters), selector.PAGE_SIZE
    ).get_page(request.GET.get("page"))

    context = {
        "form": form,
        "filters": filters,
        "kpis": selector.kpis(filters),
        "page_obj": page_obj,
        "rows": selector.attach_coverage(page_obj.object_list, filters),
        "columns": _sort_columns(filters.sort),
        "period_query": _period_query(filters),
        "range_choices": SessionPeriodForm.RANGE_CHOICES,
        "gap_warning_days": selector.GAP_WARNING_DAYS,
    }

    return render(request, "supervisor/sessions.html", context)


@require_supervisor
def class_subject_timeline(request, pk):
    """
    The sessions of one supervised class subject as a timeline, in the
    date range / status of the query string. A fragment for the expanded
    table row with ``?partial=1``, else a full page.
    """

    selector = SupervisorSessionsSelector(request.supervisor)
    class_subject = get_object_or_404(selector.timeline_class_subjects(), pk=pk)

    form = SessionPeriodForm(
        request.GET,
        academic_year=class_subject.school_class.year,
        today=selector.today,
    )
    filters = form.filters()

    sessions = selector.timeline(class_subject, filters)
    holidays = sum(1 for s in sessions if s.status == SchoolSession.Status.HOLIDAY)

    context = {
        "class_subject": class_subject,
        "sessions": sessions,
        "counted_sessions": len(sessions) - holidays,
        "holiday_sessions": holidays,
        "filters": filters,
        "form": form,
        "status_label": SchoolSession.Status(filters.status).label if filters.status else "",
        "gap_warning_days": selector.GAP_WARNING_DAYS,
    }

    template = (
        "supervisor/partials/_session_timeline.html" if _is_partial(request)
        else "supervisor/session_timeline.html"
    )
    return render(request, template, context)


@require_supervisor
def session_detail(request, pk):
    """
    Everything recorded for one supervised session (full content,
    activity, homework, notes) plus its attendance counts. A fragment for
    the drawer with ``?partial=1``, else a full page.
    """

    selector = SupervisorSessionsSelector(request.supervisor)
    session = get_object_or_404(selector.detail_sessions(), pk=pk)

    try:
        content = session.session_contents
    except SessionContent.DoesNotExist:
        content = None

    context = {
        "session": session,
        "content": content,
        "attendance": selector.attendance_summary(session),
    }

    template = (
        "supervisor/partials/_session_detail.html" if _is_partial(request)
        else "supervisor/session_detail.html"
    )
    return render(request, template, context)


@require_supervisor
def supervised_teachers(request):
    """
    "معلمان من": the teachers of the supervisor's classes, with their
    session-recording activity at a glance, as cards or a table
    (``?view=table``).
    """

    selector = SupervisorTeachersSelector(request.supervisor)
    form = TeacherFilterForm(request.GET, selector=selector)
    filters = form.filters()

    page_obj = Paginator(
        selector.teachers(**filters), selector.PAGE_SIZE
    ).get_page(request.GET.get("page"))

    # The "view sessions" links open the sessions page on the same year
    # (and subject) as this page, plus ?teacher=<id>.
    sessions_query = {}
    if filters["year"]:
        sessions_query["academic_year"] = filters["year"].pk
    if filters["subject"]:
        sessions_query["subject"] = filters["subject"].pk

    context = {
        "form": form,
        "academic_year": filters["year"],
        "sessions_query": urlencode(sessions_query),
        "page_obj": page_obj,
        "teachers": selector.decorate(
            page_obj.object_list, filters["year"], filters["subject"]
        ),
        "view_mode": form.view_mode,
        "inactivity_warning_days": selector.INACTIVITY_WARNING_DAYS,
        "is_filtered": bool(filters["search"] or filters["subject"]),
    }

    return render(request, "supervisor/teachers.html", context)
