from django.db import models
from django_jalali.db import models as jmodels

from school.colors import hex_color_validator
from website.images import METADATA_HELP, reencode
from website.models.base import image_url
from website.validators import IMAGE_VALIDATORS

from ..validators import clean_url, safe_https_url, split_domains, tidy_domains, validate_domains, validate_https_url

LOGO_MAX_SIDE = 256


class OnlinePlatform(models.Model):
    """A service classes and exams run on. Data the admin creates; nothing is hard-coded for any of them."""

    name = models.CharField(max_length=100, unique=True, verbose_name="نام")
    logo = models.ImageField(
        upload_to="online_classes/platforms/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="لوگو",
        help_text="jpg، png یا webp، حداکثر ۲ مگابایت؛ روی زمینه‌ی سفید نمایش داده می‌شود. " + METADATA_HELP,
    )
    color = models.CharField(
        max_length=7, blank=True, validators=[hex_color_validator], verbose_name="رنگ", help_text="اختیاری، مثل ‎#2563eb‎."
    )
    join_help = models.TextField(
        blank=True,
        verbose_name="راهنمای ورود",
        help_text="کوتاه و ساده، برای پدر و مادر: برای ورود دقیقاً چه کار کنند؟ به دانش‌آموز نشان داده می‌شود.",
    )
    support_contact = models.CharField(
        max_length=150, blank=True, verbose_name="پشتیبانی", help_text="اختیاری؛ مثلاً یک شماره تلفن."
    )
    support_url = models.CharField(
        max_length=500, blank=True, validators=[validate_https_url], verbose_name="لینک پشتیبانی"
    )
    allowed_domains = models.TextField(
        blank=True,
        validators=[validate_domains],
        verbose_name="دامنه‌های مجاز",
        help_text="اختیاری؛ هر دامنه در یک خط، مثل skyroom.online. اگر پر باشد، فقط لینک‌های این دامنه‌ها "
                  "و زیردامنه‌هایشان (از جمله www) پذیرفته می‌شوند. اگر لینک کامل یا www بنویسید، "
                  "هنگام ذخیره فقط نام دامنه نگه داشته می‌شود.",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = jmodels.jDateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "پلتفرم آنلاین"
        verbose_name_plural = "پلتفرم‌های آنلاین"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def domains(self):
        return split_domains(self.allowed_domains)

    @property
    def safe_support_url(self):
        return safe_https_url(self.support_url)

    @property
    def logo_url(self):
        return image_url(self.logo)

    def clean_fields(self, exclude=None):
        # Store one plain domain per line and the link without invisible marks;
        # an unusable line is left as typed so the validator can name it.
        exclude = exclude or ()
        if "allowed_domains" not in exclude:
            self.allowed_domains = tidy_domains(self.allowed_domains)
        if "support_url" not in exclude:
            self.support_url = clean_url(self.support_url)
        super().clean_fields(exclude)

    def save(self, *args, **kwargs):
        if self.logo and not self.logo._committed:
            self.logo = reencode(self.logo.file, max_side=LOGO_MAX_SIDE)
        super().save(*args, **kwargs)
