"""
Page data of the director panel: the school's daily attendance at a glance.

Every count comes from ``attendance.services`` -- the same functions the
supervisor's daily attendance page uses (``class_day_statuses`` over
``planned_class_days`` and ``class_day_tallies``, ``student_tallies``,
``get_absences``) -- and the supporters of a class from
``supervisor.selectors.class_supervisors``. This module only picks the
classes, the days and the thresholds, and turns the results into rows and
sentences for the templates. Views call one function per page and run no
query of their own.

Only daily attendance is shown: every range starts at
``ATTENDANCE_DAILY_START_DATE`` at the earliest (``forms.daily_range``),
so archived per-session records never mix in. «غیبت موجه» is an absence;
late is attended and only shown on its own line.

Bounded queries: each page loads the year and branches, the classes of the
scope, the timetable and the calendar once, and a fixed number of grouped
queries -- whatever the number of classes, students or records.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from academic_calendar import services as calendar
from analytics import periods
from analytics.definitions import EXCUSED, LATE, rate, rounded
from attendance import services as attendance
from attendance.services import ClassDay
from core.templatetags.jalali_tags import MONTHS, WEEKDAYS, fa_digits, format_jalali
from school.models import AcademicYear, Branch, SchoolClass
from student.models.student_enrollment import StudentEnrollment
from supervisor.selectors import class_supervisors

from .forms import daily_range

#: How far ahead the home page looks for the next school day (on a
#: holiday) and for the next holiday.
NEXT_SCHOOL_DAY_WITHIN = 14
NEXT_HOLIDAY_WITHIN = 60


def threshold(name):
    """A policy value of the panel (``DIRECTOR_*`` in the settings), read on each request."""

    return getattr(settings, name)


# ----------------------------------------------------------------------
# Dimensions and labels
# ----------------------------------------------------------------------

@dataclass
class Dimensions:
    """What every page needs before it can read its filters (two queries)."""

    year: object
    branches: list

    @classmethod
    def load(cls):
        return cls(
            year=AcademicYear.objects.filter(is_current=True).order_by("-start_date").first(),
            branches=list(Branch.objects.filter(is_active=True).order_by("order", "id")),
        )


def class_label(school_class):
    """"هفتم ۲": grade and section, in Persian digits (sections are often numbers)."""

    return fa_digits(f"{school_class.grade.name} {school_class.section}")


def person_name(user):
    return user.get_full_name() or user.username


def day_label(day):
    """"۳ آبان": a chart axis label."""

    jalali = calendar.to_jalali(day)
    return fa_digits(f"{jalali.day} {MONTHS[jalali.month - 1]}")


def weekday_name(day):
    return WEEKDAYS[calendar.to_jalali(day).weekday()]


def scope_classes(year, branch=None):
    """The active classes of the year (in ``branch``), in school order (one query)."""

    classes = SchoolClass.objects.filter(year=year, is_active=True)
    if branch is not None:
        classes = classes.filter(branch=branch)
    return list(
        classes.select_related("grade", "branch")
        .order_by("branch__order", "branch_id", "grade__level", "section", "pk")
    )


def _queryset(classes):
    """``classes`` as a queryset for ``attendance.services`` (a subquery, no query of its own)."""

    return SchoolClass.objects.filter(pk__in=[c.pk for c in classes])


def supporters(supervisors):
    """The supporters of a class as one line, or «پشتیبان ندارد»."""

    if not supervisors:
        return ""
    return "، ".join(person_name(s.user) for s in supervisors)


# ----------------------------------------------------------------------
# Students absent on several days
# ----------------------------------------------------------------------

def frequent_absentees(classes, start, end):
    """
    Students of ``classes`` absent (absent or excused) on at least
    ``DIRECTOR_FREQUENT_ABSENCE_DAYS`` days from ``start`` to ``end``,
    most days first, each with those days (absent, excused and late, with
    the supporter's description). Daily attendance only: the range starts
    at the cutoff (``forms.daily_range``), and a daily record is one day.
    One grouped query, plus one for the days when someone is listed.
    """

    minimum = threshold("DIRECTOR_FREQUENT_ABSENCE_DAYS")
    tallies = attendance.student_tallies(_queryset(classes), start, end)
    listed = sorted(
        ((pk, row) for pk, row in tallies.items() if row["absences"] >= minimum),
        key=lambda item: (-item[1]["absences"], item[1]["last_name"], item[1]["first_name"], item[0]),
    )

    days = defaultdict(list)
    if listed:
        enrollments = StudentEnrollment.objects.filter(pk__in=[pk for pk, _ in listed])
        for record in attendance.get_absences(enrollments, start, end):
            days[record.student_enrollment.pk].append(record)

    rows = []
    for pk, row in listed:
        rows.append({
            "pk": pk,
            "name": " ".join(filter(None, (row["first_name"], row["last_name"]))) or row["username"],
            "class_label": fa_digits(f"{row['grade']} {row['section']}"),
            "branch": row["branch"],
            "absences": row["absences"],
            "excused": row["excused"],
            "late": row["late"],
            "days": days.get(pk, []),
        })
    return {"rows": rows, "minimum": minimum}


# ----------------------------------------------------------------------
# Home page: today
# ----------------------------------------------------------------------

def _holiday_reason(today, closed):
    """Why nobody takes attendance today: the weekend, the calendar, or no lessons."""

    if calendar.is_weekend(today):
        return f"امروز {weekday_name(today)} است؛ مدرسه تعطیل است."
    titles = list(dict.fromkeys(day.closure.title for day in closed))
    if titles:
        return f"امروز تعطیل است: {'، '.join(titles)}."
    return "امروز کلاسی در برنامه نیست."


def _closes_part(event, dims, filters):
    """Does ``event`` close only some of the scope (some grades, bells or branches)?"""

    if event.grades.all() or event.bells.all():
        return True
    branch_ids = {b.pk for b in event.branches.all()}
    if filters.branch is None and branch_ids:
        return not {b.pk for b in dims.branches} <= branch_ids
    return False


def home(dims, filters, as_of):
    """Everything the home page shows: today, in the selected branch (or all)."""

    year = filters.year
    today = timezone.localtime(as_of).date()
    tomorrow = today + timedelta(days=1)
    classes = scope_classes(year, filters.branch)
    data = {
        "day": today,
        "is_daily": attendance.is_daily(today),
        "daily_start": attendance.daily_start(),
        "has_classes": bool(classes),
    }

    # One load of the calendar serves today, the next school day and the
    # next holiday.
    closures = calendar.Closures.between(
        today, today + timedelta(days=NEXT_HOLIDAY_WITHIN), academic_year=year, branch=filters.branch,
    )
    upcoming = [
        event for event in closures.events(tomorrow, today + timedelta(days=NEXT_HOLIDAY_WITHIN))
        if calendar.to_gregorian(event.start_date) > today
    ]
    data["next_holiday"] = (
        {
            "event": upcoming[0],
            "start": calendar.to_gregorian(upcoming[0].start_date),
            "end": calendar.to_gregorian(upcoming[0].end_date),
            "is_partial": _closes_part(upcoming[0], dims, filters),
        }
        if upcoming else None
    )

    if not data["is_daily"] or not classes:
        return data

    # This month's frequent absences, on a holiday too.
    start, end, _ = daily_range(periods.MONTH, today, year)
    data["month"] = {"start": start, "end": end}
    data["frequent"] = frequent_absentees(classes, start, end) if start else None

    days = attendance.class_day_statuses(today, today, classes, as_of, closures)
    due = [day for day in days.values() if day.is_due]
    closed = [day for day in days.values() if day.status == ClassDay.CLOSED]
    by_id = {c.pk: c for c in classes}

    if not due:
        planned = attendance.planned_class_days(
            tomorrow, today + timedelta(days=NEXT_SCHOOL_DAY_WITHIN), _queryset(classes), closures,
        )
        data["holiday"] = {
            "reason": _holiday_reason(today, closed),
            "next_school_day": min((day for (_, day), event in planned.items() if event is None), default=None),
            "within": NEXT_SCHOOL_DAY_WITHIN,
        }
        return data

    recorded = [day for day in due if day.status == ClassDay.RECORDED]
    data["summary"] = {
        "due": len(due),
        "recorded": len(recorded),
        "pending": sum(1 for day in due if day.status == ClassDay.PENDING),
        "absences": sum(day.absences for day in recorded),
        "excused": sum(day.excused for day in recorded),
        "late": sum(day.late for day in recorded),
    }
    data["closed_classes"] = {
        "count": len(closed),
        "reasons": "، ".join(dict.fromkeys(day.closure.title for day in closed)),
    }

    supervisors = class_supervisors(list(by_id))
    data["missing"] = [
        {
            "school_class": school_class,
            "label": class_label(school_class),
            "branch": school_class.branch.name,
            "supporters": supporters(supervisors.get(school_class.pk)),
        }
        for school_class in classes
        if getattr(days.get((school_class.pk, today)), "status", None) == ClassDay.MISSING
    ]

    data["absent_by_class"] = (
        absent_by_class(classes, today) if any(day.absences or day.late for day in recorded) else []
    )
    return data


def absent_by_class(classes, day):
    """
    Today's absent (absent or excused) and late students, grouped by
    class in school order: ``[{"label", "branch", "absent": [records],
    "late": [records], "excused"}]``. One query.
    """

    groups = {c.pk: {"school_class": c, "absent": [], "late": []} for c in classes}
    for record in attendance.get_absences(_queryset(classes), day, day):
        group = groups.get(record.student_enrollment.school_class_id)
        if group is not None:
            group["late" if record.status == LATE else "absent"].append(record)

    result = []
    for group in groups.values():
        if not group["absent"] and not group["late"]:
            continue
        school_class = group["school_class"]
        result.append({
            **group,
            "label": class_label(school_class),
            "branch": school_class.branch.name,
            "excused": sum(1 for r in group["absent"] if r.status == EXCUSED),
        })
    return result


# ----------------------------------------------------------------------
# Attendance page: a period
# ----------------------------------------------------------------------

#: The absence label of a class: (level, badge colour, words).
ABSENCE_LEVELS = {
    "good": ("success", "وضعیت خوب"),
    "attention": ("warning", "نیاز به توجه"),
    "high": ("danger", "غیبت زیاد"),
}


def absence_level(absences, total):
    """
    ``(level, share)`` of a class: its absent days as a share of its
    records against ``DIRECTOR_CLASS_ABSENCE_YELLOW`` / ``_RED`` (%), and
    that share rounded; ``(None, None)`` without records.
    """

    share = rate(absences, total)
    if share is None:
        return None, None
    if share >= threshold("DIRECTOR_CLASS_ABSENCE_RED"):
        level = "high"
    elif share >= threshold("DIRECTOR_CLASS_ABSENCE_YELLOW"):
        level = "attention"
    else:
        level = "good"
    return level, rounded(share)


def attendance_page(dims, filters, as_of):
    """Everything the attendance page shows for the filters' period and branch."""

    data = {"daily_start": attendance.daily_start()}
    if filters.is_empty:
        return data

    classes = scope_classes(filters.year, filters.branch)
    days = attendance.class_day_statuses(filters.start, filters.end, classes, as_of)
    supervisors = class_supervisors([c.pk for c in classes]) if classes else {}

    data["daily"] = daily_points(filters.start, filters.end, days)
    data["classes"] = class_rows(classes, days, supervisors)
    data["totals"] = {
        "absences": sum(day.absences for day in days.values()),
        "excused": sum(day.excused for day in days.values()),
        "late": sum(day.late for day in days.values()),
        "missing": sum(1 for day in days.values() if day.status == ClassDay.MISSING),
        "recorded": sum(1 for day in days.values() if day.status == ClassDay.RECORDED),
    }
    data["frequent"] = (
        None if filters.period == periods.TODAY or not classes
        else frequent_absentees(classes, filters.start, filters.end)
    )
    return data


def daily_points(start, end, days):
    """
    One point per working day (Saturday..Wednesday) of the range: how
    many students were absent, or why there is no number -- the calendar
    closed every class (``closed``, with the event: never plotted as
    zero), no class had a lesson (``no_lessons``), or no sheet was taken
    yet (``missing`` / ``pending``).
    """

    by_day = defaultdict(list)
    for day in days.values():
        by_day[day.date].append(day)

    points = []
    for day in calendar.date_range(start, end):
        rows = by_day.get(day, [])
        if calendar.is_weekend(day) and not rows:
            continue
        due = [row for row in rows if row.is_due]
        recorded = [row for row in due if row.status == ClassDay.RECORDED]
        missing = sum(1 for row in due if row.status == ClassDay.MISSING)
        if not due:
            closed = [row for row in rows if row.status == ClassDay.CLOSED]
            kind = "closed" if closed else "no_lessons"
            closure = closed[0].closure.title if closed else ""
        else:
            kind = "recorded" if recorded else ("missing" if missing else "pending")
            closure = ""
        points.append({
            "date": day,
            "label": day_label(day),
            "title": format_jalali(day, with_weekday=True),
            "kind": kind,
            "closure": closure,
            "absences": sum(row.absences for row in recorded) if recorded else None,
            "excused": sum(row.excused for row in recorded),
            "late": sum(row.late for row in recorded),
            "due": len(due),
            "recorded": len(recorded),
            "missing": missing,
        })

    with_data = sum(1 for p in points if p["absences"] is not None)
    return {
        "points": points,
        "has_data": with_data > 0,
        "enough": with_data >= 2,
        "chart": {
            "labels": [p["label"] for p in points],
            "titles": [p["title"] for p in points],
            "kinds": [p["kind"] for p in points],
            "closures": [p["closure"] for p in points],
            "absences": [p["absences"] for p in points],
            "excused": [p["excused"] for p in points],
            "late": [p["late"] for p in points],
            "missing": [p["missing"] for p in points],
        },
    }


def class_rows(classes, days, supervisors):
    """
    One row per class: its supporters, absent days (excused among them),
    late, and the days it should have taken attendance and did not, each
    with its label (``ABSENCE_LEVELS``; a missing day is red).
    """

    per_class = defaultdict(list)
    for day in days.values():
        per_class[day.school_class_id].append(day)

    rows = []
    for school_class in classes:
        class_days = per_class.get(school_class.pk, [])
        recorded = [d for d in class_days if d.status == ClassDay.RECORDED]
        absences = sum(d.absences for d in recorded)
        total = sum(d.total for d in recorded)
        level, share = absence_level(absences, total)
        missing = sum(1 for d in class_days if d.status == ClassDay.MISSING)
        pending = any(d.status == ClassDay.PENDING for d in class_days)

        if missing:
            recording = ("danger", f"{fa_digits(missing)} روز ثبت نشده")
        elif recorded:
            recording = ("success", "همه ثبت شده")
        elif pending:
            recording = ("", "هنوز وقت دارد")
        else:
            recording = ("", "کلاسی نداشته")

        rows.append({
            "school_class": school_class,
            "label": class_label(school_class),
            "branch": school_class.branch.name,
            "supporters": supporters(supervisors.get(school_class.pk)),
            "absences": absences,
            "excused": sum(d.excused for d in recorded),
            "late": sum(d.late for d in recorded),
            "total": total,
            "share": share,
            "level": level,
            "level_badge": ABSENCE_LEVELS[level] if level else None,
            "missing": missing,
            "recording": recording,
        })
    return rows
