"""
The director panel's filters: a period (today / this week / this month)
and a branch, read from the query string so every view is a plain link
(and works without JavaScript).

Like the supervisor's filters, invalid input never breaks a page. An
unknown branch is reported and not applied; an unknown period -- an old
link's «از ابتدای سال» or custom range -- quietly opens the default.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from django import forms

from academic_calendar.services import to_gregorian
from analytics import periods
from attendance import services as attendance
from core.forms import ObjectChoiceField

PERIOD_CHOICES = [
    (periods.TODAY, "امروز"),
    (periods.WEEK, "این هفته"),
    (periods.MONTH, "این ماه"),
]

#: The period the attendance page opens with.
DEFAULT_PERIOD = periods.MONTH


@dataclass(frozen=True)
class DirectorFilters:
    """
    The validated filters and the range they give. ``start`` / ``end``
    are Gregorian, clamped to the days with daily attendance (from
    ``ATTENDANCE_DAILY_START_DATE``) and to the academic year up to
    today; both are None when no such day is left. ``clamped`` says the
    cutoff cut days off the start of the period (the page notes it).
    """

    year: object
    period: str
    branch: object = None
    start: date | None = None
    end: date | None = None
    clamped: bool = False

    @property
    def is_empty(self):
        return self.start is None

    def query(self, **overrides):
        """These filters as a query string (``overrides`` replace or, with None, drop one)."""

        params = {"period": self.period, "branch": self.branch.pk if self.branch else None}
        params.update(overrides)
        return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def daily_range(period, today, year):
    """
    ``(start, end, clamped)`` of ``period`` (a preset of
    ``analytics.periods``): its days from the attendance cutoff on, in the
    academic year, up to today; ``(None, None, clamped)`` when none is left.
    """

    start, end = periods.period_range(period, today, year)
    start = max(start, to_gregorian(year.start_date))
    end = min(end, to_gregorian(year.end_date))
    clamped = start < attendance.daily_start() <= end
    _, daily = attendance.split_range(start, end)
    if daily is None or start > end:
        return None, None, clamped
    return daily[0], daily[1], clamped


class DirectorFilterForm(forms.Form):
    period = forms.ChoiceField(
        label="بازه", choices=PERIOD_CHOICES, required=False, widget=forms.HiddenInput,
    )
    branch = ObjectChoiceField(label="شعبه", empty_label="همه‌ی شعبه‌ها")

    def __init__(self, data, *, year, branches, today):
        data = data.copy()
        if data.get("period") not in dict(PERIOD_CHOICES):
            data["period"] = DEFAULT_PERIOD
        super().__init__(data)
        self.year = year
        self.today = today
        self.fields["branch"].set_objects(branches, lambda branch: branch.name)
        self.fields["branch"].widget.attrs["class"] = "sv-input director-select"

    def filters(self):
        self.is_valid()   # runs the cleaning; an invalid branch is only dropped
        period = self.cleaned_data.get("period") or DEFAULT_PERIOD
        branch = None if "branch" in self.errors else self.cleaned_data.get("branch")
        start, end, clamped = daily_range(period, self.today, self.year)
        return DirectorFilters(
            year=self.year, period=period, branch=branch, start=start, end=end, clamped=clamped,
        )
