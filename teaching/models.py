from django.db import models
from django_jalali.db import models as jmodels
from school.models import ClassSubject

# Create your models here.

class SchoolSession(models.Model):
    class Status(models.TextChoices):
        COMPENSATORY = 'JB', 'جبرانی'
        CANCELED = 'CD', 'کنسل شده'
        HELD = 'HD', 'برگزار شده'

    class_subject = models.ForeignKey(ClassSubject, on_delete=models.DO_NOTHING, verbose_name='درس کلاس')
    date = jmodels.jDateField(verbose_name='تاریخ جلسه')
    session_number = models.IntegerField(verbose_name='شماره جلسه')
    status = models.CharField(
        max_length=2,
        choices=Status,
        default=Status.HELD,
        verbose_name='وضعیت'
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')

    class Meta:
        verbose_name = 'جلسه درسی'
        verbose_name_plural = 'جلسات درسی'
        ordering = ['-date', '-session_number']

    def __str__(self):
        return f"{self.class_subject} - جلسه {self.session_number}"

class SessionContent(models.Model):
    session = models.OneToOneField(SchoolSession, on_delete=models.DO_NOTHING, verbose_name='جلسه')
    title = models.CharField(max_length=255, verbose_name='عنوان')
    content = models.TextField(verbose_name='محتوا')
    activity = models.TextField(verbose_name='فعالیت')
    homework = models.TextField(verbose_name='تکلیف')
    notes = models.TextField(verbose_name='یادداشت‌ها')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')

    class Meta:
        verbose_name = 'محتوای جلسه'
        verbose_name_plural = 'محتوای جلسات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.session} - {self.title}"