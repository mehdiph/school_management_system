from django.db import models
from django.contrib.auth.models import User
from django_jalali.db import models as jmodels
from django.forms import ValidationError
from django.conf import settings

# Create your models here.

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


class SchoolClass(models.Model):
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, verbose_name='سال تحصیلی')
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, verbose_name='پایه')
    section = models.CharField(max_length=255, verbose_name='نام کلاس')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'کلاس'
        verbose_name_plural = 'کلاس‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.grade.name} - {self.section}"

    
class ClassSubject(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.DO_NOTHING, verbose_name='کلاس')
    subject = models.ForeignKey(Subject, on_delete=models.DO_NOTHING, verbose_name='درس')
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

