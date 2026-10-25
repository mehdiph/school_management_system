"""
The public contact form. Topic and branch choices come from lists the
view has already fetched, so building and validating the form costs no
queries.
"""

from django import forms
from django.conf import settings
from django.core import signing
from django.utils import timezone

from accounts.validators import normalize_mobile, validate_mobile
from core.forms import ObjectChoiceField

_FORM_SALT = "website.contact.started"


def form_token(at=None):
    """A signed timestamp of when the form was rendered (the time trap)."""
    at = at or timezone.now()
    return signing.dumps(at.timestamp(), salt=_FORM_SALT)


class ContactForm(forms.Form):
    name = forms.CharField(
        label="نام و نام خانوادگی",
        min_length=2,
        max_length=100,
        error_messages={
            "required": "نام و نام خانوادگی را وارد کنید.",
            "min_length": "نام باید دست‌کم ۲ حرف باشد.",
            "max_length": "نام حداکثر ۱۰۰ حرف است.",
        },
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    mobile = forms.CharField(
        label="شماره موبایل",
        max_length=20,
        help_text="با این شماره با شما تماس می‌گیریم؛ مثل ۰۹۱۲۳۴۵۶۷۸۹.",
        error_messages={"required": "شماره موبایل را وارد کنید."},
        widget=forms.TextInput(
            attrs={"autocomplete": "tel", "inputmode": "tel", "dir": "ltr", "placeholder": "۰۹۱۲۳۴۵۶۷۸۹"}
        ),
    )
    topic = ObjectChoiceField(
        label="موضوع",
        required=True,
        empty_label="انتخاب کنید",
        error_messages={"required": "موضوع پیام را انتخاب کنید."},
    )
    location = ObjectChoiceField(label="شعبه", empty_label="فرقی نمی‌کند")
    message = forms.CharField(
        label="متن پیام",
        min_length=10,
        max_length=2000,
        error_messages={
            "required": "متن پیام را بنویسید.",
            "min_length": "متن پیام باید دست‌کم ۱۰ حرف باشد.",
            "max_length": "متن پیام حداکثر ۲۰۰۰ حرف است.",
        },
        widget=forms.Textarea(attrs={"rows": 6}),
    )
    # Honeypot: hidden from people (CSS + aria-hidden), filled in by bots.
    website = forms.CharField(
        label="این فیلد را خالی بگذارید",
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    def __init__(self, *args, topics=(), locations=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].set_objects(topics)
        if not topics:
            del self.fields["topic"]
        self.fields["location"].set_objects(locations, label=lambda loc: loc.display_title)
        if len(locations) < 2:
            del self.fields["location"]

    @property
    def is_spam(self):
        """The honeypot was filled in: pretend success, save nothing."""
        return bool(self.data.get("website", "").strip())

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_mobile(self):
        value = normalize_mobile(self.cleaned_data["mobile"])
        validate_mobile(value)
        return value

    def clean_message(self):
        return self.cleaned_data["message"].strip()

    def clean(self):
        # The time trap: a non-field error, since the field itself is hidden.
        cleaned = super().clean()
        try:
            started = float(signing.loads(self.data.get("started", ""), salt=_FORM_SALT))
        except (signing.BadSignature, TypeError, ValueError):
            raise forms.ValidationError("فرم معتبر نیست؛ صفحه را دوباره باز کنید و پیام را ثبت کنید.")
        age = timezone.now().timestamp() - started
        if age < settings.CONTACT_MIN_FILL_SECONDS:
            raise forms.ValidationError("فرم خیلی سریع ارسال شد؛ چند ثانیه صبر کنید و دوباره ثبت کنید.")
        if age > settings.CONTACT_MAX_FORM_AGE_SECONDS:
            raise forms.ValidationError("فرم منقضی شده است؛ دوباره ثبت کنید.")
        return cleaned
