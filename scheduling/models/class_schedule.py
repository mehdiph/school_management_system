from django.core.exceptions import ValidationError
from django.db import models, transaction
from django_jalali.db import models as jmodels

from .bell import Bell


class ClassScheduleQuerySet(models.QuerySet):
    def for_week(self, week_type):
        """
        Slots that take place in rotation week ``week_type`` (WEEK_ONE or
        WEEK_TWO): that week's own slots plus the every-week (BOTH) ones.
        """

        return self.filter(
            week_type__in=[week_type, ClassSchedule.WeekTypeChoices.BOTH]
        )

    # bulk_create(), bulk_update() and update() skip clean() and save(),
    # so they run the conflict rules (scheduling.conflicts) themselves.

    def bulk_create(self, objs, *args, **kwargs):
        from scheduling.conflicts import check_slots, schedules_as_slots

        objs = list(objs)
        check_no_new_thursday(objs)
        with transaction.atomic(using=self.db):
            check_slots(schedules_as_slots(objs))
            return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        from scheduling.conflicts import (
            CONFLICT_FIELDS,
            check_slots,
            prevalidated,
            schedules_as_slots,
        )

        objs = list(objs)
        fields = list(fields)
        if "day_of_week" in fields:
            check_no_new_thursday(objs)
        with transaction.atomic(using=self.db):
            if CONFLICT_FIELDS & {_field_name(name) for name in fields}:
                check_slots(schedules_as_slots(self._as_saved_with(objs, fields)))
            with prevalidated():
                return super().bulk_update(objs, fields, *args, **kwargs)

    def update(self, **kwargs):
        from scheduling.conflicts import (
            CONFLICT_FIELDS,
            check_slots,
            is_prevalidated,
            schedules_as_slots,
        )

        if (
            kwargs.get("day_of_week") == ClassSchedule.DayChoices.THURSDAY
            and self.exclude(day_of_week=ClassSchedule.DayChoices.THURSDAY).exists()
        ):
            raise ValidationError({"day_of_week": THURSDAY_MESSAGE})

        if is_prevalidated() or not CONFLICT_FIELDS & {_field_name(k) for k in kwargs}:
            return super().update(**kwargs)

        for name, value in kwargs.items():
            if hasattr(value, "resolve_expression"):
                raise TypeError(
                    f"ClassSchedule update() cannot check timetable conflicts for "
                    f"an expression on {name!r}; use save() or bulk_update()."
                )

        with transaction.atomic(using=self.db):
            rows = list(self.select_related("class_subject__school_class", "class_subject__teacher_assignment"))
            for row in rows:
                for name, value in kwargs.items():
                    setattr(row, name, value)
            check_slots(schedules_as_slots(rows))
            return super().update(**kwargs)

    def _as_saved_with(self, objs, fields):
        """``objs`` as they will be after bulk_update: saved row + ``fields``."""

        saved = ClassSchedule.objects.in_bulk([obj.pk for obj in objs])
        merged = []
        for obj in objs:
            row = saved.get(obj.pk, obj)
            for name in fields:
                setattr(row, name, getattr(obj, name))
            merged.append(row)
        return merged


#: Thursday and Friday are non-working days (see academic_calendar).
THURSDAY_MESSAGE = "ثبت برنامه در روز پنج‌شنبه مجاز نیست؛ پنج‌شنبه و جمعه تعطیل هستند."


def check_no_new_thursday(objs):
    """
    Raises ``ValidationError`` if any of ``objs`` would *become* a
    Thursday slot (new, or moved to Thursday). Rows already saved on a
    Thursday (legacy data) may still be kept or edited, so they can be
    cleaned up without the timetable editor refusing to save.
    """

    thursday = ClassSchedule.DayChoices.THURSDAY
    candidates = [obj for obj in objs if obj.day_of_week == thursday]
    if not candidates:
        return

    saved_days = dict(
        ClassSchedule.objects.filter(pk__in=[obj.pk for obj in candidates if obj.pk])
        .values_list("pk", "day_of_week")
    )
    if any(saved_days.get(obj.pk) != thursday for obj in candidates):
        raise ValidationError({"day_of_week": THURSDAY_MESSAGE})


def _field_name(name):
    return name[:-3] if name.endswith("_id") else name


class ClassSchedule(models.Model):
    objects = ClassScheduleQuerySet.as_manager()

    class DayChoices(models.IntegerChoices):
        SATURDAY = 0, "شنبه"
        SUNDAY = 1, "یکشنبه"
        MONDAY = 2, "دوشنبه"
        TUESDAY = 3, "سه‌شنبه"
        WEDNESDAY = 4, "چهارشنبه"
        #: Kept only so legacy rows still display: no new slot may be
        #: put on Thursday (``check_no_new_thursday``).
        THURSDAY = 5, "پنج‌شنبه"

    class WeekTypeChoices(models.IntegerChoices):
        """
        The school runs a two-week rotation (see ``scheduling.utils``):

        * WEEK_ONE / WEEK_TWO -- the slot only happens in that week.
        * BOTH -- "every week": the slot happens in week 1 *and* week 2,
          and is shown on both. Use ``ClassSchedule.objects.for_week()``
          rather than filtering on ``week_type`` by hand.
        """

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

        if self.day_of_week is not None:
            check_no_new_thursday([self])

        if not self.class_subject_id or not self.bell_id:
            return

        if self.bell.start_time >= self.bell.end_time:
            raise ValidationError({
                "bell": "زمان پایان زنگ باید بعد از زمان شروع باشد."
            })

        # Class and teacher conflicts: see scheduling.conflicts.
        from scheduling.conflicts import Slot, find_conflicts

        conflicts = find_conflicts([Slot.of(self)])
        if conflicts:
            raise ValidationError({
                "bell": list(dict.fromkeys(conflict.message for conflict in conflicts))
            })

    def save(self, *args, **kwargs):
        from scheduling.conflicts import Slot, lock_slots

        with transaction.atomic():
            # Lock the class and the teacher before clean() looks for
            # conflicts, so a concurrent save cannot slip in between.
            if self.class_subject_id:
                lock_slots([Slot.of(self)])
            self.full_clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.class_subject.school_class} | "
            f"{self.class_subject.subject.name} | "
            f"{self.get_day_of_week_display()} | "
            f"{self.bell}"
        )