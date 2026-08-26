from django.db import models
from django_jalali.db import models as jmodels
from core.managers.school import SchoolClassManager

class SchoolClass(models.Model):
    objects = SchoolClassManager()
    year = models.ForeignKey('school.AcademicYear', on_delete=models.CASCADE, verbose_name='سال تحصیلی')
    grade = models.ForeignKey('school.Grade', on_delete=models.CASCADE, verbose_name='پایه')
    branch = models.ForeignKey(
    "school.Branch",
    on_delete=models.PROTECT,
    related_name="classes",
    verbose_name="شعبه",
)
    section = models.CharField(max_length=255, verbose_name='نام کلاس')
    created_at = jmodels.jDateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'کلاس'
        verbose_name_plural = 'کلاس‌ها'
        ordering = [
            "branch",
            "year",
            "grade__level",
            "section",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "branch",
                    "year",
                    "grade",
                    "section",
                ],
                name="unique_class_per_branch_year_grade_section",
            )
        ]

    def __str__(self):
        return (
            f"{self.grade.name} | "
            f"{self.section} | "
            f"{self.branch.name}"
        )