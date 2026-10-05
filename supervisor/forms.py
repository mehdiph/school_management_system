"""
GET filter forms of the supervisor pages.

The forms are always bound to ``request.GET``. Invalid input never
breaks a page: the field shows its (Persian) error and is simply not
applied -- see ``filters()``.

Every option list comes from the supervisor's scope (the page's
selector) and is materialized once: ``ObjectChoiceField`` validates
against that list instead of re-querying like ``ModelChoiceField``, so an
id outside the scope is just an invalid choice.
"""

from datetime import timedelta

import jdatetime
from django import forms
from django.core.exceptions import ValidationError

from core.templatetags.jalali_tags import fa_digits
from scheduling.utils import week_start
from teaching.models import SchoolSession

from .selectors import SessionFilters, SupervisorSessionsSelector, SupervisorTeachersSelector

#: Persian and Arabic-Indic digits -> ASCII (a date may be typed either way).
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


#: The date inputs: typeable, and the page's JS attaches the Jalali picker.
DATE_INPUT_ATTRS = {
    "class": "sv-input",
    "placeholder": "مثلاً ۱۴۰۵/۰۷/۰۱",
    "maxlength": "10",
    "autocomplete": "off",
    "dir": "ltr",
    "data-jalali-date": "",
}


class JalaliDateField(forms.CharField):
    """A Jalali date typed as 1405/07/01 or 1405-07-01, in any digits."""

    default_error_messages = {
        "invalid": "تاریخ معتبر نیست؛ آن را به شکل ۱۴۰۵/۰۷/۰۱ وارد کنید یا از تقویم انتخاب کنید.",
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    @staticmethod
    def normalize(value):
        return (value or "").strip().translate(_DIGITS).replace("/", "-")

    def to_python(self, value):
        value = self.normalize(super().to_python(value))
        if not value:
            return None
        try:
            return jdatetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError(self.error_messages["invalid"], code="invalid")


class ObjectChoiceField(forms.ChoiceField):
    """A select over an already-fetched list of model instances; cleans to the instance."""

    default_error_messages = {
        "invalid_choice": "گزینه‌ی انتخاب‌شده معتبر نیست.",
    }

    def __init__(self, *, empty_label=None, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)
        self.empty_label = empty_label
        self.objects = {}

    def set_objects(self, objects, label=str):
        objects = list(objects)
        self.objects = {str(obj.pk): obj for obj in objects}
        empty = [("", self.empty_label)] if self.empty_label is not None else []
        self.choices = empty + [(str(obj.pk), label(obj)) for obj in objects]

    def clean(self, value):
        value = super().clean(value)
        return self.objects.get(value) if value else None


def _year_label(year):
    return fa_digits(year.title)


def _class_label(school_class):
    return f"{school_class.grade.name} — {school_class.section} — {school_class.branch.name}"


def _teacher_label(teacher):
    user = teacher.staff.user
    return user.get_full_name() or user.username


class AcademicYearFormMixin:
    """
    Resolves the academic year *before* the other fields are built (their
    options depend on it): the requested one if the supervisor may pick
    it, else the current year, else the newest one. When none was asked
    for, the resolved id is written into the data so the select shows it;
    an invalid one is left for the field to report.
    """

    YEAR_ERRORS = {
        "invalid_choice": "سال تحصیلی انتخاب‌شده معتبر نیست؛ سال جاری نمایش داده می‌شود.",
    }

    @staticmethod
    def resolve_academic_year(data, years):
        requested = next((y for y in years if str(y.pk) == data.get("academic_year")), None)
        current = next((y for y in years if y.is_current), None)
        year = requested or current or (years[0] if years else None)

        if year is not None and not data.get("academic_year"):
            data["academic_year"] = str(year.pk)

        return year


class SessionPeriodForm(forms.Form):
    """
    Date range + status: the part of the session filters that the
    timeline of a single class subject understands too.

    ``range`` (this week / this month / whole year) is a shortcut used by
    links only: it is turned into ``date_from`` / ``date_to`` here, so the
    date inputs show the actual range and a later submit keeps it.
    """

    RANGE_CHOICES = [
        ("week", "این هفته"),
        ("month", "این ماه"),
        ("year", "کل سال"),
    ]

    date_from = JalaliDateField(label="از تاریخ", widget=forms.TextInput(attrs=DATE_INPUT_ATTRS))
    date_to = JalaliDateField(label="تا تاریخ", widget=forms.TextInput(attrs=DATE_INPUT_ATTRS))
    range = forms.ChoiceField(choices=[("", "")] + RANGE_CHOICES, required=False)
    status = forms.ChoiceField(
        label="وضعیت جلسه",
        # «تعطیل» rows are not sessions: they are counted in their own column
        choices=[("", "همه‌ی وضعیت‌ها")] + [
            choice for choice in SchoolSession.Status.choices
            if choice[0] != SchoolSession.Status.HOLIDAY
        ],
        required=False,
        error_messages={"invalid_choice": "وضعیت انتخاب‌شده معتبر نیست."},
    )

    def __init__(self, data, *, academic_year=None, today=None, **kwargs):
        data = data.copy()
        for name in ("date_from", "date_to"):
            if name in data:
                data[name] = JalaliDateField.normalize(data[name])

        period = self.period_dates(data.get("range"), academic_year, today)
        if period is not None:
            data["date_from"], data["date_to"] = (
                day.strftime("%Y-%m-%d") for day in period
            )

        super().__init__(data, **kwargs)

    @staticmethod
    def period_dates(name, academic_year, today):
        """``(first, last)`` Jalali dates of a ``range`` shortcut, or None."""

        if today is None:
            return None

        if name == "week":
            saturday = week_start(today)
            return (
                jdatetime.date.fromgregorian(date=saturday),
                jdatetime.date.fromgregorian(date=saturday + timedelta(days=6)),
            )

        if name == "month":
            day = jdatetime.date.fromgregorian(date=today)
            first = day.replace(day=1)
            next_month = (first + timedelta(days=31)).replace(day=1)
            return first, next_month - timedelta(days=1)

        if name == "year" and academic_year is not None:
            return academic_year.start_date, academic_year.end_date

        return None

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "تاریخ پایان نباید قبل از تاریخ شروع باشد.")

        return cleaned_data

    def filter_values(self):
        """The valid fields' values (an invalid field is not applied)."""

        self.is_valid()
        cleaned = self.cleaned_data
        return {
            "date_from": cleaned.get("date_from"),
            "date_to": cleaned.get("date_to"),
            "status": cleaned.get("status", ""),
        }

    def filters(self):
        return SessionFilters(**self.filter_values())

    @property
    def active_range(self):
        """The ``range`` shortcut the page was opened with, if any."""

        self.is_valid()
        return self.cleaned_data.get("range", "")


class SessionFilterForm(AcademicYearFormMixin, SessionPeriodForm):
    """The filter bar of the training sessions page."""

    SORT_CHOICES = [
        (prefix + key, key)
        for key in SupervisorSessionsSelector.SORT_FIELDS
        for prefix in ("", "-")
    ]

    academic_year = ObjectChoiceField(
        label="سال تحصیلی", error_messages=AcademicYearFormMixin.YEAR_ERRORS
    )
    teacher = ObjectChoiceField(label="معلم", empty_label="همه‌ی معلمان")
    subject = ObjectChoiceField(label="درس", empty_label="همه‌ی دروس")
    school_class = ObjectChoiceField(label="کلاس", empty_label="همه‌ی کلاس‌ها")
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False)

    field_order = [
        "academic_year", "teacher", "subject", "school_class",
        "date_from", "date_to", "status",
    ]

    def __init__(self, data, *, selector, **kwargs):
        data = data.copy()
        years = list(selector.academic_years())
        year = self.resolve_academic_year(data, years)
        self.academic_year = year

        super().__init__(data, academic_year=year, today=selector.today, **kwargs)

        self.fields["academic_year"].set_objects(years, _year_label)
        self.fields["teacher"].set_objects(
            selector.teacher_options(year) if year else [], _teacher_label
        )
        self.fields["subject"].set_objects(selector.subject_options(year) if year else [])
        self.fields["school_class"].set_objects(
            selector.class_options(year) if year else [], _class_label
        )

    @property
    def has_classes(self):
        """Does the supervisor have any (active) class in the selected year?"""

        return bool(self.fields["school_class"].objects)

    def filters(self):
        self.is_valid()
        cleaned = self.cleaned_data
        return SessionFilters(
            academic_year=self.academic_year,
            teacher=cleaned.get("teacher"),
            subject=cleaned.get("subject"),
            school_class=cleaned.get("school_class"),
            sort=cleaned.get("sort") or SupervisorSessionsSelector.DEFAULT_SORT,
            **self.filter_values(),
        )


class TeacherFilterForm(AcademicYearFormMixin, forms.Form):
    """The filter bar of the supervised teachers page."""

    SORT_CHOICES = [
        ("name", "نام"),
        ("-sessions", "بیشترین جلسه"),
        ("sessions", "کمترین جلسه"),
        ("-last_activity", "تازه‌ترین فعالیت"),
        ("last_activity", "قدیمی‌ترین فعالیت"),
    ]
    VIEW_CHOICES = [("cards", "کارتی"), ("table", "جدولی")]

    q = forms.CharField(
        label="جستجو",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            "type": "search",
            "class": "sv-input",
            "placeholder": "نام یا کد پرسنلی",
            "autocomplete": "off",
            "data-debounced-search": "",
        }),
        error_messages={"max_length": "عبارت جستجو نباید بیشتر از ۱۰۰ حرف باشد."},
    )
    academic_year = ObjectChoiceField(
        label="سال تحصیلی", error_messages=AcademicYearFormMixin.YEAR_ERRORS
    )
    subject = ObjectChoiceField(label="درس", empty_label="همه‌ی دروس")
    sort = forms.ChoiceField(
        label="مرتب‌سازی",
        choices=SORT_CHOICES,
        required=False,
        error_messages={"invalid_choice": "ترتیب انتخاب‌شده معتبر نیست."},
    )
    view = forms.ChoiceField(choices=VIEW_CHOICES, required=False)

    def __init__(self, data, *, selector, **kwargs):
        data = data.copy()
        years = list(selector.academic_years())
        year = self.resolve_academic_year(data, years)
        self.academic_year = year

        super().__init__(data, **kwargs)

        self.fields["academic_year"].set_objects(years, _year_label)
        self.fields["subject"].set_objects(selector.subject_options(year) if year else [])

    def filters(self):
        self.is_valid()
        cleaned = self.cleaned_data
        return {
            "year": self.academic_year,
            "subject": cleaned.get("subject"),
            "search": cleaned.get("q", ""),
            "sort": cleaned.get("sort") or SupervisorTeachersSelector.DEFAULT_SORT,
        }

    @property
    def view_mode(self):
        self.is_valid()
        return self.cleaned_data.get("view") or "cards"
