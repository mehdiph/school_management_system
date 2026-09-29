from django.conf import settings
from django.db import models


class LoginActivity(models.Model):
    """
    One successful sign-in (``user_logged_in``, see accounts.signals).

    ``session_key`` is set while that sign-in's session may still be
    alive, so "sign out of other devices" can end exactly those sessions
    (accounts.sessions.end_other_sessions). It is cleared on logout and
    when the session is ended from another device.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='login_activities',
        verbose_name='کاربر',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ورود')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='آی‌پی')
    user_agent = models.CharField(max_length=512, blank=True, default='', verbose_name='مرورگر (کامل)')
    browser = models.CharField(max_length=64, blank=True, default='', verbose_name='مرورگر')
    os = models.CharField(max_length=64, blank=True, default='', verbose_name='سیستم‌عامل')
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True, verbose_name='کلید نشست')

    class Meta:
        verbose_name = 'ورود'
        verbose_name_plural = 'ورودها'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='login_activity_user_idx'),
        ]

    def __str__(self):
        return f'{self.user} | {self.created_at:%Y-%m-%d %H:%M}'
