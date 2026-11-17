from django.db import models


class AudienceTargets(models.Model):
    """
    Who an event or an announcement is for (D2, D3). Only
    ``online_classes.audience`` reads these fields; no page filters an
    audience on its own. Nothing selected means nobody.
    """

    is_whole_school = models.BooleanField(default=False, verbose_name="کل مدرسه")
    branches = models.ManyToManyField("school.Branch", blank=True, related_name="+", verbose_name="شعبه‌ها")
    grades = models.ManyToManyField("school.Grade", blank=True, related_name="+", verbose_name="پایه‌ها")
    classes = models.ManyToManyField("school.SchoolClass", blank=True, related_name="+", verbose_name="کلاس‌ها")
    students = models.ManyToManyField(
        "student.StudentProfile", blank=True, related_name="+", verbose_name="دانش‌آموزان"
    )
    excluded_students = models.ManyToManyField(
        "student.StudentProfile", blank=True, related_name="+", verbose_name="دانش‌آموزان مستثنا"
    )

    class Meta:
        abstract = True
