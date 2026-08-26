from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels
from core.managers.student import StudentEnrollmentManager


class StudentEnrollment(models.Model):

    objects = StudentEnrollmentManager()
    class EnrollmentStatus(models.TextChoices):
        ACTIVE = "active", "فعال"
        TRANSFERRED = "transferred", "منتقل شده"
        GRADUATED = "graduated", "فارغ‌التحصیل"
        WITHDRAWN = "withdrawn", "انصراف"

    student = models.ForeignKey(
        "student.StudentProfile",
        on_delete=models.PROTECT,
        related_name="enrollments",
        verbose_name="دانش‌آموز",
    )

    academic_year = models.ForeignKey(
        "school.AcademicYear",
        on_delete=models.PROTECT,
        related_name="student_enrollments",
        editable=False,
        verbose_name="سال تحصیلی",
    )

    school_class = models.ForeignKey(
        "school.SchoolClass",
        on_delete=models.PROTECT,
        related_name="student_enrollments",
        verbose_name="کلاس",
    )

    enrollment_date = jmodels.jDateField(
        verbose_name="تاریخ ثبت‌نام",
    )

    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
        verbose_name="وضعیت",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "ثبت‌نام دانش‌آموز"
        verbose_name_plural = "ثبت‌نام دانش‌آموزان"

        ordering = [
            "-academic_year__start_date",
            "student__user__last_name",
            "student__user__first_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                name="unique_student_per_academic_year",
            )
        ]

    def save(self, *args, **kwargs):
        self.academic_year = self.school_class.year
        self.full_clean()
        super().save(*args, **kwargs)


    def __str__(self):
        return (
            f"{self.student.user.get_full_name()}"
        )