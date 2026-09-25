from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from teaching.models.school_session import SchoolSession
from student.models.student_profile import StudentProfile
from student.models.student_enrollment import StudentEnrollment
from .models import Attendance

def manage_attendance(request, session_id):
    # دریافت جلسه مربوطه
    session = get_object_or_404(SchoolSession, pk=session_id)

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
        return redirect('teaching:session_list', session.class_subject.id)  # نام روت بعدی خود را وارد کنید

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
