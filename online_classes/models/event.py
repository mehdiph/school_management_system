from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from django_jalali.db import models as jmodels

from core.moments import as_datetime, to_utc, utc_now

from ..validators import MAX_URL_LENGTH, validate_https_url
from .audience import AudienceTargets

#: The event's own moments, compared with the clock in queries (``core.moments``).
MOMENT_FIELDS = ("start_at", "end_at")


class Tab(models.TextChoices):
    TODAY = "today", "امروز"
    UPCOMING = "upcoming", "پیش‌رو"
    PAST = "past", "گذشته"


def _end_of_today():
    """The next Tehran midnight, in UTC."""

    today = timezone.localdate()
    midnight = timezone.make_aware(timezone.datetime(today.year, today.month, today.day)) + timedelta(days=1)
    return to_utc(midnight)


class OnlineEventQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_active=True)

    def in_tab(self, tab):
        """
        One rule for what is on which tab (D9). The clock decides, and nothing
        is stored; a postponed event has no time yet, so it stays in «پیش‌رو»
        until an admin edits it.
        """

        now = utc_now()
        end_of_today = _end_of_today()
        postponed = Q(status=OnlineEvent.Status.POSTPONED)

        if tab == Tab.TODAY:
            return self.filter(~postponed, end_at__gt=now, start_at__lt=end_of_today)
        if tab == Tab.UPCOMING:
            return self.filter(postponed | Q(start_at__gte=end_of_today))
        past_from = now - timedelta(days=settings.ONLINE_PAST_DAYS)
        return self.filter(~postponed, end_at__lte=now, end_at__gt=past_from)

    def current_or_coming(self):
        """Today's and upcoming events, for the dashboard: not ended, or postponed."""

        return self.filter(Q(end_at__gt=utc_now()) | Q(status=OnlineEvent.Status.POSTPONED))

    def in_order(self, tab=Tab.TODAY):
        """Live first, then by start; undated postponed events last, so they can't push real dates out."""

        if tab == Tab.PAST:
            return self.order_by("-end_at", "-pk")

        now = utc_now()
        end_of_today = _end_of_today()
        scheduled = OnlineEvent.Status.SCHEDULED
        return self.annotate(
            order_rank=Case(
                When(status=OnlineEvent.Status.POSTPONED, then=Value(3)),
                When(status=scheduled, start_at__lte=now, end_at__gt=now, then=Value(0)),
                When(start_at__lt=end_of_today, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("order_rank", "start_at", "pk")


class OnlineEvent(AudienceTargets):
    """A live class, exam or meeting on an external platform, or an in-school one announced here."""

    class EventType(models.TextChoices):
        CLASS = "class", "کلاس"
        EXAM = "exam", "آزمون"
        MEETING = "meeting", "جلسه"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "طبق برنامه"
        CANCELLED = "cancelled", "لغو شده"
        POSTPONED = "postponed", "به تعویق افتاده"

    class AccessMode(models.TextChoices):
        SHARED = "shared", "لینک مشترک برای همه"
        PERSONAL = "personal", "اطلاعات ورود جدا برای هر دانش‌آموز"
        INFO = "info", "فقط اطلاع‌رسانی (بدون لینک)"

    class State(models.TextChoices):
        """Derived from the clock, never stored."""

        UPCOMING = "upcoming", "پیش‌رو"
        LIVE = "live", "در حال برگزاری"
        ENDED = "ended", "پایان یافته"

    title = models.CharField(max_length=200, verbose_name="عنوان")
    event_type = models.CharField(
        max_length=10, choices=EventType.choices, default=EventType.CLASS, verbose_name="نوع"
    )
    platform = models.ForeignKey(
        "online_classes.OnlinePlatform",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="پلتفرم",
    )
    subject = models.ForeignKey(
        "school.Subject", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="درس"
    )
    class_subject = models.ForeignKey(
        "school.ClassSubject", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="درس کلاس"
    )
    start_at = jmodels.jDateTimeField(verbose_name="شروع")
    end_at = jmodels.jDateTimeField(verbose_name="پایان")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED, verbose_name="وضعیت")
    status_note = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="توضیح وضعیت",
        help_text="برای «لغو شده» و «به تعویق افتاده» لازم است و به خانواده‌ها نشان داده می‌شود.",
    )
    access_mode = models.CharField(
        max_length=10, choices=AccessMode.choices, default=AccessMode.SHARED, verbose_name="نحوه‌ی دسترسی"
    )
    join_url = models.CharField(
        max_length=MAX_URL_LENGTH,
        blank=True,
        validators=[validate_https_url],
        verbose_name="لینک ورود",
        help_text="https. برای «لینک مشترک» لازم است؛ در حالت «جدا برای هر دانش‌آموز» برای کسانی به کار می‌رود "
                  "که لینک خودشان را ندارند.",
    )
    join_lead_minutes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(1440)],
        verbose_name="باز شدن دکمه‌ی ورود (چند دقیقه قبل از شروع)",
        help_text="خالی یعنی مقدار پیش‌فرض مدرسه.",
    )
    credentials_lead_hours = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(168)],
        verbose_name="نمایش اطلاعات ورود از چند ساعت قبل از شروع",
        help_text="فقط برای «جدا برای هر دانش‌آموز»، تا خانواده‌ها ورود را پیش از آزمون امتحان کنند. "
                  "۰ یعنی همزمان با باز شدن دکمه‌ی ورود. دکمه‌ی ورود زودتر باز نمی‌شود.",
    )
    is_active = models.BooleanField(
        default=True, verbose_name="فعال", help_text="غیرفعال یعنی کاملاً پنهان؛ برای اعلام لغو، «وضعیت» را تغییر دهید."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="+", verbose_name="ثبت‌کننده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="+", verbose_name="آخرین ویرایش توسط",
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = jmodels.jDateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    objects = OnlineEventQuerySet.as_manager()

    class Meta:
        verbose_name = "کلاس یا آزمون آنلاین"
        verbose_name_plural = "کلاس‌ها و آزمون‌های آنلاین"
        ordering = ["-start_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=models.F("start_at")), name="online_event_end_after_start"),
        ]
        indexes = [
            models.Index(fields=["is_active", "start_at", "end_at"], name="online_event_window_idx"),
        ]

    def __str__(self):
        return self.title

    # ---------------------------------------------------------------- moments

    @property
    def start(self):
        return as_datetime(self.start_at)

    @property
    def end(self):
        return as_datetime(self.end_at)

    @property
    def is_scheduled(self):
        return self.status == self.Status.SCHEDULED

    @property
    def is_postponed(self):
        return self.status == self.Status.POSTPONED

    @property
    def is_cancelled(self):
        return self.status == self.Status.CANCELLED

    @property
    def join_opens_at(self):
        lead = self.join_lead_minutes
        if lead is None:
            lead = settings.ONLINE_JOIN_LEAD_MINUTES
        return self.start - timedelta(minutes=lead)

    @property
    def credentials_open_at(self):
        """Never later than the join button, which needs them (D11)."""

        return min(self.join_opens_at, self.start - timedelta(hours=self.credentials_lead_hours))

    def state_at(self, now):
        if now < self.start:
            return self.State.UPCOMING
        if now < self.end:
            return self.State.LIVE
        return self.State.ENDED

    def can_join_at(self, now):
        return self.is_scheduled and self.join_opens_at <= now < self.end

    def credentials_open_on(self, now):
        return (
            self.is_scheduled
            and self.access_mode == self.AccessMode.PERSONAL
            and self.credentials_open_at <= now < self.end
        )

    def next_change_after(self, now):
        """The next moment this event's card looks different, or ``None``."""

        if not self.is_scheduled:
            return None
        moments = [self.credentials_open_at, self.join_opens_at, self.start, self.end]
        return min((moment for moment in moments if moment > now), default=None)

    # ------------------------------------------------------------------- rules

    def clean(self):
        errors = {}

        if self.start_at and self.end_at and self.end <= self.start:
            errors["end_at"] = "پایان باید بعد از شروع باشد."

        if not self.is_scheduled and not self.status_note.strip():
            errors["status_note"] = "برای لغو یا تعویق، یک توضیح کوتاه برای خانواده‌ها بنویسید."

        if self.access_mode == self.AccessMode.INFO:
            if self.join_url:
                errors["join_url"] = "رویداد «فقط اطلاع‌رسانی» لینک ندارد."
        elif self.platform_id is None:
            errors["platform"] = "پلتفرم را انتخاب کنید؛ فقط رویداد «فقط اطلاع‌رسانی» می‌تواند بدون پلتفرم باشد."

        if self.access_mode == self.AccessMode.SHARED and not self.join_url:
            errors["join_url"] = "برای «لینک مشترک»، لینک ورود لازم است."

        if self.join_url and self.platform_id and "join_url" not in errors:
            try:
                validate_https_url(self.join_url, self.platform.allowed_domains)
            except ValidationError as error:
                errors["join_url"] = error.messages

        if self.credentials_lead_hours and self.access_mode != self.AccessMode.PERSONAL:
            errors["credentials_lead_hours"] = "این گزینه فقط برای «جدا برای هر دانش‌آموز» است."

        if self.class_subject_id and self.subject_id and self.class_subject.subject_id != self.subject_id:
            errors["subject"] = "این درس با «درس کلاس» انتخاب‌شده یکی نیست."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        for name in MOMENT_FIELDS:
            setattr(self, name, to_utc(getattr(self, name)))
        if self.class_subject_id and not self.subject_id:
            self.subject_id = self.class_subject.subject_id
        super().save(*args, **kwargs)

