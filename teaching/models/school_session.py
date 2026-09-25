from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels
from core.managers.teaching import SchoolSessionManager


class SchoolSession(models.Model):

    objects = SchoolSessionManager()
    class Status(models.TextChoices):
        COMPENSATORY = "JB", "جبرانی"
        CANCELED = "CD", "کنسل شده"
        HELD = "HD", "برگزار شده"

    class_subject = models.ForeignKey(
        "school.ClassSubject",
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name="درس کلاس",
    )

    date = jmodels.jDateField(
        verbose_name="تاریخ جلسه",
    )

    session_number = models.PositiveIntegerField(
        editable=False,
        verbose_name="شماره جلسه",
    )

    status = models.CharField(
        max_length=2,
        choices=Status.choices,
        default=Status.HELD,
        verbose_name="وضعیت",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "جلسه درسی"
        verbose_name_plural = "جلسات درسی"

        ordering = [
            "-date",
            "-session_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["class_subject", "session_number"],
                name="unique_session_number_per_class_subject",
            )
        ]

    def clean(self):
        super().clean()

        # Both may be missing when a form failed to validate them; that is
        # reported on the fields themselves, there is nothing to compare.
        if self.class_subject_id and self.date:
            if self.date < self.class_subject.start_date:
                raise ValidationError({
                    "date": "تاریخ جلسه قبل از تاریخ شروع درس است."
                })

            if self.date > self.class_subject.end_date:
                raise ValidationError({
                    "date": "تاریخ جلسه بعد از تاریخ پایان درس است."
                })

            if self.session_number:
                previous_session = (
                    SchoolSession.objects.filter(
                        class_subject=self.class_subject,
                        session_number=self.session_number - 1,
                    )
                    .exclude(pk=self.pk)
                    .first()
                )
            else:
                previous_session = None

            if previous_session and self.date < previous_session.date:
                raise ValidationError({
                    "date": (
                        f"تاریخ این جلسه نباید قبل از "
                        f"جلسه {previous_session.session_number} باشد."
                    )
                })
            
            if self.session_number:

                next_session = (
                    SchoolSession.objects.filter(
                        class_subject=self.class_subject,
                        session_number=self.session_number + 1,
                    )
                    .exclude(pk=self.pk)
                    .first()
                )
            else:
                next_session = None

            if next_session and self.date > next_session.date:
                raise ValidationError({
                    "date": (
                        f"تاریخ این جلسه نباید بعد از "
                        f"جلسه {next_session.session_number} باشد."
                    )
                })

    def save(self, *args, **kwargs):
        if self._state.adding and not self.session_number:
            last_session = (
                SchoolSession.objects.filter(
                    class_subject=self.class_subject
                )
                .order_by("-session_number")
                .first()
            )

            self.session_number = (
                1 if last_session is None
                else last_session.session_number + 1
            )

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.class_subject} - جلسه {self.session_number}"