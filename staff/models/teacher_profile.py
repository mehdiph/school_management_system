from django.db import models
from django_jalali.db import models as jmodels
    

class TeacherProfile(models.Model):

    staff = models.OneToOneField(
        "staff.Staff",
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        limit_choices_to={"user__role": "teacher"},
        verbose_name="پرسنل",
    )

    education = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="مدرک تحصیلی",
    )

    field_of_study = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="رشته تحصیلی",
    )

    teaching_experience = models.PositiveIntegerField(
        default=0,
        verbose_name="سابقه تدریس (سال)",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
    )

    updated_at = jmodels.jDateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "پروفایل معلم"
        verbose_name_plural = "پروفایل معلمان"
        ordering = [
            "staff__user__last_name",
            "staff__user__first_name",
        ]

    def __str__(self):
        return (
            f"{self.staff.user.get_full_name()}"
        )