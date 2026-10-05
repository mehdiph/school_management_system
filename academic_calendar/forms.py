"""
Admin forms of the academic calendar.

A non-superuser admin is branch-scoped (``core.services.access``): they
may only pick their own branches and must pick at least one -- an empty
branch scope means "every branch", which only a superuser may declare.
"""

from django import forms
from django_jalali import forms as jforms
from django_jalali.admin.widgets import AdminjDateWidget

from core.services import access
from scheduling.models.bell import Bell
from school.models import AcademicYear, Branch, Grade

from .models import CalendarEvent

ALL_BRANCHES_SUPERUSER_ONLY = (
    "شعبه را انتخاب کنید؛ فقط مدیر کل می‌تواند رویداد همه‌ی شعبه‌ها را ثبت کند."
)


def branch_choices(user):
    branches = Branch.objects.filter(is_active=True).order_by("order", "name")
    if user.is_superuser:
        return branches
    return branches.filter(pk__in=access.get_accessible_branch_ids(user))


def _check_branches(user, branches):
    if user.is_superuser:
        return
    if not branches:
        raise forms.ValidationError({"branches": ALL_BRANCHES_SUPERUSER_ONLY})


class CalendarEventAdminForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = [
            "academic_year", "title", "event_type", "start_date", "end_date",
            "branches", "grades", "bells", "description", "is_active",
        ]

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        if not self.instance.pk:
            self.fields["academic_year"].initial = AcademicYear.objects.filter(is_current=True).first()
        if request is not None and "branches" in self.fields:
            self.fields["branches"].queryset = branch_choices(request.user)
        if "grades" in self.fields:
            self.fields["grades"].queryset = Grade.objects.filter(is_active=True).order_by("level")
        if "bells" in self.fields:
            self.fields["bells"].queryset = Bell.objects.filter(is_active=True).order_by("order")

    def clean(self):
        cleaned = super().clean()
        if self.request is not None:
            _check_branches(self.request.user, cleaned.get("branches"))
        return cleaned


class QuickClosureForm(forms.Form):
    """«تعطیلی اضطراری»: an unplanned closure, often entered on the day or after it."""

    title = forms.CharField(
        label="عنوان",
        max_length=200,
        initial="تعطیلی اضطراری",
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    date = jforms.jDateField(
        label="تاریخ",
        widget=AdminjDateWidget,
        error_messages={"invalid": "تاریخ معتبر نیست (قالب: ۱۴۰۵-۰۷-۱۲)."},
    )
    end_date = jforms.jDateField(
        label="تا تاریخ",
        required=False,
        widget=AdminjDateWidget,
        help_text="برای تعطیلی یک‌روزه خالی بگذارید.",
        error_messages={"invalid": "تاریخ معتبر نیست (قالب: ۱۴۰۵-۰۷-۱۲)."},
    )
    branches = forms.ModelMultipleChoiceField(
        label="شعبه‌ها",
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="خالی یعنی همه‌ی شعبه‌ها.",
    )
    grades = forms.ModelMultipleChoiceField(
        label="پایه‌ها",
        queryset=Grade.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="خالی یعنی همه‌ی پایه‌ها.",
    )
    bells = forms.ModelMultipleChoiceField(
        label="زنگ‌ها",
        queryset=Bell.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="خالی یعنی کل روز؛ برای «از زنگ سوم به بعد» همان زنگ‌ها را بزنید.",
    )
    description = forms.CharField(
        label="توضیحات",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "vLargeTextField"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.academic_year = AcademicYear.objects.filter(is_current=True).first()
        self.fields["branches"].queryset = branch_choices(user)
        self.fields["grades"].queryset = Grade.objects.filter(is_active=True).order_by("level")
        self.fields["bells"].queryset = Bell.objects.filter(is_active=True).order_by("order")

    def clean(self):
        cleaned = super().clean()
        if self.academic_year is None:
            raise forms.ValidationError("سال تحصیلی جاری تعریف نشده است.")
        _check_branches(self.user, cleaned.get("branches"))

        start, end = cleaned.get("date"), cleaned.get("end_date") or cleaned.get("date")
        if start and end:
            if end < start:
                self.add_error("end_date", "تاریخ پایان نباید قبل از تاریخ شروع باشد.")
            elif start < self.academic_year.start_date or end > self.academic_year.end_date:
                self.add_error("date", f"تاریخ باید داخل سال تحصیلی «{self.academic_year.title}» باشد.")
        return cleaned


class EventImportForm(forms.Form):
    file = forms.FileField(
        label="فایل اکسل",
        help_text="فایل xlsx ساخته‌شده از روی قالب.",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )


class ConflictFilterForm(forms.Form):
    year = forms.ModelChoiceField(
        label="سال تحصیلی",
        queryset=AcademicYear.objects.order_by("-start_date"),
        required=False,
        empty_label=None,
    )
