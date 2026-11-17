"""
Admin forms. A non-superuser admin is branch-scoped (``core.services.access``)
and may only target their own branches (D23): ``audience.targets_problems``
decides, whatever the browser sent.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.html import format_html

from core.moments import format_jalali_datetime, parse_jalali_datetime
from core.services import access
from school.models import Branch, Grade, SchoolClass
from student.models.student_enrollment import StudentEnrollment

from . import audience
from .models import Announcement, OnlineEvent, OnlineEventAccess, OnlinePlatform
from .validators import clean_url, validate_https_url

MOMENT_HELP = "به تاریخ شمسی و ساعت تهران، مثل ۱۴۰۵/۰۹/۱۲ ۱۰:۳۰."


class MomentField(forms.CharField):
    """A Jalali date and time typed as text, the same way as the blog's publish form."""

    widget = forms.TextInput(attrs={"dir": "ltr", "placeholder": "1405/09/12 10:30", "size": 20})

    def prepare_value(self, value):
        if value and not isinstance(value, str):
            return format_jalali_datetime(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return None
        moment = parse_jalali_datetime(value)
        if moment is None:
            raise ValidationError("تاریخ و ساعت معتبر نیست (قالب: ۱۴۰۵/۰۹/۱۲ ۱۰:۳۰).")
        return moment

    def has_changed(self, initial, data):
        return self.prepare_value(initial) != format_jalali_datetime(parse_jalali_datetime(data))


class AudienceFormMixin:
    """The shared audience part of the event and announcement forms (D3, D23)."""

    def setup_audience(self, request):
        self.request = request
        user = request.user if request else None
        restricted = user is not None and not user.is_superuser
        allowed = access.get_accessible_branch_ids(user, request=request) if restricted else None

        classes = SchoolClass.objects.filter(year__is_current=True, is_active=True)
        branches = Branch.objects.filter(is_active=True)
        if restricted:
            classes = classes.filter(branch__in=allowed)
            branches = branches.filter(pk__in=allowed)
        selected = self.instance.classes.all() if self.instance.pk else SchoolClass.objects.none()

        if "branches" in self.fields:
            self.fields["branches"].queryset = branches.order_by("order", "name")
        if "grades" in self.fields:
            self.fields["grades"].queryset = Grade.objects.filter(is_active=True).order_by("level")
        if "classes" in self.fields:
            self.fields["classes"].queryset = (
                SchoolClass.objects.filter(Q(pk__in=classes) | Q(pk__in=selected))
                .select_related("grade", "branch")
                .order_by("branch__order", "grade__level", "section")
            )
        if restricted and "is_whole_school" in self.fields:
            self.fields["is_whole_school"].disabled = True
            self.fields["is_whole_school"].help_text = "فقط مدیر کل می‌تواند «کل مدرسه» را انتخاب کند."

    def clean_audience(self, cleaned):
        whole = cleaned.get("is_whole_school")
        branches = cleaned.get("branches") or []
        grades = cleaned.get("grades") or []
        classes = cleaned.get("classes") or []
        students = cleaned.get("students") or []
        excluded = cleaned.get("excluded_students") or []

        if whole and (branches or grades or classes or students):
            self.add_error("is_whole_school", "«کل مدرسه» با شعبه، پایه، کلاس یا دانش‌آموز با هم انتخاب نمی‌شود.")
        both = {s.pk for s in students} & {s.pk for s in excluded}
        if both:
            self.add_error("excluded_students", "یک دانش‌آموز نمی‌تواند هم انتخاب و هم مستثنا شده باشد.")

        user = self.request.user if self.request else None
        if user is not None and not user.is_superuser:
            problems = audience.targets_problems(
                is_whole_school=whole,
                branch_ids=[b.pk for b in branches],
                grade_ids=[g.pk for g in grades],
                class_ids=[c.pk for c in classes],
                student_ids=[s.pk for s in students],
                excluded_ids=[s.pk for s in excluded],
                allowed=access.get_accessible_branch_ids(user, request=self.request),
            )
            for name, message in problems.items():
                self.add_error(name if name in self.fields else None, message)


class OnlineEventAdminForm(AudienceFormMixin, forms.ModelForm):
    start_at = MomentField(label="شروع", help_text=MOMENT_HELP)
    end_at = MomentField(label="پایان", help_text=MOMENT_HELP)

    class Meta:
        model = OnlineEvent
        fields = "__all__"

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_audience(request)
        if "platform" in self.fields:
            current = self.instance.platform_id
            self.fields["platform"].queryset = OnlinePlatform.objects.filter(Q(is_active=True) | Q(pk=current))

    def clean(self):
        cleaned = super().clean()
        self.clean_audience(cleaned)
        return cleaned


class AnnouncementAdminForm(AudienceFormMixin, forms.ModelForm):
    visible_from = MomentField(label="نمایش از", help_text=MOMENT_HELP)
    visible_until = MomentField(label="نمایش تا", help_text=MOMENT_HELP)

    class Meta:
        model = Announcement
        fields = "__all__"

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_audience(request)

    def clean(self):
        cleaned = super().clean()
        self.clean_audience(cleaned)
        if cleaned.get("level") == Announcement.Level.URGENT:
            cleaned["is_dismissible"] = False
            self.instance.is_dismissible = False
        return cleaned


class StudentLabelWidget(forms.HiddenInput):
    """An existing row's student: the name, with no per-row query for a picker's option."""

    def __init__(self, label, attrs=None):
        super().__init__(attrs)
        self.label = label

    @property
    def is_hidden(self):
        return False

    def render(self, name, value, attrs=None, renderer=None):
        return format_html("{}{}", super().render(name, value, attrs, renderer), self.label)


class OnlineEventAccessForm(forms.ModelForm):
    """
    A secret is never put back into the page: a blank field keeps what is stored
    (D15), so staff can enter or replace one without being able to read it.
    """

    url = forms.CharField(
        label="لینک شخصی",
        required=False,
        max_length=2000,
        widget=forms.TextInput(attrs={"dir": "ltr", "autocomplete": "off", "size": 20}),
    )
    password = forms.CharField(
        label="رمز عبور",
        required=False,
        max_length=200,
        widget=forms.PasswordInput(render_value=False, attrs={"dir": "ltr", "autocomplete": "new-password", "size": 14}),
    )
    access_code = forms.CharField(
        label="کد دسترسی",
        required=False,
        max_length=200,
        widget=forms.PasswordInput(render_value=False, attrs={"dir": "ltr", "autocomplete": "off", "size": 14}),
    )

    #: Set by the admin: the logged-in request, and the event of a new row.
    request = None
    parent_event = None

    class Meta:
        model = OnlineEventAccess
        fields = ["student", "url", "username", "password", "access_code", "note"]
        widgets = {
            "username": forms.TextInput(attrs={"dir": "ltr", "autocomplete": "off", "size": 14}),
            "note": forms.TextInput(attrs={"size": 18}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and "student" in self.fields:
            field = self.fields["student"]
            field.disabled = True
            field.widget = StudentLabelWidget(label=self.instance.student)
        stored = {
            "url": self.instance.url_encrypted,
            "password": self.instance.password_encrypted,
            "access_code": self.instance.access_code_encrypted,
        }
        for name, value in stored.items():
            if value and name in self.fields:
                self.fields[name].widget.attrs["placeholder"] = "ثبت شده"

    def _event(self):
        if self.parent_event is not None:
            return self.parent_event
        return self.instance.event if self.instance.event_id else None

    def clean_student(self):
        student = self.cleaned_data["student"]
        request = self.request
        if request is not None and not request.user.is_superuser and not self.instance.pk:
            allowed = access.get_accessible_branch_ids(request.user, request=request)
            inside = StudentEnrollment.objects.current().filter(student=student, school_class__branch__in=allowed)
            if not inside.exists():
                raise ValidationError("این دانش‌آموز در شعبه‌های شما نیست.")
        return student

    def clean_url(self):
        url = clean_url(self.cleaned_data["url"])
        if url:
            event = self._event()
            platform = event.platform if event is not None and event.platform_id else None
            validate_https_url(url, platform.allowed_domains if platform else "")
        return url

    def clean(self):
        cleaned = super().clean()
        has_input = any(cleaned.get(name) for name in ("url", "username", "password", "access_code"))
        has_stored = any((self.instance.url_encrypted, self.instance.password_encrypted, self.instance.access_code_encrypted))
        if not has_input and not has_stored:
            raise ValidationError("لینک، نام کاربری، رمز یا کد لازم است؛ فقط «توضیح» کافی نیست.")
        return cleaned

    def save(self, commit=True):
        self.instance.set_secrets(
            url=self.cleaned_data.get("url"),
            password=self.cleaned_data.get("password"),
            access_code=self.cleaned_data.get("access_code"),
        )
        if self.request is not None:
            self.instance.updated_by = self.request.user
        return super().save(commit)


class AccessImportForm(forms.Form):
    file = forms.FileField(
        label="فایل اکسل",
        help_text="فایل xlsx ساخته‌شده از روی قالب همین رویداد.",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )
