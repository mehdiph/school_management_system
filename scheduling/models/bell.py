from django.db import models

class Bell(models.Model):
    title = models.CharField(
        max_length=50,
        verbose_name='عنوان'
    )

    order = models.PositiveSmallIntegerField(
        unique=True,
        verbose_name='ترتیب'
    )

    start_time = models.TimeField(
        verbose_name='زمان شروع'
    )

    end_time = models.TimeField(
        verbose_name='زمان پایان'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )

    class Meta:
        verbose_name = 'زنگ'
        verbose_name_plural = 'زنگ ها'

    def __str__(self):
        return self.title