from django.db import models

from website.models.base import SingletonModel
from website.validators import IMAGE_VALIDATORS

DEFAULT_REMINDER = (
    "این نوشته در سایت عمومی مدرسه منتشر می‌شود. نام کامل، عکس چهره، کلاس یا هر نشانه‌ای "
    "که دانش‌آموزی را قابل شناسایی کند، بدون رضایت کتبی ولی او ننویسید و نگذارید. در "
    "نوشته‌های مشاوره، ماجراهای واقعی را طوری تغییر دهید که به هیچ دانش‌آموز یا خانواده‌ای "
    "نرسد."
)
DEFAULT_ACK = "این نوشته و عکس‌هایش هیچ دانش‌آموزی را بدون رضایت ولی‌اش قابل شناسایی نمی‌کند."
DEFAULT_CHECKLIST = "\n".join([
    "هیچ دانش‌آموزی بدون رضایت کتبی ولی قابل شناسایی نیست (نام، چهره، کلاس).",
    "در نوشته‌های مشاوره، هیچ ماجرای واقعی به دانش‌آموز یا خانواده‌ای قابل ردیابی نیست.",
    "هیچ اطلاعات داخلی مدرسه (نمره، غیبت، شماره تماس، نشانی) در متن یا عکس‌ها نیست.",
    "همه عکس‌ها متن جایگزین دارند و اجازه انتشارشان گرفته شده است.",
])


class BlogPage(SingletonModel):
    """The blog's own texts: its home page, the safety texts of writing and review, and SEO."""

    title = models.CharField(max_length=80, default="وبلاگ نسل قلم", verbose_name="نام وبلاگ")
    intro = models.TextField(
        max_length=300,
        blank=True,
        default="نوشته‌هایی از معلمان و مشاور مدرسه، برای بچه‌ها و پدر و مادرها.",
        verbose_name="جمله معرفی",
    )

    # --- Safety (D16) ---
    author_reminder = models.TextField(
        default=DEFAULT_REMINDER,
        verbose_name="یادآوری بالای ویرایشگر",
        help_text="بالای صفحه نوشتن، برای همه نویسندگان نمایش داده می‌شود.",
    )
    author_ack = models.CharField(
        max_length=300,
        default=DEFAULT_ACK,
        verbose_name="جمله تأیید نویسنده",
        help_text="نویسنده پیش از «ارسال برای بررسی» باید این جمله را تیک بزند.",
    )
    review_checklist = models.TextField(
        default=DEFAULT_CHECKLIST,
        verbose_name="فهرست بررسی پیش از انتشار",
        help_text="هر خط یک مورد. ویراستار پیش از انتشار باید همه موارد را تیک بزند.",
    )

    # --- SEO ---
    og_image = models.ImageField(
        upload_to="blog/page/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="تصویر پیش‌فرض اشتراک‌گذاری",
        help_text="برای نوشته‌های بدون تصویر شاخص، در پیش‌نمایش پیوند در شبکه‌های اجتماعی. "
                  "ابعاد پیشنهادی ۱۲۰۰×۶۳۰؛ jpg، png یا webp، حداکثر ۲ مگابایت.",
    )
    meta_title = models.CharField(
        max_length=70,
        default="وبلاگ",
        verbose_name="عنوان صفحه (meta title)",
        help_text="عنوان تب مرورگر در صفحه اصلی وبلاگ؛ نام سایت پس از آن می‌آید.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="توضیح صفحه (meta description)",
        help_text="حداکثر ۱۶۰ کاراکتر؛ در نتایج جستجو زیر عنوان نمایش داده می‌شود.",
    )

    class Meta:
        verbose_name = "صفحه وبلاگ"
        verbose_name_plural = "صفحه وبلاگ"

    def __str__(self):
        return "تنظیمات و متن‌های وبلاگ"

    def checklist_items(self):
        return [line.strip() for line in self.review_checklist.splitlines() if line.strip()]
