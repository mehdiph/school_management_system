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

from attendance.models.attendance import Attendance
from school.models import ClassSubject, SchoolClass, Subject
from school.models.academic_year import AcademicYear
from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import (
    DateBeforeAcademicYearError,
    count_scheduled_occurrences,
    get_today_schedule_day,
    get_week_cycle,
)
from staff.models.teacher_assignment import TeacherAssignment
from staff.models.teacher_profile import TeacherProfile
from student.models.student_enrollment import StudentEnrollment
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

    def attendance(self):
        return Attendance.objects.filter(
            session__in=self.sessions(),
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
            "sessions_count": self.scope.sessions().count(),
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

        sessions = self.scope.sessions()

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
            },
        }

    # ------------------------------------------------------------------
    # Attendance statistics
    # ------------------------------------------------------------------

    def attendance_statistics(self):
        aggregates = self.scope.attendance().aggregate(
            total=Count("id"),
            present=Count(
                "id",
                filter=Q(status=Attendance.AttendanceStatus.PRESENT),
            ),
            absent=Count(
                "id",
                filter=Q(status=Attendance.AttendanceStatus.ABSENT),
            ),
            late=Count(
                "id",
                filter=Q(status=Attendance.AttendanceStatus.LATE),
            ),
        )

        total = aggregates["total"] or 0
        present = aggregates["present"] or 0

        aggregates["present_rate"] = (
            round((present / total) * 100) if total else 0
        )

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
        if day_of_week is None:
            # No classes are scheduled on this weekday (e.g. Friday).
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

    def today_schedule_count(self):
        """How many class slots are scheduled for today, in scope."""

        return self._scheduled_today(timezone.localdate()).count()

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

        SchoolSession has no bell/schedule FK, so a scheduled slot and a
        registered session are matched by (class_subject, date) *count*
        rather than by a direct foreign key: if a class_subject meets
        twice today (two distinct ClassSchedule slots) and only one
        SchoolSession has been registered for today, exactly one
        occurrence is reported as missing -- whichever slot's grace
        period elapsed first.
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

        # Single extra query: how many sessions were already registered
        # today for each of the overdue class_subjects.
        registered_counts = dict(
            SchoolSession.objects.filter(
                class_subject_id__in=overdue_by_class_subject.keys(),
                date=today_jalali,
            )
            .values("class_subject_id")
            .annotate(count=Count("id"))
            .values_list("class_subject_id", "count")
        )

        items = []

        for class_subject_id, entries in overdue_by_class_subject.items():
            registered = registered_counts.get(class_subject_id, 0)
            missing = len(entries) - registered

            if missing <= 0:
                continue

            # The slots whose grace period elapsed earliest are reported
            # first as "missing" (entries are already ordered by
            # bell end time, ascending).
            for schedule, deadline in entries[:missing]:
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
        }


class SupervisorAttendanceSelector:
    """
    Query/data layer for the supervisor's per-class attendance page.

    ``Attendance`` rows belong to a ``SchoolSession`` (one class_subject,
    one date), not directly to a ``SchoolClass`` -- a class can have
    several class_subjects (subjects/teachers), each with its own
    session stream. So "this class's attendance" here means: the most
    recently registered session across all of the class's subjects,
    and that session's attendance rows -- the same "latest activity"
    notion ``SupervisorDashboardSelector.recent_sessions()`` uses.

    Like ``SupervisorDashboardSelector``, every query is derived from
    ``SupervisorScope`` so a caller can never reach data outside the
    supervisor's branch/grade/assigned classes -- in particular,
    ``resolve_class()`` is the only way a client-supplied ``class_id``
    may be turned into a ``SchoolClass``; nothing here ever does
    ``SchoolClass.objects.get(pk=...)`` directly.
    """

    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.scope = SupervisorScope(supervisor)

    def classes(self):
        """The classes this supervisor is allowed to pick from."""

        return (
            self.scope.classes()
            .select_related("grade", "branch")
            .order_by("grade__level", "section")
        )

    def resolve_class(self, class_id):
        """
        ``class_id`` -> in-scope ``SchoolClass``, or ``None``.

        Filtering through ``self.classes()`` (rather than looking the
        class up directly) is what makes a tampered/foreign class_id
        harmless: if it doesn't belong to this supervisor's scope, it
        simply doesn't match and ``None`` comes back.
        """

        if class_id is None:
            return None

        return self.classes().filter(pk=class_id).first()

    def latest_session(self, school_class):
        """The most recently registered session for ``school_class``."""

        if school_class is None:
            return None

        return (
            self.scope.sessions()
            .filter(class_subject__school_class=school_class)
            .select_related(
                "class_subject",
                "class_subject__subject",
                "class_subject__school_class",
                "class_subject__school_class__grade",
                "class_subject__school_class__branch",
            )
            .order_by("-date", "-session_number")
            .first()
        )

    def attendance_rows(self, session):
        """Attendance rows for ``session``, with everything the template needs already joined in."""

        if session is None:
            return Attendance.objects.none()

        return (
            self.scope.attendance()
            .filter(session=session)
            .select_related(
                "student_enrollment",
                "student_enrollment__student",
                "student_enrollment__student__user",
            )
            .order_by(
                "student_enrollment__student__user__last_name",
                "student_enrollment__student__user__first_name",
            )
        )

    def summary(self, session):
        """total/present/absent/late counts for ``session``, computed in the DB."""

        if session is None:
            return {"total": 0, "present": 0, "absent": 0, "late": 0}

        aggregates = self.scope.attendance().filter(session=session).aggregate(
            total=Count("id"),
            present=Count(
                "id", filter=Q(status=Attendance.AttendanceStatus.PRESENT)
            ),
            absent=Count(
                "id", filter=Q(status=Attendance.AttendanceStatus.ABSENT)
            ),
            late=Count(
                "id", filter=Q(status=Attendance.AttendanceStatus.LATE)
            ),
        )

        return aggregates

    def get_attendance_page_data(self, class_id):
        """
        Everything the attendance view/template needs for one request,
        in one call -- the view has no queries of its own.

        ``classes`` is materialized once and reused to pick the selected
        class (instead of calling ``resolve_class()``, which would run
        its own query) -- a supervisor's class list is small, so doing
        the id lookup in Python here saves a redundant round trip
        without weakening the scoping: the list itself already came
        from ``self.classes()``.
        """

        classes = list(self.classes())
        classes_by_id = {school_class.pk: school_class for school_class in classes}
        selected_class = classes_by_id.get(class_id) or (classes[0] if classes else None)
        session = self.latest_session(selected_class)

        return {
            "classes": classes,
            "selected_class": selected_class,
            "session": session,
            "attendance_rows": self.attendance_rows(session),
            "summary": self.summary(session),
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


def _no_content_q(prefix=""):
    """
    Sessions with no ``SessionContent`` row. Cancelled sessions are left
    out: nothing was taught, so a missing content is expected there.
    """

    return (
        Q(**{f"{prefix}session_contents__isnull": True})
        & ~Q(**{f"{prefix}status": SchoolSession.Status.CANCELED})
    )


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
        content), ``first_date`` and ``last_date``. ``delivered_count``
        (held + compensatory, date range only) feeds the coverage column
        (see :meth:`attach_coverage`). Class subjects without any matching
        session are kept -- a teacher who records nothing is exactly what
        the supervisor needs to see.
        """

        in_range = self._session_q(filters, "sessions__")
        delivered = (
            self._session_q(filters, "sessions__", with_status=False)
            & ~Q(sessions__status=SchoolSession.Status.CANCELED)
        )

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
                session_count=Count("sessions", filter=in_range or None),
                empty_count=Count("sessions", filter=in_range & _no_content_q("sessions__")),
                delivered_count=Count("sessions", filter=delivered),
                first_date=Min("sessions__date", filter=in_range or None),
                last_date=Max("sessions__date", filter=in_range or None),
            )
            .order_by(*_ordering(filters.sort, self.SORT_FIELDS, self.DEFAULT_SORT))
        )

    def kpis(self, filters):
        """The KPI cards, for every row the filters select (one query)."""

        in_range = self._session_q(filters, "sessions__")

        return self.class_subjects(filters).aggregate(
            session_count=Count("sessions", filter=in_range or None),
            empty_count=Count("sessions", filter=in_range & _no_content_q("sessions__")),
            teacher_count=Count("teacher_assignment__teacher", distinct=True),
            last_date=Max("sessions__date", filter=in_range or None),
        )

    def attach_coverage(self, rows, filters):
        """
        ``rows`` (a page of :meth:`summary_rows`) as a list, each with:

        * ``expected_count`` -- sessions the weekly timetable (both weeks of
          the rotation) planned from the class subject's start, or the
          filter's ``date_from``, up to today / ``date_to``; ``None`` when
          the class subject has no timetable slot.
        * ``coverage`` -- ``delivered_count`` as a % of it (``None`` when
          nothing was expected yet), ``coverage_bar`` (the same, capped at
          100 for the progress bar) and ``coverage_level``.

        Holidays are not modelled, so the expected count includes them.
        One query (the timetable slots of the whole page).
        """

        rows = list(rows)
        if not rows:
            return rows

        slots = defaultdict(list)
        for class_subject_id, day, week_type in ClassSchedule.objects.filter(
            class_subject__in=[row.pk for row in rows]
        ).values_list("class_subject_id", "day_of_week", "week_type"):
            slots[class_subject_id].append((day, week_type))

        today = jdatetime.date.fromgregorian(date=self.today)

        for row in rows:
            row.expected_count = None
            row.coverage = None
            row.coverage_level = ""

            row_slots = slots.get(row.pk)
            if not row_slots:
                continue

            year = row.school_class.year
            start = max(
                d for d in (row.start_date, year.start_date, filters.date_from) if d
            )
            end = min(
                d for d in (today, row.end_date, year.end_date, filters.date_to) if d
            )

            row.expected_count = (
                count_scheduled_occurrences(row_slots, start, end, year)
                if start <= end else 0
            )

            if row.expected_count:
                row.coverage = round(row.delivered_count * 100 / row.expected_count)
                row.coverage_bar = min(row.coverage, 100)
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
            .only("id", "class_subject_id", "date", "session_number", "status")
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
            .order_by("session_number", "date")
        )

        previous = None
        for session in sessions:
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
            "class_subject__subject",
            "class_subject__school_class__grade",
            "class_subject__school_class__branch",
            "class_subject__teacher_assignment__teacher__staff__user",
        )

    def attendance_summary(self, session):
        """Attendance counts per status for ``session`` (one query)."""

        return Attendance.objects.filter(session=session).aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=Attendance.AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=Attendance.AttendanceStatus.ABSENT)),
            late=Count("id", filter=Q(status=Attendance.AttendanceStatus.LATE)),
        )


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
                session_count=Count(sessions),
                empty_count=Count(sessions, filter=_no_content_q(f"{sessions}__")),
                last_session_date=Max(f"{sessions}__date"),
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
