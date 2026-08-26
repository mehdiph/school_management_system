from django.db import models
from core.managers.base import BranchManager

class Branch(models.Model):
    objects = BranchManager()
    name = models.CharField(max_length=100, unique=True, verbose_name='نام')
    code = models.SlugField(max_length=30, unique=True, verbose_name='کد')
    address = models.TextField(blank=True, verbose_name='آدرس')
    phone_number = models.CharField(max_length=20, blank=True, verbose_name='شماره تلفن')
    order = models.PositiveSmallIntegerField(default=1, verbose_name='ترتیب')
    is_active = models.BooleanField(default=True, verbose_name='وضعیت')

    class Meta:
        verbose_name = 'شعبه'
        verbose_name_plural = 'شعبه ها'

    def __str__(self):
        return self.name