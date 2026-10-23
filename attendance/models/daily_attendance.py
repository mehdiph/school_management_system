from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django_jalali.db import models as jmodels

from analytics.definitions import ABSENT, EXCUSED, LATE, PRESENT
from core.managers.teaching import DailyAttendanceManager


class DailyAttendanceSheet(models.Model):
    """
    The attendance of one class on one day, taken once in the morning by
    the class's grade supporter (``SupervisorProfile``). Replaced the
    teacher's per-session attendance from
    ``settings.ATTENDANCE_DAILY_START_DATE`` on.

    Which days can have a sheet is decided by
    ``attendance.services.day_error`` (the class's timetable, the
    academic calendar, the cutoff and today), checked when a sheet is
    created.
    """

    school_class = models.ForeignKey(
        "school.SchoolClass",
        on_delete=models.PROTECT,
        related_name="daily_attendance_sheets",
        verbose_name="کلاس",
    )

    date = jmodels.jDateField(
        verbose_name="تاریخ",
    )

    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="daily_attendance_sheets",
        verbose_name="ثبت‌کننده",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت",
    )

    class Meta:
        verbose_name = "حضور و غیاب روزانه"
        verbose_name_plural = "حضور و غیاب روزانه"
        ordering = ["-date", "school_class__grade__level", "school_class__section"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "date"],
                name="unique_daily_attendance_sheet_per_class_day",
            ),
        ]

    def clean(self):
        super().clean()

        # Only a new sheet: an existing one stays editable even if the
        # timetable or the calendar changed after it was taken.
        if self._state.adding and self.school_class_id and self.date:
            from attendance.services import day_error

            error = day_error(self.school_class, self.date)
            if error:
                raise ValidationError({"date": error})

    def save(self, *args, **kwargs):
        # The unique (class, day) pair is left to the database: two first
        # saves racing for one sheet then raise IntegrityError, which
        # get_or_create (attendance.services.save_daily_sheet) resolves by
        # reading the winner's sheet. The admin form still checks it.
        self.full_clean(validate_unique=False, validate_constraints=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school_class} | {self.date}"


class DailyAttendance(models.Model):
    """One student's status on a ``DailyAttendanceSheet``."""

    objects = DailyAttendanceManager()

    class Status(models.TextChoices):
        PRESENT = PRESENT, "حاضر"
        ABSENT = ABSENT, "غایب"
        LATE = LATE, "تأخیر"
        EXCUSED = EXCUSED, "غیبت موجه"

    sheet = models.ForeignKey(
        DailyAttendanceSheet,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name="برگه‌ی حضور و غیاب",
    )

    student_enrollment = models.ForeignKey(
        "student.StudentEnrollment",
        on_delete=models.PROTECT,
        related_name="daily_attendances",
        verbose_name="ثبت‌نام دانش‌آموز",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
        verbose_name="وضعیت",
    )

    description = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )

    # Set when the record changes after the sheet was first taken (e.g. a
    # student marked absent at 8:30 arrives late); the first save has
    # the sheet's ``taken_by``.
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_attendance_updates",
        verbose_name="آخرین ویرایش توسط",
    )

    updated_at = jmodels.jDateTimeField(
        auto_now=True,
        verbose_name="آخرین تغییر",
    )

    class Meta:
        verbose_name = "حضور و غیاب روزانه‌ی دانش‌آموز"
        verbose_name_plural = "حضور و غیاب روزانه‌ی دانش‌آموزان"
        ordering = [
            "-sheet__date",
            "student_enrollment__student__user__last_name",
            "student_enrollment__student__user__first_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "student_enrollment"],
                name="unique_daily_attendance_per_sheet",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.sheet_id
            and self.student_enrollment_id
            and self.student_enrollment.school_class_id != self.sheet.school_class_id
        ):
            raise ValidationError({
                "student_enrollment": "دانش‌آموز عضو کلاس این برگه نیست."
            })

    def __str__(self):
        return (
            f"{self.student_enrollment.student.user.get_full_name()} | "
            f"{self.sheet.date} | "
            f"{self.get_status_display()}"
        )
