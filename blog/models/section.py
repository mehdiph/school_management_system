from django.db import models
from django_jalali.db import models as jmodels

from blog.text import normalize, unique_slug

SLUG_HELP = (
    "بخشی از نشانی صفحه. اگر خالی باشد از عنوان ساخته می‌شود؛ تغییرش پیوندهایی را که "
    "دیگران به این صفحه داده‌اند خراب می‌کند."
)


class Paper(models.TextChoices):
    """The coloured card a section is printed on (blog.css); every one passes contrast with navy text."""

    TOMATO = "tomato", "گوجه‌ای"
    SUNFLOWER = "sunflower", "آفتابگردانی"
    GRASS = "grass", "چمنی"
    SKY = "sky", "آسمانی"
    GRAPE = "grape", "انگوری"
    BUBBLEGUM = "bubblegum", "آدامسی"


class Section(models.Model):
    """A part of the blog with its own authors: «پرورشی»، «مشاوره»."""

    title = models.CharField(max_length=60, verbose_name="عنوان")
    slug = models.SlugField(max_length=80, unique=True, blank=True, allow_unicode=True, verbose_name="نامک", help_text=SLUG_HELP)
    description = models.CharField(max_length=200, blank=True, verbose_name="توضیح یک‌خطی")
    paper = models.CharField(max_length=20, choices=Paper.choices, default=Paper.SKY, verbose_name="رنگ کاغذ")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
        help_text="بخش غیرفعال و همه نوشته‌هایش در سایت دیده نمی‌شوند و کسی در آن نمی‌نویسد.",
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "بخش"
        verbose_name_plural = "بخش‌ها"

    def __str__(self):
        return self.title if self.is_active else f"{self.title} (غیرفعال)"

    def save(self, *args, **kwargs):
        self.title = normalize(self.title)
        if not self.slug:
            self.slug = unique_slug(self, self.title, fallback="section")
        super().save(*args, **kwargs)


class Category(models.Model):
    """A shelf inside a section («اردو و گردش»): a post's optional second level."""

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="categories", verbose_name="بخش")
    title = models.CharField(max_length=60, verbose_name="عنوان")
    slug = models.SlugField(max_length=80, blank=True, allow_unicode=True, verbose_name="نامک", help_text=SLUG_HELP)
    order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
        help_text="نوشته‌های دسته غیرفعال دیده می‌شوند، ولی پیوند و صفحه دسته نه.",
    )

    class Meta:
        ordering = ["section", "order", "id"]
        verbose_name = "دسته"
        verbose_name_plural = "دسته‌ها"
        constraints = [
            models.UniqueConstraint(fields=["section", "slug"], name="blog_unique_category_slug_per_section"),
        ]

    def __str__(self):
        return self.title if self.is_active else f"{self.title} (غیرفعال)"

    def save(self, *args, **kwargs):
        self.title = normalize(self.title)
        if not self.slug:
            self.slug = unique_slug(self, self.title, fallback="category", section_id=self.section_id)
        super().save(*args, **kwargs)
