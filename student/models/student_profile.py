from django.db import models
from django_jalali.db import models as jmodels
from django.conf import settings
from school.models import SchoolClass

# Create your models here.

class StudentProfile(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'فعال'
        GRADUATED = 'graduated', 'فارغ التحصیل'
        TRANSFERRED = 'transferred', 'انتقالی'

    user = models.OneToOneField(
                            settings.AUTH_USER_MODEL,
                            on_delete=models.CASCADE,
                            related_name='student_profile',
                            limit_choices_to={'role': 'student'}
                        )
    student_code = models.CharField(
                            max_length=20,
                            unique=True,
                            verbose_name='کد دانش آموزی'
                        )
    school_class = models.ForeignKey(
                            SchoolClass,
                            on_delete=models.PROTECT,
                            related_name='students',
                            verbose_name='کلاس'
                        )
    enrollment_date = jmodels.jDateField(
                            verbose_name='تاریخ ثبت نام'
                        )
    status = models.CharField(
                            max_length=20,
                            choices=Status.choices,
                            verbose_name='وضعیت'
                        )
    
    class Meta:
        verbose_name = 'پروفایل دانش آموز'
        verbose_name_plural = 'پروفایل دانش آموزان'

    def __str__(self):
        return self.user.get_full_name()