import jdatetime
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels


def _jalali(value):
    if hasattr(value, 'togregorian'):
        return value.strftime('%Y/%m/%d')
    return jdatetime.date.fromgregorian(date=value).strftime('%Y/%m/%d')


class CalendarEventQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def overlapping(self, start, end):
        """Events with at least one day in ``start``..``end`` (both inclusive)."""

        return self.filter(start_date__lte=end, end_date__gte=start)


class CalendarEvent(models.Model):
    """
    A day or range of days on which (part of) the school is closed.

    Scope: ``branches``, ``grades`` and ``bells`` narrow which classes and
    which bells are closed; an empty set means "all". A bell scope is a
    partial-day closure ("closed from the 3rd bell on").

    Thursday and Friday are never part of an event's effect, even when the
    range covers them (``academic_calendar.services.is_working_day``).

    Saving an event does not touch sessions by itself: the admin and the
    import go through ``academic_calendar.services.save_event`` /
    ``deactivate_event`` / ``import_events``, which run the session sync
    after the many-to-many scope is saved. Events are never deleted, only
    deactivated (``is_active``), so the sessions that point at them keep
    their reason.
    """

    objects = CalendarEventQuerySet.as_manager()

    class EventType(models.TextChoices):
        OFFICIAL_HOLIDAY = 'official', 'تعطیل رسمی'
        UNPLANNED_CLOSURE = 'unplanned', 'تعطیلی غیرمنتظره'

    academic_year = models.ForeignKey(
        'school.AcademicYear',
        on_delete=models.PROTECT,
        related_name='calendar_events',
        verbose_name='سال تحصیلی',
    )

    title = models.CharField(
        max_length=200,
        verbose_name='عنوان',
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        default=EventType.OFFICIAL_HOLIDAY,
        verbose_name='نوع',
    )

    start_date = jmodels.jDateField(
        verbose_name='تاریخ شروع',
    )

    end_date = jmodels.jDateField(
        verbose_name='تاریخ پایان',
        help_text='برای تعطیلی یک‌روزه همان تاریخ شروع را وارد کنید.',
    )

    branches = models.ManyToManyField(
        'school.Branch',
        blank=True,
        related_name='calendar_events',
        verbose_name='شعبه‌ها',
        help_text='خالی یعنی همه‌ی شعبه‌ها.',
    )

    grades = models.ManyToManyField(
        'school.Grade',
        blank=True,
        related_name='calendar_events',
        verbose_name='پایه‌ها',
        help_text='خالی یعنی همه‌ی پایه‌ها.',
    )

    bells = models.ManyToManyField(
        'scheduling.Bell',
        blank=True,
        related_name='calendar_events',
        verbose_name='زنگ‌ها',
        help_text='خالی یعنی همه‌ی زنگ‌ها (تعطیلی کامل روز).',
    )

    description = models.TextField(
        blank=True,
        verbose_name='توضیحات',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='+',
        verbose_name='ثبت‌کننده',
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ ایجاد',
    )

    updated_at = jmodels.jDateTimeField(
        auto_now=True,
        verbose_name='آخرین تغییر',
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال',
    )

    class Meta:
        verbose_name = 'رویداد تقویم آموزشی'
        verbose_name_plural = 'تقویم آموزشی (تعطیلات)'
        ordering = ['-start_date', '-pk']

        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')),
                name='calendar_event_end_after_start',
                violation_error_message='تاریخ پایان نباید قبل از تاریخ شروع باشد.',
            ),
        ]

        indexes = [
            models.Index(
                fields=['academic_year', 'is_active', 'start_date', 'end_date'],
                name='calendar_event_range_idx',
            ),
        ]

    def clean(self):
        super().clean()

        if not (self.start_date and self.end_date):
            return

        if self.end_date < self.start_date:
            raise ValidationError({'end_date': 'تاریخ پایان نباید قبل از تاریخ شروع باشد.'})

        year = self.academic_year if self.academic_year_id else None
        if year is not None and (
            self.start_date < year.start_date or self.end_date > year.end_date
        ):
            raise ValidationError(
                f'بازه‌ی رویداد باید داخل سال تحصیلی «{year.title}» باشد '
                f'({_jalali(year.start_date)} تا {_jalali(year.end_date)}).'
            )

    @property
    def is_single_day(self):
        return self.start_date == self.end_date

    def __str__(self):
        return self.title
