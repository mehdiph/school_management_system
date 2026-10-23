from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe

from academic_calendar.services import parse_jalali_date, to_gregorian, to_jalali
from accounts.utils import role_dashboard
from school.models import SchoolClass
from supervisor.models import SupervisorProfile
from teaching.models.school_session import SchoolSession

from . import services
from .models import DailyAttendance, DailyAttendanceSheet, SessionAttendance
from .permissions import (
    can_record_daily_attendance,
    can_view_session_attendance,
    is_class_supervisor,
    is_session_teacher,
)


def daily_sheet_url(school_class, day):
    """The daily sheet page of ``school_class`` on ``day``."""

    query = urlencode({'date': to_jalali(day).strftime('%Y/%m/%d')})
    return f"{reverse('attendance:daily_sheet', args=[school_class.pk])}?{query}"


@require_safe
@login_required
def session_attendance(request, session_id):
    """
    The archived attendance of one session (read-only). Per-session
    attendance ended on ``settings.ATTENDANCE_DAILY_START_DATE``: for a
    session from that day on, the session's teacher gets 403 and a
    supervisor or admin is sent to the class's daily sheet of that day.
    """

    session = get_object_or_404(
        SchoolSession.objects.select_related(
            'class_subject__school_class__grade',
            'class_subject__subject',
            'class_subject__teacher_assignment',
            'calendar_event',
        ),
        pk=session_id,
    )
    # Same answer as for a session that does not exist, like the teacher's
    # own session pages: nobody learns which session ids are in use.
    if not can_view_session_attendance(request.user, session, request=request):
        raise Http404

    school_class = session.class_subject.school_class
    if services.is_daily(session.date):
        if not can_record_daily_attendance(request.user, school_class, request=request):
            raise PermissionDenied
        return redirect(daily_sheet_url(school_class, session.date))

    if session.is_holiday:
        reason = session.calendar_event.title if session.calendar_event_id else 'تعطیلی'
        messages.error(request, f'این جلسه به‌دلیل «{reason}» لغو شده است و حضور و غیاب ندارد.')
        if is_session_teacher(request.user, session):
            return redirect('teaching:session_list', session.class_subject_id)
        return redirect(role_dashboard(request.user))

    records = (
        SessionAttendance.objects.filter(session=session)
        .select_related('student_enrollment__student__user')
        .order_by(
            'student_enrollment__student__user__last_name',
            'student_enrollment__student__user__first_name',
        )
    )
    return render(request, 'attendance/session_attendance.html', {
        'session': session,
        'class_subject': session.class_subject,
        'records': records,
        'counts': records.status_counts(),
        'daily_start': services.daily_start(),
        'is_teacher': is_session_teacher(request.user, session),
    })


def _requested_day(request):
    """``?date=`` (Jalali) as a Gregorian date; today when missing or invalid."""

    value = request.GET.get('date')
    if value:
        try:
            return to_gregorian(parse_jalali_date(value))
        except ValueError:
            messages.error(request, 'تاریخ واردشده معتبر نیست؛ حضور و غیاب امروز نمایش داده شد.')
    return timezone.localdate()


def _posted_entries(request, enrollments):
    """``{enrollment id: (status or None, description or None)}`` from the form."""

    entries = {}
    for enrollment in enrollments:
        status = request.POST.get(f'status-{enrollment.pk}')
        description = request.POST.get(f'description-{enrollment.pk}')
        entries[enrollment.pk] = (
            status if status in DailyAttendance.Status.values else None,
            # a form without this field must not wipe the description
            description.strip() if description is not None else None,
        )
    return entries


@login_required
def daily_sheet(request, class_id):
    """
    Take or edit the daily attendance of a class (``?date=``, default
    today). Everyone starts «حاضر»; the supporter marks the exceptions.
    The class's supporter, a superuser or a staff admin of its branch with
    ``attendance.change_dailyattendancesheet``; anyone else gets 403.
    """

    school_class = get_object_or_404(
        SchoolClass.objects.select_related('grade', 'branch', 'year'), pk=class_id,
    )
    if not can_record_daily_attendance(request.user, school_class, request=request):
        raise PermissionDenied

    try:
        # the supervisor sidebar shows the supervisor's grade
        request.supervisor = request.user.supervisor_profile
    except SupervisorProfile.DoesNotExist:
        pass

    day = _requested_day(request)
    sheet = (
        DailyAttendanceSheet.objects.filter(school_class=school_class, date=to_jalali(day))
        .select_related('taken_by')
        .first()
    )
    # A sheet that exists stays editable; a new one must be for a day the
    # class has lessons (services.day_error).
    error = None if sheet is not None else services.day_error(school_class, day)
    enrollments = list(services.sheet_enrollments(school_class, sheet))
    is_supervisor = is_class_supervisor(request.user, school_class)

    if request.method == 'POST':
        if error is None:
            sheet, created = services.save_daily_sheet(
                school_class, day, request.user, _posted_entries(request, enrollments),
            )
            messages.success(
                request,
                'حضور و غیاب روزانه ثبت شد.' if created else 'تغییرات حضور و غیاب روزانه ذخیره شد.',
            )
            if is_supervisor:
                query = urlencode({'date': to_jalali(day).strftime('%Y/%m/%d'), 'class': school_class.pk})
                return redirect(f"{reverse('supervisor:attendance')}?{query}")
            return redirect(daily_sheet_url(school_class, day))
        messages.error(request, error)

    records = {}
    if sheet is not None:
        records = {
            record.student_enrollment_id: record
            for record in sheet.records.select_related('updated_by')
        }
    students = []
    for enrollment in enrollments:
        record = records.get(enrollment.pk)
        students.append({
            'enrollment': enrollment,
            'name': enrollment.student.user.get_full_name() or enrollment.student.user.username,
            'record': record,
            'status': record.status if record else DailyAttendance.Status.PRESENT,
            'description': record.description if record else '',
        })

    return render(request, 'attendance/daily_sheet.html', {
        'school_class': school_class,
        'day': to_jalali(day),
        'today': to_jalali(timezone.localdate()),
        'sheet': sheet,
        'students': students,
        'statuses': DailyAttendance.Status.choices,
        'error': error,
        'is_supervisor': is_supervisor,
    })
