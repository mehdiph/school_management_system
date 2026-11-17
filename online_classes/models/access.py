from django.conf import settings
from django.db import models
from django.db.models import Q
from django_jalali.db import models as jmodels

from .. import crypto

#: Stored encrypted (D14). Read through ``secret``, never loaded into a page by accident.
SECRET_FIELDS = ("url_encrypted", "password_encrypted", "access_code_encrypted")


class OnlineEventAccess(models.Model):
    """
    One student's way into a personal-mode event: a link and/or a username,
    password or access code. The link, password and code are encrypted at rest
    in explicit ``*_encrypted`` columns: they appear in the admin history, logs
    and ``dumpdata`` only as tokens, and reading one is a deliberate call.
    """

    event = models.ForeignKey(
        "online_classes.OnlineEvent", on_delete=models.CASCADE, related_name="access_rows", verbose_name="رویداد"
    )
    student = models.ForeignKey(
        "student.StudentProfile", on_delete=models.CASCADE, related_name="+", verbose_name="دانش‌آموز"
    )
    url_encrypted = models.TextField(blank=True, editable=False)
    username = models.CharField(max_length=150, blank=True, verbose_name="نام کاربری")
    password_encrypted = models.TextField(blank=True, editable=False)
    access_code_encrypted = models.TextField(blank=True, editable=False)
    note = models.CharField(max_length=300, blank=True, verbose_name="توضیح")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="+", verbose_name="آخرین ویرایش توسط",
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = jmodels.jDateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "دسترسی شخصی"
        verbose_name_plural = "دسترسی‌های شخصی"
        ordering = ["student__user__last_name", "student__user__first_name", "pk"]
        permissions = [
            ("view_access_secret", "می‌تواند رمز، کد و لینک شخصی دانش‌آموزان را ببیند"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["event", "student"], name="unique_online_access_per_student"),
            models.CheckConstraint(
                condition=~Q(url_encrypted="", username="", password_encrypted="", access_code_encrypted=""),
                name="online_access_has_a_way_in",
            ),
        ]

    def __str__(self):
        return f"دسترسی شخصی #{self.pk}"

    def set_secrets(self, *, url=None, password=None, access_code=None):
        """``None`` keeps a value; a blank one never overwrites it (D15, D18)."""

        if url:
            self.url_encrypted = crypto.encrypt(url)
        if password:
            self.password_encrypted = crypto.encrypt(password)
        if access_code:
            self.access_code_encrypted = crypto.encrypt(access_code)

    def read_secrets(self):
        """``{"url", "password", "access_code"}`` in plain text, or ``crypto.DecryptionFailed``."""

        return {
            "url": crypto.decrypt(self.url_encrypted),
            "password": crypto.decrypt(self.password_encrypted),
            "access_code": crypto.decrypt(self.access_code_encrypted),
        }
