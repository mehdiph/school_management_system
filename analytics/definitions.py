"""
The few rules every panel must agree on, written once.

This module imports no model on purpose: ``core.querysets`` (which the
models themselves import) uses it, and so do the supervisor selectors and
the analytics engine. Status values are spelled out for the same reason
(they are ``SchoolSession.Status`` / ``SessionAttendance.AttendanceStatus``
/ ``DailyAttendance.Status``).

* A session **counts** unless the academic calendar created it (``HL``).
* A session was **delivered** (something was taught) when it is held
  (``HD``) or compensatory (``JB``); a cancelled (``CD``) or holiday
  (``HL``) session teaches nothing.
* A delivered session **has content** when a ``SessionContent`` row exists
  for it. Its fields are all required except ``activity`` / ``notes``, so
  the row's existence is the whole test; a missing row on a cancelled or
  holiday session is expected and never reported.
* A student **attended** when present or late (the student was in
  class); absent and excused («غیبت موجه», daily attendance only) are
  both **absences**. Lateness is reported on its own.
* Which attendance a date has -- the teacher's per-session records
  before ``settings.ATTENDANCE_DAILY_START_DATE``, the supporter's daily
  sheets from then on -- is decided in ``attendance.services`` only.
"""

from django.db.models import Q

HELD = "HD"
CANCELLED = "CD"
COMPENSATORY = "JB"
HOLIDAY = "HL"

#: Sessions in which something was taught.
DELIVERED_STATUSES = (HELD, COMPENSATORY)

#: A slot of today is expected only once its bell has ended and the
#: teacher has had this long to record it (the supervisor's «نیازمند
#: پیگیری» list uses the same grace).
REGISTRATION_GRACE_MINUTES = 15

PRESENT = "present"
ABSENT = "absent"
LATE = "late"
EXCUSED = "excused"

#: Statuses that are an absence: the student was not in class.
ABSENCE_STATUSES = (ABSENT, EXCUSED)


def counted_q(prefix=""):
    """``SchoolSession.objects.counted()`` as a Q, for aggregates over a relation."""

    return ~Q(**{f"{prefix}status": HOLIDAY})


def delivered_q(prefix=""):
    """Held or compensatory sessions."""

    return Q(**{f"{prefix}status__in": DELIVERED_STATUSES})


def has_content_q(prefix=""):
    """Sessions with a ``SessionContent`` row (whatever their status)."""

    return Q(**{f"{prefix}session_contents__isnull": False})


def missing_content_q(prefix=""):
    """Delivered sessions without a ``SessionContent`` row."""

    return delivered_q(prefix) & ~has_content_q(prefix)


def rate(part, whole):
    """``part`` as a percentage of ``whole`` (a float), or None when ``whole`` is 0."""

    if not whole:
        return None
    return part * 100 / whole


def attendance_rate(total, absences):
    """
    The share of attendance records that are not absences (present +
    late), as a percentage; None without records. ``absences`` is absent
    plus excused records.
    """

    return rate(total - absences, total)


def rounded(value):
    """A percentage for display: a whole number, None stays None."""

    return None if value is None else round(value)
