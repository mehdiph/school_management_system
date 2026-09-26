from django.db import models
from django_jalali.db import models as jmodels

from school.colors import DEFAULT_SUBJECT_COLOR, hex_color_validator


class Subject(models.Model):
    name = models.CharField(max_length=255, verbose_name='نام درس')
    slug = models.SlugField(max_length=255, verbose_name='نامک')
    color = models.CharField(
        max_length=7,
        default=DEFAULT_SUBJECT_COLOR,
        validators=[hex_color_validator],
        verbose_name='رنگ',
        help_text='رنگ این درس در برنامه هفتگی و فایل PDF آن.',
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'درس'
        verbose_name_plural = 'دروس'
        ordering = ['name']

    def save(self, *args, **kwargs):
        # One canonical spelling, so "#2563EB" and "#2563eb" never differ.
        if self.color:
            self.color = self.color.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
