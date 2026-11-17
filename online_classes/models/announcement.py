from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django_jalali.db import models as jmodels

from core.moments import as_datetime, to_utc, utc_now
from website.images import METADATA_HELP, reencode
from website.models.base import image_url
from website.validators import IMAGE_VALIDATORS

from ..validators import MAX_URL_LENGTH, clean_url, safe_button_url, validate_button_url
from .audience import AudienceTargets

IMAGE_MAX_SIDE = 1600
IMAGE_HELP = (
    "jpg، png یا webp، حداکثر ۲ مگابایت. " + METADATA_HELP + " تصویرها بدون نیاز به ورود قابل دیدن‌اند؛ "
    "اطلاعات خصوصی یا رمز روی تصویر نگذارید."
)
#: The moments compared with the clock in queries (``core.moments``).
MOMENT_FIELDS = ("visible_from", "visible_until")


class AnnouncementQuerySet(models.QuerySet):
    def live(self):
        """Active, and the clock is inside its display window."""

        now = utc_now()
        return self.filter(is_active=True, visible_from__lte=now, visible_until__gt=now)

    def not_dismissed_by(self, student_profile):
        """A dismissal counts only while the banner may still be dismissed (D20)."""

        dismissed = AnnouncementDismissal.objects.filter(announcement=OuterRef("pk"), student=student_profile)
        return self.filter(
            Q(level=Announcement.Level.URGENT) | Q(is_dismissible=False) | ~Exists(dismissed)
        )

    def in_order(self):
        """Urgent first, then pinned, then priority, then newest (D21)."""

        return self.annotate(
            level_rank=Case(
                When(level=Announcement.Level.URGENT, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("level_rank", "-is_pinned", "-priority", "-visible_from", "-pk")


class Announcement(AudienceTargets):
    """A banner at the top of the student dashboard. Plain text only; there is no sending of any kind."""

    class Level(models.TextChoices):
        INFO = "info", "اطلاع‌رسانی"
        IMPORTANT = "important", "مهم"
        URGENT = "urgent", "فوری"

    title = models.CharField(max_length=120, verbose_name="عنوان")
    body = models.TextField(
        max_length=600,
        blank=True,
        verbose_name="متن",
        help_text="کوتاه و ساده، حداکثر ۶۰۰ حرف. فقط متن و خط جدید؛ HTML نمایش داده نمی‌شود.",
    )
    image = models.ImageField(
        upload_to="online_classes/announcements/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="تصویر",
        help_text=IMAGE_HELP,
    )
    image_mobile = models.ImageField(
        upload_to="online_classes/announcements/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="تصویر موبایل",
        help_text="اختیاری؛ اگر خالی باشد همان تصویر بالا در موبایل نمایش داده می‌شود.",
    )
    button_label = models.CharField(max_length=40, blank=True, verbose_name="متن دکمه")
    button_url = models.CharField(
        max_length=MAX_URL_LENGTH,
        blank=True,
        validators=[validate_button_url],
        verbose_name="لینک دکمه",
        help_text="لینک https یا مسیر داخلی سایت، مثل ‎/student/online/‎.",
    )
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO, verbose_name="سطح")
    visible_from = jmodels.jDateTimeField(verbose_name="نمایش از")
    visible_until = jmodels.jDateTimeField(verbose_name="نمایش تا")
    priority = models.PositiveSmallIntegerField(
        default=0, verbose_name="اولویت", help_text="عدد بزرگ‌تر بالاتر نمایش داده می‌شود."
    )
    is_pinned = models.BooleanField(default=False, verbose_name="سنجاق‌شده")
    is_dismissible = models.BooleanField(
        default=True, verbose_name="قابل بستن", help_text="اطلاعیه‌ی «فوری» هیچ‌وقت قابل بستن نیست."
    )
    event = models.ForeignKey(
        "online_classes.OnlineEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
        verbose_name="رویداد مرتبط",
        help_text="اختیاری؛ شمارش معکوس تا این رویداد کنار اطلاعیه نمایش داده می‌شود. لینک و رمز رویداد هرگز "
                  "در اطلاعیه نمایش داده نمی‌شود.",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
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

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        verbose_name = "اطلاعیه"
        verbose_name_plural = "اطلاعیه‌ها"
        ordering = ["-visible_from", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(visible_until__gt=models.F("visible_from")), name="announcement_until_after_from"
            ),
            models.CheckConstraint(
                condition=Q(button_label="", button_url="") | (~Q(button_label="") & ~Q(button_url="")),
                name="announcement_button_label_and_url",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "visible_from", "visible_until"], name="announcement_window_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def can_be_dismissed(self):
        return self.is_dismissible and self.level != self.Level.URGENT

    @property
    def image_url(self):
        return image_url(self.image)

    @property
    def image_mobile_url(self):
        return image_url(self.image_mobile)

    @property
    def safe_button_url(self):
        return safe_button_url(self.button_url)

    @property
    def button_is_external(self):
        return self.safe_button_url.startswith("https://")

    def clean_fields(self, exclude=None):
        if "button_url" not in (exclude or ()):
            self.button_url = clean_url(self.button_url)
        super().clean_fields(exclude)

    def clean(self):
        errors = {}
        if self.visible_from and self.visible_until and as_datetime(self.visible_until) <= as_datetime(self.visible_from):
            errors["visible_until"] = "پایان نمایش باید بعد از شروع آن باشد."
        if bool(self.button_label.strip()) != bool(self.button_url.strip()):
            errors["button_url" if self.button_label.strip() else "button_label"] = "متن و لینک دکمه با هم لازم‌اند."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        for name in MOMENT_FIELDS:
            setattr(self, name, to_utc(getattr(self, name)))
        if self.image and not self.image._committed:
            self.image = reencode(self.image.file, max_side=IMAGE_MAX_SIDE)
        if self.image_mobile and not self.image_mobile._committed:
            self.image_mobile = reencode(self.image_mobile.file, max_side=IMAGE_MAX_SIDE)
        super().save(*args, **kwargs)


class AnnouncementDismissal(models.Model):
    """A student closed this banner; remembered on the server, so it holds on every device (D20)."""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="dismissals", verbose_name="اطلاعیه"
    )
    student = models.ForeignKey(
        "student.StudentProfile", on_delete=models.CASCADE, related_name="+", verbose_name="دانش‌آموز"
    )
    dismissed_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="زمان بستن")

    class Meta:
        verbose_name = "بستن اطلاعیه"
        verbose_name_plural = "بستن اطلاعیه‌ها"
        constraints = [
            models.UniqueConstraint(fields=["announcement", "student"], name="unique_dismissal_per_student"),
        ]

    def __str__(self):
        return f"{self.announcement_id} / {self.student_id}"
