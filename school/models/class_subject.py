from django.db import models
from django_jalali.db import models as jmodels
from django.conf import settings

class ClassSubject(models.Model):
    school_class = models.ForeignKey('school.SchoolClass', on_delete=models.DO_NOTHING, verbose_name='کلاس')
    subject = models.ForeignKey('school.Subject', on_delete=models.DO_NOTHING, verbose_name='درس')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, verbose_name='معلم', limit_choices_to={'role': 'teacher'})
    start_date = jmodels.jDateField(verbose_name='تاریخ شروع')
    end_date = jmodels.jDateField(verbose_name='تاریخ پایان')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'درس کلاس'
        verbose_name_plural = 'دروس کلاس‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school_class} - {self.subject.name}"