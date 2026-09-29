"""
Weekly schedule -> A4 landscape PDF (WeasyPrint): the student's has one
page per rotation week, the teacher's one page with both weeks merged.

Font and logo are handed to WeasyPrint as local ``file://`` URIs, so it
never fetches anything over the network (no CDN, no request back to our
own server) and Persian shaping works the same in every environment.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from website.models import SiteSettings

FONT_STATIC_PATH = "report/fonts/Vazirmatn-VariableFont_wght.ttf"


def _file_uri(path):
    return Path(path).resolve().as_uri() if path else None


def _logo_uri(site_settings):
    if not site_settings.logo:
        return None
    try:
        path = site_settings.logo.path
    except (NotImplementedError, ValueError):
        return None
    return _file_uri(path) if Path(path).exists() else None


def _render_html(template_name, context):
    site_settings = SiteSettings.load()
    return render_to_string(template_name, {
        **context,
        "school_name": site_settings.site_name,
        "logo_uri": _logo_uri(site_settings),
        "font_uri": _file_uri(finders.find(FONT_STATIC_PATH)),
    })


def _write_pdf(html):
    return HTML(string=html).write_pdf(font_config=FontConfiguration())


def render_schedule_html(schedule):
    return _render_html("scheduling/weekly-schedule-pdf.html", {
        "schedule": schedule,
        "enrollment": schedule.enrollment,
    })


def render_schedule_pdf(schedule):
    return _write_pdf(render_schedule_html(schedule))


def render_teacher_schedule_html(schedule):
    return _render_html("scheduling/teacher-schedule-pdf.html", {"schedule": schedule})


def render_teacher_schedule_pdf(schedule):
    return _write_pdf(render_teacher_schedule_html(schedule))
