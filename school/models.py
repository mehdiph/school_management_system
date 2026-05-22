from django.db import models
from django.contrib.auth.models import User
from django_jalali.db import models as jmodels
from django.forms import ValidationError

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
    teacher = models.ForeignKey(User, on_delete=models.DO_NOTHING, verbose_name='معلم')
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

class ClassSchedule(models.Model):
    class DayChoices(models.IntegerChoices):
        SATURDAY = 0, 'شنبه'
        SUNDAY = 1, 'یکشنبه'
        MONDAY = 2, 'دوشنبه'
        TUESDAY = 3, 'سه‌شنبه'
        WEDNESDAY = 4, 'چهارشنبه'
        THURSDAY = 5, 'پنج‌شنبه'

    class WeekTypeChoices(models.IntegerChoices):
        WEEK_ONE = 1, 'هفته اول'
        WEEK_TWO = 2, 'هفته دوم'
        BOTH = 3, 'هر دو هفته'

    class_room = models.ForeignKey(
        ClassSubject,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name='کلاس درس'
    )
    day_of_week = models.IntegerField(choices=DayChoices, verbose_name='روز هفته')
    week_type = models.IntegerField(
        choices=WeekTypeChoices,
        default=WeekTypeChoices.BOTH,
        verbose_name='نوع هفته'
    )
    start_time = models.TimeField(verbose_name='زمان شروع')
    end_time = models.TimeField(verbose_name='زمان پایان')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')

    class Meta:
        verbose_name = 'برنامه کلاسی'
        verbose_name_plural = 'برنامه‌های کلاسی'
        ordering = ['day_of_week', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['class_room', 'day_of_week', 'week_type', 'start_time'],
                name='uniq_class_schedule_slot'
            )
        ]

    def __str__(self):
        return (
            f"{self.class_room} | "
            f"{self.get_day_of_week_display()} | "
            f"{self.start_time}-{self.end_time}"
        )

    def clean(self):
        super().clean()

        if not self.class_room_id:
            return

        if self.start_time >= self.end_time:
            raise ValidationError({'end_time': 'زمان پایان باید بعد از زمان شروع باشد.'})

        if self.week_type == self.WeekTypeChoices.BOTH:
            applicable_weeks = [
                self.WeekTypeChoices.WEEK_ONE,
                self.WeekTypeChoices.WEEK_TWO,
                self.WeekTypeChoices.BOTH,
            ]
        elif self.week_type == self.WeekTypeChoices.WEEK_ONE:
            applicable_weeks = [self.WeekTypeChoices.WEEK_ONE, self.WeekTypeChoices.BOTH]
        else:
            applicable_weeks = [self.WeekTypeChoices.WEEK_TWO, self.WeekTypeChoices.BOTH]

        overlap_qs = ClassSchedule.objects.filter(
            class_room__teacher=self.class_room.teacher,
            day_of_week=self.day_of_week,
            week_type__in=applicable_weeks,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        )

        if self.pk:
            overlap_qs = overlap_qs.exclude(pk=self.pk)

        if overlap_qs.exists():
            raise ValidationError(
                'برای این معلم در همین روز/هفته، بازه زمانی همپوشان ثبت شده است.'
            )