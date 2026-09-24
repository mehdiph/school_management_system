from django.db import models
from django_jalali.db import models as jmodels


class BranchAccess(models.Model):
    """
    *Explicit* branch access for a staff member.

    This is not the whole picture: a teacher automatically gets access
    to the branches of their active assignments in the current academic
    year, and a supervisor to the branch on their profile. Rows here are
    only needed for staff who do not teach (accountant, IT, services,
    ...) or to grant a teacher access on top of what they teach.

    See ``core.services.access`` -- never query this model directly to
    decide what somebody may see.
    """

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
        help_text=(
            "دسترسی مستقیم و اضافی به این شعبه. معلمان به‌صورت خودکار به "
            "شعبه‌ی انتساب‌های فعال خود در سال تحصیلی جاری دسترسی دارند و "
            "نیازی به ثبت این رکورد ندارند."
        ),
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name="شعبه پیش‌فرض",
        help_text=(
            "شعبه‌ای که پس از ورود به‌صورت پیش‌فرض انتخاب می‌شود. برای هر "
            "پرسنل حداکثر یک شعبه می‌تواند پیش‌فرض باشد."
        ),
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
            ),
            # At most one default branch per staff member. Conditional,
            # so the many ``is_default=False`` rows a staff member may
            # have stay unaffected.
            models.UniqueConstraint(
                fields=["staff"],
                condition=models.Q(is_default=True),
                name="unique_default_branch_access_per_staff",
            ),
        ]

    def __str__(self):
        return f"{self.staff} → {self.branch}"
