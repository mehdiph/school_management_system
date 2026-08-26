from django.shortcuts import render
from teaching.models.session_content import SessionContent
from school.models.class_subject import ClassSubject
from datetime import date, timedelta
from django.http import JsonResponse
from .templatetags import persian_filters
from .services import get_classes_for_day

# Create your views here.

def student_dashboard(request):
    student = request.user.student_profile.enrollments.all()[0]
    print(f"student: {student}")
    school_class = student.school_class
    today_classes = get_classes_for_day(school_class, date.today())
    tomorrow_classes = get_classes_for_day(school_class, date.today() + timedelta(days=1))
    homework_queryset = (
        SessionContent.objects
        .filter(session__class_subject__school_class=school_class)
        .exclude(homework='')
        .select_related('session', 'session__class_subject', 'session__class_subject__subject')
        .order_by('-session__date')[:5]
    )

    print(today_classes)

    context = {
        'today_classes': today_classes,
        'tomorrow_classes': tomorrow_classes,
        'homeworks': homework_queryset,
        'student': student, 
        'school_class': school_class
    }

    return render(request, 'student/dashboard.html', context)



def sessions_list(request):
    # print(type(request.user.student_profile.enrollments.all()[0]))
    # print(hasattr(request.user.student_profile.enrollments.all()[0], 'school_class'))
    school_class = request.user.student_profile.enrollments.get().school_class
    class_subject_query = ClassSubject.objects\
        .filter(school_class=school_class)\
        .prefetch_related('sessions', 'sessions__session_contents')

    context = {
        'class_subjects': class_subject_query,
    }
    return render(request, 'student/session_list.html', context)


def session_list_json(request, subject):
    school_class = request.user.student_profile.enrollments.get().school_class

    class_subject = (
        ClassSubject.objects
        .filter(
            school_class=school_class,
            subject__slug=subject
        )
        .select_related('subject')
        .prefetch_related(
            'sessions',
            'sessions__session_contents'
        )
        .get()
    )

    sessions = class_subject.sessions.all()

    data = [
        {
            'id': session.id,
            'label': (
                f'جلسه '
                f'{persian_filters.persian_ordinal(session.session_number)}'
                f' - '
                f'{persian_filters.persian_date(session.date)}'
            ),
            'title': session.session_contents.title,
            'content': session.session_contents.content,
        }
        for session in sessions
    ]

    return JsonResponse({
        'subject': str(class_subject.subject),
        'sessions': data,
    })