"""
The director panel: the school's daily attendance at a glance, read-only.

Every page is a GET view whose state is in the query string (branch, and
on the attendance page the period), so any view can be bookmarked or sent
as a link and works without JavaScript. The page data comes from
``director.selectors`` in one call; the views only read the request and
render.
"""

from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from . import selectors
from .forms import PERIOD_CHOICES, DirectorFilterForm
from .permissions import director_required


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

    form = DirectorFilterForm(request.GET, year=dims.year, branches=dims.branches, today=as_of.date())
    filters = form.filters()
    context.update({
        "form": form,
        "filters": filters,
        # The sidebar's links keep the branch only: each page has its own period.
        "director_query": filters.query(period=None),
        "period_choices": PERIOD_CHOICES,
        "year": dims.year,
    })
    return context, filters, dims, as_of


@director_required
def dashboard(request):
    context, filters, dims, as_of = _setup(request, "dashboard")
    if filters is not None:
        context.update(selectors.home(dims, filters, as_of))
    return render(request, "director/home.html", context)


@director_required
def attendance(request):
    context, filters, dims, as_of = _setup(request, "attendance")
    if filters is not None:
        context.update(selectors.attendance_page(dims, filters, as_of))
    return render(request, "director/attendance.html", context)


@director_required
def execution(request):
    """
    Program execution is deferred until curriculum budgeting («بودجه‌بندی»)
    exists (ADR-023): old links and bookmarks land on the home page, with
    their branch. A temporary redirect, since the page is to come back.
    """

    url = reverse("director:dashboard")
    branch = request.GET.get("branch", "")
    return redirect(f"{url}?{urlencode({'branch': branch})}" if branch.isdigit() else url)
