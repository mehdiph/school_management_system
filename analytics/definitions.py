"""
The few rules every panel must agree on, written once.

This module imports no model on purpose: ``core.querysets`` (which the
models themselves import) uses it, and so do the supervisor selectors and
the analytics engine. Status values are spelled out for the same reason
(they are ``SchoolSession.Status`` / ``Attendance.AttendanceStatus``).

* A session **counts** unless the academic calendar created it (``HL``).
* A session was **delivered** (something was taught) when it is held
  (``HD``) or compensatory (``JB``); a cancelled (``CD``) or holiday
  (``HL``) session teaches nothing.
* A delivered session **has content** when a ``SessionContent`` row exists
  for it. Its fields are all required except ``activity`` / ``notes``, so
  the row's existence is the whole test; a missing row on a cancelled or
  holiday session is expected and never reported.
* A student **attended** unless marked absent: late counts as attended
  (the student was in class). Lateness is reported on its own.
"""

from django.db.models import Q

HELD = "HD"
CANCELLED = "CD"
COMPENSATORY = "JB"
HOLIDAY = "HL"

#: Sessions in which something was taught.
DELIVERED_STATUSES = (HELD, COMPENSATORY)

PRESENT = "present"
ABSENT = "absent"
LATE = "late"


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


def attendance_rate(total, absent):
    """
    The share of attendance records that are not absences (present +
    late), as a percentage; None without records.
    """

    return rate(total - absent, total)


def rounded(value):
    """A percentage for display: a whole number, None stays None."""

    return None if value is None else round(value)
