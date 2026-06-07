from django.db import models
from django_jalali.db import models as jmodels

class Grade(models.Model):
    name = models.CharField(max_length=255, verbose_name='نام')
    level = models.IntegerField(unique=True, verbose_name='سطح')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'پایه تحصیلی'
        verbose_name_plural = 'پایه‌های تحصیلی'
        ordering = ['level']

    def __str__(self):
        return self.name