"""
Calendar rules of the school week and the two-week rotation.

Everything that turns a date into "which weekday / which rotation week"
lives here, so the student schedule, the teacher dashboard and the
supervisor pages cannot disagree about what "today" is.

* The Persian week starts on Saturday: ``persian_weekday`` maps
  Saturday=0 .. Friday=6, which is exactly how
  ``ClassSchedule.day_of_week`` is stored (Friday has no choice).
* Rotation weeks run Saturday..Friday. Week 1 is the week containing
  the *anchor*: ``settings.SCHEDULE_ROTATION_ANCHOR`` if set, otherwise
  the Saturday on or before the academic year's ``start_date``. From
  there the weeks alternate 1, 2, 1, 2, ...
* "Today" is ``timezone.localdate()`` (Asia/Tehran), never the server's
  naive ``date.today()``.
"""

from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from school.models import AcademicYear
from scheduling.models import ClassSchedule

#: Only used when there is no academic year at all.
DEFAULT_SCHEDULE_START_DATE = date(2025, 9, 23)


def persian_weekday(value):
    """Saturday=0, Sunday=1, ... Friday=6 (Python's weekday() is Monday=0)."""

    return (value.weekday() + 2) % 7


def week_start(value):
    """The Saturday on or before ``value``."""

    return value - timedelta(days=persian_weekday(value))


def _to_gregorian(value):
    # jDateField values are jdatetime.date; everything here is Gregorian.
    return value.togregorian() if hasattr(value, "togregorian") else value


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    raise ValueError(f"SCHEDULE_ROTATION_ANCHOR must be a date or 'YYYY-MM-DD', got {value!r}")


def _default_academic_year():
    return (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-start_date")
        .first()
    )


def get_rotation_anchor(academic_year=None):
    """
    Saturday that starts rotation week 1.

    ``academic_year`` defaults to the latest active one (what the teacher
    and supervisor pages have always used); the student schedule passes
    the student's own enrollment year.
    """

    configured = getattr(settings, "SCHEDULE_ROTATION_ANCHOR", None)
    if configured:
        return week_start(_parse_date(configured))

    if academic_year is None:
        academic_year = _default_academic_year()

    start = (
        _to_gregorian(academic_year.start_date)
        if academic_year is not None
        else DEFAULT_SCHEDULE_START_DATE
    )
    return week_start(start)


def week_type_for(current_date, anchor):
    weeks = (week_start(current_date) - anchor).days // 7
    if weeks % 2 == 0:
        return ClassSchedule.WeekTypeChoices.WEEK_ONE
    return ClassSchedule.WeekTypeChoices.WEEK_TWO


def get_current_week_type(current_date=None, academic_year=None):
    if current_date is None:
        current_date = timezone.localdate()

    return week_type_for(current_date, get_rotation_anchor(academic_year))


def get_today_schedule_day(current_date=None):
    """``ClassSchedule.DayChoices`` value for the date, or None on Friday."""

    if current_date is None:
        current_date = timezone.localdate()

    day = persian_weekday(current_date)
    if day in ClassSchedule.DayChoices.values:
        return ClassSchedule.DayChoices(day)
    return None
