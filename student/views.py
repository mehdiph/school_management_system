from django.db.models import Count, F, Q
from django.shortcuts import render
from teaching.models.school_session import SchoolSession
from teaching.models.session_content import SessionContent
from school.models.class_subject import ClassSubject
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse
from .templatetags import persian_filters
from .decorators import student_required
from .services import get_classes_for_day

# Create your views here.

@student_required
def student_dashboard(request):
    student = request.user.student_profile.enrollments.all()[0]
    print(f"student: {student}")
    school_class = student.school_class
    today_classes = get_classes_for_day(school_class, timezone.localdate())
    tomorrow_classes = get_classes_for_day(school_class, timezone.localdate() + timedelta(days=1))
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



@student_required
def sessions_list(request):
    # print(type(request.user.student_profile.enrollments.all()[0]))
    # print(hasattr(request.user.student_profile.enrollments.all()[0], 'school_class'))
    school_class = request.user.student_profile.enrollments.get().school_class
    class_subject_query = ClassSubject.objects\
        .filter(school_class=school_class)\
        .annotate(session_count=Count(
            'sessions', filter=~Q(sessions__status=SchoolSession.Status.HOLIDAY)
        ))\
        .prefetch_related('sessions', 'sessions__session_contents')

    context = {
        'class_subjects': class_subject_query,
    }
    return render(request, 'student/session_list.html', context)


def _session_json(session):
    """
    One session for the student's timeline. A holiday (closed by the
    academic calendar) has no number, the event as its reason, and is
    flagged so the page can show it apart; it is never counted.
    """

    content = getattr(session, 'session_contents', None)
    bell = f' · {session.bell.title}' if session.bell_id else ''
    date = persian_filters.persian_date(session.date)

    if session.is_holiday:
        reason = session.calendar_event.title if session.calendar_event_id else ''
        return {
            'id': session.id,
            'label': f'تعطیل - {date}{bell}',
            'title': f'تعطیل: {reason}' if reason else 'تعطیل',
            'content': 'این زنگ تعطیل بوده است و جزو جلسات شمرده نمی‌شود.',
            'is_holiday': True,
            'reason': reason,
        }

    return {
        'id': session.id,
        'label': f'جلسه {persian_filters.persian_ordinal(session.session_number)} - {date}{bell}',
        # older sessions may have no content yet
        'title': content.title if content else 'بدون عنوان',
        'content': content.content if content else '',
        'is_holiday': False,
        'reason': '',
    }


@student_required
def session_list_json(request, subject):
    school_class = request.user.student_profile.enrollments.get().school_class

    class_subject = (
        ClassSubject.objects
        .filter(
            school_class=school_class,
            subject__slug=subject
        )
        .select_related('subject')
        .get()
    )

    sessions = (
        class_subject.sessions
        .select_related('session_contents', 'bell', 'calendar_event')
        .order_by('-date', F('bell__order').desc(nulls_last=True), '-session_number')
    )

    data = [_session_json(session) for session in sessions]

    return JsonResponse({
        'subject': str(class_subject.subject),
        'sessions': data,
    })