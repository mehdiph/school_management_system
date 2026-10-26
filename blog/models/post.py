from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django_jalali.db import models as jmodels
from PIL import Image

from blog import content
from blog.text import normalize, reading_minutes, search_key, summary, unique_slug
from website.images import METADATA_HELP, reencode
from website.models.base import image_url
from website.validators import IMAGE_VALIDATORS

COVER_MAX_SIDE = 1600
#: The post's own moments, compared with ``timezone.now()`` in queries.
MOMENT_FIELDS = ("published_at", "submitted_at", "privacy_ack_at", "reviewed_at", "content_updated_at")
IMAGE_MAX_SIDE = 1600


def public_q(prefix=""):
    """
    The one rule of what the public sees (D8), as a ``Q`` over the posts
    at ``prefix`` ("" for posts themselves, "posts__" from a section or a
    tag): published, its time has come, and its section is active.
    """

    return Q(**{
        f"{prefix}status": Post.Status.PUBLISHED,
        f"{prefix}published_at__lte": utc_now(),
        f"{prefix}section__is_active": True,
    })


def utc_now():
    """
    ``timezone.now()`` in UTC, the zone the post's moments are written in
    (``Post.save``): on SQLite, django_jalali compares them as text, so
    both sides must carry the same offset.
    """

    return timezone.now().astimezone(dt_timezone.utc)


class PostQuerySet(models.QuerySet):
    def public(self):
        """
        Public posts (``public_q``). Every public page, feed and the
        sitemap start here; anything else is a 404 on a public URL.
        """

        return self.filter(public_q())

    def for_author(self, author):
        return self.filter(author=author)


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        SUBMITTED = "submitted", "در انتظار بررسی"
        PUBLISHED = "published", "منتشرشده"
        ARCHIVED = "archived", "بایگانی"

    section = models.ForeignKey("blog.Section", on_delete=models.PROTECT, related_name="posts", verbose_name="بخش")
    category = models.ForeignKey(
        "blog.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posts",
        verbose_name="دسته",
    )
    author = models.ForeignKey("blog.BlogAuthor", on_delete=models.PROTECT, related_name="posts", verbose_name="نویسنده")
    tags = models.ManyToManyField("blog.Tag", blank=True, related_name="posts", verbose_name="برچسب‌ها")

    title = models.CharField(max_length=120, verbose_name="عنوان")
    slug = models.SlugField(
        max_length=140,
        unique=True,
        blank=True,
        allow_unicode=True,
        verbose_name="نامک",
        help_text="بخشی از نشانی نوشته؛ اگر خالی باشد از عنوان ساخته می‌شود. پس از انتشار تغییرش "
                  "ندهید: پیوندهایی که دیگران داده‌اند خراب می‌شوند.",
    )
    excerpt = models.TextField(
        max_length=300,
        blank=True,
        verbose_name="خلاصه",
        help_text="حداکثر ۳۰۰ کاراکتر؛ در فهرست نوشته‌ها و زیر عنوان. اگر خالی باشد، آغاز متن نمایش داده می‌شود.",
    )
    body = models.TextField(blank=True, verbose_name="متن")
    cover = models.ImageField(
        upload_to="blog/covers/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="تصویر شاخص",
        help_text="افقی، حداقل ۱۲۰۰ پیکسل عرض؛ jpg، png یا webp، حداکثر ۲ مگابایت. " + METADATA_HELP,
    )
    cover_alt = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="متن جایگزین تصویر شاخص",
        help_text="توضیح کوتاه تصویر برای نابینایان و موتورهای جستجو؛ با تصویر شاخص لازم است.",
    )

    # --- Derived on save (blog.content, blog.text) ---
    body_text = models.TextField(blank=True, editable=False)
    search_text = models.TextField(blank=True, editable=False)
    toc = models.JSONField(default=list, blank=True, editable=False)
    reading_minutes = models.PositiveSmallIntegerField(default=1, editable=False)

    # --- Workflow (blog.services) ---
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="وضعیت"
    )
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")
    published_at = jmodels.jDateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان انتشار",
        help_text="نوشته منتشرشده با زمان آینده، از همان زمان در سایت دیده می‌شود (زمان‌بندی‌شده).",
    )
    submitted_at = jmodels.jDateTimeField(null=True, blank=True, editable=False, verbose_name="زمان ارسال برای بررسی")
    privacy_ack_at = jmodels.jDateTimeField(null=True, blank=True, editable=False, verbose_name="زمان تأیید حریم خصوصی")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = jmodels.jDateTimeField(null=True, blank=True, editable=False, verbose_name="زمان بررسی")
    review_note = models.TextField(
        blank=True,
        verbose_name="یادداشت ویراستار",
        help_text="وقتی نوشته به نویسنده بازگردانده می‌شود، به او نمایش داده می‌شود.",
    )

    # --- SEO ---
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        verbose_name="عنوان سئو",
        help_text="اگر خالی باشد، عنوان نوشته.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="توضیح سئو",
        help_text="حداکثر ۱۶۰ کاراکتر. اگر خالی باشد، خلاصه.",
    )

    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = jmodels.jDateTimeField(auto_now=True, verbose_name="آخرین ویرایش")
    content_updated_at = jmodels.jDateTimeField(
        null=True, blank=True, editable=False, verbose_name="به‌روزرسانی متن پس از انتشار"
    )

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "نوشته"
        verbose_name_plural = "نوشته‌ها"
        permissions = [("publish_post", "انتشار، زمان‌بندی، لغو انتشار و بازگرداندن نوشته‌ها")]
        indexes = [
            models.Index(fields=["status", "published_at"], name="blog_post_status_pub"),
            models.Index(fields=["section", "status", "published_at"], name="blog_post_section_pub"),
            models.Index(fields=["author", "status"], name="blog_post_author_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="published") | Q(published_at__isnull=False),
                name="blog_published_post_has_date",
            ),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("blog:post", args=[self.slug])

    @property
    def preview_url(self):
        return reverse("blog:preview", args=[self.pk])

    # ------------------------------------------------------------- validation

    def clean(self):
        errors = {}
        if self.category_id and self.section_id and self.category.section_id != self.section_id:
            errors["category"] = "این دسته در بخش انتخاب‌شده نیست."
        if self.section_id and not self.category_id and self.section.categories.filter(is_active=True).exists():
            errors["category"] = "برای نوشته‌های این بخش، یک دسته انتخاب کنید."
        if self.cover and not self.cover_alt.strip():
            errors["cover_alt"] = "برای تصویر شاخص، متن جایگزین بنویسید."
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------- save

    def save(self, *args, **kwargs):
        old = None
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("title", "body", "excerpt", "published_at").first()

        # django_jalali writes a moment as text with its own UTC offset, and
        # a loaded row holds Tehran-time jdatetimes: re-saved as they are,
        # SQLite (which compares the text) would put an edited post 3½ hours
        # into the future and drop it from ``public()``. Write every moment
        # in UTC, like ``timezone.now()`` that queries compare it with.
        for name in MOMENT_FIELDS:
            value = _aware(getattr(self, name))
            setattr(self, name, value.astimezone(dt_timezone.utc) if value else value)

        self.title = normalize(self.title)
        self.excerpt = normalize(self.excerpt)
        prepared = content.prepare(self.body)
        self.body = prepared.html
        self.body_text = prepared.text
        self.toc = prepared.toc
        self.reading_minutes = reading_minutes(prepared.text)
        self.search_text = search_key(" ".join([self.title, self.excerpt, prepared.text]))

        if self.cover and not self.cover._committed:
            self.cover = reencode(self.cover.file, max_side=COVER_MAX_SIDE)
        if not self.slug:
            self.slug = unique_slug(self, self.title, max_length=140, fallback="post")

        if old and old["published_at"] and any(old[f] != getattr(self, f) for f in ("title", "body", "excerpt")):
            if self.status in (self.Status.PUBLISHED, self.Status.ARCHIVED):
                self.content_updated_at = timezone.now()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # Derived fields always follow the body and the title.
            kwargs["update_fields"] = set(update_fields) | {
                "title", "excerpt", "body", "body_text", "toc", "reading_minutes", "search_text",
                "content_updated_at", "updated_at",
            }
        super().save(*args, **kwargs)
        self.prune_images()

    def prune_images(self, grace=None):
        """
        Delete inline images no longer in the body (their files go after
        commit, ``website.signals``). Images uploaded in the last day are
        kept: an author may have added one that is still only in the
        editor, not yet saved.
        """

        grace = grace if grace is not None else timedelta(days=1)
        cutoff = timezone.now() - grace
        for image in self.images.filter(created_at__lt=cutoff):
            if image.url not in self.body:
                image.delete()

    # ------------------------------------------------------------- properties

    @property
    def summary(self):
        return self.excerpt or summary(self.body_text)

    @property
    def cover_url(self):
        return image_url(self.cover)

    @property
    def is_public(self):
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and _aware(self.published_at) <= timezone.now()
            and self.section.is_active
        )

    @property
    def is_scheduled(self):
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and _aware(self.published_at) > timezone.now()
        )

    @property
    def status_label(self):
        return "زمان‌بندی‌شده" if self.is_scheduled else self.get_status_display()

    @property
    def was_published(self):
        """Published at least once: its slug is frozen for the author."""

        return self.published_at is not None

    @property
    def published_dt(self):
        """``published_at`` as an aware ``datetime`` (feeds, the sitemap, ``<time datetime>``)."""

        return _aware(self.published_at) if self.published_at else None

    @property
    def modified_dt(self):
        """When the text last changed in public: a later edit, else the publication."""

        return _aware(self.content_updated_at) if self.content_updated_at else self.published_dt

    @property
    def shows_updated(self):
        """«به‌روزرسانی: …» only for an edit more than a day after publication."""

        return bool(
            self.content_updated_at and self.published_at
            and self.modified_dt - self.published_dt > timedelta(days=1)
        )

    @property
    def seo_title(self):
        return self.meta_title or self.title

    @property
    def seo_description(self):
        return self.meta_description or summary(self.summary, 160)


def _aware(value):
    """A ``jdatetime`` from a jDateTimeField -> a ``datetime`` to compare with ``timezone.now()``."""

    return value.togregorian() if hasattr(value, "togregorian") else value


class PostImage(models.Model):
    """An image inside a post's body, uploaded from the editor and re-encoded (no EXIF, at most 1600 px)."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images", verbose_name="نوشته")
    image = models.ImageField(upload_to="blog/posts/", validators=IMAGE_VALIDATORS, verbose_name="تصویر")
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="بارگذاری‌کننده",
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ بارگذاری")

    class Meta:
        ordering = ["id"]
        verbose_name = "تصویر نوشته"
        verbose_name_plural = "تصویرهای نوشته"

    def __str__(self):
        return self.image.name

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            self.image = reencode(self.image.file, max_side=IMAGE_MAX_SIDE)
            with Image.open(self.image.file) as decoded:
                self.width, self.height = decoded.size
            self.image.file.seek(0)
        super().save(*args, **kwargs)

    @property
    def url(self):
        return self.image.url


class PostAwaitingReview(Post):
    """The «در انتظار بررسی» queue in the admin: submitted posts only, oldest first."""

    class Meta:
        proxy = True
        verbose_name = "نوشته در انتظار بررسی"
        verbose_name_plural = "در انتظار بررسی"
