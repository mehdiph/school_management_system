"""
Jalali dates and Persian digits for the teacher panel.

    {% load jalali_tags %}
    {{ session.date|jalali_date }}           ->  ۷ مهر ۱۴۰۵
    {{ today|jalali_date:"weekday" }}        ->  سه‌شنبه ۷ مهر ۱۴۰۵
    {{ login.created_at|jalali_datetime }}   ->  ۷ مهر ۱۴۰۵، ۱۷:۲۰
    {{ year.title|fa_digits }}               ->  ۱۴۰۵–۱۴۰۶

Accepts ``datetime.date`` / ``datetime`` (aware datetimes are shown in
Asia/Tehran), ``jdatetime.date`` / ``jdatetime.datetime`` (what the
project's jDateField / jDateTimeField hold). Anything else is returned
unchanged, so a template never breaks on an empty value.
"""

import re
from datetime import date, datetime

import jdatetime
from django import template
from django.utils import timezone

register = template.Library()

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

#: jdatetime's weekday(): Saturday=0. Spelled like ClassSchedule.DayChoices.
WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه")

# "1405-1406" -> en dash between the two years.
_RANGE = re.compile(r"(?<=\d)\s*-\s*(?=\d)")


def fa_digits(value):
    if value is None:
        return ""
    return _RANGE.sub("–", str(value)).translate(_DIGITS)


register.filter("fa_digits", fa_digits)


def _to_jalali(value):
    """-> (jdatetime.date, time or None), or None when ``value`` is not a date."""

    if isinstance(value, jdatetime.datetime):
        if timezone.is_aware(value.togregorian()):
            value = jdatetime.datetime.fromgregorian(datetime=timezone.localtime(value.togregorian()))
        return value.date(), value.time()
    if isinstance(value, jdatetime.date):
        return value, None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.date.fromgregorian(date=value.date()), value.time()
    if isinstance(value, date):
        return jdatetime.date.fromgregorian(date=value), None
    return None


def format_jalali(value, with_weekday=False):
    converted = _to_jalali(value)
    if converted is None:
        return value
    day = converted[0]
    text = f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    if with_weekday:
        text = f"{WEEKDAYS[day.weekday()]} {text}"
    return fa_digits(text)


@register.filter
def jalali_date(value, arg=""):
    return format_jalali(value, with_weekday=(arg == "weekday"))


@register.filter
def jalali_datetime(value):
    converted = _to_jalali(value)
    if converted is None:
        return value
    day, time = converted
    text = format_jalali(day)
    if time is not None:
        text = f"{text}، {fa_digits(time.strftime('%H:%M'))}"
    return text


@register.filter
def fa_time(value):
    """A ``time`` / ``datetime`` -> "۰۸:۰۰"."""

    if hasattr(value, "strftime"):
        return fa_digits(value.strftime("%H:%M"))
    return value
