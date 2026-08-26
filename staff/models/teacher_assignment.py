from django.db import models
from django_jalali.db import models as jmodels
from core.managers.teaching import TeacherAssignmentManager


class TeacherAssignment(models.Model):

    objects = TeacherAssignmentManager()
    class AssignmentStatus(models.TextChoices):
        ACTIVE = "active", "فعال"
        TRANSFERRED = "transferred", "منتقل شده"
        TERMINATED = "terminated", "پایان همکاری"
        LEAVE = "leave", "مرخصی"

    teacher = models.ForeignKey(
        "staff.TeacherProfile",
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="معلم",
    )

    branch = models.ForeignKey(
        "school.Branch",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
        verbose_name="شعبه",
    )

    academic_year = models.ForeignKey(
        "school.AcademicYear",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
        verbose_name="سال تحصیلی",
    )

    hire_date = jmodels.jDateField(
        verbose_name="تاریخ شروع همکاری",
    )

    end_date = jmodels.jDateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پایان همکاری",
    )

    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        verbose_name="وضعیت",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "انتساب معلم"
        verbose_name_plural = "انتساب معلمان"

        ordering = [
            "-academic_year__start_date",
            "teacher__staff__user__last_name",
            "teacher__staff__user__first_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "teacher",
                    "branch",
                    "academic_year",
                ],
                name="unique_teacher_branch_year",
            )
        ]

    def __str__(self):
        return (
            f"{self.teacher.staff.user.get_full_name()} | "
            f"{self.branch.name} | "
            f"{self.academic_year.title}"
        )