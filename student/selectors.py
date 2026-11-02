"""
Which enrolment a page is about. A student keeps one row per academic year,
so a page must never take "the" enrolment with ``.get()`` or ``[0]``.
"""

from .models.student_enrollment import StudentEnrollment


def current_enrollment(student_profile):
    """
    The enrolment that decides what a student receives right now (online
    classes, announcements), or ``None``: someone who left or hasn't
    re-enrolled receives nothing.
    """

    return (
        StudentEnrollment.objects.current()
        .filter(student=student_profile)
        .select_related("school_class__grade", "school_class__branch", "school_class__year")
        .first()
    )


def panel_enrollment(student_profile):
    """
    The enrolment the student's own pages (timetable, homework, sessions)
    show: the newest year's, in any status, or ``None`` when there is none.
    """

    return (
        student_profile.enrollments
        .select_related("school_class__year", "student__user")
        .order_by("-academic_year__start_date", "-pk")
        .first()
    )
