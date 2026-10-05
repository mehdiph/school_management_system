"""
Builds the two-week timetable -- the single source of data for the
weekly schedule pages (desktop grid and mobile day cards) and their PDFs:

* a class's, for the student page (``get_student_weekly_schedule``);
  three queries: enrollment, bells, schedule slots;
* a teacher's, across all their classes and branches in the current
  academic year (``get_teacher_weekly_schedule``); three queries: year,
  bells, schedule slots.

Both go through the same rotation and grid code (``_rotation``,
``_in_effect``, ``_build_weeks``), so they cannot disagree about which
week is which or which lessons are in effect.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import jdatetime
from django.conf import settings
from django.utils import timezone

from school.colors import readable_text_color, safe_hex, tint
from school.models import AcademicYear
from student.models.student_enrollment import StudentEnrollment

from .models.bell import Bell
from .models.class_schedule import ClassSchedule
from .utils import get_week_cycle, persian_weekday, week_start

WEEK_LABELS = {
    ClassSchedule.WeekTypeChoices.WEEK_ONE: "هفته اول",
    ClassSchedule.WeekTypeChoices.WEEK_TWO: "هفته دوم",
}

#: Saturday..Wednesday. ``settings.SCHOOL_WORKING_DAYS`` overrides it.
#: No new slot may be put on Thursday (``ClassSchedule``), but a day that
#: has (legacy) slots is shown even if it is not listed, so a
#: misconfiguration never hides real classes.
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
    #: Every lesson in the cell. The student view keeps one (``entry``);
    #: the teacher view keeps all of them, so a clash is visible.
    entries: list = field(default_factory=list)

    @property
    def has_conflict(self):
        return len(self.entries) > 1


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
        # Before the academic year starts no week holds today; open on week 1.
        return next((week for week in self.weeks if week.is_current), self.weeks[0])

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


@dataclass(frozen=True)
class _Rotation:
    """Which calendar weeks the two rotation weeks are shown as (see build_weekly_schedule)."""

    started: bool
    current_type: int
    week_starts: dict   # week_type -> Saturday

    @property
    def span(self):
        """First and last day covered by both weeks, for the teaching-window filter."""

        starts = sorted(self.week_starts.values())
        return starts[0], starts[-1] + timedelta(days=6)


def _rotation(academic_year, today):
    year_start = _to_gregorian(academic_year.start_date)
    started = today >= year_start
    reference = today if started else year_start

    current_type = get_week_cycle(reference, academic_year)
    this_week = week_start(reference)
    next_week = this_week + timedelta(days=7)
    if get_week_cycle(next_week, academic_year) == current_type:
        next_week += timedelta(days=7)
    other_type = (
        ClassSchedule.WeekTypeChoices.WEEK_TWO
        if current_type == ClassSchedule.WeekTypeChoices.WEEK_ONE
        else ClassSchedule.WeekTypeChoices.WEEK_ONE
    )
    return _Rotation(
        started=started,
        current_type=current_type,
        week_starts={current_type: this_week, other_type: next_week},
    )


def _in_effect(queryset, rotation):
    """Rows whose class subject is active and teaching during the two weeks, on an active bell."""

    span_start, span_end = rotation.span
    return queryset.filter(
        class_subject__is_active=True,
        class_subject__start_date__lte=jdatetime.date.fromgregorian(date=span_end),
        class_subject__end_date__gte=jdatetime.date.fromgregorian(date=span_start),
        bell__is_active=True,
    )


def _build_weeks(schedules, rotation, now, make_entry, keep_all=False):
    """
    ``schedules`` (ordered week-specific first) -> ``WeeklySchedule``.

    Per cell, the student view keeps the first class subject only
    (``keep_all=False``: a week-specific slot wins over an every-week one
    on bad legacy data); the teacher view keeps them all, so a clash
    shows up instead of being hidden.
    """

    today = now.date()
    bells = list(Bell.objects.filter(is_active=True).order_by("order"))
    today_day = persian_weekday(today)
    days = _working_days(s.day_of_week for s in schedules)
    day_labels = dict(ClassSchedule.DayChoices.choices)

    weeks = []
    for number, week_type in ((1, ClassSchedule.WeekTypeChoices.WEEK_ONE),
                              (2, ClassSchedule.WeekTypeChoices.WEEK_TWO)):
        start = rotation.week_starts[week_type]
        end = start + timedelta(days=6)
        is_current = rotation.started and week_type == rotation.current_type

        cells = {}
        for schedule in schedules:
            if schedule.week_type not in (week_type, ClassSchedule.WeekTypeChoices.BOTH):
                continue
            if not _runs_in(schedule.class_subject, start, end):
                continue
            cell = cells.setdefault((schedule.day_of_week, schedule.bell_id), [])
            if keep_all or not cell:
                cell.append(schedule.class_subject)

        week_days = []
        for day in days:
            is_today = is_current and day == today_day
            slots = []
            for bell in bells:
                entries = [make_entry(cs) for cs in cells.get((day, bell.id), [])]
                slots.append(Slot(
                    bell=bell,
                    entry=entries[0] if entries else None,
                    is_now=is_today and bell.start_time <= now.time() < bell.end_time,
                    entries=entries,
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

    return bells, weeks, (today_day if today_day in days else None)


def build_weekly_schedule(school_class, academic_year=None, now=None):
    """
    Both rotation weeks of ``school_class``.

    The current rotation week is the calendar week (Sat..Fri) containing
    today; the other one is shown as it will be when it next comes round
    (usually next week, but two weeks ahead during the merged first week
    of the year, see ``scheduling.utils``). Before the academic year
    starts, both are shown as they will be in its first weeks. A slot is
    listed when its ``week_type`` is that week or BOTH, its class subject
    is active and teaching during that calendar week, and its bell is
    active.
    """

    now = timezone.localtime(now) if now else timezone.localtime()
    academic_year = academic_year or school_class.year
    rotation = _rotation(academic_year, now.date())

    schedules = list(
        _in_effect(ClassSchedule.objects.filter(class_subject__school_class=school_class), rotation)
        .select_related(
            "bell",
            "class_subject__subject",
            "class_subject__teacher_assignment__teacher__staff__user",
        )
        # Week-specific slots (1, 2) before every-week ones (3): if bad
        # legacy data puts both on one cell, the specific one wins.
        .order_by("week_type", "bell__order")
    )

    bells, weeks, today_day = _build_weeks(schedules, rotation, now, _entry)
    return WeeklySchedule(
        bells=bells,
        weeks=weeks,
        today=now.date(),
        today_day=today_day,
        generated_on=jalali_long(now.date()),
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


# ----------------------------------------------------------------------
# Teacher schedule
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class TeacherScheduleEntry:
    key: int          # ClassSubject pk
    subject: str
    class_label: str  # "اول - یک"
    branch: str
    school_class_id: int
    subject_id: int
    color: str        # validated #rrggbb
    tint: str         # for the PDF

    @property
    def style(self):
        # Only values that went through safe_hex(): safe in style="".
        return f"--subject-color: {self.color};"


@dataclass
class WeekSummary:
    periods: int
    classes: int
    subjects: int
    conflicts: int


@dataclass
class CombinedCell:
    """One day x bell of the one-page print/PDF grid: both weeks merged."""

    bell: Bell
    items: list  # [(TeacherScheduleEntry, week label or None), ...]
    has_conflict: bool = False


@dataclass
class TeacherWeeklySchedule(WeeklySchedule):
    academic_year: object = None
    teacher_name: str = ""

    def summary(self, week):
        entries = [entry for day in week.days for slot in day.slots for entry in slot.entries]
        return WeekSummary(
            periods=len(entries),
            classes=len({entry.school_class_id for entry in entries}),
            subjects=len({entry.subject_id for entry in entries}),
            conflicts=sum(1 for day in week.days for slot in day.slots if slot.has_conflict),
        )

    @property
    def has_entries(self):
        return any(day.has_entries for week in self.weeks for day in week.days)

    @property
    def weeks_differ(self):
        first, second = self.weeks
        return [
            [[e.key for e in slot.entries] for slot in day.slots] for day in first.days
        ] != [
            [[e.key for e in slot.entries] for slot in day.slots] for day in second.days
        ]

    @property
    def combined_days(self):
        """
        ``[(DaySchedule of week 1, [CombinedCell, ...]), ...]``: a lesson
        held in both weeks is listed once; one held in only one week is
        tagged with that week. For a one-page PDF/print.
        """

        first, second = self.weeks
        rows = []
        for day_one, day_two in zip(first.days, second.days):
            cells = []
            for slot_one, slot_two in zip(day_one.slots, day_two.slots):
                keys_one = [e.key for e in slot_one.entries]
                keys_two = [e.key for e in slot_two.entries]
                items = [(e, None) for e in slot_one.entries if e.key in keys_two]
                items += [(e, WEEK_LABELS[first.week_type]) for e in slot_one.entries if e.key not in keys_two]
                items += [(e, WEEK_LABELS[second.week_type]) for e in slot_two.entries if e.key not in keys_one]
                cells.append(CombinedCell(
                    bell=slot_one.bell,
                    items=items,
                    has_conflict=slot_one.has_conflict or slot_two.has_conflict,
                ))
            rows.append((day_one, cells))
        return rows


def _teacher_entry(class_subject):
    color = safe_hex(class_subject.subject.color)
    school_class = class_subject.school_class
    return TeacherScheduleEntry(
        key=class_subject.pk,
        subject=class_subject.subject.name,
        class_label=f"{school_class.grade.name} - {school_class.section}",
        branch=school_class.branch.name,
        school_class_id=school_class.pk,
        subject_id=class_subject.subject_id,
        color=color,
        tint=tint(color, 0.12),
    )


def build_teacher_weekly_schedule(teacher_profile, academic_year, now=None):
    """
    Both rotation weeks of everything ``teacher_profile`` teaches in
    ``academic_year``, across all classes and branches (same rules as
    ``build_weekly_schedule``; inactive classes are left out, like on the
    dashboard). Two lessons in one slot are both kept (``has_conflict``).
    """

    now = timezone.localtime(now) if now else timezone.localtime()
    rotation = _rotation(academic_year, now.date())

    schedules = list(
        _in_effect(
            ClassSchedule.objects.filter(
                class_subject__teacher_assignment__teacher=teacher_profile,
                class_subject__school_class__year=academic_year,
                class_subject__school_class__is_active=True,
            ),
            rotation,
        )
        .select_related(
            "bell",
            "class_subject__subject",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
        )
        .order_by("week_type", "bell__order", "class_subject__school_class__grade__level", "pk")
    )

    bells, weeks, today_day = _build_weeks(schedules, rotation, now, _teacher_entry, keep_all=True)
    user = teacher_profile.staff.user
    return TeacherWeeklySchedule(
        bells=bells,
        weeks=weeks,
        today=now.date(),
        today_day=today_day,
        generated_on=jalali_long(now.date()),
        academic_year=academic_year,
        teacher_name=user.get_full_name() or user.get_username(),
    )


def get_teacher_weekly_schedule(teacher_profile, now=None):
    """The teacher's own schedule for the current academic year, or None when there is none."""

    academic_year = AcademicYear.objects.filter(is_current=True).first()
    if academic_year is None:
        return None
    return build_teacher_weekly_schedule(teacher_profile, academic_year, now=now)


def academic_year_span(academic_year):
    """"1405-1406" from the Jalali years the academic year starts and ends in."""

    start = jdatetime.date.fromgregorian(date=_to_gregorian(academic_year.start_date)).year
    end = jdatetime.date.fromgregorian(date=_to_gregorian(academic_year.end_date)).year
    return f"{start}-{end}" if end != start else f"{start}"


def teacher_schedule_pdf_filename(schedule):
    return f"weekly-schedule-{academic_year_span(schedule.academic_year)}.pdf"


# ----------------------------------------------------------------------
# Teacher schedule: one dated week, every cell a slot with a state
# ----------------------------------------------------------------------
# The screen version of the teacher's schedule shows one calendar week
# (Saturday..Wednesday) with real dates, so each cell is a concrete slot
# (class subject + date + bell) the teacher can record a session for.
# Which slots exist and which are closed comes from academic_calendar --
# the same rules as the session form, so the page and the server agree.

#: ``SlotLesson.state`` values.
SLOT_OPEN = "open"              # can be recorded: a link to the session form
SLOT_FUTURE = "future"          # later than today: not clickable
SLOT_REGISTERED = "registered"  # a session exists for this slot
SLOT_HOLIDAY = "holiday"        # closed by the academic calendar

FUTURE_TOOLTIP = "امکان ثبت جلسه برای تاریخ‌های آینده وجود ندارد"
REGISTERED_MESSAGE = "برای این درس در این زنگ و این تاریخ قبلاً جلسه ثبت شده است"


@dataclass
class SlotLesson:
    entry: TeacherScheduleEntry
    class_subject_id: int
    state: str
    event_title: str = ""
    session_id: int | None = None
    session_number: int | None = None

    @property
    def is_link(self):
        """Open and registered cells are links (the server answers a registered one with its error)."""

        return self.state in (SLOT_OPEN, SLOT_REGISTERED)

    @property
    def tooltip(self):
        if self.state == SLOT_FUTURE:
            return FUTURE_TOOLTIP
        if self.state == SLOT_HOLIDAY:
            return f"تعطیل: {self.event_title}"
        if self.state == SLOT_REGISTERED:
            return REGISTERED_MESSAGE
        return "ثبت جلسه"


@dataclass
class DatedCell:
    bell: Bell
    lessons: list
    is_now: bool = False

    @property
    def has_conflict(self):
        return len(self.lessons) > 1


@dataclass
class DatedDay:
    date: date            # Gregorian
    value: int            # ClassSchedule.DayChoices value
    label: str
    cells: list
    is_today: bool = False

    @property
    def jalali(self):
        """"1405-07-12": the session form's ``?date=``."""

        return jdatetime.date.fromgregorian(date=self.date).strftime("%Y-%m-%d")

    @property
    def has_lessons(self):
        return any(cell.lessons for cell in self.cells)


@dataclass
class TeacherWeek:
    start: date           # Saturday (Gregorian)
    week_type: int | None
    days: list
    bells: list
    is_current: bool
    previous_start: date | None
    next_start: date | None
    today: date

    @property
    def end(self):
        return self.start + timedelta(days=6)

    @property
    def last_school_day(self):
        return self.days[-1].date if self.days else self.start

    @property
    def label(self):
        return WEEK_LABELS.get(self.week_type, "")

    @staticmethod
    def param(day):
        """The ``?week=`` value of the week starting on ``day``: its Jalali date."""

        return jdatetime.date.fromgregorian(date=day).strftime("%Y-%m-%d") if day else ""

    @property
    def query(self):
        return self.param(self.start)

    @property
    def previous_query(self):
        return self.param(self.previous_start)

    @property
    def next_query(self):
        return self.param(self.next_start)

    @property
    def default_day(self):
        values = [day.value for day in self.days]
        today = persian_weekday(self.today)
        return today if self.is_current and today in values else (values[0] if values else None)

    @property
    def lessons(self):
        return [lesson for day in self.days for cell in day.cells for lesson in cell.lessons]

    def count(self, state):
        return sum(1 for lesson in self.lessons if lesson.state == state)

    @property
    def summary(self):
        return {
            "periods": len(self.lessons),
            "registered": self.count(SLOT_REGISTERED),
            "open": self.count(SLOT_OPEN),
            "holidays": self.count(SLOT_HOLIDAY),
        }


def parse_week(value):
    """``?week=`` (a Jalali date, any day of the week) -> Gregorian date, or None."""

    from academic_calendar.services import parse_jalali_date

    try:
        return parse_jalali_date(value).togregorian()
    except ValueError:
        return None


def build_teacher_week(teacher_profile, academic_year, week_of=None, now=None):
    """
    The calendar week containing ``week_of`` (default: today), clamped to
    ``academic_year``: Saturday..Wednesday, the active bells, and per cell
    the teacher's lessons as ``SlotLesson`` with a state:

    * ``holiday`` -- an active ``CalendarEvent`` closes the slot;
    * ``registered`` -- a session exists for class subject + date + bell
      (a legacy session without a bell counts against that day's slots
      in bell order);
    * ``future`` -- the date is after today;
    * ``open`` -- the teacher can record it.

    Slots come from ``academic_calendar.services.get_slots`` (weekday,
    rotation week, teaching windows, never Thursday/Friday). A fixed
    number of queries: slots, events (+ scope), sessions, bells.
    """

    from academic_calendar import services as calendar
    from teaching.models import SchoolSession

    now = timezone.localtime(now) if now else timezone.localtime()
    today = now.date()

    first_week = week_start(_to_gregorian(academic_year.start_date))
    last_week = week_start(_to_gregorian(academic_year.end_date))
    start = week_start(week_of or today)
    start = min(max(start, first_week), last_week)
    end = start + timedelta(days=6)

    slots = calendar.get_slots(
        start, end,
        class_subject__teacher_assignment__teacher=teacher_profile,
        class_subject__school_class__year=academic_year,
    )
    closures = calendar.Closures.between(start, end, academic_year=academic_year)

    by_slot, legacy = {}, defaultdict(list)
    for session in (
        SchoolSession.objects.filter(
            class_subject_id__in={slot.class_subject.pk for slot in slots},
            date__gte=jdatetime.date.fromgregorian(date=start),
            date__lte=jdatetime.date.fromgregorian(date=end),
        )
        .exclude(status=SchoolSession.Status.HOLIDAY)
        .only("pk", "class_subject_id", "date", "bell_id", "session_number")
        .order_by("session_number", "pk")
    ):
        day = _to_gregorian(session.date)
        if session.bell_id is None:
            legacy[(session.class_subject_id, day)].append(session)
        else:
            by_slot[(session.class_subject_id, day, session.bell_id)] = session

    day_slots = defaultdict(list)
    for slot in slots:
        day_slots[(slot.class_subject.pk, slot.date)].append(slot)
    for key, sessions in legacy.items():
        free = [s for s in day_slots.get(key, ()) if s.key not in by_slot]
        for slot, session in zip(free, sessions):
            by_slot[slot.key] = session

    cells = defaultdict(list)
    for slot in slots:
        class_subject = slot.class_subject
        event = closures.event_for(slot.date, class_subject.school_class, slot.bell)
        session = by_slot.get(slot.key)
        if event is not None:
            state = SLOT_HOLIDAY
        elif session is not None:
            state = SLOT_REGISTERED
        elif slot.date > today:
            state = SLOT_FUTURE
        else:
            state = SLOT_OPEN
        cells[(slot.date, slot.bell.pk)].append(SlotLesson(
            entry=_teacher_entry(class_subject),
            class_subject_id=class_subject.pk,
            state=state,
            event_title=event.title if event else "",
            session_id=session.pk if session else None,
            session_number=session.session_number if session else None,
        ))

    bells = list(Bell.objects.filter(is_active=True).order_by("order"))
    day_labels = dict(ClassSchedule.DayChoices.choices)
    days = []
    for value in _working_days(()):
        if value == ClassSchedule.DayChoices.THURSDAY:
            continue  # never a school day, whatever the settings say
        day = start + timedelta(days=value)
        days.append(DatedDay(
            date=day,
            value=value,
            label=day_labels[value],
            is_today=day == today,
            cells=[
                DatedCell(
                    bell=bell,
                    lessons=cells.get((day, bell.pk), []),
                    is_now=day == today and bell.start_time <= now.time() < bell.end_time,
                )
                for bell in bells
            ],
        ))

    return TeacherWeek(
        start=start,
        week_type=calendar.get_week_type(max(start, _to_gregorian(academic_year.start_date)), academic_year),
        days=days,
        bells=bells,
        is_current=start == week_start(today),
        previous_start=start - timedelta(days=7) if start > first_week else None,
        next_start=start + timedelta(days=7) if start < last_week else None,
        today=today,
    )
