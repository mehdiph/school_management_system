from django.db import models
from django.contrib.auth.models import AbstractUser

from accounts.validators import validate_national_code

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
    phone_number = models.CharField(max_length=20, blank=True, default='', verbose_name='شماره تماس')
    # The single source of truth for a person's national code (Staff used
    # to carry its own copy). Null only for legacy / superuser accounts.
    national_code = models.CharField(
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_national_code],
        verbose_name='کد ملی',
    )
    # Set for accounts created with a known password (the Excel import
    # uses the national code). Cleared only by a successful password
    # change -- see accounts.middleware and accounts.views.password_change.
    must_change_password = models.BooleanField(default=False, verbose_name='باید رمز عبور را تغییر دهد')
    avatar = models.ImageField(upload_to='users/avatars/', blank=True, null=True, verbose_name='تصویر پروفایل')

    @property
    def avatar_url(self):
        """
        The avatar's URL, or None when none is set. Never raises.

        Deliberately does not check the file exists (that would hit
        storage on every page): a path whose file is gone still gets a
        URL, and ``partials/avatar.html`` falls back to ``initials`` in
        the browser when the image fails to load.
        """

        if not self.avatar:
            return None
        try:
            return self.avatar.url
        except (ValueError, OSError):
            return None

    @property
    def initials(self):
        """One letter for the avatar placeholder: first name, else last name, else username."""

        for name in (self.first_name, self.last_name, self.username):
            name = (name or "").strip()
            if name:
                return name[0].upper()
        return "?"

    def __str__(self):
        return self.get_full_name() or self.username