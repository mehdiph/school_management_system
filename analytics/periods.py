"""
Teaching days, date-range presets and the comparison period.

A **teaching day** of a scope is a working day (Saturday..Wednesday) of
the academic year on which at least one of the scope's units -- a
(branch, grade) pair -- is not closed for the whole day. A closure of one
branch therefore removes the day from that branch's teaching days only;
with every branch selected, the day is lost only when every branch (and
grade) is closed. Closures limited to some bells never remove a day.

The **previous period** of a range is the same number of teaching days
immediately before it, so "this week" (with a holiday in it) is compared
with as many real school days, not with seven calendar days.
"""

from datetime import timedelta
from types import SimpleNamespace

import jdatetime

from academic_calendar.services import date_range, is_weekend, to_gregorian
from scheduling.utils import week_start

TODAY = "today"
WEEK = "week"
MONTH = "month"
YEAR = "year"
CUSTOM = "custom"

PERIOD_CHOICES = [
    (TODAY, "امروز"),
    (WEEK, "این هفته"),
    (MONTH, "این ماه"),
    (YEAR, "از ابتدای سال تحصیلی"),
    (CUSTOM, "بازه‌ی دلخواه"),
]


def period_range(period, today, year):
    """
    ``(start, end)`` (Gregorian) of a preset: today, this week (from
    Saturday), this Jalali month, or the academic year so far. ``CUSTOM``
    has no preset range: None.
    """

    if period == TODAY:
        return today, today
    if period == WEEK:
        return week_start(today), today
    if period == MONTH:
        first = jdatetime.date.fromgregorian(date=today).replace(day=1)
        return first.togregorian(), today
    if period == YEAR:
        return to_gregorian(year.start_date), today
    return None


def units(year, branch_ids, grade_ids):
    """
    The (branch, grade) pairs of a scope, shaped like a ``SchoolClass``
    for ``Closures.is_closed`` (``year_id`` / ``branch_id`` / ``grade_id``).
    """

    return [
        SimpleNamespace(year_id=year.pk, branch_id=branch_id, grade_id=grade_id)
        for branch_id in branch_ids
        for grade_id in grade_ids
    ]


def _bounds(year, start, end):
    first = max(to_gregorian(start), to_gregorian(year.start_date))
    last = min(to_gregorian(end), to_gregorian(year.end_date))
    return first, last


def _is_teaching_day(day, closures, units, closed_candidates):
    if is_weekend(day):
        return False
    if day not in closed_candidates or not units:
        return True
    return any(not closures.is_closed(day, unit) for unit in units)


def teaching_days(year, start, end, closures, units):
    """
    The teaching days of ``year`` from ``start`` to ``end`` (both
    inclusive), sorted. ``closures`` must cover the range; ``units`` come
    from :func:`units` (none: closures are ignored).
    """

    first, last = _bounds(year, start, end)
    if first > last:
        return []
    candidates = set(closures.days(first, last))
    return [
        day for day in date_range(first, last)
        if _is_teaching_day(day, closures, units, candidates)
    ]


def closed_days(year, start, end, closures, units):
    """Working days of the range that are not teaching days: lost to closures."""

    first, last = _bounds(year, start, end)
    if first > last:
        return []
    candidates = set(closures.days(first, last))
    return [
        day for day in sorted(candidates)
        if first <= day <= last and not _is_teaching_day(day, closures, units, candidates)
    ]


def preceding_teaching_days(year, before, count, closures, units):
    """
    The ``count`` teaching days just before ``before`` (oldest first) --
    fewer when the academic year starts first. ``closures`` must cover
    the year up to ``before``.
    """

    if count <= 0:
        return []
    first = to_gregorian(year.start_date)
    day = to_gregorian(before) - timedelta(days=1)
    last = min(day, to_gregorian(year.end_date))
    candidates = set(closures.days(first, last)) if first <= last else set()

    days = []
    while day >= first and len(days) < count:
        if day <= last and _is_teaching_day(day, closures, units, candidates):
            days.append(day)
        day -= timedelta(days=1)
    return days[::-1]


def previous_period(year, start, end, closures, units):
    """
    ``(previous start, previous end, complete)`` for the range ``start``..
    ``end``: as many teaching days as the range has, immediately before
    it. ``complete`` is False when the year began too recently to have
    that many; None when the range has no teaching day at all.
    """

    count = len(teaching_days(year, start, end, closures, units))
    if not count:
        return None
    days = preceding_teaching_days(year, start, count, closures, units)
    if not days:
        return None
    return days[0], days[-1], len(days) == count
