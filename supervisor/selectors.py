"""
Supervisor query/selector layer.

Layering:

              SupervisorScope
             /               \\
    SupervisorDashboardSelector   SupervisorAttendanceSelector
            v                              v
    Supervisor dashboard view      Supervisor attendance view
            v                              v
          Template                       Template

``SupervisorScope`` is the single source of truth for "what is this
supervisor allowed to see" (their branch, their grade, their assigned
classes). Every page-specific selector builds its data on top of that
scope and never queries the underlying models directly without going
through it, so the access boundary can't be accidentally bypassed by
view/template code.
"""

from collections import defaultdict
from datetime import datetime, timedelta

import jdatetime
from django.db.models import Count, Q
from django.utils import timezone

from attendance.models.attendance import Attendance
from school.models import ClassSubject, SchoolClass
from school.models.academic_year import AcademicYear
from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import get_current_week_type, get_today_schedule_day
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

        week_type = get_current_week_type(today)
        today_jalali = jdatetime.date.fromgregorian(date=today)

        return ClassSchedule.objects.filter(
            class_subject__in=self.scope.class_subjects(),
            day_of_week=day_of_week,
        ).filter(
            Q(week_type=week_type)
            | Q(week_type=ClassSchedule.WeekTypeChoices.BOTH)
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
