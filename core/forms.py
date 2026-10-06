"""
Form fields shared by the panels' GET filter forms (supervisor, director).
"""

import jdatetime
from django import forms
from django.core.exceptions import ValidationError


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
