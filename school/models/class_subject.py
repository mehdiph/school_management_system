from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels
from core.managers.school import ClassSubjectManager


class ClassSubject(models.Model):
    objects = ClassSubjectManager()
    school_class = models.ForeignKey(
        "school.SchoolClass",
        on_delete=models.PROTECT,
        related_name="class_subjects",
        verbose_name="کلاس",
    )

    subject = models.ForeignKey(
        "school.Subject",
        on_delete=models.PROTECT,
        related_name="class_subjects",
        verbose_name="درس",
    )

    teacher_assignment = models.ForeignKey(
        "staff.TeacherAssignment",
        on_delete=models.PROTECT,
        related_name="class_subjects",
        verbose_name="معلم",
    )

    start_date = jmodels.jDateField(
        verbose_name="تاریخ شروع",
    )

    end_date = jmodels.jDateField(
        verbose_name="تاریخ پایان",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )

    def clean(self):
        """
        A teacher may only be given a class/subject through an
        assignment that actually belongs to that class's branch *and*
        academic year.

        Without this, an admin can pick any assignment in the dropdown
        and silently produce a row where the teacher teaches in a branch
        (or a year) they were never assigned to -- which then leaks into
        every branch-scoped query built on ``ClassSubject``.
        """

        super().clean()

        if not self.teacher_assignment_id or not self.school_class_id:
            return

        messages = []

        if self.teacher_assignment.branch_id != self.school_class.branch_id:
            messages.append(
                "شعبه‌ی انتساب معلم با شعبه‌ی کلاس یکسان نیست "
                f"(انتساب: {self.teacher_assignment.branch}، "
                f"کلاس: {self.school_class.branch})."
            )

        if self.teacher_assignment.academic_year_id != self.school_class.year_id:
            messages.append(
                "سال تحصیلی انتساب معلم با سال تحصیلی کلاس یکسان نیست "
                f"(انتساب: {self.teacher_assignment.academic_year}، "
                f"کلاس: {self.school_class.year})."
            )

        if messages:
            raise ValidationError({"teacher_assignment": messages})

    @property
    def icon(self):
        icons = {
            "math": "fa-calculator",
            "science": "fa-flask",
            "farsi": "fa-book",
            "computer": "fa-laptop-code",
            "qoran": "fa-star-and-crescent",
            "motaleat": "fa-book",
            "varzesh": "fa-basketball",
            "art": "fa-palette",
        }
        return icons.get(self.subject.slug, "fa-book")

    class Meta:
        verbose_name = "درس کلاس"
        verbose_name_plural = "دروس کلاس‌ها"

        ordering = [
            "school_class",
            "subject__name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "school_class",
                    "subject",
                    "teacher_assignment",
                ],
                name="unique_class_subject_teacher_assignment",
            )
        ]

    def __str__(self):
        return (
            f"{self.school_class} | "
            f"{self.subject.name} | "
            f"{self.teacher_assignment.teacher.staff.user.get_full_name()}"
        )