from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from teaching.models.school_session import SchoolSession
from student.models.student_profile import StudentProfile
from student.models.student_enrollment import StudentEnrollment
from accounts.utils import role_dashboard
from .models import Attendance
from .permissions import can_manage_attendance, is_session_teacher


@login_required
def manage_attendance(request, session_id):
    # دریافت جلسه مربوطه
    session = get_object_or_404(
        SchoolSession.objects.select_related(
            'class_subject__school_class',
            'class_subject__teacher_assignment',
        ),
        pk=session_id,
    )
    # Same answer as for a session that does not exist, like the teacher's
    # own session pages: nobody learns which session ids are in use.
    if not can_manage_attendance(request.user, session, request=request):
        raise Http404

    if session.is_holiday:
        reason = session.calendar_event.title if session.calendar_event_id else 'تعطیلی'
        messages.error(request, f'این جلسه به‌دلیل «{reason}» لغو شده است و حضور و غیاب ندارد.')
        if is_session_teacher(request.user, session):
            return redirect('teaching:session_list', session.class_subject_id)
        return redirect(role_dashboard(request.user))

    # دریافت لیست دانش‌آموزان کلاس جلسه (مرتب بر اساس نام خانوادگی، طبق Meta.ordering)
    students = (
        StudentEnrollment.objects
        .filter(school_class=session.class_subject.school_class)
        .select_related('student__user')
    )

    if request.method == 'POST':
        for student in students:
            # دریافت وضعیت مربوط به هر دانش‌آموز از روی ID او
            status_value = request.POST.get(f'status-{student.id}')
            if status_value in Attendance.AttendanceStatus.values:
                defaults = {'status': status_value}
                # توضیح هر دانش‌آموز فقط وقتی فیلدش ارسال شده باشد به‌روز می‌شود،
                # تا فرمی بدون این فیلد توضیح قبلی را پاک نکند
                description = request.POST.get(f'description-{student.id}')
                if description is not None:
                    defaults['description'] = description.strip()
                # استفاده از update_or_create برای ثبت جدید یا به‌روزرسانی رکورد قبلی
                Attendance.objects.update_or_create(
                    session=session,
                    student_enrollment=student,
                    defaults=defaults
                )

        messages.success(request, "حضور و غیاب با موفقیت ثبت شد.")
        if is_session_teacher(request.user, session):
            return redirect('teaching:session_list', session.class_subject.id)
        # supervisors and admins have no teacher session list: stay here
        return redirect('attendance:attendance_form', session.id)

    # در درخواست GET: دریافت وضعیت‌های ثبت‌شده قبلی برای این جلسه
    existing_attendances = Attendance.objects.filter(session=session).values('student_enrollment', 'status', 'description')
    # تبدیل داده‌ها به یک دیکشنری برای دسترسی سریع در قالب {student_id: {status, description}}
    attendance_dict = {item['student_enrollment']: item for item in existing_attendances}

    # افزودن وضعیت فعلی به شیء دانش‌آموز جهت استفاده آسان در تمپلیت
    for student in students:
        existing = attendance_dict.get(student.id, {})
        # اگر قبلاً ثبت نشده باشد، به صورت پیش‌فرض 'present' در نظر گرفته می‌شود
        student.current_status = existing.get('status', 'present')
        student.current_description = existing.get('description', '')

    context = {
        'session': session,
        'students': students,
        'class_subject': session.class_subject
    }
    return render(request, 'attendance/attendance_management.html', context)
