"""
The director panel's filter bar: a GET form shared by every page, so
each view is a plain link (and works without JavaScript).

Like the supervisor's filters, invalid input never breaks a page: the
field shows its error and is not applied. The date inputs always show
the range in effect; dates that differ from the selected preset's range
make it a custom range (so editing a date works without JavaScript), and
a custom range without dates falls back to the default range.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from django import forms

from academic_calendar.services import to_gregorian, to_jalali
from analytics import periods
from core.forms import DATE_INPUT_ATTRS, JalaliDateField, ObjectChoiceField

#: The range a page opens with: this Jalali month. "Since the start of the
#: academic year" stays a preset, but it is the slowest view late in the
#: year (docs/apps/director.md §8), so it is not what every visit pays for.
DEFAULT_PERIOD = periods.MONTH


@dataclass(frozen=True)
class DirectorFilters:
    """
    The validated filters. ``start`` / ``end`` are the requested
    Gregorian range; the analytics scope still clamps it to the year and
    to today. ``branch`` / ``grade`` are None for "all".
    """

    year: object
    period: str
    start: date
    end: date
    branch: object = None
    grade: object = None

    def query(self, **overrides):
        """
        These filters as a query string (``overrides`` replace or, with
        None, drop a parameter): what every link of the panel carries.
        """

        params = {"period": self.period}
        if self.period == periods.CUSTOM:
            params["date_from"] = _jalali_text(self.start)
            params["date_to"] = _jalali_text(self.end)
        if self.branch is not None:
            params["branch"] = self.branch.pk
        if self.grade is not None:
            params["grade"] = self.grade.pk
        params.update(overrides)
        return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def _jalali_text(day):
    return to_jalali(day).strftime("%Y-%m-%d")


def custom_range_query(start, end, **params):
    """A query string for a custom range (alert links use it for their window)."""

    return urlencode({
        "period": periods.CUSTOM,
        "date_from": _jalali_text(start),
        "date_to": _jalali_text(end),
        **{key: value for key, value in params.items() if value not in (None, "")},
    })


def _branch_label(branch):
    return branch.name


def _grade_label(grade):
    return grade.name


class DirectorFilterForm(forms.Form):
    #: Set by the preset links; a submitted form keeps it unless the dates
    #: were edited (see the module docstring).
    period = forms.ChoiceField(
        label="بازه", choices=periods.PERIOD_CHOICES, required=False, widget=forms.HiddenInput,
    )
    date_from = JalaliDateField(label="از تاریخ", widget=forms.TextInput(attrs=DATE_INPUT_ATTRS))
    date_to = JalaliDateField(label="تا تاریخ", widget=forms.TextInput(attrs=DATE_INPUT_ATTRS))
    branch = ObjectChoiceField(label="شعبه", empty_label="همه‌ی شعبه‌ها")
    grade = ObjectChoiceField(label="پایه", empty_label="همه‌ی پایه‌ها")

    def __init__(self, data, *, year, branches, grades, today):
        data = data.copy()
        if not data.get("period"):
            has_dates = data.get("date_from") or data.get("date_to")
            data["period"] = periods.CUSTOM if has_dates else DEFAULT_PERIOD
        super().__init__(data)
        self.year = year
        self.today = today
        self.fields["branch"].set_objects(branches, _branch_label)
        self.fields["grade"].set_objects(grades, _grade_label)
        for name in ("branch", "grade"):
            self.fields[name].widget.attrs["class"] = "sv-input"

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", "تاریخ پایان نباید قبل از تاریخ شروع باشد.")
        return cleaned

    def _value(self, name):
        """A field's cleaned value, or None when it is invalid (not applied)."""

        if name in self.errors:
            return None
        return self.cleaned_data.get(name)

    def filters(self):
        self.is_valid()   # runs the cleaning; errors only drop their field

        period = self._value("period") or DEFAULT_PERIOD
        date_from, date_to = self._value("date_from"), self._value("date_to")
        typed = (
            to_gregorian(date_from) if date_from else None,
            to_gregorian(date_to) if date_to else None,
        )
        preset = periods.period_range(period, self.today, self.year)
        if any(typed) and typed != preset:
            period = periods.CUSTOM

        if period == periods.CUSTOM and any(typed):
            start = typed[0] or to_gregorian(self.year.start_date)
            end = typed[1] or self.today
        else:
            if period == periods.CUSTOM:
                period = DEFAULT_PERIOD
            start, end = periods.period_range(period, self.today, self.year)

        # Show the range in effect (unless a date was rejected: then the
        # typed text stays next to its error).
        self.data = self.data.copy()
        self.data["period"] = period
        for name, value in (("date_from", start), ("date_to", end)):
            if name not in self.errors:
                self.data[name] = _jalali_text(value)

        return DirectorFilters(
            year=self.year,
            period=period,
            start=start,
            end=end,
            branch=self._value("branch"),
            grade=self._value("grade"),
        )
