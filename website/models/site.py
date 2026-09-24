from django.db import models

from website.validators import IMAGE_VALIDATORS, validate_link

from .base import OrderedItem, SingletonModel, image_url

LINK_HELP = "مثال: /auth/login/ یا #contact یا https://instagram.com/..."


class SiteSettings(SingletonModel):
    """Site-wide values used by the shared navbar and footer (base.html)."""

    site_name = models.CharField(
        max_length=100,
        default="مدرسه نسل قلم",
        verbose_name="نام سایت",
    )
    logo = models.ImageField(
        upload_to="website/logo/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="لوگو",
        help_text="اختیاری. PNG یا WebP با پس‌زمینه شفاف، حدود ۲۴۰×۸۰ پیکسل. "
                  "اگر خالی باشد، نام سایت نمایش داده می‌شود.",
    )
    login_text = models.CharField(
        max_length=30,
        default="ورود",
        verbose_name="متن دکمه ورود",
    )
    login_url = models.CharField(
        max_length=300,
        blank=True,
        validators=[validate_link],
        verbose_name="لینک دکمه ورود",
        help_text="اگر خالی باشد، به صفحه ورود سامانه می‌رود.",
    )
    copyright_text = models.CharField(
        max_length=200,
        default="تمامی حقوق برای مدرسه نسل قلم محفوظ است.",
        verbose_name="متن کپی‌رایت",
    )
    footer_note = models.CharField(
        max_length=200,
        blank=True,
        default="Made with 💗 in Urmia",
        verbose_name="متن پایین فوتر",
    )
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        verbose_name="عنوان صفحه (meta title)",
        help_text="عنوان تب مرورگر و نتایج گوگل. اگر خالی باشد، نام سایت استفاده می‌شود.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="توضیح صفحه (meta description)",
        help_text="حداکثر ۱۶۰ کاراکتر؛ در نتایج جستجو زیر عنوان نمایش داده می‌شود.",
    )

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return "تنظیمات سایت"

    @property
    def logo_url(self):
        return image_url(self.logo)


class NavMenuItem(OrderedItem):
    site = models.ForeignKey(
        SiteSettings,
        on_delete=models.CASCADE,
        related_name="nav_items",
        verbose_name="تنظیمات سایت",
    )
    title = models.CharField(max_length=50, verbose_name="عنوان")
    url = models.CharField(
        max_length=300,
        default="#",
        validators=[validate_link],
        verbose_name="لینک",
        help_text=LINK_HELP,
    )
    open_in_new_tab = models.BooleanField(default=False, verbose_name="باز شدن در تب جدید")

    class Meta(OrderedItem.Meta):
        verbose_name = "آیتم منو"
        verbose_name_plural = "آیتم‌های منو"

    def __str__(self):
        return self.title


class FooterLink(OrderedItem):
    class Kind(models.TextChoices):
        SOCIAL = "social", "شبکه اجتماعی"
        PAGE = "page", "صفحه"

    class Icon(models.TextChoices):
        # Font Awesome classes already bundled in static/assets.
        INSTAGRAM = "fa-brands fa-instagram", "اینستاگرام"
        TELEGRAM = "fa-brands fa-telegram", "تلگرام"
        WHATSAPP = "fa-brands fa-whatsapp", "واتساپ"
        X = "fa-brands fa-x-twitter", "ایکس (توییتر)"
        VIDEO = "fa-solid fa-circle-play", "ویدیو (آپارات / یوتیوب)"
        PHONE = "fa-solid fa-phone", "تلفن"
        EMAIL = "fa-solid fa-envelope", "ایمیل"
        LOCATION = "fa-solid fa-location-dot", "آدرس"
        INFO = "fa-solid fa-circle-info", "اطلاعات"
        QUESTION = "fa-solid fa-circle-question", "سوال"

    site = models.ForeignKey(
        SiteSettings,
        on_delete=models.CASCADE,
        related_name="footer_links",
        verbose_name="تنظیمات سایت",
    )
    title = models.CharField(max_length=50, verbose_name="عنوان")
    url = models.CharField(
        max_length=300,
        default="#",
        validators=[validate_link],
        verbose_name="لینک",
        help_text=LINK_HELP,
    )
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
        default=Kind.PAGE,
        verbose_name="نوع",
    )
    icon = models.CharField(
        max_length=40,
        choices=Icon.choices,
        blank=True,
        verbose_name="آیکون",
    )

    class Meta(OrderedItem.Meta):
        verbose_name = "لینک فوتر"
        verbose_name_plural = "لینک‌های فوتر"

    def __str__(self):
        return self.title

    @property
    def opens_externally(self):
        return self.url.startswith(("http://", "https://"))
