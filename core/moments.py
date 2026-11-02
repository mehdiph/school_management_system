"""
Moments (``jDateTimeField`` values) compared with the clock in queries.

On SQLite, django_jalali stores a datetime as text with its own UTC offset,
so a Tehran-time value compares wrong against a UTC one; PostgreSQL compares
real timestamps and is not affected. Everything that filters a moment against
the clock therefore writes it with ``to_utc`` and compares it with
``utc_now`` (ADR-026). Used by the blog and by online classes.
"""

import re
from datetime import datetime
from datetime import timezone as dt_timezone

import jdatetime
from django.utils import timezone

_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_JALALI_DATETIME = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")


def utc_now():
    """``timezone.now()`` in UTC, the zone moments are written in."""

    return timezone.now().astimezone(dt_timezone.utc)


def as_datetime(value):
    """A ``jdatetime`` from a jDateTimeField -> a ``datetime`` to compare with ``timezone.now()``."""

    return value.togregorian() if hasattr(value, "togregorian") else value


def to_utc(value):
    """A moment as an aware UTC ``datetime``, to write; ``None`` stays ``None``."""

    value = as_datetime(value)
    if not value:
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value.astimezone(dt_timezone.utc)


def parse_jalali_datetime(value):
    """«۱۴۰۵/۰۸/۱۲ ۱۰:۳۰» (Persian or ASCII digits; time optional, default 00:00) -> aware datetime, or None."""

    match = _JALALI_DATETIME.fullmatch((value or "").strip().translate(_TO_ASCII_DIGITS))
    if not match:
        return None
    year, month, day, hour, minute = (int(part) if part else 0 for part in match.groups())
    try:
        moment = jdatetime.datetime(year, month, day, hour, minute).togregorian()
    except ValueError:
        return None
    return timezone.make_aware(datetime(moment.year, moment.month, moment.day, moment.hour, moment.minute))


def format_jalali_datetime(value):
    """A moment -> «1405/08/12 10:30» in Tehran time, what ``parse_jalali_datetime`` reads back."""

    value = as_datetime(value)
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return jdatetime.datetime.fromgregorian(datetime=value.replace(tzinfo=None)).strftime("%Y/%m/%d %H:%M")
