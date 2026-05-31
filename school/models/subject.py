from django.db import models
from django_jalali.db import models as jmodels


class Subject(models.Model):
    name = models.CharField(max_length=255, verbose_name='نام درس')
    slug = models.SlugField(max_length=255, verbose_name='نامک')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'درس'
        verbose_name_plural = 'دروس'
        ordering = ['name']

    def __str__(self):
        return self.name