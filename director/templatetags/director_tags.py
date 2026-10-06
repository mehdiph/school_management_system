"""
Number formatting for the director panel.

    {% load director_tags %}
    {{ breakdown.execution_rate|percent }}       ->  ۸۵٪  (None -> —)
    {{ kpi.delta|signed }}                       ->  +۳ / −۲ / ۰
    {{ breakdown.execution_rate|rate_level }}    ->  low / warning / ok / ""
"""

from django import template

from core.templatetags.jalali_tags import fa_digits

register = template.Library()

#: Under these a rate is shown as a problem / a warning (the supervisor's
#: coverage uses the same bands).
RATE_LOW = 60
RATE_WARNING = 85


@register.filter
def percent(value):
    if value is None or value == "":
        return "—"
    return f"{fa_digits(round(value))}٪"


@register.filter
def signed(value):
    """
    A signed whole number in Persian digits. Wrap it in ``<bdi dir="ltr">``
    in RTL text, or the bidi algorithm moves the sign after the digits.
    """

    if value is None:
        return ""
    if value > 0:
        return f"+{fa_digits(value)}"
    if value < 0:
        return f"−{fa_digits(-value)}"
    return fa_digits(0)


@register.filter
def rate_level(value):
    """The band of the *shown* (rounded) rate, so «۸۵٪» is never amber."""

    if value is None:
        return ""
    value = round(value)
    if value < RATE_LOW:
        return "low"
    if value < RATE_WARNING:
        return "warning"
    return "ok"


@register.filter
def bar(value):
    """A rate as a CSS width (0..100), for the progress bars."""

    if value is None:
        return 0
    return max(0, min(100, round(value)))
