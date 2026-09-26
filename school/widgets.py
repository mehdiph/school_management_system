from django import forms

from .colors import DEFAULT_SUBJECT_COLOR, SUBJECT_PALETTE, safe_hex


class ColorPickerWidget(forms.TextInput):
    """
    ``<input type="color">`` plus a hex text field kept in sync, a live
    preview of how the colour looks on a schedule card, and one-click
    palette presets. The colour input is the one that submits; it can
    only ever produce ``#rrggbb``.
    """

    input_type = "color"
    template_name = "school/widgets/color_picker.html"

    class Media:
        css = {"all": ["school/admin/color-picker.css"]}
        js = ["school/admin/color-picker.js"]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, safe_hex(value, DEFAULT_SUBJECT_COLOR), attrs)
        context["widget"]["palette"] = SUBJECT_PALETTE
        return context
