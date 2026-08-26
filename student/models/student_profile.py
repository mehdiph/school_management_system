from django.conf import settings
from django.db import models


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        limit_choices_to={"role": "student"},
        verbose_name="کاربر",
    )

    student_code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="کد دانش‌آموزی",
    )

    class Meta:
        verbose_name = "پروفایل دانش‌آموز"
        verbose_name_plural = "پروفایل دانش‌آموزان"
        ordering = [
            "user__last_name",
            "user__first_name",
        ]

    def __str__(self):
        return f"{self.student_code} - {self.user.get_full_name()}"