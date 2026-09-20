from django.conf import settings
from django.db import models


class SupervisorProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervisor_profile",
        verbose_name="کاربر",
    )

    branch = models.ForeignKey(
        "school.Branch",
        on_delete=models.PROTECT,
        related_name="supervisors",
        verbose_name="شعبه",
        null=True
    )

    grade = models.ForeignKey(
        "school.Grade",
        on_delete=models.PROTECT,
        related_name="supervisors",
        verbose_name="پایه",
    )

    class Meta:
        verbose_name = "پروفایل پشتیبان"
        verbose_name_plural = "پروفایل‌های پشتیبان"

    def __str__(self):
        return f"{self.user} - {self.branch} - {self.grade}"