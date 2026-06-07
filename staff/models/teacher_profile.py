from django.db import models
from django_jalali.db import models as jmodels
    

class TeacherProfile(models.Model):
    """
    Teachers specific information just for users that have teacher role
    """

    staff = models.OneToOneField('staff.Staff',
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