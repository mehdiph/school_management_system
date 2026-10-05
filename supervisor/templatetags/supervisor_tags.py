"""
    {% load supervisor_tags %}
    {{ teacher.days_since_last_session|relative_days }}   ->  ۳ روز پیش
"""

from django import template

from core.templatetags.jalali_tags import fa_digits

register = template.Library()


@register.filter
def relative_days(days):
    """A number of days ago as Persian text ("امروز", "دیروز", "۲ هفته پیش", ...)."""

    if days is None or days == "":
        return ""

    days = int(days)

    if days < 0:
        return "در آینده"
    if days == 0:
        return "امروز"
    if days == 1:
        return "دیروز"
    if days < 7:
        amount, unit = days, "روز"
    elif days < 30:
        amount, unit = days // 7, "هفته"
    elif days < 365:
        amount, unit = days // 30, "ماه"
    else:
        amount, unit = days // 365, "سال"

    return f"{fa_digits(amount)} {unit} پیش"
