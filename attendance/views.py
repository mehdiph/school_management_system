from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from teaching.models.school_session import SchoolSession
from student.models.student_profile import StudentProfile
from .models import Attendance

def manage_attendance(request, session_id):
    # دریافت جلسه مربوطه
    session = get_object_or_404(SchoolSession, pk=session_id)
    
    # دریافت لیست دانش‌آموزان (می‌توانید بر اساس کلاس مربوط به جلسه فیلتر کنید)
    students = StudentProfile.objects.filter(school_class=session.class_subject.school_class)

    if request.method == 'POST':
        for student in students:
            # دریافت وضعیت مربوط به هر دانش‌آموز از روی ID او
            status_value = request.POST.get(f'status-{student.id}')
            if status_value in Attendance.AttendanceStatus.values:
                print("hello")
                # استفاده از update_or_create برای ثبت جدید یا به‌روزرسانی رکورد قبلی
                Attendance.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={'status': status_value}
                )
        
        messages.success(request, "حضور و غیاب با موفقیت ثبت شد.")
        return redirect('teaching:session_list', session.class_subject.id)  # نام روت بعدی خود را وارد کنید

    # در درخواست GET: دریافت وضعیت‌های ثبت‌شده قبلی برای این جلسه
    existing_attendances = Attendance.objects.filter(session=session).values('student_id', 'status')
    print(existing_attendances)
    # تبدیل داده‌ها به یک دیکشنری برای دسترسی سریع در قالب {student_id: status}
    attendance_dict = {item['student_id']: item['status'] for item in existing_attendances}

    # افزودن وضعیت فعلی به شیء دانش‌آموز جهت استفاده آسان در تمپلیت
    for student in students:
        # اگر قبلاً ثبت نشده باشد، به صورت پیش‌فرض 'present' در نظر گرفته می‌شود
        student.current_status = attendance_dict.get(student.id, 'present')

    context = {
        'session': session,
        'students': students,
        'class_subject': session.class_subject
    }
    return render(request, 'attendance/attendance_management.html', context)