import jdatetime
from django import template

from report.templatetags.report_tags import to_persian

register = template.Library()


@register.filter
def jalali_long_date(value):
    """
    A Jalali date as "یک‌شنبه ۵ مهر ۱۴۰۵" (weekday, day, month name, year),
    in Persian digits. Anything that is not a date is returned unchanged.
    """

    if not isinstance(value, jdatetime.date):
        return value

    weekday = jdatetime.date.j_weekdays_fa[value.weekday()]
    month = jdatetime.date.j_months_fa[value.month - 1]

    return to_persian(f"{weekday} {value.day} {month} {value.year}")
