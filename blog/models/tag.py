from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from blog.text import normalize, search_key, unique_slug


class TagQuerySet(models.QuerySet):
    def named(self, name):
        """The tag whose name is ``name`` in any spelling: «كتاب خوانی» finds «کتاب‌خوانی»."""

        key = search_key(name)
        return self.filter(key=key) if key else self.none()


class Tag(models.Model):
    """
    A free label on posts. One row per spelling-independent ``key``, so
    «کتاب‌خوانی» and «كتاب خوانی» are the same tag (D14).
    """

    name = models.CharField(max_length=40, verbose_name="نام")
    key = models.CharField(max_length=60, unique=True, editable=False)
    slug = models.SlugField(max_length=60, unique=True, blank=True, allow_unicode=True, verbose_name="نامک")
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
        help_text="برچسب غیرفعال روی نوشته‌ها می‌ماند، ولی نمایش داده نمی‌شود و صفحه ندارد.",
    )

    objects = TagQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "برچسب"
        verbose_name_plural = "برچسب‌ها"

    def __str__(self):
        return self.name if self.is_active else f"{self.name} (غیرفعال)"

    def get_absolute_url(self):
        return reverse("blog:tag", args=[self.slug])

    def save(self, *args, **kwargs):
        self.name = normalize(self.name)
        self.key = search_key(self.name)
        if not self.slug:
            self.slug = unique_slug(self, self.name, max_length=60, fallback="tag")
        super().save(*args, **kwargs)

    def validate_unique(self, exclude=None):
        # ``key`` is not on the form: report a clash on ``name`` instead.
        super().validate_unique(exclude)
        key = search_key(self.name)
        if key and Tag.objects.filter(key=key).exclude(pk=self.pk).exists():
            raise ValidationError({"name": "برچسبی با همین نام (با املای دیگر) وجود دارد."})
