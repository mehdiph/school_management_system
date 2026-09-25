"""
Report query/selector layer.

``ReportScope`` is the single source of truth for "what may this user
report on". The filter form, the JSON options endpoint and the report
builders all go through it, so a teacher can never reach another
teacher's classes by editing the query string -- the restriction lives
in the querysets, not in the template.

Only teachers are restricted. Every other role keeps the unrestricted
behaviour the report page always had.
"""

from collections import OrderedDict

import jdatetime
from django.db.models import Prefetch, Q

from core.services.access import today_jalali
from school.models import AcademicYear, ClassSubject, Grade, SchoolClass
from staff.models import TeacherAssignment, TeacherProfile
from teaching.models import SchoolSession

#: Everything a report row needs from a session, joined in one query.
SESSION_RELATED = (
    "session_contents",
    "class_subject__subject",
    "class_subject__teacher_assignment__teacher__staff__user",
)

NO_TEACHER_PROFILE_MESSAGE = (
    "حساب کاربری شما به پروفایل معلم متصل نیست. "
    "لطفاً با مدیر سامانه تماس بگیرید."
)
NO_ASSIGNMENT_MESSAGE = (
    "برای شما در سال تحصیلی جاری کلاس فعالی ثبت نشده است؛ "
    "به همین دلیل گزارشی برای نمایش وجود ندارد."
)
NO_CURRENT_YEAR_NOTICE = (
    "در سال تحصیلی جاری انتساب فعالی برای شما ثبت نشده است؛ "
    "گزارش سال‌های قبل نمایش داده می‌شود."
)


def teacher_display_name(class_subject):
    user = class_subject.teacher_assignment.teacher.staff.user
    return user.get_full_name() or user.username


class ReportScope:
    """
    Access boundary for the report pages.

    A teacher may only report on ``ClassSubject`` rows that are:
      * theirs, through a ``TeacherAssignment`` whose status is ``ACTIVE``
        and that has not ended (``end_date`` empty or not in the past) --
        the same "active assignment" rule ``core.services.access`` uses
        for branch access,
      * in the requested academic year,
      * active, in an active ``SchoolClass``.

    Classes and grades are derived from those rows via ``id__in``
    subqueries, so a teacher with several subjects in one class never
    produces duplicate options (no ``DISTINCT`` needed).
    """

    def __init__(self, user):
        self.user = user
        self.is_restricted = (
            user.role == user.Roles.TEACHER and not user.is_superuser
        )
        self.teacher = None
        self.error_message = None

        if self.is_restricted:
            self.teacher = (
                TeacherProfile.objects.filter(staff__user=user).first()
            )
            if self.teacher is None:
                self.error_message = NO_TEACHER_PROFILE_MESSAGE

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------

    def _assignments(self):
        return TeacherAssignment.objects.filter(
            teacher=self.teacher,
            status=TeacherAssignment.AssignmentStatus.ACTIVE,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today_jalali())
        )

    def years(self):
        if not self.is_restricted:
            return AcademicYear.objects.all()

        if self.teacher is None:
            return AcademicYear.objects.none()

        return AcademicYear.objects.filter(
            id__in=self._assignments().values("academic_year_id")
        )

    def default_year(self, years):
        """The current academic year if it is in ``years``, else the latest one."""

        for year in years:
            if year.is_current:
                return year

        return years[0] if years else None

    def class_subjects(self, year):
        queryset = ClassSubject.objects.filter(school_class__year=year)

        if not self.is_restricted:
            return queryset

        if self.teacher is None:
            return ClassSubject.objects.none()

        return queryset.filter(
            teacher_assignment__in=self._assignments().filter(
                academic_year=year
            ),
            is_active=True,
            school_class__is_active=True,
        )

    def classes(self, year):
        if not self.is_restricted:
            return SchoolClass.objects.filter(year=year)

        return SchoolClass.objects.filter(
            id__in=self.class_subjects(year).values("school_class_id")
        )

    def grades(self, year):
        grades = Grade.objects.filter(is_active=True)

        if not self.is_restricted:
            return grades

        return grades.filter(
            id__in=self.classes(year).values("grade_id")
        )


# ----------------------------------------------------------------------
# Report builders
# ----------------------------------------------------------------------

def _content_summary(session, limit=None):
    content = getattr(session, "session_contents", None)

    if content is None:
        return ""

    if limit is None:
        return f"{content.title}: {content.content}"

    text = content.content
    return text[:limit] + "..." if len(text) > limit else text


def build_class_report(scope, school_class):
    """
    Class report: one entry per subject of ``school_class`` that is in
    ``scope``, with its sessions. Runs a fixed three queries no matter
    how many subjects or sessions there are.
    """

    class_subjects = (
        scope.class_subjects(school_class.year_id)
        .filter(school_class=school_class)
        .select_related(
            "subject",
            "teacher_assignment__teacher__staff__user",
        )
        .prefetch_related(
            Prefetch(
                "sessions",
                queryset=(
                    SchoolSession.objects
                    .select_related("session_contents")
                    .order_by("date", "session_number")
                ),
            )
        )
        .order_by("subject__name")
    )

    subjects_data = []
    first_dates = []
    last_dates = []
    total_held = 0

    for class_subject in class_subjects:
        sessions = list(class_subject.sessions.all())
        session_list = [
            {
                "number": session.session_number,
                "date": session.date,
                "content": _content_summary(session),
                "status": session.status,
            }
            for session in sessions
        ]
        total_held += sum(
            1 for session in sessions
            if session.status == SchoolSession.Status.HELD
        )

        first_date = sessions[0].date if sessions else None
        last_date = sessions[-1].date if sessions else None

        if sessions:
            first_dates.append(first_date)
            last_dates.append(last_date)

        subjects_data.append({
            "name": class_subject.subject.name,
            "teacher_name": teacher_display_name(class_subject),
            "session_count": len(session_list),
            "first_date": first_date,
            "last_date": last_date,
            "sessions": session_list,
        })

    return {
        "class_name": school_class.section,
        "grade": school_class.grade.name,
        "academic_year": school_class.year.title,
        "report_date": jdatetime.datetime.now().strftime("%Y-%m-%d"),
        "total_subjects": len(subjects_data),
        "total_sessions": total_held,
        "first_session_date": min(first_dates) if first_dates else None,
        "last_session_date": max(last_dates) if last_dates else None,
        "subjects": subjects_data,
    }


def build_grade_report(scope, year, grade=None):
    """
    Grade report: every in-scope class of ``year`` (optionally only
    ``grade``), grouped by grade, with its sessions. Runs a fixed two
    queries (classes, sessions) instead of one per grade and class.
    """

    classes = (
        scope.classes(year)
        .filter(grade__is_active=True)
        .select_related("grade")
        .order_by("grade__level", "section")
    )

    if grade is not None:
        classes = classes.filter(grade=grade)

    classes = list(classes)

    sessions_by_class = {school_class.pk: [] for school_class in classes}

    sessions = (
        SchoolSession.objects
        .filter(
            class_subject__in=scope.class_subjects(year).filter(
                school_class__in=[c.pk for c in classes]
            )
        )
        .select_related(*SESSION_RELATED)
        .order_by("date", "session_number")
    )

    for session in sessions:
        class_subject = session.class_subject
        sessions_by_class[class_subject.school_class_id].append({
            "date": session.date,
            "subject_name": class_subject.subject.name,
            "teacher_name": teacher_display_name(class_subject),
            "content_summary": _content_summary(session, limit=50),
        })

    grades = OrderedDict()

    for school_class in classes:
        entry = grades.setdefault(
            school_class.grade_id,
            {"grade_name": school_class.grade.name, "classes": []},
        )
        entry["classes"].append({
            "class_name": school_class.section,
            "sessions": sessions_by_class[school_class.pk],
        })

    return {
        "academic_year": year.title,
        "report_date": jdatetime.datetime.now().strftime("%Y/%m/%d"),
        "grades_data": list(grades.values()),
    }
