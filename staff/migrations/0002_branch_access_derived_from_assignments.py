"""
Backs the "branch access is derived, not stored" change:

  * documents ``BranchAccess`` as *explicit/extra* access (help texts),
  * guarantees at most one default branch per staff member,
  * indexes the active-assignment lookup the access service runs on
    every branch-scoped request.

The constraint is guarded by a data step: an existing database may
already hold several ``is_default=True`` rows for one staff member
(nothing prevented it until now), and ``AddConstraint`` would abort the
whole deploy on such a row. No ``BranchAccess`` row is ever deleted
here -- see the ``cleanup_redundant_branch_access`` management command
for that, which is opt-in and reviewed first.
"""

import django.db.models.deletion
from django.db import migrations, models


def demote_duplicate_default_branches(apps, schema_editor):
    """
    Keeps the oldest ``is_default=True`` row per staff member and clears
    the flag on the rest, so the conditional unique constraint below can
    be created.
    """

    BranchAccess = apps.get_model("staff", "BranchAccess")

    seen_staff_ids = set()
    demoted_ids = []

    for row in (
        BranchAccess.objects
        .filter(is_default=True)
        .order_by("staff_id", "pk")
        .only("pk", "staff_id")
    ):
        if row.staff_id in seen_staff_ids:
            demoted_ids.append(row.pk)
        else:
            seen_staff_ids.add(row.staff_id)

    if demoted_ids:
        BranchAccess.objects.filter(pk__in=demoted_ids).update(is_default=False)

        print(
            f"  Demoted {len(demoted_ids)} duplicate default BranchAccess "
            f"row(s) (ids: {demoted_ids}); the oldest one per staff member "
            f"was kept."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0004_alter_branch_options_alter_branch_address_and_more'),
        ('staff', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='branchaccess',
            name='branch',
            field=models.ForeignKey(help_text='دسترسی مستقیم و اضافی به این شعبه. معلمان به‌صورت خودکار به شعبه‌ی انتساب‌های فعال خود در سال تحصیلی جاری دسترسی دارند و نیازی به ثبت این رکورد ندارند.', on_delete=django.db.models.deletion.CASCADE, related_name='staff_accesses', to='school.branch', verbose_name='شعبه'),
        ),
        migrations.AlterField(
            model_name='branchaccess',
            name='is_default',
            field=models.BooleanField(default=False, help_text='شعبه‌ای که پس از ورود به‌صورت پیش‌فرض انتخاب می‌شود. برای هر پرسنل حداکثر یک شعبه می‌تواند پیش‌فرض باشد.', verbose_name='شعبه پیش‌فرض'),
        ),
        migrations.AddIndex(
            model_name='teacherassignment',
            index=models.Index(fields=['teacher', 'academic_year', 'status'], name='teacher_assign_active_idx'),
        ),
        migrations.RunPython(
            demote_duplicate_default_branches,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='branchaccess',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('staff',), name='unique_default_branch_access_per_staff'),
        ),
    ]
