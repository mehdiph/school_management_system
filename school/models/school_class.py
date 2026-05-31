from django.db import models
from django_jalali.db import models as jmodels

class SchoolClass(models.Model):
    year = models.ForeignKey('school.AcademicYear', on_delete=models.CASCADE, verbose_name='سال تحصیلی')
    grade = models.ForeignKey('school.Grade', on_delete=models.CASCADE, verbose_name='پایه')
    section = models.CharField(max_length=255, verbose_name='نام کلاس')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'کلاس'
        verbose_name_plural = 'کلاس‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.grade.name} - {self.section}"