"""
Calendar rules of the school week and the two-week rotation.

Everything that turns a date into "which weekday / which rotation week"
lives here, so the student schedule, the teacher dashboard and the
supervisor pages cannot disagree about what "today" is.

* The Persian week starts on Saturday: ``persian_weekday`` maps
  Saturday=0 .. Friday=6, which is exactly how
  ``ClassSchedule.day_of_week`` is stored (Friday has no choice).
* Academic weeks run Saturday..Friday and are counted from the academic
  year's ``start_date`` (see ``get_academic_week_number``). When the year
  starts mid-week, those first partial days are *merged* into the
  following full week: 1405/07/01 is a Wednesday, so 1 Mehr .. 10 Mehr
  (Wed 2026-09-23 .. Fri 2026-10-02) is academic week 1.
* The rotation is odd week -> "هفته اول", even week -> "هفته دوم"
  (``get_week_cycle``), toggling every Saturday after the first week.
* "Today" is ``timezone.localdate()`` (Asia/Tehran), never the server's
  naive ``date.today()``.
"""

from datetime import date, datetime, timedelta

import jdatetime
from django.utils import timezone

from scheduling.models import ClassSchedule


class DateBeforeAcademicYearError(ValueError):
    """The date falls before the academic year's ``start_date``."""


def persian_weekday(value):
    """Saturday=0, Sunday=1, ... Friday=6 (Python's weekday() is Monday=0)."""

    return (value.weekday() + 2) % 7


def week_start(value):
    """The Saturday on or before ``value``."""

    return value - timedelta(days=persian_weekday(value))


def _to_gregorian(value):
    """``date`` / ``datetime`` / ``jdatetime.date`` (what jDateField holds) -> ``date``."""

    if isinstance(value, (jdatetime.date, jdatetime.datetime)):
        value = value.togregorian()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Expected a date, got {value!r}")


def first_full_week_start(academic_year):
    """
    Saturday that starts the first *full* week of the academic year: the
    ``start_date`` itself when it is a Saturday, otherwise the next one.
    The days from ``start_date`` up to it still belong to week 1.
    """

    start = _to_gregorian(academic_year.start_date)
    return start + timedelta(days=(7 - persian_weekday(start)) % 7)


def get_academic_week_number(value, academic_year):
    """
    1-based academic week of ``value`` (a Gregorian or Jalali date).

    Weeks run Saturday..Friday. The partial days from ``start_date`` up
    to the first Friday are merged into the following full week, so the
    first week of the year can be up to 13 days long. Raises
    ``DateBeforeAcademicYearError`` for a date before ``start_date``.
    """

    day = _to_gregorian(value)
    start = _to_gregorian(academic_year.start_date)

    if day < start:
        raise DateBeforeAcademicYearError(
            f"{day} is before the start of academic year {academic_year} "
            f"({jdatetime.date.fromgregorian(date=start)} = {start})."
        )

    weeks_after_first = (week_start(day) - first_full_week_start(academic_year)).days // 7
    return max(weeks_after_first, 0) + 1


def get_week_cycle(value, academic_year):
    """
    ``ClassSchedule.WeekTypeChoices.WEEK_ONE`` or ``WEEK_TWO`` for the
    rotation week ``value`` falls in (odd academic week -> week 1). Raises
    ``DateBeforeAcademicYearError`` like ``get_academic_week_number``.
    """

    if get_academic_week_number(value, academic_year) % 2 == 1:
        return ClassSchedule.WeekTypeChoices.WEEK_ONE
    return ClassSchedule.WeekTypeChoices.WEEK_TWO


def get_today_schedule_day(current_date=None):
    """``ClassSchedule.DayChoices`` value for the date, or None on Friday."""

    if current_date is None:
        current_date = timezone.localdate()

    day = persian_weekday(current_date)
    if day in ClassSchedule.DayChoices.values:
        return ClassSchedule.DayChoices(day)
    return None
