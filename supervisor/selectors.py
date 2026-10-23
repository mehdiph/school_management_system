"""
Supervisor query/selector layer.

Layering:

                              SupervisorScope
             /                  /              \\                  \\
    Dashboard selector   Attendance selector   Sessions selector   Teachers selector
            v                  v                    v                   v
      dashboard view    attendance view    sessions / timeline /   teachers view
                                             session detail views

``SupervisorScope`` is the single source of truth for "what is this
supervisor allowed to see" (their branch, their grade, their assigned
classes). Every page-specific selector builds its data on top of that
scope and never queries the underlying models directly without going
through it, so the access boundary can't be accidentally bypassed by
view/template code.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import jdatetime
from django.conf import settings
from django.db.models import BooleanField, Count, ExpressionWrapper, F, Max, Min, Q
from django.db.models.functions import Substr
from django.utils import timezone

from attendance import services as attendance
from school.models import ClassSubject, SchoolClass, Subject
from school.models.academic_year import AcademicYear
from scheduling.models.class_schedule import ClassSchedule
from academic_calendar import services as calendar
from analytics import engine, metrics
from analytics.definitions import counted_q, missing_content_q, rounded
from analytics.scope import AnalyticsScope, as_of_for
from scheduling.utils import (
    DateBeforeAcademicYearError,
    get_today_schedule_day,
    get_week_cycle,
)
from staff.models.teacher_assignment import TeacherAssignment
from staff.models.teacher_profile import TeacherProfile
from student.models.student_enrollment import StudentEnrollment
from supervisor.models.supervisor_class import SupervisorClass
from teaching.models.school_session import SchoolSession


class SupervisorScope:
    """
    Access boundary for supervisor-visible data.

    A supervisor may only ever see data belonging to:
      1. the classes explicitly assigned to them (SupervisorClass)
      2. their own branch
      3. their own grade
    """

    def __init__(self, supervisor):
        self.supervisor = supervisor

    def classes(self):
        return SchoolClass.objects.filter(
            supervisor_assignments__supervisor=self.supervisor,
            branch=self.supervisor.branch,
            grade=self.supervisor.grade,
        ).distinct()

    def class_subjects(self):
        return ClassSubject.objects.filter(
            school_class__in=self.classes(),
        ).distinct()

    def supervised_class_subjects(self, year=None):
        """
        The active class subjects of the supervisor's active classes,
        optionally in one academic year: the rows the "training sessions"
        and "supervised teachers" pages are built from. Every detail /
        partial view of those pages looks its object up through this (or
        :meth:`supervised_sessions`), so anything outside it is a 404.

        Not ``distinct()`` like :meth:`class_subjects`: nothing here joins
        a multi-valued relation, and DISTINCT would get in the way of the
        callers' GROUP BY / ORDER BY on related fields.
        """

        queryset = ClassSubject.objects.filter(
            school_class__in=self.classes(),
            is_active=True,
            school_class__is_active=True,
        )
        if year is not None:
            queryset = queryset.filter(school_class__year=year)
        return queryset

    def supervised_sessions(self):
        """Sessions of :meth:`supervised_class_subjects` (any year)."""

        return SchoolSession.objects.filter(
            class_subject__in=self.supervised_class_subjects(),
        )

    def academic_years(self):
        """
        Years the supervisor has classes in, plus the current year (the
        default even before any class is assigned for it), newest first.
        """

        return (
            AcademicYear.objects.filter(
                Q(schoolclass__in=self.classes()) | Q(is_current=True)
            )
            .distinct()
            .order_by("-start_date")
        )

    def sessions(self):
        return SchoolSession.objects.filter(
            class_subject__in=self.class_subjects(),
        ).distinct()

    def student_enrollments(self):
        return StudentEnrollment.objects.filter(
            school_class__in=self.classes(),
        ).distinct()

    def teachers(self):
        """
        Teachers *currently* teaching in the supervisor's scope.

        Both ``class_subjects__is_active`` and ``assignments__status``
        are checked -- a class_subject deactivated (e.g. reassigned to
        a different teacher via a new ClassSubject row, since PROTECT
        on ``teacher_assignment`` means the old row is usually
        deactivated rather than deleted) or a teacher assignment that
        has ended must not still count towards "معلم فعال" on the
        dashboard.
        """

        return TeacherProfile.objects.filter(
            assignments__status=TeacherAssignment.AssignmentStatus.ACTIVE,
            assignments__branch=self.supervisor.branch,
            assignments__class_subjects__in=self.class_subjects(),
            assignments__class_subjects__is_active=True,
        ).distinct()


def class_supervisors(class_ids):
    """
    ``{class id: [SupervisorProfile, ...]}``: who supervises each class,
    by the rule of :meth:`SupervisorScope.classes` (assigned to the class,
    of its branch and of its grade), active users only, by name. A class
    without one is missing from the result. One query.
    """

    assignments = (
        SupervisorClass.objects.filter(
            school_class_id__in=class_ids,
            supervisor__branch=F("school_class__branch"),
            supervisor__grade=F("school_class__grade"),
            supervisor__user__is_active=True,
        )
        .select_related("supervisor__user")
        .order_by("supervisor__user__last_name", "supervisor__user__first_name", "supervisor_id")
    )
    supervisors = defaultdict(list)
    for assignment in assignments:
        supervisors[assignment.school_class_id].append(assignment.supervisor)
    return dict(supervisors)


class SupervisorDashboardSelector:
    """
    Builds all the read-only data needed by the supervisor dashboard.

    Every query here is derived from ``SupervisorScope`` (directly, or by
    filtering further on top of a scoped queryset) so supervisor-visible
    data can never leak outside their branch/grade/assigned classes.
    """

    #: grace period (in minutes) a teacher has, after a bell's end time,
    #: to register the corresponding SchoolSession before it is treated
    #: as "not registered" on the dashboard.
    SESSION_REGISTRATION_GRACE_MINUTES = 15

    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.scope = SupervisorScope(supervisor)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self):
        """
        High level counters for the supervisor's scope.

        Students and teachers are counted as unique people, not as
        rows (a student has one enrollment row per academic year, a
        teacher can teach more than one class/subject).
        """

        students_count = (
            self.scope.student_enrollments()
            .active()
            .values("student_id")
            .distinct()
            .count()
        )

        return {
            "classes_count": self.scope.classes().count(),
            "teachers_count": self.scope.teachers().count(),
            "students_count": students_count,
            "sessions_count": self.scope.sessions().counted().count(),
        }

    # ------------------------------------------------------------------
    # Recent sessions
    # ------------------------------------------------------------------

    def recent_sessions(self, limit=5):
        """
        The most recently registered sessions visible to the supervisor,
        with everything the dashboard needs already joined in (no N+1
        queries when the template accesses class/grade/subject/teacher).
        """

        return (
            self.scope.sessions()
            .counted()
            .select_related(
                "class_subject",
                "class_subject__school_class",
                "class_subject__school_class__grade",
                "class_subject__school_class__branch",
                "class_subject__subject",
                "class_subject__teacher_assignment",
                "class_subject__teacher_assignment__teacher",
                "class_subject__teacher_assignment__teacher__staff",
                "class_subject__teacher_assignment__teacher__staff__user",
            )
            .order_by("-date", "-created_at")[:limit]
        )

    # ------------------------------------------------------------------
    # Session statistics
    # ------------------------------------------------------------------

    def session_statistics(self):
        today_jalali = jdatetime.date.fromgregorian(
            date=timezone.localdate()
        )

        current_year = AcademicYear.objects.filter(is_current=True).first()

        # Holidays are not sessions: left out of every count and status.
        sessions = self.scope.sessions().counted()

        current_year_sessions = (
            sessions.filter(
                class_subject__school_class__year=current_year
            ).count()
            if current_year
            else 0
        )

        status_counts = dict(
            sessions.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        return {
            "total_sessions": sessions.count(),
            "today_sessions": sessions.filter(date=today_jalali).count(),
            "current_year_sessions": current_year_sessions,
            "by_status": {
                value: status_counts.get(value, 0)
                for value, _ in SchoolSession.Status.choices
                if value != SchoolSession.Status.HOLIDAY
            },
        }

    # ------------------------------------------------------------------
    # Attendance statistics
    # ------------------------------------------------------------------

    def attendance_statistics(self):
        """
        Counts per status over the attendance of the supervisor's classes
        (the archived records of delivered sessions before the cutoff, the
        daily sheets from it on: ``attendance.services``), and
        ``present_rate``: the attendance rate every panel uses (late
        counts as attended, absent and excused do not), 0 without records.
        """

        aggregates = attendance.attendance_counts(self.scope.classes())
        aggregates["present_rate"] = aggregates["rate"] or 0
        return aggregates

    # ------------------------------------------------------------------
    # Need attention
    # ------------------------------------------------------------------

    def _scheduled_today(self, today):
        """
        ``ClassSchedule`` slots visible to the supervisor that are
        supposed to happen on ``today`` (respecting weekday, week type,
        and the class_subject/teacher-assignment active window).

        Shared by :meth:`attention_items` (which needs each slot to
        compute overdue deadlines) and :meth:`today_schedule_count`
        (which only needs how many there are), so the "what should
        happen today" business rule is defined in exactly one place.
        """

        day_of_week = get_today_schedule_day(today)
        if day_of_week is None or not calendar.is_working_day(today):
            # Thursday and Friday are never school days (a legacy Thursday
            # slot is not expected either), nor are days outside the year.
            return ClassSchedule.objects.none()

        # Week 1 / week 2 depends on each class's own academic year.
        in_this_week = Q()
        years = AcademicYear.objects.filter(
            schoolclass__in=self.scope.classes()
        ).distinct()
        for year in years:
            try:
                week_type = get_week_cycle(today, year)
            except DateBeforeAcademicYearError:
                continue  # that year has not started: nothing is held
            in_this_week |= Q(
                class_subject__school_class__year=year,
                week_type__in=[week_type, ClassSchedule.WeekTypeChoices.BOTH],
            )

        if not in_this_week:
            return ClassSchedule.objects.none()

        today_jalali = jdatetime.date.fromgregorian(date=today)

        return ClassSchedule.objects.filter(
            class_subject__in=self.scope.class_subjects(),
            day_of_week=day_of_week,
        ).filter(
            in_this_week
        ).filter(
            class_subject__is_active=True,
            class_subject__school_class__is_active=True,
            class_subject__start_date__lte=today_jalali,
            class_subject__end_date__gte=today_jalali,
            class_subject__teacher_assignment__status=(
                TeacherAssignment.AssignmentStatus.ACTIVE
            ),
        )

    def _open_today(self, schedules, today):
        """``schedules`` minus the slots the academic calendar closed today."""

        closures = calendar.Closures.between(today, today)
        return [
            schedule for schedule in schedules
            if not closures.is_closed(today, schedule.class_subject.school_class, schedule.bell)
        ]

    def today_schedule_count(self):
        """How many class slots are held today, in scope (closed ones are not)."""

        today = timezone.localdate()
        schedules = self._scheduled_today(today).select_related("bell", "class_subject__school_class")
        return len(self._open_today(schedules, today))

    def attention_items(self):
        """
        Classes whose scheduled slot has already ended (plus a grace
        period) today, but for which no SchoolSession has been
        registered yet.

        This intentionally does NOT start from SchoolSession (a missing
        session has no row to start from). It starts from
        ``ClassSchedule`` -- the source of truth for what *should* have
        happened today -- and checks which of those slots have no
        matching registration.

        A slot is matched to a session by (class_subject, date, bell):
        two bells of one subject are two expected sessions, and recording
        one does not cover the other. A legacy session recorded without a
        bell covers that day's first uncovered slot (in bell order). Slots
        the academic calendar closed are never reported.
        """

        now = timezone.localtime(timezone.now())
        today = now.date()
        today_jalali = jdatetime.date.fromgregorian(date=today)

        schedules = list(
            self._scheduled_today(today)
            .select_related(
                "bell",
                "class_subject__school_class__grade",
                "class_subject__school_class__branch",
                "class_subject__subject",
                "class_subject__teacher_assignment__teacher__staff__user",
            )
            .order_by("bell__end_time", "class_subject_id")
        )
        schedules = self._open_today(schedules, today)

        if not schedules:
            return []

        grace = timedelta(minutes=self.SESSION_REGISTRATION_GRACE_MINUTES)
        tz = timezone.get_default_timezone()

        overdue_by_class_subject = defaultdict(list)

        for schedule in schedules:
            naive_deadline = datetime.combine(today, schedule.bell.end_time) + grace
            deadline = timezone.make_aware(naive_deadline, tz)

            if now >= deadline:
                overdue_by_class_subject[schedule.class_subject_id].append(
                    (schedule, deadline)
                )

        if not overdue_by_class_subject:
            return []

        # Single extra query: the sessions already registered today for
        # the overdue class subjects, matched to today's open slots (a
        # legacy bell-less session fills the first one in bell order).
        registered = SchoolSession.objects.counted().filter(
            class_subject_id__in=overdue_by_class_subject.keys(),
            date=today_jalali,
        ).only("pk", "class_subject_id", "date", "bell_id", "status", "session_number")
        slot_keys = [
            (schedule.class_subject_id, today, schedule.bell_id)
            for schedule in sorted(schedules, key=lambda s: s.bell.order)
        ]
        covered = calendar.match_sessions(slot_keys, registered)

        items = []

        for class_subject_id, entries in overdue_by_class_subject.items():
            # entries are ordered by bell end time: earliest overdue first
            for schedule, deadline in entries:
                if (class_subject_id, today, schedule.bell_id) in covered:
                    continue
                class_subject = schedule.class_subject
                school_class = class_subject.school_class
                teacher_assignment = class_subject.teacher_assignment

                items.append({
                    "type": "missing_session",
                    "title": "جلسه ثبت نشده",
                    "class_subject_id": class_subject_id,
                    "school_class": school_class,
                    "grade": school_class.grade,
                    "branch": school_class.branch,
                    "subject": class_subject.subject,
                    "teacher": teacher_assignment.teacher,
                    "bell": schedule.bell,
                    "scheduled_end_time": schedule.bell.end_time,
                    "deadline": deadline,
                })

        items.sort(key=lambda item: item["scheduled_end_time"])

        return items

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------

    def get_dashboard_data(self):
        return {
            "summary": self.summary(),
            "recent_sessions": self.recent_sessions(),
            "session_statistics": self.session_statistics(),
            "attendance_statistics": self.attendance_statistics(),
            "attention_items": self.attention_items(),
            "today_schedule_count": self.today_schedule_count(),
            "daily_attendance": SupervisorAttendanceSelector(self.supervisor).today_summary(),
        }


@dataclass
class ClassAttendanceDay:
    """One class on one day of the daily attendance overview."""

    RECORDED = "recorded"       # the sheet is taken
    MISSING = "missing"         # the class has lessons, the sheet is not taken
    CLOSED = "closed"           # every lesson of the day closed by the calendar
    NO_LESSONS = "no_lessons"   # nothing in the timetable that day
    ARCHIVE = "archive"         # before the cutoff: per-session attendance
    FUTURE = "future"

    school_class: SchoolClass
    status: str
    closure: object = None      # the closing CalendarEvent (CLOSED)
    counts: dict = None         # total / absent / late / excused (RECORDED)

    @property
    def needs_attention(self):
        return self.status == self.MISSING


class SupervisorAttendanceSelector:
    """
    Daily attendance of the supervisor's classes: which classes have their
    sheet on a day (the overview the attendance page opens with, today by
    default), and the records to follow up for one class on that day.

    Attendance is read through ``attendance.services``, so a day before
    ``settings.ATTENDANCE_DAILY_START_DATE`` shows the archived
    per-session records instead (read-only; that day has no sheets).

    Every query is derived from ``SupervisorScope``: a client-supplied
    ``class`` id is looked up among :meth:`classes`, so a tampered or
    foreign id never reaches another class's data (it falls back to the
    first class).
    """

    def __init__(self, supervisor, today=None):
        self.supervisor = supervisor
        self.scope = SupervisorScope(supervisor)
        self.today = today or timezone.localdate()

    def classes(self, day):
        """The supervisor's active classes of the academic year ``day`` is in."""

        jalali = jdatetime.date.fromgregorian(date=day)
        return (
            self.scope.classes()
            .filter(is_active=True, year__start_date__lte=jalali, year__end_date__gte=jalali)
            .select_related("grade", "branch", "year")
            .order_by("grade__level", "section")
        )

    def overview(self, day):
        """
        ``[ClassAttendanceDay]`` for every class of :meth:`classes` on
        ``day``. A class has lessons on a day when its weekly timetable
        has an open slot (``attendance.services.planned_class_days``).
        Three queries (classes, timetable, sheets) on a daily day.
        """

        classes = list(self.classes(day))
        if not classes:
            return []
        if not attendance.is_daily(day):
            return [ClassAttendanceDay(c, ClassAttendanceDay.ARCHIVE) for c in classes]
        if day > self.today:
            return [ClassAttendanceDay(c, ClassAttendanceDay.FUTURE) for c in classes]

        ids = [c.pk for c in classes]
        planned = attendance.planned_class_days(day, day, SchoolClass.objects.filter(pk__in=ids))
        sheets = {
            class_id: {"total": total, "absent": absent, "late": late, "excused": excused}
            for class_id, _, total, absent, late, excused
            in attendance.class_day_tallies(day, day, ids)
        }

        rows = []
        for school_class in classes:
            key = (school_class.pk, day)
            if school_class.pk in sheets:
                row = ClassAttendanceDay(
                    school_class, ClassAttendanceDay.RECORDED, counts=sheets[school_class.pk]
                )
            elif key not in planned:
                row = ClassAttendanceDay(school_class, ClassAttendanceDay.NO_LESSONS)
            elif planned[key] is not None:
                row = ClassAttendanceDay(school_class, ClassAttendanceDay.CLOSED, closure=planned[key])
            else:
                row = ClassAttendanceDay(school_class, ClassAttendanceDay.MISSING)
            rows.append(row)
        return rows

    @staticmethod
    def summarize(rows):
        """How many classes take attendance that day, how many are done, which are not."""

        due = [row for row in rows if row.status in (ClassAttendanceDay.RECORDED, ClassAttendanceDay.MISSING)]
        missing = [row for row in due if row.needs_attention]
        return {"due": len(due), "recorded": len(due) - len(missing), "missing": missing}

    def today_summary(self):
        """The dashboard's «حضور و غیاب امروز» card."""

        rows = self.overview(self.today)
        return {
            **self.summarize(rows),
            "is_daily": attendance.is_daily(self.today),
            "daily_start": attendance.daily_start(),
        }

    def get_attendance_page_data(self, class_id, day=None):
        """
        Everything the attendance page needs for ``day`` (default today):
        the overview, and for the selected class (``class_id`` if it is one
        of the supervisor's, else the first) its counts and the records to
        follow up (absent, late, excused).
        """

        day = day or self.today
        rows = self.overview(day)
        classes = [row.school_class for row in rows]
        selected_class = next((c for c in classes if c.pk == class_id), None) or (
            classes[0] if classes else None
        )
        selected_row = next((row for row in rows if row.school_class == selected_class), None)

        return {
            "day": jdatetime.date.fromgregorian(date=day),
            "today": jdatetime.date.fromgregorian(date=self.today),
            "is_today": day == self.today,
            "is_daily": attendance.is_daily(day),
            "daily_start": attendance.daily_start(),
            "previous_day": jdatetime.date.fromgregorian(date=day - timedelta(days=1)),
            "next_day": (
                jdatetime.date.fromgregorian(date=day + timedelta(days=1)) if day < self.today else None
            ),
            "overview": rows,
            "overview_summary": self.summarize(rows),
            "classes": classes,
            "selected_class": selected_class,
            "selected_row": selected_row,
            "absences": attendance.get_absences(selected_class, day, day) if selected_class else [],
            "summary": attendance.attendance_counts(selected_class, day, day) if selected_class else None,
        }


# ----------------------------------------------------------------------
# Training sessions ("جلسات آموزشی") and supervised teachers pages
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SessionFilters:
    """
    The validated filters of the training sessions page (see
    ``supervisor.forms.SessionFilterForm.filters``). Every value is
    already an in-scope object or a parsed value; ``None`` / ``""``
    means "not filtered".
    """

    academic_year: AcademicYear = None
    teacher: TeacherProfile = None
    subject: Subject = None
    school_class: SchoolClass = None
    date_from: jdatetime.date = None
    date_to: jdatetime.date = None
    status: str = ""
    sort: str = ""


def _ordering(sort, fields, default):
    """``"-name"`` -> the ``order_by()`` terms of ``fields["name"]``, descending."""

    key = sort.lstrip("-")
    if key not in fields:
        key, sort = default, default

    descending = sort.startswith("-")
    terms = []
    for name in fields[key]:
        expression = F(name)
        terms.append(
            expression.desc(nulls_last=True) if descending
            else expression.asc(nulls_last=True)
        )
    return [*terms, "pk"]


class SupervisorSessionsSelector:
    """
    Data of the training sessions page: one summary row per supervised
    ``ClassSubject`` (teacher x subject x class), the KPIs above it, the
    session timeline of one row and the details of one session.

    Everything starts from ``SupervisorScope.supervised_class_subjects``,
    so neither the filters nor a tampered URL can reach anything outside
    the supervisor's classes.
    """

    PAGE_SIZE = 20

    #: Two consecutive sessions further apart than this are marked as a
    #: long gap on the timeline.
    GAP_WARNING_DAYS = getattr(settings, "SUPERVISOR_SESSION_GAP_WARNING_DAYS", 14)

    #: Coverage (delivered / expected sessions, %) under these is shown
    #: as a problem / a warning.
    COVERAGE_LOW = 60
    COVERAGE_WARNING = 85

    #: How much of a session's content the timeline loads (it only shows
    #: two lines; the full text is in the session detail).
    EXCERPT_LENGTH = 240

    SORT_FIELDS = {
        "teacher": (
            "teacher_assignment__teacher__staff__user__last_name",
            "teacher_assignment__teacher__staff__user__first_name",
        ),
        "subject": ("subject__name",),
        "class": ("school_class__grade__level", "school_class__section"),
        "sessions": ("session_count",),
        "empty": ("empty_count",),
        "holidays": ("holiday_count",),
        "first_date": ("first_date",),
        "last_date": ("last_date",),
    }
    DEFAULT_SORT = "teacher"

    def __init__(self, supervisor, today=None):
        self.supervisor = supervisor
        self.scope = SupervisorScope(supervisor)
        self.today = today or timezone.localdate()

    # ------------------------------------------------------------------
    # Filter options (all from the supervisor's scope)
    # ------------------------------------------------------------------

    def academic_years(self):
        return self.scope.academic_years()

    def teacher_options(self, year, class_subjects=None):
        if class_subjects is None:
            class_subjects = self.scope.supervised_class_subjects(year)
        return (
            TeacherProfile.objects.filter(
                pk__in=class_subjects.values("teacher_assignment__teacher")
            )
            .select_related("staff__user")
            .order_by("staff__user__last_name", "staff__user__first_name", "pk")
        )

    def subject_options(self, year):
        return Subject.objects.filter(
            pk__in=self.scope.supervised_class_subjects(year).values("subject")
        ).order_by("name", "pk")

    def class_options(self, year):
        return (
            SchoolClass.objects.filter(
                pk__in=self.scope.supervised_class_subjects(year).values("school_class")
            )
            .select_related("grade", "branch")
            .order_by("grade__level", "section", "pk")
        )

    # ------------------------------------------------------------------
    # Summary table + KPIs
    # ------------------------------------------------------------------

    @staticmethod
    def _session_q(filters, prefix="", with_status=True):
        conditions = {}
        if filters.date_from:
            conditions[f"{prefix}date__gte"] = filters.date_from
        if filters.date_to:
            conditions[f"{prefix}date__lte"] = filters.date_to
        if with_status and filters.status:
            conditions[f"{prefix}status"] = filters.status
        return Q(**conditions)

    @classmethod
    def _holiday_q(cls, filters, prefix=""):
        """Holiday sessions in the filtered date range (whatever the status filter)."""

        return cls._session_q(filters, prefix, with_status=False) & Q(
            **{f"{prefix}status": SchoolSession.Status.HOLIDAY}
        )

    @classmethod
    def _counted_session_q(cls, filters, prefix=""):
        """The filtered sessions, holidays excluded (what every count uses)."""

        return cls._session_q(filters, prefix) & counted_q(prefix)

    def class_subjects(self, filters):
        """The supervised class subjects the filters select (no annotations)."""

        queryset = self.scope.supervised_class_subjects(filters.academic_year)
        if filters.teacher:
            queryset = queryset.filter(teacher_assignment__teacher=filters.teacher)
        if filters.subject:
            queryset = queryset.filter(subject=filters.subject)
        if filters.school_class:
            queryset = queryset.filter(school_class=filters.school_class)
        return queryset

    def summary_rows(self, filters):
        """
        One row per class subject with, for the sessions in the filtered
        date range / status: ``session_count``, ``empty_count`` (no
        content), ``first_date`` and ``last_date``; the coverage column is
        added per page by :meth:`attach_coverage`. Class subjects without
        any matching session are kept -- a teacher who records nothing is
        exactly what the supervisor needs to see.
        """

        in_range = self._counted_session_q(filters, "sessions__")

        return (
            self.class_subjects(filters)
            .select_related(
                "subject",
                "school_class__grade",
                "school_class__branch",
                "school_class__year",
                "teacher_assignment__teacher__staff__user",
            )
            .annotate(
                session_count=Count("sessions", filter=in_range),
                empty_count=Count("sessions", filter=in_range & missing_content_q("sessions__")),
                # per class subject: slots the academic calendar closed
                holiday_count=Count("sessions", filter=self._holiday_q(filters, "sessions__")),
                first_date=Min("sessions__date", filter=in_range),
                last_date=Max("sessions__date", filter=in_range),
            )
            .order_by(*_ordering(filters.sort, self.SORT_FIELDS, self.DEFAULT_SORT))
        )

    def kpis(self, filters):
        """The KPI cards, for every row the filters select (one query)."""

        in_range = self._counted_session_q(filters, "sessions__")

        return self.class_subjects(filters).aggregate(
            session_count=Count("sessions", filter=in_range),
            empty_count=Count("sessions", filter=in_range & missing_content_q("sessions__")),
            teacher_count=Count("teacher_assignment__teacher", distinct=True),
            last_date=Max("sessions__date", filter=in_range),
            holiday_count=Count("sessions", filter=self._holiday_q(filters, "sessions__")),
        )

    def attach_coverage(self, rows, filters):
        """
        ``rows`` (a page of :meth:`summary_rows`) as a list, each with:

        * ``expected_count`` -- the slots the timetable expected from the
          class subject's start, or the filter's ``date_from``, up to now /
          ``date_to``; ``None`` when the class subject has no timetable slot.
        * ``held_count`` -- how many of them were held.
        * ``coverage`` -- the execution rate (``held_count`` as a % of
          ``expected_count``; ``None`` when nothing was expected yet),
          ``coverage_bar`` (the same, for the progress bar) and
          ``coverage_level``.
        * ``compensatory_count`` -- compensatory sessions made up outside
          the timetable's slots (on a Thursday, at a free bell), for every
          row, timetable or not. They do not raise the rate, so the page
          shows them next to it: make-up work stays visible.

        All of it comes from the analytics engine, so the director
        dashboard shows exactly the same numbers for the same class
        subjects (see ``analytics.engine`` for what is expected and what
        is held: never Thursday/Friday, never a closed slot, a slot of
        today only once its bell is over, a held or compensatory session
        in the slot itself). A fixed number of queries for the whole page.
        """

        rows = list(rows)
        if not rows:
            return rows

        with_timetable = set(
            ClassSchedule.objects.filter(class_subject__in=[row.pk for row in rows])
            .values_list("class_subject_id", flat=True)
        )

        # Every row goes through the engine (not only those with a
        # timetable): a class subject without slots can still have
        # compensatory sessions to count.
        by_year = defaultdict(list)
        for row in rows:
            by_year[row.school_class.year].append(row)

        breakdowns = {}
        as_of = as_of_for(self.today)
        for year, year_rows in by_year.items():
            scope = AnalyticsScope.build(
                year, filters.date_from, filters.date_to, as_of=as_of,
                class_subjects=[row.pk for row in year_rows],
            )
            result = engine.compute(
                scope, with_attendance=False, class_subjects={row.pk: row for row in year_rows},
            )
            breakdowns.update(metrics.breakdowns(result, metrics.by_class_subject))

        for row in rows:
            breakdown = breakdowns.get(row.pk, metrics.Breakdown())
            row.expected_count = None
            row.held_count = None
            row.coverage = None
            row.coverage_level = ""
            row.compensatory_count = breakdown.compensatory

            if row.pk not in with_timetable:
                continue

            row.expected_count = breakdown.expected
            row.held_count = breakdown.held

            if row.expected_count:
                row.coverage = rounded(breakdown.execution_rate)
                row.coverage_bar = row.coverage
                if row.coverage < self.COVERAGE_LOW:
                    row.coverage_level = "low"
                elif row.coverage < self.COVERAGE_WARNING:
                    row.coverage_level = "warning"
                else:
                    row.coverage_level = "ok"

        return rows

    # ------------------------------------------------------------------
    # Timeline of one class subject
    # ------------------------------------------------------------------

    def timeline_class_subjects(self):
        """What the timeline view may look its class subject up in."""

        return self.scope.supervised_class_subjects().select_related(
            "subject",
            "school_class__grade",
            "school_class__branch",
            "school_class__year",
            "teacher_assignment__teacher__staff__user",
        )

    def timeline(self, class_subject, filters):
        """
        ``class_subject``'s sessions in the filtered range, in teaching
        order, with only what the timeline shows: the title, the start of
        the content (``excerpt``) and whether homework / activity / notes
        exist -- never the full texts. Each session also gets ``gap_days``
        (days since the previous one shown), ``is_long_gap`` and
        ``is_missing_content``.
        """

        def present(field):
            return ExpressionWrapper(
                Q(**{f"session_contents__{field}__gt": ""}),
                output_field=BooleanField(),
            )

        sessions = list(
            SchoolSession.objects.filter(class_subject=class_subject)
            .filter(self._session_q(filters))
            .select_related("bell", "calendar_event")
            .only(
                "id", "class_subject_id", "date", "session_number", "status",
                "bell__title", "bell__order", "calendar_event__title",
            )
            .annotate(
                title=F("session_contents__title"),
                excerpt=Substr("session_contents__content", 1, self.EXCERPT_LENGTH),
                has_content=ExpressionWrapper(
                    Q(session_contents__isnull=False), output_field=BooleanField()
                ),
                has_homework=present("homework"),
                has_activity=present("activity"),
                has_notes=present("notes"),
            )
            .order_by("date", F("bell__order").asc(nulls_first=True), "session_number")
        )

        # Holidays are shown in place, but a gap is measured between
        # counted sessions only: a closure neither breaks nor makes one.
        previous = None
        for session in sessions:
            if session.status == SchoolSession.Status.HOLIDAY:
                session.gap_days, session.is_long_gap, session.is_missing_content = None, False, False
                continue
            session.gap_days = (session.date - previous.date).days if previous else None
            session.is_long_gap = (
                session.gap_days is not None and session.gap_days > self.GAP_WARNING_DAYS
            )
            session.is_missing_content = (
                not session.has_content
                and session.status != SchoolSession.Status.CANCELED
            )
            previous = session

        return sessions

    # ------------------------------------------------------------------
    # One session
    # ------------------------------------------------------------------

    def detail_sessions(self):
        """What the session detail view may look its session up in."""

        return self.scope.supervised_sessions().select_related(
            "session_contents",
            "bell",
            "calendar_event",
            "class_subject__subject",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
            "class_subject__teacher_assignment__teacher__staff__user",
        )

    def attendance_summary(self, session):
        """
        Attendance counts for ``session``: its own archived records before
        the cutoff, the class's daily sheet of that day from it on
        (``attendance.services.session_counts``; one query).
        """

        return attendance.session_counts(session)


class SupervisorTeachersSelector:
    """
    Data of the supervised teachers page.

    A supervised teacher is a ``TeacherProfile`` with at least one active
    class subject in the supervisor's (active) classes in the selected
    academic year. Their session statistics only count those class
    subjects -- what the teacher does in other classes is not this
    supervisor's business.
    """

    PAGE_SIZE = 12

    #: A teacher whose last recorded session is older than this (in the
    #: current academic year) is highlighted.
    INACTIVITY_WARNING_DAYS = getattr(settings, "SUPERVISOR_INACTIVITY_WARNING_DAYS", 7)

    SORT_FIELDS = {
        "name": ("staff__user__last_name", "staff__user__first_name"),
        "sessions": ("session_count",),
        "last_activity": ("last_session_date",),
    }
    DEFAULT_SORT = "name"

    def __init__(self, supervisor, today=None):
        self.supervisor = supervisor
        self.scope = SupervisorScope(supervisor)
        self.today = today or timezone.localdate()

    def academic_years(self):
        return self.scope.academic_years()

    def subject_options(self, year):
        return Subject.objects.filter(
            pk__in=self.scope.supervised_class_subjects(year).values("subject")
        ).order_by("name", "pk")

    def _class_subjects(self, year, subject=None):
        queryset = self.scope.supervised_class_subjects(year)
        if subject is not None:
            queryset = queryset.filter(subject=subject)
        return queryset

    def teachers(self, year, subject=None, search="", sort=""):
        """
        The supervised teachers, with ``session_count``, ``empty_count``
        and ``last_session_date`` over their in-scope class subjects.

        The scope is applied in a single ``filter()`` *before* the
        ``annotate()``, so the aggregates run over exactly the class
        subjects that filter joined (Django reuses that join) -- not over
        every class the teacher has.
        """

        teachers = TeacherProfile.objects.filter(
            assignments__class_subjects__in=self._class_subjects(year, subject),
        )

        for word in search.split():
            teachers = teachers.filter(
                Q(staff__user__first_name__icontains=word)
                | Q(staff__user__last_name__icontains=word)
                | Q(staff__personnel_code__icontains=word)
            )

        sessions = "assignments__class_subjects__sessions"

        return (
            teachers.select_related("staff__user")
            .annotate(
                session_count=Count(sessions, filter=counted_q(f"{sessions}__")),
                empty_count=Count(sessions, filter=missing_content_q(f"{sessions}__")),
                # a holiday is not activity
                last_session_date=Max(f"{sessions}__date", filter=counted_q(f"{sessions}__")),
            )
            .order_by(*_ordering(sort, self.SORT_FIELDS, self.DEFAULT_SORT))
        )

    def decorate(self, teachers, year, subject=None):
        """
        ``teachers`` (a page of :meth:`teachers`) as a list, each with
        ``subject_chips`` / ``class_chips`` (what they teach in scope),
        ``days_since_last_session`` and ``is_inactive``. One query.
        """

        teachers = list(teachers)
        if not teachers:
            return teachers

        subjects = defaultdict(dict)
        classes = defaultdict(dict)

        rows = (
            self._class_subjects(year, subject)
            .filter(teacher_assignment__teacher__in=[t.pk for t in teachers])
            .order_by("subject__name", "school_class__grade__level", "school_class__section")
            .values_list(
                "teacher_assignment__teacher_id",
                "subject_id",
                "subject__name",
                "school_class_id",
                "school_class__grade__name",
                "school_class__section",
            )
        )
        for teacher_id, subject_id, subject_name, class_id, grade_name, section in rows:
            subjects[teacher_id][subject_id] = subject_name
            classes[teacher_id][class_id] = f"{grade_name} {section}"

        today = jdatetime.date.fromgregorian(date=self.today)
        is_current_year = bool(year and year.is_current)

        for teacher in teachers:
            teacher.subject_chips = list(subjects[teacher.pk].values())
            teacher.class_chips = list(classes[teacher.pk].values())

            last = teacher.last_session_date
            teacher.days_since_last_session = (today - last).days if last else None
            # "Inactive" only means something for the year in progress.
            teacher.is_inactive = is_current_year and (
                last is None
                or teacher.days_since_last_session > self.INACTIVITY_WARNING_DAYS
            )

        return teachers
