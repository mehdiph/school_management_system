"""
Weekly schedule -> A4 landscape PDF (WeasyPrint), one page per rotation week.

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


def render_schedule_html(schedule):
    site_settings = SiteSettings.load()
    return render_to_string("scheduling/weekly-schedule-pdf.html", {
        "schedule": schedule,
        "enrollment": schedule.enrollment,
        "school_name": site_settings.site_name,
        "logo_uri": _logo_uri(site_settings),
        "font_uri": _file_uri(finders.find(FONT_STATIC_PATH)),
    })


def render_schedule_pdf(schedule):
    return HTML(string=render_schedule_html(schedule)).write_pdf(
        font_config=FontConfiguration(),
    )
