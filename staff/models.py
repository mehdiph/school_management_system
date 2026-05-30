from django.db import models
from django.conf import settings
from django_jalali.db import models as jmodels

# Create your models here.

class Staff(models.Model):
    """
    all public informations about school employees
    """

    class Gender(models.TextChoices):
        MALE = 'male', 'مرد'
        FEMALE = 'female', 'زن'

    user = models.OneToOneField(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='staff_profile',
                                verbose_name='کاربر'
                                )
    personnel_code = models.CharField(max_length=20,
                                      unique=True,
                                      verbose_name='کد پرسنلی'
                                      )
    national_code = models.CharField(max_length=10,
                                     unique=True,
                                     verbose_name='کد ملی'
                                     )
    gender = models.CharField(choices=Gender.choices,
                              max_length=10,
                              verbose_name='جنسیت'
                              )
    birth_date = jmodels.jDateField(blank=True,
                                    null=True,
                                    verbose_name='تاریخ تولد'
                                    )
    hire_date = jmodels.jDateField(verbose_name='تاریخ استخدام')
    address = models.TextField(blank=True,
                               null=True,
                               verbose_name='آدرس'
                               )
    emergency_phone = models.CharField(max_length=15,
                                       blank=True,
                                       null=True,
                                       verbose_name='شماره تماس اضطراری'
                                       )
    is_active = models.BooleanField(default=True,
                                    verbose_name='فعال'
                                    )
    created_at = jmodels.jDateTimeField(auto_now_add=True,
                                        verbose_name='تاریخ ایجاد',
                                        )
    updated_at = jmodels.jDateTimeField(auto_now=True,
                                        verbose_name='آخرین بروزرسانی',
                                        )
    
    class Meta:
        verbose_name = 'پرسنل'
        verbose_name_plural = 'پرسنل'
        ordering = ['user__first_name', 'user__last_name']

    def __str__(self):
        return self.user.get_full_name()
    

class TeacherProfile(models.Model):
    """
    Teachers specific information just for users that have teacher role
    """

    staff = models.OneToOneField(Staff,
                                 on_delete=models.CASCADE,
                                 related_name='teacher_profile',
                                 verbose_name='پرسنل',
                                 limit_choices_to={'user__role': 'teacher'}
                                 )
    education = models.CharField(max_length=255,
                                 blank=True,
                                 null=True,
                                 verbose_name='مدرک تحصیلی'
                                 )
    field_of_study = models.CharField(max_length=255,
                                      blank=True,
                                      null=True,
                                      verbose_name='رشته تحصیلی'
                                      )
    teaching_experience = models.PositiveIntegerField(default=0,
                                                      verbose_name='سابقه تدریس',
                                                      )
    is_homeroom_teacher = models.BooleanField(default=True,
                                              verbose_name='معلم ثابت'
                                              )
    created_at = jmodels.jDateTimeField(auto_now_add=True,
                                        verbose_name='تاریخ ایجاد',
                                        )
    updated_at = jmodels.jDateTimeField(auto_now=True,
                                        verbose_name='آخرین بروزرسانی',
                                        )
    
    class Meta:
        verbose_name = 'پروفایل معلم'
        verbose_name_plural = 'پروفایل معلمان'

    def __str__(self):
        return self.staff.user.get_full_name()