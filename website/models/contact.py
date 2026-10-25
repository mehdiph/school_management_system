import re

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models
from django_jalali.db import models as jmodels

from accounts.validators import normalize_mobile, validate_mobile

from .base import OrderedItem, SingletonModel, image_url
from .landing import _alt_field, _image_field, _link_field

HERO_IMAGE_FALLBACK = "website/images/teacher.jpg"

_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TO_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(value):
    # Not core's ``fa_digits``: that one turns "044-3344" into a range.
    return str(value or "").translate(_TO_PERSIAN_DIGITS)


def phone_digits(value):
    """'۰۴۴ ۳۳۴۴-۵۵۶۶' -> '04433445566'; a leading + is kept."""
    value = str(value or "").strip().translate(_TO_ASCII_DIGITS)
    plus = "+" if value.startswith("+") else ""
    return plus + re.sub(r"\D", "", value)


class ContactPage(SingletonModel):
    """Texts and section switches of the «تماس با ما» page."""

    show_social = models.BooleanField(default=True, verbose_name="نمایش شبکه‌های اجتماعی")
    show_channels = models.BooleanField(default=True, verbose_name="نمایش سکشن راه‌های تماس")
    show_locations = models.BooleanField(default=True, verbose_name="نمایش سکشن نشانی شعبه‌ها")
    show_form = models.BooleanField(default=True, verbose_name="نمایش فرم پیام")
    show_faq = models.BooleanField(
        default=False,
        verbose_name="نمایش کادر سوالات متداول",
        help_text="تا وقتی صفحه سوالات متداول ساخته نشده، خاموش بماند.",
    )

    # --- Hero ---
    hero_title = models.CharField(max_length=120, default="با دفتر مدرسه در تماس باشید", verbose_name="عنوان")
    hero_text = models.TextField(
        blank=True,
        default="برای ثبت‌نام، پیگیری درس فرزندتان یا هر پرسش دیگری، با دفتر مدرسه تماس بگیرید "
                "یا برایمان پیام بگذارید.",
        verbose_name="توضیح",
    )
    hero_image = _image_field("website/contact/", "۶۰۰×۶۰۰ (مربع)")  # empty: the bundled teacher picture
    hero_image_alt = _alt_field()
    hero_call_text = models.CharField(
        max_length=40,
        default="تماس با دفتر",
        verbose_name="متن دکمه تماس",
        help_text="دکمه با اولین شماره تلفنِ بدون شعبه در «راه‌های تماس» تماس می‌گیرد.",
    )
    hero_message_text = models.CharField(max_length=40, blank=True, default="پیام بگذارید", verbose_name="متن دکمه پیام")

    # --- Sections ---
    channels_title = models.CharField(max_length=100, default="راه‌های تماس", verbose_name="عنوان سکشن راه‌های تماس")
    locations_title = models.CharField(max_length=100, default="نشانی شعبه‌ها", verbose_name="عنوان سکشن شعبه‌ها")

    # --- Form ---
    form_title = models.CharField(max_length=100, default="برای ما بنویسید", verbose_name="عنوان فرم")
    form_intro = models.TextField(
        blank=True,
        default="پیامتان به دفتر مدرسه می‌رسد و همکاران ما با شماره‌ای که وارد می‌کنید تماس می‌گیرند.",
        verbose_name="توضیح فرم",
    )
    submit_text = models.CharField(max_length=40, default="ثبت پیام", verbose_name="متن دکمه ارسال")
    success_message = models.CharField(
        max_length=200,
        default="پیامتان ثبت شد. همکاران ما با شماره {mobile} تماس می‌گیرند.",
        verbose_name="پیام موفقیت",
        help_text="{mobile} با شماره موبایلی که وارد شده جایگزین می‌شود.",
    )

    # --- FAQ teaser ---
    faq_title = models.CharField(max_length=100, blank=True, default="سوالات متداول", verbose_name="عنوان کادر سوالات")
    faq_text = models.TextField(
        blank=True,
        default="پاسخ پرسش‌های رایج درباره ثبت‌نام، شهریه و برنامه کلاس‌ها.",
        verbose_name="توضیح کادر سوالات",
    )
    faq_link_text = models.CharField(max_length=40, blank=True, default="دیدن سوالات", verbose_name="متن لینک سوالات")
    faq_url = _link_field("لینک صفحه سوالات")

    meta_title = models.CharField(
        max_length=70,
        default="تماس با ما",
        verbose_name="عنوان صفحه (meta title)",
        help_text="عنوان تب مرورگر؛ نام سایت پس از آن می‌آید.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="توضیح صفحه (meta description)",
        help_text="حداکثر ۱۶۰ کاراکتر؛ در نتایج جستجو زیر عنوان نمایش داده می‌شود.",
    )

    class Meta:
        verbose_name = "صفحه تماس با ما"
        verbose_name_plural = "صفحه تماس با ما"

    def __str__(self):
        return "محتوای صفحه تماس با ما"

    @property
    def hero_image_url(self):
        return image_url(self.hero_image, HERO_IMAGE_FALLBACK)

    def success_text(self, mobile):
        return self.success_message.replace("{mobile}", persian_digits(mobile))


class ContactLocation(OrderedItem):
    """
    One branch's address block. Linked to a ``school.Branch`` when
    possible, so the name, address and phone already entered for the
    branch show here; the ``*_override`` fields win when filled in.
    """

    page = models.ForeignKey(ContactPage, on_delete=models.CASCADE, related_name="locations", verbose_name="صفحه تماس")
    branch = models.ForeignKey(
        "school.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_locations",
        verbose_name="شعبه",
    )
    title_override = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="عنوان",
        help_text="اگر خالی باشد، نام شعبه نمایش داده می‌شود.",
    )
    address_override = models.TextField(
        blank=True,
        verbose_name="نشانی",
        help_text="اگر خالی باشد، نشانی ثبت‌شده برای شعبه نمایش داده می‌شود.",
    )
    hours = models.TextField(
        blank=True,
        verbose_name="ساعت کاری",
        help_text="مثال: شنبه تا چهارشنبه، ۷:۳۰ تا ۱۴:۰۰. با Enter چند خط بنویسید.",
    )
    map_image = _image_field("website/contact/maps/", "۸۰۰×۶۰۰", "تصویر نقشه")
    map_image_alt = _alt_field()
    neshan_url = _link_field("لینک نشان", default="")
    balad_url = _link_field("لینک بلد", default="")
    google_maps_url = _link_field("لینک گوگل مپ", default="")

    class Meta(OrderedItem.Meta):
        verbose_name = "شعبه در صفحه تماس"
        verbose_name_plural = "شعبه‌ها در صفحه تماس"

    def __str__(self):
        return self.display_title or "شعبه"

    def clean(self):
        if not self.branch_id and not self.title_override.strip():
            raise ValidationError("یک شعبه انتخاب کنید یا عنوان را وارد کنید.")

    @property
    def display_title(self):
        if self.title_override:
            return self.title_override
        return self.branch.name if self.branch else ""

    @property
    def display_address(self):
        if self.address_override:
            return self.address_override
        return self.branch.address if self.branch else ""

    @property
    def branch_phone(self):
        return self.branch.phone_number if self.branch else ""

    @property
    def branch_phone_href(self):
        return f"tel:{phone_digits(self.branch_phone)}"

    @property
    def branch_phone_display(self):
        return persian_digits(self.branch_phone)

    @property
    def phone_channels(self):
        """This location's phones, set by the contact view (no query)."""
        return [c for c in getattr(self, "contact_channels", []) if not c.is_email]

    @property
    def map_image_url(self):
        return image_url(self.map_image)

    @property
    def map_alt_text(self):
        return self.map_image_alt or f"نقشه محل {self.display_title}"

    @property
    def map_links(self):
        links = [("نشان", self.neshan_url), ("بلد", self.balad_url), ("گوگل مپ", self.google_maps_url)]
        return [(label, url) for label, url in links if url]


class ContactChannel(OrderedItem):
    class Kind(models.TextChoices):
        PHONE = "phone", "تلفن ثابت"
        MOBILE = "mobile", "موبایل"
        EMAIL = "email", "ایمیل"

    ICONS = {
        Kind.PHONE: "fa-solid fa-phone",
        Kind.MOBILE: "fa-solid fa-mobile-screen-button",
        Kind.EMAIL: "fa-solid fa-envelope",
    }

    page = models.ForeignKey(ContactPage, on_delete=models.CASCADE, related_name="channels", verbose_name="صفحه تماس")
    location = models.ForeignKey(
        ContactLocation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="channels",
        verbose_name="شعبه",
        help_text="خالی: در «راه‌های تماس» کل مدرسه نمایش داده می‌شود. شعبه تازه را اول ذخیره کنید تا اینجا دیده شود.",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PHONE, verbose_name="نوع")
    label = models.CharField(max_length=60, verbose_name="عنوان", help_text="مثال: دفتر مدرسه، معاونت آموزشی")
    value = models.CharField(max_length=100, verbose_name="شماره یا ایمیل", help_text="مثال: ۰۴۴-۳۳۴۴۵۵۶۶")
    note = models.CharField(max_length=120, blank=True, verbose_name="توضیح", help_text="مثال: پاسخگویی ۸ تا ۱۴")

    class Meta(OrderedItem.Meta):
        verbose_name = "راه تماس"
        verbose_name_plural = "راه‌های تماس"

    def __str__(self):
        return f"{self.label}: {self.value}"

    def clean(self):
        value = (self.value or "").strip()
        try:
            if self.kind == self.Kind.EMAIL:
                EmailValidator(message="ایمیل معتبر نیست؛ مثل info@example.com.")(value)
            elif self.kind == self.Kind.MOBILE:
                validate_mobile(normalize_mobile(value))
            elif not 4 <= len(phone_digits(value).lstrip("+")) <= 15:
                raise ValidationError("شماره تلفن باید بین ۴ تا ۱۵ رقم باشد.")
        except ValidationError as error:
            raise ValidationError({"value": error.messages})

    @property
    def is_email(self):
        return self.kind == self.Kind.EMAIL

    @property
    def raw_value(self):
        """What a dialer or mail client needs: ASCII digits, or the address."""
        if self.is_email:
            return self.value.strip()
        if self.kind == self.Kind.MOBILE:
            return normalize_mobile(self.value)
        return phone_digits(self.value)

    @property
    def href(self):
        return f"{'mailto' if self.is_email else 'tel'}:{self.raw_value}"

    @property
    def display_value(self):
        return self.value if self.is_email else persian_digits(self.value)

    @property
    def icon(self):
        return self.ICONS.get(self.kind, "")


class ContactTopic(OrderedItem):
    page = models.ForeignKey(ContactPage, on_delete=models.CASCADE, related_name="topics", verbose_name="صفحه تماس")
    title = models.CharField(max_length=60, verbose_name="عنوان")

    class Meta(OrderedItem.Meta):
        verbose_name = "موضوع پیام"
        verbose_name_plural = "موضوع‌های پیام"

    def __str__(self):
        return self.title


class ContactMessage(models.Model):
    """
    A message sent from the contact form. Topic and branch are copied as
    text, so the record stays readable after either is renamed or deleted.
    Only an HMAC of the sender's IP is kept (for the rate limit).
    """

    name = models.CharField(max_length=100, verbose_name="نام و نام خانوادگی")
    mobile = models.CharField(max_length=11, verbose_name="شماره موبایل")
    topic = models.CharField(max_length=60, blank=True, verbose_name="موضوع")
    location = models.CharField(max_length=100, blank=True, verbose_name="شعبه")
    message = models.TextField(verbose_name="متن پیام")
    ip_hash = models.CharField(max_length=64, editable=False, verbose_name="شناسه دستگاه")
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ارسال")
    is_handled = models.BooleanField(default=False, verbose_name="پیگیری شد")

    class Meta:
        verbose_name = "پیام تماس با ما"
        verbose_name_plural = "پیام‌های تماس با ما"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["ip_hash", "created_at"], name="website_contact_ip_idx"),
            models.Index(fields=["mobile", "created_at"], name="website_contact_mobile_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.mobile})"

    @property
    def mobile_display(self):
        return persian_digits(self.mobile)
