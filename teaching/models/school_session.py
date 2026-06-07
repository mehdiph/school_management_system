from django.db import models
from django_jalali.db import models as jmodels

class SchoolSession(models.Model):
    class Status(models.TextChoices):
        COMPENSATORY = 'JB', 'جبرانی'
        CANCELED = 'CD', 'کنسل شده'
        HELD = 'HD', 'برگزار شده'

    class_subject = models.ForeignKey('school.ClassSubject', on_delete=models.DO_NOTHING, verbose_name='درس کلاس', related_name='sessions')
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