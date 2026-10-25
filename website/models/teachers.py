from django.db import models

from .base import OrderedItem, SingletonModel
from .landing import _link_field


class TeachersPage(SingletonModel):
    """
    Texts and section switches of the «معلمان» page. The teachers
    themselves are ``LandingTeacher`` rows ticked «نمایش در صفحه معلمان».
    """

    show_intro = models.BooleanField(default=True, verbose_name="نمایش متن معرفی بالای صفحه")
    show_filter = models.BooleanField(
        default=True,
        verbose_name="نمایش دکمه‌های گروه‌ها",
        help_text="فقط وقتی دست‌کم دو گروه معلم منتشرشده داشته باشند نمایش داده می‌شود.",
    )
    show_cta = models.BooleanField(default=True, verbose_name="نمایش دعوت پایانی")

    # --- Intro ---
    hero_title = models.TextField(
        max_length=200,
        default="معلمان نسل قلم",
        verbose_name="عنوان صفحه",
        help_text="عنوان اصلی صفحه؛ اگر متن معرفی خاموش باشد، فقط برای صفحه‌خوان‌ها خوانده می‌شود.",
    )
    hero_text = models.TextField(
        blank=True,
        default="با معلمانی آشنا شوید که هر روز در کلاس‌ها کنار فرزندان شما هستند.",
        verbose_name="متن معرفی",
    )

    # --- List ---
    filter_label = models.CharField(
        max_length=60,
        default="گروه‌های آموزشی",
        verbose_name="نام فهرست گروه‌ها",
        help_text="برای صفحه‌خوان‌ها خوانده می‌شود و روی صفحه دیده نمی‌شود.",
    )
    all_text = models.CharField(max_length=30, default="همه", verbose_name="متن دکمه «همه»")
    list_title = models.CharField(
        max_length=100,
        default="فهرست معلمان",
        verbose_name="عنوان فهرست بدون گروه",
        help_text="وقتی هیچ گروهی به کار نرفته، برای صفحه‌خوان‌ها خوانده می‌شود و روی صفحه دیده نمی‌شود.",
    )
    other_group_title = models.CharField(
        max_length=80,
        default="سایر معلمان",
        verbose_name="عنوان معلمان بدون گروه",
        help_text="وقتی بعضی معلمان گروه دارند و بعضی نه، معلمان بدون گروه زیر این عنوان می‌آیند.",
    )
    empty_text = models.TextField(
        default="فهرست معلمان به‌زودی در این صفحه منتشر می‌شود.",
        verbose_name="متن صفحه خالی",
        help_text="وقتی هنوز هیچ معلمی برای این صفحه انتخاب نشده است.",
    )

    # --- Closing call to action ---
    cta_title = models.CharField(max_length=120, default="از نزدیک با مدرسه آشنا شوید", verbose_name="عنوان")
    cta_text = models.TextField(
        blank=True,
        default="برای بازدید از مدرسه و گفت‌وگو درباره ثبت‌نام، با دفتر مدرسه هماهنگ کنید.",
        verbose_name="توضیح",
    )
    cta_primary_text = models.CharField(max_length=40, blank=True, default="تماس با مدرسه", verbose_name="متن دکمه اول")
    cta_primary_url = _link_field("لینک دکمه اول", default="/contact/")
    cta_secondary_text = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="متن دکمه دوم",
        help_text="اختیاری. بدون متن یا لینک نمایش داده نمی‌شود.",
    )
    cta_secondary_url = _link_field("لینک دکمه دوم", default="")

    meta_title = models.CharField(
        max_length=70,
        default="معلمان",
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
        verbose_name = "صفحه معلمان"
        verbose_name_plural = "صفحه معلمان"

    def __str__(self):
        return "محتوای صفحه معلمان"

    @property
    def has_cta_secondary(self):
        return bool(self.cta_secondary_text.strip() and self.cta_secondary_url.strip())


class TeacherGroup(OrderedItem):
    """A department on the «معلمان» page («آموزگاران پایه»، «زبان انگلیسی»…): a section and a filter."""

    page = models.ForeignKey(TeachersPage, on_delete=models.CASCADE, related_name="groups", verbose_name="صفحه معلمان")
    title = models.CharField(max_length=80, verbose_name="عنوان", help_text="مثال: آموزگاران پایه، زبان انگلیسی، هنر")

    class Meta(OrderedItem.Meta):
        verbose_name = "گروه آموزشی"
        verbose_name_plural = "گروه‌های آموزشی (دسته‌بندی و فیلتر صفحه معلمان)"

    def __str__(self):
        return self.title if self.is_active else f"{self.title} (غیرفعال)"
