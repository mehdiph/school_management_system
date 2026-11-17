"""Writes and rules of online classes; admin pages and the importer call these."""

from django.db import transaction
from django.utils import timezone

from . import audience
from .models import AnnouncementDismissal, OnlineEvent, OnlineEventAccess

COPY_SUFFIX = " (کپی)"


@transaction.atomic
def duplicate_event(event, user=None):
    """
    A hidden copy with the same audience, without personal access rows. It
    starts inactive (D24): visible at once, it would appear with the old time.
    """

    max_title = OnlineEvent._meta.get_field("title").max_length - len(COPY_SUFFIX)

    # A fresh instance: one from the admin's list carries prefetched targets,
    # and ``set()`` on those would see the original's rows and add nothing.
    copy = OnlineEvent.objects.get(pk=event.pk)
    copy.pk = None
    copy._state.adding = True
    copy.title = event.title[:max_title] + COPY_SUFFIX
    copy.status = OnlineEvent.Status.SCHEDULED
    copy.status_note = ""
    copy.is_active = False
    copy.created_by = user
    copy.updated_by = user
    copy.save()

    for field in audience.ALL_TARGET_FIELDS:
        getattr(copy, field).set(getattr(event, field).all())
    return copy


def dismiss(announcement, student_profile):
    """Idempotent: a repeated click changes nothing."""

    AnnouncementDismissal.objects.get_or_create(announcement=announcement, student=student_profile)


def missing_access(event):
    """The current enrolments of a personal-mode event's audience with no access row."""

    have = OnlineEventAccess.objects.filter(event=event).values_list("student_id", flat=True)
    return audience.reached_enrollments(event).exclude(student__in=have)


def clear_access_rows(events):
    """Deletes the personal rows of events that have ended (D19). Returns how many rows went."""

    now = timezone.now()
    ended = [event.pk for event in events if event.state_at(now) == OnlineEvent.State.ENDED]
    deleted, _ = OnlineEventAccess.objects.filter(event__in=ended).delete()
    return deleted


@transaction.atomic
def save_access_import(plan, user=None):
    """
    Creates or updates every row of a valid import plan, all or nothing, with
    the event locked so two imports can't interleave. A blank cell keeps what
    is stored: a file of corrected passwords can't wipe links (D18).
    """

    OnlineEvent.objects.select_for_update().get(pk=plan.event.pk)
    existing = {
        row.student_id: row
        for row in OnlineEventAccess.objects.select_for_update().filter(event=plan.event)
    }

    created = updated = 0
    for item in plan.rows_to_save:
        row = existing.get(item.student.pk)
        if row is None:
            row = OnlineEventAccess(event=plan.event, student=item.student)
            created += 1
        else:
            updated += 1
        row.set_secrets(url=item.url, password=item.password, access_code=item.access_code)
        row.username = item.username or row.username
        row.note = item.note or row.note
        row.updated_by = user
        row.save()
    return created, updated
