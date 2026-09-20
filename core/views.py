from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch
from datetime import date

from school.models import AcademicYear, ClassSubject
from teaching.models import SchoolSession
from scheduling.models.class_schedule import ClassSchedule

from scheduling.utils import (
    get_current_week_type,
    get_today_schedule_day
)


@login_required
def dashboard(request):
    """
    Dashboard view for teacher.
    """

    teacher_profile = request.user.staff_profile.teacher_profile

    # -----------------------------
    # Current academic year
    # -----------------------------

    current_year = (
        AcademicYear.objects
        .filter(is_current=True)
        .first()
    )


    academic_year_title = (
        current_year.title
        if current_year
        else "تعریف نشده"
    )


    # -----------------------------
    # Teacher classes
    # -----------------------------

    print(request.branch)

    class_subjects_query = (
        ClassSubject.objects
        .for_teacher(teacher_profile)
        .filter(
            is_active=True,
            school_class__is_active=True,
            school_class__year=current_year,
        )
        .select_related(
            'school_class',
            'school_class__grade',
            'subject',
        )
        .prefetch_related(
            Prefetch(
                'schedules',
                queryset=ClassSchedule.objects.select_related('bell'),
            )
        )
        .order_by(
            'school_class__grade__level',
            'subject__name',
            'school_class__section'
        )
    )

    print(class_subjects_query)
    week_type = get_current_week_type(
        date.today()
    )

    today_day = get_today_schedule_day(
        date.today()
    )


    if current_year:

        class_subjects_query = (
            class_subjects_query
            .filter(
                schedules__day_of_week=today_day
            )
            .filter(
                Q(
                    schedules__week_type=week_type
                )
                |
                Q(
                    schedules__week_type=
                    ClassSchedule.WeekTypeChoices.BOTH
                )
            )
            .distinct()
        )

        # print(class_subjects_query)

    today_class_subjects = []

    class_subjects_summary = []


    for cs in class_subjects_query:


        class_name = (
            f"{cs.school_class.grade.name} - "
            f"{cs.school_class.section} - "
            f"{cs.school_class.branch}"
        )


        subject_name = cs.subject.name

        today_bell_order = None

        for schedule in cs.schedules.all():
            if schedule.day_of_week == today_day and schedule.week_type in (
                week_type,
                ClassSchedule.WeekTypeChoices.BOTH,
            ):
                today_bell_order = schedule.bell.order
                break


        class_subjects_summary.append(
            {
                "class_name": class_name,
                "subject_name": subject_name,
                "grade_name": cs.school_class.grade.name,
                "id": cs.id,
            }
        )


        last_session = (
            SchoolSession.objects
            .filter(
                class_subject=cs
            )
            .order_by(
                "-session_number"
            )
            .first()
        )


        last_session_num = 0
        last_summary = ""


        if last_session:

            last_session_num = (
                last_session.session_number
            )

            content = (
                getattr(
                    last_session,
                    "session_contents",
                    None
                )
            )

            if content:
                last_summary = content.content



        today_class_subjects.append(
            {
                "id": cs.id,
                "class_name": class_name,
                "subject_name": subject_name,
                "last_session_number": last_session_num,
                "last_session_summary": last_summary,
                "bell_order": today_bell_order,
            }
        )

    today_class_subjects.sort(
        key=lambda item: (
            item["bell_order"] is None,
            item["bell_order"],
        )
    )



    # -----------------------------
    # Recent sessions
    # -----------------------------

    recent_sessions = (
        SchoolSession.objects
        .filter(class_subject__teacher_assignment__teacher=teacher_profile)
        .select_related(
            'class_subject',
            'class_subject__subject',
            'class_subject__school_class'
        )
        .order_by(
            '-date',
            '-created_at'
        )[:5]
    )


    # -----------------------------
    # Statistics
    # -----------------------------

    total_sessions = (
        SchoolSession.objects
        .filter(
            class_subject__teacher_assignment__teacher=
            teacher_profile
        )
        .count()
    )


    context = {
        "academic_year": academic_year_title,
        "today_class_subjects":today_class_subjects[:6],
        "class_subjects_summary":class_subjects_summary,
        "recent_sessions":recent_sessions,
        "total_sessions":total_sessions,
    }


    return render(
        request,
        "core/dashboard.html",
        context
    )