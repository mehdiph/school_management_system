from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django_jalali.db import models as jmodels

from blog.text import normalize, unique_slug
from website.images import METADATA_HELP, PUBLIC_PHOTO_HELP, reencode_new_photo
from website.models.base import image_url
from website.validators import IMAGE_VALIDATORS


def author_user_choices():
    """
    Users the admin may pick for a ``BlogAuthor``: holders of an eligible
    role (``BLOG_AUTHOR_ROLES``), plus whoever already is an author, so an
    author whose role changed can still be opened and deactivated.
    """

    return Q(role__in=settings.BLOG_AUTHOR_ROLES) | Q(blog_author__isnull=False)


class BlogAuthor(models.Model):
    """
    A person the website admin lets write in the blog, and their public
    byline. Being an author is a grant on top of a role, like
    ``BranchAccess`` on top of teaching: whether they can write right now
    is decided in one place, ``blog.permissions`` (D4).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="blog_author",
        limit_choices_to=author_user_choices,
        verbose_name="کاربر",
        help_text="فقط معلمان، مشاوران، پشتیبان‌ها، مدیر مدرسه و مدیر سامانه می‌توانند نویسنده باشند؛ "
                  "دانش‌آموزان هرگز.",
    )
    sections = models.ManyToManyField(
        "blog.Section",
        through="blog.AuthorSection",
        through_fields=("author", "section"),
        related_name="authors",
        blank=True,
        verbose_name="بخش‌هایی که می‌تواند در آن‌ها بنویسد",
    )
    display_name = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="نام نمایشی",
        help_text="اگر خالی باشد، نام و نام خانوادگی حساب نمایش داده می‌شود؛ نام کاربری هرگز.",
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        blank=True,
        allow_unicode=True,
        verbose_name="نامک (برای لینک صفحه نویسنده)",
        help_text="اگر خالی باشد، از نام ساخته می‌شود و بعد از آن با تغییر نام عوض نمی‌شود.",
    )
    bio = models.TextField(
        max_length=600,
        blank=True,
        verbose_name="معرفی کوتاه",
        help_text="حداکثر ۶۰۰ کاراکتر؛ زیر نوشته‌ها و در صفحه نویسنده. اگر خالی باشد، معرفی کارت معلم "
                  "(اگر انتخاب شده باشد) نمایش داده می‌شود.",
    )
    photo = models.ImageField(
        upload_to="blog/authors/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="عکس",
        help_text="مربعی، حداقل ۴۰۰×۴۰۰؛ jpg، png یا webp، حداکثر ۲ مگابایت. " + PUBLIC_PHOTO_HELP + " "
                  + METADATA_HELP + " بدون عکس، عکس کارت معلم و بعد حرف اول نام نمایش داده می‌شود.",
    )
    teacher_card = models.ForeignKey(
        "website.LandingTeacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_authors",
        verbose_name="کارت معلم در صفحه معلمان",
        help_text="اختیاری. پیوند «صفحه معلم» فقط وقتی نمایش داده می‌شود که این کارت در صفحه معلمان "
                  "منتشر شده باشد.",
    )
    show_profile = models.BooleanField(
        default=True,
        verbose_name="نمایش صفحه نویسنده",
        help_text="خاموش: صفحه نویسنده و پیوند نام او حذف می‌شوند؛ نامش روی نوشته‌ها می‌ماند.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="اجازه نوشتن",
        help_text="خاموش: دیگر نمی‌تواند بنویسد. نوشته‌های منتشرشده‌اش در سایت می‌مانند.",
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        ordering = ["display_name", "id"]
        verbose_name = "نویسنده وبلاگ"
        verbose_name_plural = "نویسندگان وبلاگ"

    def __str__(self):
        return self.name or "نویسنده"

    def clean(self):
        if self.user_id is None:
            return
        user_changed = self._state.adding or not type(self).objects.filter(pk=self.pk, user_id=self.user_id).exists()
        if user_changed and self.user.role not in settings.BLOG_AUTHOR_ROLES:
            raise ValidationError({"user": "نقش این کاربر اجازه نویسندگی در وبلاگ را ندارد."})
        if not self.name:
            raise ValidationError(
                {"display_name": "حساب این کاربر نام و نام خانوادگی ندارد؛ نام نمایشی را بنویسید."}
            )

    def save(self, *args, **kwargs):
        self.display_name = normalize(self.display_name)
        reencode_new_photo(self, "photo")
        if not self.slug:
            self.slug = unique_slug(self, self.name, fallback="author")
        super().save(*args, **kwargs)

    @property
    def name(self):
        """The public name: the display name, else the account's first and last name. Never the username."""

        if self.display_name.strip():
            return self.display_name.strip()
        if self.user_id is None:
            return ""
        return normalize(f"{self.user.first_name} {self.user.last_name}")

    @property
    def initial(self):
        return self.name[:1] or "?"

    @property
    def photo_url(self):
        """The author's own photo, else the linked teacher card's photo. Never the account avatar (ADR-025)."""

        if self.photo:
            return image_url(self.photo)
        if self.teacher_card_id and self.teacher_card.photo_override:
            return image_url(self.teacher_card.photo_override)
        return ""

    @property
    def public_bio(self):
        if self.bio.strip():
            return self.bio.strip()
        if self.teacher_card_id:
            return self.teacher_card.bio.strip()
        return ""


class AuthorSection(models.Model):
    """A section an author may write in, with who granted it and when."""

    author = models.ForeignKey(BlogAuthor, on_delete=models.CASCADE, related_name="grants", verbose_name="نویسنده")
    section = models.ForeignKey("blog.Section", on_delete=models.CASCADE, related_name="grants", verbose_name="بخش")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="اجازه‌دهنده",
    )
    granted_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ اجازه")

    class Meta:
        ordering = ["section__order", "section_id"]
        verbose_name = "اجازه نوشتن در بخش"
        verbose_name_plural = "اجازه‌های نوشتن در بخش‌ها"
        constraints = [
            models.UniqueConstraint(fields=["author", "section"], name="blog_unique_author_section"),
        ]

    def __str__(self):
        return f"{self.author} — {self.section}"
