from django.db import models
from teaching.models.school_session import SchoolSession
from student.models.student_profile import StudentProfile


class Attendance(models.Model):
    class AttendanceStatus(models.TextChoices):
        PRESENT = 'present', 'حاضر'
        ABSENT = 'absent', 'غایب'
        LATE = 'late', 'تاخیر'

    session = models.ForeignKey(
        SchoolSession,
        on_delete=models.CASCADE,
        verbose_name='جلسه',
        related_name='attendances'
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        verbose_name='دانش آموز'
    )

    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
        verbose_name='وضعیت'
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'حضور و غیاب'
        verbose_name_plural = 'حضور و  غیاب'
        unique_together = [
            ('student', 'session')
        ]