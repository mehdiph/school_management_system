"""
The body field's editor. Without JavaScript it is a plain textarea (text
typed there becomes paragraphs, ``blog.content.plain_to_html``); with it,
``blog/js/editor.js`` puts Trix over the same textarea, which stays the
field that is submitted.
"""

from django import forms

from . import content

EDITOR_JS = ("blog/js/editor.js", "vendor/trix/trix.umd.min.js")  # editor.js first: it configures Trix
EDITOR_CSS = ("vendor/trix/trix.css", "blog/css/editor.css")


class EditorWidget(forms.Textarea):
    template_name = "blog/widgets/editor.html"

    def __init__(self, attrs=None, upload_url=""):
        super().__init__({"rows": 18, "dir": "rtl", **(attrs or {})})
        self.upload_url = upload_url

    def format_value(self, value):
        # The stored body, in Trix's markup so image captions survive editing.
        return content.to_editor(value) if value else value

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["upload_url"] = self.upload_url
        return context

    @property
    def media(self):
        return forms.Media(js=EDITOR_JS, css={"all": EDITOR_CSS})


class ImageInput(forms.ClearableFileInput):
    """A file input that shows the current image itself (not its file path) and a «حذف تصویر» tick."""

    template_name = "blog/widgets/image_input.html"
    clear_checkbox_label = "حذف تصویر"

    def __init__(self, attrs=None):
        super().__init__({"accept": "image/jpeg,image/png,image/webp", **(attrs or {})})
