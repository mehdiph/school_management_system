from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, F, Value, When
from django_jalali.db import models as jmodels
from core.managers.teaching import SchoolSessionManager

#: Shown when a second session is recorded for the same slot.
DUPLICATE_SLOT_MESSAGE = "برای این درس در این زنگ و این تاریخ قبلاً جلسه ثبت شده است"

# Phase one of a renumbering moves the changed rows out of the way by this
# much, so no intermediate state ever repeats a (class_subject, number).
_RENUMBER_OFFSET = 1_000_000


class SchoolSession(models.Model):
    """
    One lesson of a ``ClassSubject`` on one date, at one bell.

    A slot is ``(class_subject, date, bell)``: the same subject may be
    taught twice on one day (two bells), and each is its own session.
    ``bell`` is NULL only on sessions recorded before it existed (see
    the ``backfill_session_bells`` command).

    ``status == HOLIDAY`` rows are created by the academic calendar
    (``academic_calendar.services.sync_cancelled_sessions``) for slots a
    ``CalendarEvent`` closed. They have no ``session_number`` and are
    excluded from every count: use ``SchoolSession.objects.counted()``.

    Numbering: the counted sessions of a class subject are always numbered
    1..N in teaching order (date, then bell). Recording a session for an
    earlier date, moving one, or changing its status renumbers the later
    ones (``renumber_sessions``), so a number shown in the past can change.
    """

    objects = SchoolSessionManager()

    class Status(models.TextChoices):
        COMPENSATORY = "JB", "جبرانی"
        CANCELED = "CD", "کنسل شده"
        HELD = "HD", "برگزار شده"
        #: Closed by the academic calendar; never entered by hand.
        HOLIDAY = "HL", "تعطیل"

    class_subject = models.ForeignKey(
        "school.ClassSubject",
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name="درس کلاس",
    )

    date = jmodels.jDateField(
        verbose_name="تاریخ جلسه",
    )

    bell = models.ForeignKey(
        "scheduling.Bell",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="زنگ",
    )

    session_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="شماره جلسه",
    )

    status = models.CharField(
        max_length=2,
        choices=Status.choices,
        default=Status.HELD,
        verbose_name="وضعیت",
    )

    calendar_event = models.ForeignKey(
        "academic_calendar.CalendarEvent",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="رویداد تقویم",
    )

    is_auto_created = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="ایجاد خودکار",
        help_text="جلسه‌ای که تقویم آموزشی ساخته است، نه معلم.",
    )

    created_at = jmodels.jDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "جلسه درسی"
        verbose_name_plural = "جلسات درسی"

        ordering = [
            "-date",
            "-session_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["class_subject", "session_number"],
                name="unique_session_number_per_class_subject",
            ),
            models.UniqueConstraint(
                fields=["class_subject", "date", "bell"],
                condition=models.Q(bell__isnull=False),
                name="unique_session_per_slot",
                violation_error_message=DUPLICATE_SLOT_MESSAGE,
            ),
            # Holiday rows are never numbered; every other row always is.
            models.CheckConstraint(
                condition=(
                    models.Q(status="HL", session_number__isnull=True)
                    | (~models.Q(status="HL") & models.Q(session_number__isnull=False))
                ),
                name="session_number_only_when_counted",
            ),
        ]

        indexes = [
            # The supervisor pages read one class subject's sessions in a
            # date range (and its first/last date); the unique constraint
            # above only covers (class_subject, session_number).
            models.Index(
                fields=["class_subject", "date"],
                name="school_session_cs_date_idx",
            )
        ]

    @property
    def is_holiday(self):
        return self.status == self.Status.HOLIDAY

    def clean(self):
        super().clean()

        # Both may be missing when a form failed to validate them; that is
        # reported on the fields themselves, there is nothing to compare.
        if self.class_subject_id and self.date:
            if self.date < self.class_subject.start_date:
                raise ValidationError({
                    "date": "تاریخ جلسه قبل از تاریخ شروع درس است."
                })

            if self.date > self.class_subject.end_date:
                raise ValidationError({
                    "date": "تاریخ جلسه بعد از تاریخ پایان درس است."
                })

        # A holiday is the calendar's doing, and only the calendar's.
        if self.is_holiday and not self.calendar_event_id:
            raise ValidationError({
                "status": "وضعیت «تعطیل» فقط برای جلساتی است که تقویم آموزشی لغو کرده است."
            })
        if self.calendar_event_id and not self.is_holiday:
            raise ValidationError({
                "status": "جلسه‌ای که تقویم آموزشی لغو کرده است فقط وضعیت «تعطیل» دارد."
            })

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Moving a session to another class subject renumbers both.
            previous_class_subject_id = (
                SchoolSession.objects.filter(pk=self.pk)
                .values_list("class_subject_id", flat=True)
                .first()
                if self.pk else None
            )
            for class_subject_id in sorted({self.class_subject_id, previous_class_subject_id} - {None}):
                # One numbering at a time per class subject.
                _lock_class_subject(class_subject_id)

            if self.is_holiday:
                self.session_number = None
            elif not self.session_number or previous_class_subject_id not in (
                None, self.class_subject_id,
            ):
                # Provisional: renumber_sessions() puts it in date order.
                last = (
                    SchoolSession.objects
                    .filter(class_subject_id=self.class_subject_id)
                    .aggregate(last=models.Max("session_number"))["last"]
                )
                self.session_number = (last or 0) + 1

            self.full_clean()
            super().save(*args, **kwargs)

            if previous_class_subject_id not in (None, self.class_subject_id):
                renumber_sessions(previous_class_subject_id)
            if self.class_subject_id:
                renumber_sessions(self.class_subject_id)
                self.session_number = (
                    SchoolSession.objects.filter(pk=self.pk)
                    .values_list("session_number", flat=True)
                    .get()
                )

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            _lock_class_subject(self.class_subject_id)
            result = super().delete(*args, **kwargs)
            renumber_sessions(self.class_subject_id)
        return result

    def __str__(self):
        if self.is_holiday:
            return f"{self.class_subject} - تعطیل {self.date}"
        return f"{self.class_subject} - جلسه {self.session_number}"


def _lock_class_subject(class_subject_id):
    from school.models import ClassSubject

    list(
        ClassSubject.objects.select_for_update()
        .filter(pk=class_subject_id)
        .values_list("pk", flat=True)
    )


def teaching_order_key(date, bell_order, session_number, pk):
    """
    Sort key of the teaching order the numbers follow: date, then bell
    (a session without a bell first), then the previous number, then pk.
    """

    return (
        date,
        bell_order if bell_order is not None else 0,
        session_number if session_number is not None else _RENUMBER_OFFSET,
        pk,
    )


def renumber_sessions(class_subject_id):
    """
    Numbers the counted sessions of one class subject 1..N in teaching
    order (``teaching_order_key``); holidays keep NULL. Only rows whose
    number changes are written, in two phases (first moved out of the way
    by a large offset, then to their final values), so the unique
    (class_subject, session_number) constraint holds after every
    statement. Call inside a transaction holding the class subject lock
    (``SchoolSession.save`` does). Returns how many rows changed.
    """

    rows = list(
        SchoolSession.objects.counted()
        .filter(class_subject_id=class_subject_id)
        .values_list("pk", "date", "bell__order", "session_number")
    )
    rows.sort(key=lambda row: teaching_order_key(row[1], row[2], row[3], row[0]))

    changes = {
        pk: number
        for number, (pk, _date, _bell, old) in enumerate(rows, start=1)
        if old != number
    }
    if not changes:
        return 0

    queryset = SchoolSession.objects.filter(pk__in=changes)
    queryset.update(session_number=F("session_number") + _RENUMBER_OFFSET)
    queryset.update(session_number=Case(
        *[When(pk=pk, then=Value(number)) for pk, number in changes.items()],
        output_field=models.PositiveIntegerField(),
    ))
    return len(changes)
