"""
Rules for recording a session in a slot (class subject + date + bell),
enforced on the server whatever the page or its JavaScript did:

* not in the future (``timezone.localdate()``, Asia/Tehran);
* never on a Friday; on a Thursday only a compensatory («جبرانی») session;
* inside the class subject's teaching window and its class's academic year;
* not in a slot the academic calendar closed (any status);
* not in a slot that already has a session;
* a held or cancelled session («برگزار شده» / «کنسل شده») must be in one
  of the subject's timetable slots on that date; a compensatory one may
  use any bell (but still not a closed one).

The session form (``teaching.forms.SchoolSessionForm``) and the prefill
check of the registration page (``teaching.views.school_session_form``)
both call ``slot_errors``; nothing else decides it.
"""

from django.utils import timezone

from academic_calendar import services as calendar
from scheduling.utils import persian_weekday

from .models import SchoolSession
from .models.school_session import DUPLICATE_SLOT_MESSAGE

FUTURE_DATE_MESSAGE = "امکان ثبت جلسه برای تاریخ‌های آینده وجود ندارد"
FRIDAY_MESSAGE = "جمعه تعطیل است؛ برای جمعه نمی‌توان جلسه ثبت کرد."
THURSDAY_MESSAGE = "پنج‌شنبه تعطیل است؛ در پنج‌شنبه فقط جلسه‌ی «جبرانی» ثبت می‌شود."
OUTSIDE_YEAR_MESSAGE = "تاریخ جلسه بیرون از سال تحصیلی این کلاس است."
OUTSIDE_RANGE_MESSAGE = "تاریخ جلسه بیرون از بازه‌ی تدریس این درس است."
BELL_REQUIRED_MESSAGE = "زنگ جلسه را انتخاب کنید."
INACTIVE_BELL_MESSAGE = "این زنگ فعال نیست."


def closed_message(event):
    return f"این زنگ به‌دلیل «{event.title}» تعطیل است؛ امکان ثبت جلسه وجود ندارد."


def not_a_slot_message(class_subject, bell):
    return (
        f"«{class_subject.subject.name}» در این تاریخ در «{bell.title}» برنامه ندارد؛ "
        "زنگ درست را انتخاب کنید، یا برای جلسه‌ی خارج از برنامه وضعیت «جبرانی» را بزنید."
    )


def existing_session(class_subject, date, bell, exclude_pk=None):
    """The session already recorded for this slot, or None."""

    if bell is None:
        return None
    sessions = SchoolSession.objects.filter(
        class_subject=class_subject, date=calendar.to_jalali(date), bell=bell
    )
    if exclude_pk is not None:
        sessions = sessions.exclude(pk=exclude_pk)
    return sessions.first()


def slot_errors(class_subject, date, bell, status=None, exclude_pk=None, today=None):
    """
    ``[(field, message), ...]`` -- why a session of ``status`` cannot be
    recorded in this slot (``field`` is "date", "bell" or "status").
    ``status=None`` runs only the checks that hold for every status (what
    the registration page checks before the teacher has chosen one).
    ``exclude_pk`` is the session being edited.
    """

    today = today or timezone.localdate()
    day = calendar.to_gregorian(date)
    school_class = class_subject.school_class
    year = school_class.year

    if day > today:
        return [("date", FUTURE_DATE_MESSAGE)]

    weekday = persian_weekday(day)
    if weekday == 6:
        return [("date", FRIDAY_MESSAGE)]
    if weekday == 5 and status is not None and status != SchoolSession.Status.COMPENSATORY:
        return [("status", THURSDAY_MESSAGE)]

    if not calendar.to_gregorian(year.start_date) <= day <= calendar.to_gregorian(year.end_date):
        return [("date", OUTSIDE_YEAR_MESSAGE)]
    if not (
        calendar.to_gregorian(class_subject.start_date) <= day
        <= calendar.to_gregorian(class_subject.end_date)
    ):
        return [("date", OUTSIDE_RANGE_MESSAGE)]

    if bell is None:
        return [("bell", BELL_REQUIRED_MESSAGE)]
    if not bell.is_active:
        return [("bell", INACTIVE_BELL_MESSAGE)]

    event = calendar.closing_event(day, school_class, bell)
    if event is not None:
        return [("bell", closed_message(event))]

    if existing_session(class_subject, day, bell, exclude_pk) is not None:
        return [("bell", DUPLICATE_SLOT_MESSAGE)]

    if status in (SchoolSession.Status.HELD, SchoolSession.Status.CANCELED):
        slots = calendar.get_slots(day, day, class_subject=class_subject)
        if bell.pk not in {slot.bell.pk for slot in slots}:
            return [("bell", not_a_slot_message(class_subject, bell))]

    return []
