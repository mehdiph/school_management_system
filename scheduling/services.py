"""
Builds a class's two-week timetable -- the single source of data for
the weekly schedule page (desktop grid and mobile day cards) and its
PDF. Three queries in total: enrollment, bells, schedule slots.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import jdatetime
from django.conf import settings
from django.utils import timezone

from school.colors import readable_text_color, safe_hex, tint
from student.models.student_enrollment import StudentEnrollment

from .models.bell import Bell
from .models.class_schedule import ClassSchedule
from .utils import get_rotation_anchor, persian_weekday, week_start, week_type_for

WEEK_LABELS = {
    ClassSchedule.WeekTypeChoices.WEEK_ONE: "هفته اول",
    ClassSchedule.WeekTypeChoices.WEEK_TWO: "هفته دوم",
}

#: Saturday..Wednesday. ``settings.SCHOOL_WORKING_DAYS`` overrides it
#: (add 5 for Thursday). A day that has slots is shown even if it is
#: not listed, so a misconfiguration never hides real classes.
DEFAULT_WORKING_DAYS = (0, 1, 2, 3, 4)

_PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(value):
    return str(value).translate(_PERSIAN_DIGITS)


def jalali_long(value):
    """date -> "۴ مهر ۱۴۰۵"."""

    j = jdatetime.date.fromgregorian(date=value)
    return persian_digits(f"{j.day} {_PERSIAN_MONTHS[j.month - 1]} {j.year}")


def _to_gregorian(value):
    return value.togregorian() if hasattr(value, "togregorian") else value


@dataclass(frozen=True)
class ScheduleEntry:
    subject: str
    teacher: str
    icon: str
    color: str       # validated #rrggbb
    on_color: str    # readable text/icon colour on top of ``color``
    tint: str        # ``color`` at 12% on white, for the PDF (no color-mix there)

    @property
    def style(self):
        # Built only from values that went through safe_hex(), so it is
        # safe to drop into a style="" attribute.
        return f"--subject-color: {self.color}; --subject-on: {self.on_color};"


@dataclass
class Slot:
    bell: Bell
    entry: ScheduleEntry | None = None
    is_now: bool = False


@dataclass
class DaySchedule:
    value: int
    label: str
    slots: list[Slot]
    is_today: bool = False

    @property
    def has_entries(self):
        return any(slot.entry for slot in self.slots)


@dataclass
class WeekSchedule:
    number: int
    week_type: int
    label: str
    start: date
    days: list[DaySchedule]
    is_current: bool

    @property
    def end(self):
        return self.start + timedelta(days=6)


@dataclass
class WeeklySchedule:
    bells: list[Bell]
    weeks: list[WeekSchedule]
    today: date
    enrollment: StudentEnrollment | None = None
    today_day: int | None = None
    generated_on: str = field(default="")

    @property
    def current_week(self):
        return next(week for week in self.weeks if week.is_current)

    def week(self, number):
        return next((week for week in self.weeks if week.number == number), None)

    @property
    def default_day(self):
        """Day the mobile view opens on: today if it is a school day, else the first day."""

        days = [day.value for day in self.weeks[0].days]
        return self.today_day if self.today_day in days else (days[0] if days else None)


def _working_days(extra_days):
    configured = getattr(settings, "SCHOOL_WORKING_DAYS", DEFAULT_WORKING_DAYS)
    valid = set(ClassSchedule.DayChoices.values)
    return sorted((set(configured) | set(extra_days)) & valid)


def _entry(class_subject):
    color = safe_hex(class_subject.subject.color)
    return ScheduleEntry(
        subject=class_subject.subject.name,
        teacher=class_subject.teacher_assignment.teacher.staff.formal_name,
        icon=class_subject.icon,
        color=color,
        on_color=readable_text_color(color),
        tint=tint(color, 0.12),
    )


def _runs_in(class_subject, start, end):
    """Is the class subject's teaching window open at any point of start..end?"""

    return (
        _to_gregorian(class_subject.start_date) <= end
        and _to_gregorian(class_subject.end_date) >= start
    )


def build_weekly_schedule(school_class, academic_year=None, now=None):
    """
    Both rotation weeks of ``school_class``.

    The current rotation week is the calendar week (Sat..Fri) containing
    today; the other one is shown as it will be next week. A slot is
    listed when its ``week_type`` is that week or BOTH, its class subject
    is active and teaching during that calendar week, and its bell is
    active.
    """

    now = timezone.localtime(now) if now else timezone.localtime()
    today = now.date()

    anchor = get_rotation_anchor(academic_year or school_class.year)
    current_type = week_type_for(today, anchor)
    this_week = week_start(today)
    week_starts = {
        current_type: this_week,
        (
            ClassSchedule.WeekTypeChoices.WEEK_TWO
            if current_type == ClassSchedule.WeekTypeChoices.WEEK_ONE
            else ClassSchedule.WeekTypeChoices.WEEK_ONE
        ): this_week + timedelta(days=7),
    }
    span_start, span_end = this_week, this_week + timedelta(days=13)

    bells = list(Bell.objects.filter(is_active=True).order_by("order"))

    schedules = list(
        ClassSchedule.objects
        .filter(
            class_subject__school_class=school_class,
            class_subject__is_active=True,
            class_subject__start_date__lte=jdatetime.date.fromgregorian(date=span_end),
            class_subject__end_date__gte=jdatetime.date.fromgregorian(date=span_start),
            bell__is_active=True,
        )
        .select_related(
            "bell",
            "class_subject__subject",
            "class_subject__teacher_assignment__teacher__staff__user",
        )
        # Week-specific slots (1, 2) before every-week ones (3): if bad
        # legacy data puts both on one cell, the specific one wins.
        .order_by("week_type", "bell__order")
    )

    today_day = persian_weekday(today)
    days = _working_days(s.day_of_week for s in schedules)
    day_labels = dict(ClassSchedule.DayChoices.choices)

    weeks = []
    for number, week_type in ((1, ClassSchedule.WeekTypeChoices.WEEK_ONE),
                              (2, ClassSchedule.WeekTypeChoices.WEEK_TWO)):
        start = week_starts[week_type]
        end = start + timedelta(days=6)
        is_current = week_type == current_type

        cells = {}
        for schedule in schedules:
            if schedule.week_type not in (week_type, ClassSchedule.WeekTypeChoices.BOTH):
                continue
            if not _runs_in(schedule.class_subject, start, end):
                continue
            cells.setdefault((schedule.day_of_week, schedule.bell_id), schedule.class_subject)

        week_days = []
        for day in days:
            is_today = is_current and day == today_day
            slots = []
            for bell in bells:
                class_subject = cells.get((day, bell.id))
                slots.append(Slot(
                    bell=bell,
                    entry=_entry(class_subject) if class_subject else None,
                    is_now=is_today and bell.start_time <= now.time() < bell.end_time,
                ))
            week_days.append(DaySchedule(
                value=day, label=day_labels[day], slots=slots, is_today=is_today,
            ))

        weeks.append(WeekSchedule(
            number=number,
            week_type=week_type,
            label=WEEK_LABELS[week_type],
            start=start,
            days=week_days,
            is_current=is_current,
        ))

    return WeeklySchedule(
        bells=bells,
        weeks=weeks,
        today=today,
        today_day=today_day if today_day in days else None,
        generated_on=jalali_long(today),
    )


def get_current_enrollment(student_profile):
    """
    The enrollment whose class the student attends now: active, and in
    the current academic year when there is one (a student keeps their
    old years' rows, so ``enrollments.get()`` is not enough).
    """

    return (
        StudentEnrollment.objects
        .filter(student=student_profile, status=StudentEnrollment.EnrollmentStatus.ACTIVE)
        .select_related(
            "student__user",
            "academic_year",
            "school_class__grade",
            "school_class__branch",
        )
        .order_by("-academic_year__is_current", "-academic_year__start_date")
        .first()
    )


def get_student_weekly_schedule(student_profile, now=None):
    """The student's own schedule, or None when they have no active enrollment."""

    enrollment = get_current_enrollment(student_profile)
    if enrollment is None:
        return None

    schedule = build_weekly_schedule(
        enrollment.school_class, academic_year=enrollment.academic_year, now=now
    )
    schedule.enrollment = enrollment
    return schedule


def schedule_pdf_filename(schedule):
    year = jdatetime.date.fromgregorian(
        date=_to_gregorian(schedule.enrollment.academic_year.start_date)
    ).year
    return f"weekly-schedule-{year}.pdf"
