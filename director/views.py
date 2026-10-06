"""
The director panel: read-only analytics over both branches.

Every page is a GET view whose state is in the query string (period,
dates, branch, grade, and the page's own view / class), so any view can
be bookmarked or sent as a link and works without JavaScript. The page
data comes from ``director.selectors`` in one call; the views only read
the request and render.
"""

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from analytics import periods

from . import selectors
from .forms import DirectorFilterForm
from .permissions import director_required


def _url(page, query=""):
    url = reverse(f"director:{page}")
    return f"{url}?{query}" if query else url


def _setup(request, page):
    """
    ``(context, filters, dims, as_of)``: the filter bar and what every
    page shows around it. ``filters`` is None when there is no current
    academic year (the page then only says so).
    """

    dims = selectors.Dimensions.load()
    as_of = timezone.localtime()
    context = {"page": page, "dims": dims, "today": as_of.date()}
    if dims.year is None:
        return context, None, dims, as_of

    form = DirectorFilterForm(
        request.GET, year=dims.year, branches=dims.branches, grades=dims.grades, today=as_of.date(),
    )
    filters = form.filters()
    context.update({
        "form": form,
        "filters": filters,
        "director_query": filters.query(),
        "period_choices": periods.PERIOD_CHOICES,
        "year": dims.year,
    })
    return context, filters, dims, as_of


def _class_id(request):
    value = request.GET.get("class", "")
    return int(value) if value.isdigit() else None


@director_required
def dashboard(request):
    context, filters, dims, as_of = _setup(request, "dashboard")
    if filters is not None:
        context.update(selectors.dashboard(dims, filters, as_of, _url))
    return render(request, "director/dashboard.html", context)


@director_required
def execution(request):
    context, filters, dims, as_of = _setup(request, "execution")
    view = request.GET.get("view")
    if view not in dict(selectors.EXECUTION_VIEWS):
        view = "breakdown"
    context.update({"view": view, "views": selectors.EXECUTION_VIEWS})
    if filters is not None:
        context.update(selectors.execution(dims, filters, as_of, view, _class_id(request), _url))
    return render(request, "director/execution.html", context)


@director_required
def attendance(request):
    context, filters, dims, as_of = _setup(request, "attendance")
    if filters is not None:
        context.update(selectors.attendance(dims, filters, as_of, _class_id(request), _url))
    return render(request, "director/attendance.html", context)
