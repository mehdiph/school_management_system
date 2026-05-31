from django.db import models
from django_jalali.db import models as jmodels



class SessionContent(models.Model):
    session = models.OneToOneField('teaching.SchoolSession', on_delete=models.DO_NOTHING, verbose_name='جلسه')
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