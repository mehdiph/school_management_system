from django.db import models
from django_jalali.db import models as jmodels


class BranchAccess(models.Model):
    staff = models.ForeignKey(
        "staff.Staff",
        on_delete=models.CASCADE,
        related_name="branch_accesses",
        verbose_name="پرسنل",
    )

    branch = models.ForeignKey(
        "school.Branch",
        on_delete=models.CASCADE,
        related_name="staff_accesses",
        verbose_name="شعبه",
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name="شعبه پیش‌فرض",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "دسترسی به شعبه"
        verbose_name_plural = "دسترسی‌های شعبه"

        constraints = [
            models.UniqueConstraint(
                fields=["staff", "branch"],
                name="unique_staff_branch_access",
            )
        ]

    def __str__(self):
        return f"{self.staff} → {self.branch}"