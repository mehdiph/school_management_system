from django.shortcuts import render
from teaching.models.session_content import SessionContent
from scheduling.models.class_schedule import ClassSchedule
from school.models.class_subject import ClassSubject
from scheduling.utils import get_today_schedule_day
from datetime import date
from django.http import JsonResponse
from .templatetags import persian_filters

# Create your views here.

def student_dashboard(request):
    student = request.user.student_profile
    school_class = student.school_class
    

    homeworks = (
        SessionContent.objects
        .filter(
            session__class_subject__school_class=school_class
        )
        .exclude(homework='')
        .select_related(
            'session',
            'session__class_subject',
            'session__class_subject__subject'
        )
        .order_by('-session__date')[:5]
    )

    today_classes = ClassSchedule.objects.filter(
        class_room__school_class=school_class,
        day_of_week=get_today_schedule_day(date.today())
    ).select_related(
        'class_room',
        'class_room__subject',
        'class_room__teacher'
    ).order_by(
        'start_time'
    )
    
    context = {
        'today_classes': today_classes,
        'homeworks': homeworks,
        'student': student, 
        'school_class': school_class
    }

    return render(request, 'student/dashboard.html', context)



def sessions_list(request, subject):
    school_class = request.user.student_profile.school_class
    class_subject_query = ClassSubject.objects\
        .filter(school_class=school_class)\
        .prefetch_related('sessions', 'sessions__session_contents')

    context = {
        'class_subjects': class_subject_query,
    }
    return render(request, 'student/session_list.html', context)


def session_list_json(request, subject):
    school_class = request.user.student_profile.school_class
    class_subject_query = ClassSubject.objects\
        .filter(school_class=school_class)\
        .prefetch_related('sessions', 'sessions__session_contents')

    lesson_class_subjects = class_subject_query.get(subject__slug=subject)

    sessions = lesson_class_subjects.sessions.all()

    data = [
        {
            'id': session.id,
            'label': f'جلسه {persian_filters.persian_ordinal(session.session_number)} - {persian_filters.persian_date(session.date)}',
            # Add extra raw fields if you ever need them
            'title': session.session_contents.title,
            'content': session.session_contents.content
        }
        for session in sessions
    ]
    return JsonResponse({'sessions': data})