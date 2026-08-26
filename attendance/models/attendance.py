from django.db import models
from django_jalali.db import models as jmodels
from django.core.exceptions import ValidationError
from teaching.models.school_session import SchoolSession
from student.models.student_enrollment import StudentEnrollment
from core.managers.teaching import AttendanceManager


class Attendance(models.Model):

    objects = AttendanceManager()
    class AttendanceStatus(models.TextChoices):
        PRESENT = "present", "حاضر"
        ABSENT = "absent", "غایب"
        LATE = "late", "تاخیر"

    session = models.ForeignKey(
        SchoolSession,
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="جلسه",
    )

    student_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.PROTECT,
        related_name="attendances",
        verbose_name="ثبت‌نام دانش‌آموز",
    )

    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
        verbose_name="وضعیت",
    )

    description = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت",
    )

    class Meta:
        verbose_name = "حضور و غیاب"
        verbose_name_plural = "حضور و غیاب"

        ordering = [
            "-session__date",
            "student_enrollment__student__user__last_name",
            "student_enrollment__student__user__first_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["session", "student_enrollment"],
                name="unique_attendance_per_session",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.session
            and self.student_enrollment
            and self.student_enrollment.school_class
            != self.session.class_subject.school_class
        ):
            raise ValidationError({
                "student_enrollment":
                    "دانش‌آموز عضو کلاس این جلسه نیست."
            })
        
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.student_enrollment.student.user.get_full_name()} | "
            f"{self.session} | "
            f"{self.get_status_display()}"
        )