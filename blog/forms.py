import re
from datetime import datetime

import jdatetime
from django import forms
from django.conf import settings
from django.utils import timezone

from .models import BlogAuthor, Category, Post, Section, Tag

_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_JALALI_DATETIME = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")


def parse_jalali_datetime(value):
    """«۱۴۰۵/۰۸/۱۲ ۱۰:۳۰» (Persian or ASCII digits; time optional, default 00:00) -> aware datetime, or None."""

    match = _JALALI_DATETIME.fullmatch((value or "").strip().translate(_TO_ASCII_DIGITS))
    if not match:
        return None
    year, month, day, hour, minute = (int(part) if part else 0 for part in match.groups())
    try:
        moment = jdatetime.datetime(year, month, day, hour, minute).togregorian()
    except ValueError:
        return None
    return timezone.make_aware(datetime(moment.year, moment.month, moment.day, moment.hour, moment.minute))


class CategoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.section.title} › {obj}"


class PostAdminForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = "__all__"
        field_classes = {"category": CategoryChoiceField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "category" in self.fields:
            self.fields["category"].queryset = Category.objects.select_related("section").order_by(
                "section__order", "section_id", "order", "id"
            )
            self.fields["category"].help_text = "دسته باید در همان بخش نوشته باشد."

    def clean_tags(self):
        tags = self.cleaned_data.get("tags")
        if tags is not None and len(tags) > settings.BLOG_MAX_TAGS_PER_POST:
            raise forms.ValidationError(f"حداکثر {settings.BLOG_MAX_TAGS_PER_POST} برچسب برای هر نوشته.")
        return tags


class BlogAuthorAdminForm(forms.ModelForm):
    grant_sections = forms.ModelMultipleChoiceField(
        queryset=Section.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="بخش‌هایی که می‌تواند در آن‌ها بنویسد",
        help_text="بخش غیرفعال اجازه نوشتن نمی‌دهد، حتی اگر تیک خورده باشد.",
    )

    class Meta:
        model = BlogAuthor
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["grant_sections"].initial = list(self.instance.sections.values_list("pk", flat=True))


class ChecklistMixin:
    """One required tick per line of «فهرست بررسی پیش از انتشار» (D16)."""

    def add_checklist(self, items):
        self.checklist_names = []
        for index, item in enumerate(items):
            name = f"check_{index}"
            self.fields[name] = forms.BooleanField(
                label=item,
                required=True,
                error_messages={"required": "این مورد را بررسی و تیک بزنید."},
            )
            self.checklist_names.append(name)

    def checklist_fields(self):
        return [self[name] for name in self.checklist_names]


class PublishForm(ChecklistMixin, forms.Form):
    when = forms.ChoiceField(
        choices=[("now", "اکنون"), ("at", "در زمان مشخص")],
        initial="now",
        widget=forms.RadioSelect,
        label="زمان انتشار",
    )
    publish_at = forms.CharField(
        required=False,
        label="تاریخ و ساعت",
        help_text="به تاریخ شمسی، مثل ۱۴۰۵/۰۸/۱۲ ۱۰:۳۰ (ساعت تهران). زمان آینده یعنی زمان‌بندی؛ "
                  "نوشته از همان زمان در سایت دیده می‌شود.",
        widget=forms.TextInput(attrs={"dir": "ltr", "placeholder": "1405/08/12 10:30", "size": 20}),
    )

    def __init__(self, *args, checklist=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.add_checklist(checklist)

    def clean(self):
        data = super().clean()
        if data.get("when") == "at":
            moment = parse_jalali_datetime(data.get("publish_at"))
            if moment is None:
                self.add_error("publish_at", "تاریخ را به شکل ۱۴۰۵/۰۸/۱۲ ۱۰:۳۰ بنویسید.")
            data["moment"] = moment
        else:
            data["moment"] = None
        return data


class ReturnForm(forms.Form):
    note = forms.CharField(
        label="یادداشت برای نویسنده",
        widget=forms.Textarea(attrs={"rows": 3, "cols": 70}),
        help_text="به نویسنده نمایش داده می‌شود: چه چیزی باید تغییر کند.",
        error_messages={"required": "برای بازگرداندن، یادداشتی برای نویسنده بنویسید."},
    )


class BulkPublishForm(ChecklistMixin, forms.Form):
    def __init__(self, *args, checklist=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.add_checklist(checklist)


class TagMergeForm(forms.Form):
    target = forms.ModelChoiceField(
        queryset=Tag.objects.filter(is_active=True),
        label="ادغام در برچسب",
        help_text="نوشته‌های برچسب‌های انتخاب‌شده این برچسب را می‌گیرند و آن برچسب‌ها غیرفعال می‌شوند.",
    )
