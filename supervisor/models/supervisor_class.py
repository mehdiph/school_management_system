from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class SupervisorClass(models.Model):
    supervisor = models.ForeignKey(
        'supervisor.SupervisorProfile',
        on_delete=models.CASCADE,
        related_name="class_assignments",
        verbose_name="پشتیبان",
    )

    school_class = models.ForeignKey(
        "school.SchoolClass",
        on_delete=models.CASCADE,
        related_name="supervisor_assignments",
        verbose_name="کلاس",
    )

    class Meta:
        verbose_name = "کلاس تحت نظارت"
        verbose_name_plural = "کلاس‌های تحت نظارت"

        constraints = [
            models.UniqueConstraint(
                fields=["supervisor", "school_class"],
                name="unique_supervisor_school_class",
            ),
        ]

    def clean(self):
        if self.school_class.grade_id != self.supervisor.grade_id:
            raise ValidationError(
                "پشتیبان فقط می‌تواند کلاس‌های مربوط به پایه خودش را تحت نظارت داشته باشد."
            )

    def __str__(self):
        return f"{self.supervisor} → {self.school_class}"