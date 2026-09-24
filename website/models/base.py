from django.db import models
from django.templatetags.static import static
from django_jalali.db import models as jmodels


class SingletonModel(models.Model):
    """
    A model with exactly one row, always stored under ``pk=1``.

    ``delete()`` is a no-op so the row the whole site reads from can't
    disappear; the admin additionally hides the add/delete buttons
    (see ``website.admin.SingletonAdmin``).
    """

    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = jmodels.jDateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        if self._state.adding and self.created_at is None:
            # A fresh instance saved over the existing row becomes an
            # UPDATE, where auto_now_add doesn't fire: keep the original.
            self.created_at = (
                type(self).objects.filter(pk=1).values_list("created_at", flat=True).first()
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return 0, {}

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class OrderedItem(models.Model):
    """Common fields for the repeatable blocks shown on the landing page."""

    order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        abstract = True
        ordering = ["order", "id"]


def image_url(field_file, static_path=""):
    """
    URL of an uploaded image, falling back to a bundled static file.

    The seed data migration points rows at the original design's images
    in ``website/static`` instead of copying them into MEDIA_ROOT, so an
    empty upload field still renders the page exactly as designed.
    """

    if field_file:
        return field_file.url
    if static_path:
        return static(static_path)
    return ""
