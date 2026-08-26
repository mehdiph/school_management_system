from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels

from .bell import Bell


class ClassSchedule(models.Model):

    class DayChoices(models.IntegerChoices):
        SATURDAY = 0, "شنبه"
        SUNDAY = 1, "یکشنبه"
        MONDAY = 2, "دوشنبه"
        TUESDAY = 3, "سه‌شنبه"
        WEDNESDAY = 4, "چهارشنبه"
        THURSDAY = 5, "پنج‌شنبه"

    class WeekTypeChoices(models.IntegerChoices):
        WEEK_ONE = 1, "هفته اول"
        WEEK_TWO = 2, "هفته دوم"
        BOTH = 3, "هر دو هفته"

    class_subject = models.ForeignKey(
        "school.ClassSubject",
        on_delete=models.PROTECT,
        related_name="schedules",
        verbose_name="درس کلاس",
    )

    day_of_week = models.IntegerField(
        choices=DayChoices.choices,
        verbose_name="روز هفته",
    )

    week_type = models.IntegerField(
        choices=WeekTypeChoices.choices,
        default=WeekTypeChoices.BOTH,
        verbose_name="نوع هفته",
    )

    bell = models.ForeignKey(
        Bell,
        on_delete=models.PROTECT,
        related_name="class_schedules",
        verbose_name="زنگ",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "برنامه کلاسی"
        verbose_name_plural = "برنامه‌های کلاسی"

        ordering = [
            "day_of_week",
            "bell__order",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "class_subject",
                    "day_of_week",
                    "week_type",
                    "bell",
                ],
                name="unique_class_schedule_slot",
            )
        ]

    def clean(self):
        super().clean()

        if not self.class_subject_id or not self.bell_id:
            return

        if self.bell.start_time >= self.bell.end_time:
            raise ValidationError({
                "bell": "زمان پایان زنگ باید بعد از زمان شروع باشد."
            })

        if self.week_type == self.WeekTypeChoices.BOTH:
            applicable_weeks = [
                self.WeekTypeChoices.WEEK_ONE,
                self.WeekTypeChoices.WEEK_TWO,
                self.WeekTypeChoices.BOTH,
            ]
        elif self.week_type == self.WeekTypeChoices.WEEK_ONE:
            applicable_weeks = [
                self.WeekTypeChoices.WEEK_ONE,
                self.WeekTypeChoices.BOTH,
            ]
        else:
            applicable_weeks = [
                self.WeekTypeChoices.WEEK_TWO,
                self.WeekTypeChoices.BOTH,
            ]

        teacher_assignment = self.class_subject.teacher_assignment
        school_class = self.class_subject.school_class

        # ---------- Teacher Conflict ----------

        teacher_conflict = ClassSchedule.objects.filter(
            class_subject__teacher_assignment=teacher_assignment,
            day_of_week=self.day_of_week,
            week_type__in=applicable_weeks,
            bell=self.bell,
        )

        if self.pk:
            teacher_conflict = teacher_conflict.exclude(pk=self.pk)

        if teacher_conflict.exists():
            raise ValidationError({
                "bell": "این معلم در این زنگ کلاس دیگری دارد."
            })

        # ---------- Class Conflict ----------

        class_conflict = ClassSchedule.objects.filter(
            class_subject__school_class=school_class,
            day_of_week=self.day_of_week,
            week_type__in=applicable_weeks,
            bell=self.bell,
        )

        if self.pk:
            class_conflict = class_conflict.exclude(pk=self.pk)

        if class_conflict.exists():
            raise ValidationError({
                "bell": "برای این کلاس در این زنگ، درس دیگری ثبت شده است."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.class_subject.school_class} | "
            f"{self.class_subject.subject.name} | "
            f"{self.get_day_of_week_display()} | "
            f"{self.bell}"
        )