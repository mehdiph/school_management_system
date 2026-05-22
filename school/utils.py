from datetime import date, datetime

from django.conf import settings

from .models import AcademicYear, ClassSchedule


DEFAULT_SCHEDULE_START_DATE = date(2025, 9, 23)


def _resolve_start_date():
    active_calendar = AcademicYear.objects.filter(is_active=True).order_by('-start_date').first()
    if active_calendar:
        return active_calendar.start_date

    configured_start = getattr(settings, 'SCHEDULE_START_DATE', DEFAULT_SCHEDULE_START_DATE)
    if isinstance(configured_start, date):
        return configured_start
    if isinstance(configured_start, str):
        try:
            return datetime.strptime(configured_start, '%Y-%m-%d').date()
        except ValueError:
            return DEFAULT_SCHEDULE_START_DATE
    return DEFAULT_SCHEDULE_START_DATE


def get_current_week_type(current_date=None):
    if current_date is None:
        current_date = date.today()

    start_date = _resolve_start_date()
    diff_days = (current_date - start_date).days
    week_index = diff_days // 7 if diff_days >= 0 else 0

    if week_index % 2 == 0:
        return ClassSchedule.WeekTypeChoices.WEEK_ONE
    return ClassSchedule.WeekTypeChoices.WEEK_TWO


def get_today_schedule_day(current_date=None):
    if current_date is None:
        current_date = date.today()

    weekday_map = {
        5: ClassSchedule.DayChoices.WEDNESDAY,
        6: ClassSchedule.DayChoices.THURSDAY,
        0: ClassSchedule.DayChoices.SATURDAY,
        1: ClassSchedule.DayChoices.SUNDAY,
        2: ClassSchedule.DayChoices.MONDAY,
        3: ClassSchedule.DayChoices.TUESDAY,
    }
    return weekday_map.get(current_date.weekday())
