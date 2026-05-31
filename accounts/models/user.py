from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.

class User(AbstractUser):
    class Roles(models.TextChoices):
        STUDENT = 'student', 'دانش آموز'
        TEACHER = 'teacher', 'معلم'
        SUPERVISOR = 'supervisor', 'پشتیبان'
        ACCOUNTANT = 'accountant', 'حسابدار'
        COUNSELOR = 'counselor', 'مشاور'
        IT = 'it', 'انفورماتیک'
        SERVICES = 'services', 'خدمات'
        ADMIN = 'admin', 'مدیر'

    role = models.CharField(choices=Roles.choices, max_length=20, verbose_name='نقش')
    phone_number = models.CharField(max_length=20, verbose_name='شماره تماس')
    avatar = models.ImageField(upload_to='users/avatars/', blank=True, null=True, verbose_name='تصویر پروفایل')

    def __str__(self):
        return self.get_full_name() or self.username