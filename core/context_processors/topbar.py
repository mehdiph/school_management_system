import jdatetime
from django.utils import timezone

#: Persian weekday names, indexed by Python's ``date.weekday()``
#: (Monday=0 .. Sunday=6) -- mirrors the mapping already used in
#: ``scheduling.utils.get_today_schedule_day`` for the school week.
_PERSIAN_WEEKDAYS = (
    "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
    "جمعه", "شنبه", "یکشنبه",
)

_PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def topbar_context(request):
    """
    Timezone-aware "now" for the global topbar (current Jalali date +
    clock). The topbar is shared by every dashboard (teacher/student/
    supervisor -- see template/partials/topbar.html), so this lives in
    one context processor instead of being computed per-view.
    """

    if not request.user.is_authenticated:
        return {}

    now = timezone.localtime(timezone.now())
    today_jalali = jdatetime.date.fromgregorian(date=now.date())

    return {
        "current_time": now,
        "topbar_weekday": _PERSIAN_WEEKDAYS[now.date().weekday()],
        "topbar_day": today_jalali.day,
        "topbar_month": _PERSIAN_MONTHS[today_jalali.month - 1],
        "topbar_year": today_jalali.year,
    }
