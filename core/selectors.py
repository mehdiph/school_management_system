"""
Data for the teacher dashboard (core.views.dashboard).

"Today's lessons" come from the timetable: the teacher's active class
subjects in the current academic year that have a ``ClassSchedule`` row
on today's weekday, in this rotation week (or every week). One row per
class subject and run of consecutive bells (a double period is one row;
the same class again later in the day is another).

A fixed number of queries whatever the number of lessons: the
last-session lookups used to run once per row.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import jdatetime
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.utils import timezone

from academic_calendar import services as calendar
from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import DateBeforeAcademicYearError, get_today_schedule_day, get_week_cycle
from school.models import AcademicYear, ClassSubject
from teaching.models import SchoolSession

RECENT_SESSIONS = 5


def class_name(school_class):
    """"اول - یک - مرکزی (عمار)": grade - section - branch."""

    return f"{school_class.grade.name} - {school_class.section} - {school_class.branch}"


@dataclass
class TodayLesson:
    class_subject_id: int
    subject: str
    class_name: str
    bells: list = field(default_factory=list)
    last_session_number: int = 0
    last_summary: str = ""
    recorded_session_id: int | None = None
    state: str | None = None        # "now" | "next" | None
    is_focus: bool = False          # the one row with the filled button
    #: Each bell is its own session (a double period is two). Bells the
    #: academic calendar closed today, and bells already recorded.
    closed_bell_ids: set = field(default_factory=set)
    recorded_bell_ids: set = field(default_factory=set)
    closed_title: str = ""
    date: str = ""                  # today, Jalali "1405-07-12" (the form's ?date=)

    @property
    def first_bell(self):
        return self.bells[0] if self.bells else None

    @property
    def start_time(self):
        return self.bells[0].start_time if self.bells else None

    @property
    def end_time(self):
        return self.bells[-1].end_time if self.bells else None

    @property
    def bell_orders(self):
        return [bell.order for bell in self.bells]

    @property
    def open_bells(self):
        return [bell for bell in self.bells if bell.pk not in self.closed_bell_ids]

    @property
    def is_closed(self):
        """Every bell of the row is closed by the academic calendar."""

        return bool(self.bells) and not self.open_bells

    @property
    def next_bell(self):
        """The first open bell without a session: what «ثبت جلسه» prefills."""

        return next(
            (bell for bell in self.open_bells if bell.pk not in self.recorded_bell_ids), None
        )

    @property
    def is_recorded(self):
        if not self.bells:
            return self.recorded_session_id is not None
        return not self.is_closed and self.next_bell is None


def current_academic_year():
    return AcademicYear.objects.filter(is_current=True).first()


def teacher_class_subjects(teacher_profile, academic_year):
    """The teacher's active class subjects (of active classes) in ``academic_year``."""

    return (
        ClassSubject.objects
        .for_teacher(teacher_profile)
        .filter(
            is_active=True,
            school_class__is_active=True,
            school_class__year=academic_year,
        )
    )


def active_classes_count(teacher_profile, academic_year):
    """Distinct classes the teacher teaches this year (a class with two subjects counts once)."""

    return (
        teacher_class_subjects(teacher_profile, academic_year)
        .order_by()
        .values("school_class")
        .distinct()
        .count()
    )


def _today_lessons(teacher_profile, academic_year, now):
    today = now.date()
    today_day = get_today_schedule_day(today)
    if academic_year is None or today_day is None:
        return []

    try:
        week_type = get_week_cycle(today, academic_year)
    except DateBeforeAcademicYearError:
        return []  # the year has not started yet: nothing is held today

    todays_slot = Q(day_of_week=today_day) & Q(
        week_type__in=[week_type, ClassSchedule.WeekTypeChoices.BOTH]
    )
    last_session = (
        SchoolSession.objects.counted()
        .filter(class_subject=OuterRef("pk"))
        .order_by("-session_number")
    )

    class_subjects = list(
        teacher_class_subjects(teacher_profile, academic_year)
        # One filter() call, so day and week type must hold for the
        # *same* schedule row (two calls would join schedules twice).
        .filter(
            Q(schedules__week_type=week_type)
            | Q(schedules__week_type=ClassSchedule.WeekTypeChoices.BOTH),
            schedules__day_of_week=today_day,
        )
        .distinct()
        .select_related("school_class__grade", "school_class__branch", "subject")
        .prefetch_related(
            Prefetch(
                "schedules",
                queryset=ClassSchedule.objects.filter(todays_slot).select_related("bell").order_by("bell__order"),
                to_attr="todays_schedules",
            )
        )
        .annotate(last_session_id=Subquery(last_session.values("pk")[:1]))
    )

    last_sessions = {
        session.pk: session
        for session in SchoolSession.objects
        .filter(pk__in=[cs.last_session_id for cs in class_subjects if cs.last_session_id])
        .select_related("session_contents")
    }

    # Today's sessions, matched to today's slots: a session without a
    # bell fills the day's free bells in order (calendar.match_sessions).
    todays_sessions = (
        SchoolSession.objects.counted()
        .filter(
            class_subject__in=[cs.pk for cs in class_subjects],
            date=jdatetime.date.fromgregorian(date=today),
        )
        .only("pk", "class_subject_id", "date", "bell_id", "status", "session_number")
    )
    slot_keys = [
        (cs.pk, today, schedule.bell_id)
        for cs in class_subjects
        for schedule in cs.todays_schedules
    ]
    recorded_bells = defaultdict(dict)       # class subject -> {bell id: session id}
    for (class_subject_id, _day, bell_id), session in calendar.match_sessions(
        slot_keys, todays_sessions
    ).items():
        recorded_bells[class_subject_id][bell_id] = session.pk

    closures = calendar.Closures.between(today, today, academic_year=academic_year)
    today_jalali = jdatetime.date.fromgregorian(date=today).strftime("%Y-%m-%d")

    lessons = []
    for cs in class_subjects:
        last_number, last_summary = 0, ""
        session = last_sessions.get(cs.last_session_id)
        if session is not None:
            last_number = session.session_number
            content = getattr(session, "session_contents", None)
            if content is not None:
                last_summary = content.content

        recorded = recorded_bells[cs.pk]

        for bells in _consecutive_runs([schedule.bell for schedule in cs.todays_schedules]):
            events = {bell.pk: closures.event_for(today, cs.school_class, bell) for bell in bells}
            closed = {pk for pk, event in events.items() if event is not None}
            lesson_sessions = [recorded[b.pk] for b in bells if b.pk in recorded]
            lessons.append(TodayLesson(
                class_subject_id=cs.pk,
                subject=cs.subject.name,
                class_name=class_name(cs.school_class),
                bells=bells,
                last_session_number=last_number,
                last_summary=last_summary,
                recorded_session_id=lesson_sessions[-1] if lesson_sessions else None,
                closed_bell_ids=closed,
                recorded_bell_ids=set(recorded) & {b.pk for b in bells},
                closed_title=next((e.title for e in events.values() if e is not None), ""),
                date=today_jalali,
            ))

    lessons.sort(key=lambda lesson: (not lesson.bells, lesson.bell_orders))
    _mark_now_and_next(lessons, now.time())
    return lessons


def _consecutive_runs(bells):
    """Bells (sorted by order) -> runs of consecutive orders: [1, 2, 5] -> [[1, 2], [5]]."""

    runs = []
    for bell in bells:
        if runs and bell.order == runs[-1][-1].order + 1:
            runs[-1].append(bell)
        else:
            runs.append([bell])
    return runs


def _mark_now_and_next(lessons, now_time):
    """
    Badge the lesson in progress ("now") and the next one to start
    ("next"). The focus row -- the only one with a filled "record" button
    -- is the lesson in progress, else the next one, unless it is
    already recorded.
    """

    current = next(
        (
            lesson for lesson in lessons
            if any(bell.start_time <= now_time < bell.end_time for bell in lesson.bells)
        ),
        None,
    )
    upcoming = next(
        (
            lesson for lesson in lessons
            if lesson is not current and lesson.start_time and lesson.start_time > now_time
        ),
        None,
    )

    if current is not None:
        current.state = "now"
    if upcoming is not None:
        upcoming.state = "next"

    focus = current or upcoming
    if focus is not None and not focus.is_recorded and not focus.is_closed:
        focus.is_focus = True


def build_teacher_dashboard(teacher_profile, now=None):
    now = timezone.localtime(now) if now else timezone.localtime()
    academic_year = current_academic_year()

    # Holidays are not sessions the teacher recorded: never counted or listed.
    teacher_sessions = SchoolSession.objects.counted().filter(
        class_subject__teacher_assignment__teacher=teacher_profile
    )

    lessons = _today_lessons(teacher_profile, academic_year, now)

    recent_sessions = (
        teacher_sessions
        .select_related(
            "class_subject__subject",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
        )
        .order_by("-date", "-created_at")[:RECENT_SESSIONS]
    )

    return {
        "academic_year": academic_year,
        "today": now.date(),
        "today_lessons": lessons,
        "has_times": any(lesson.bells for lesson in lessons),
        "active_classes_count": (
            active_classes_count(teacher_profile, academic_year) if academic_year else 0
        ),
        "total_sessions": teacher_sessions.count(),
        "today_lessons_count": len(lessons),
        "pending_today_count": sum(
            1 for lesson in lessons if not lesson.is_recorded and not lesson.is_closed
        ),
        "recent_sessions": [
            {"session": session, "class_name": class_name(session.class_subject.school_class)}
            for session in recent_sessions
        ],
    }
