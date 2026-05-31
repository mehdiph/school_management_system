from django.db import models
from django_jalali.db import models as jmodels

class AcademicYear(models.Model):
    title = models.CharField(max_length=50, verbose_name='عنوان')
    start_date = jmodels.jDateField(verbose_name='تاریخ شروع')
    end_date = jmodels.jDateField(verbose_name='تاریخ پایان')
    is_current = models.BooleanField(default=False, verbose_name='سال جاری')
    is_active = models.BooleanField(default=False, verbose_name='فعال')

    class Meta:
        verbose_name = 'سال تحصیلی'
        verbose_name_plural = 'سال‌های تحصیلی'
        ordering = ['-start_date']

    def __str__(self):
        return self.title