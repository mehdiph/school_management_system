"""
Re-syncs holiday sessions when what they are derived from changes:
timetable rows (``ClassSchedule``), class subjects, classes and bells.

The sync runs once the surrounding transaction commits (all ids touched
in it are collected and synced together), so a timetable save that
writes many rows syncs once, and a rolled-back save syncs nothing new.
``ClassScheduleQuerySet``'s bulk methods call ``resync_later`` themselves,
since ``bulk_create`` / ``bulk_update`` / ``update`` send no signals.
"""

import threading

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from scheduling.models import ClassSchedule
from scheduling.models.bell import Bell
from school.models import ClassSubject, SchoolClass

_pending = threading.local()


def resync_later(class_subject_ids):
    """Syncs these class subjects' holiday sessions after the current transaction commits."""

    ids = {pk for pk in class_subject_ids if pk is not None}
    if not ids:
        return
    if not hasattr(_pending, "ids"):
        _pending.ids = set()
    _pending.ids |= ids
    # One callback per call: the first to run syncs everything pending,
    # the others find nothing left. (A rolled-back transaction leaves its
    # ids pending, which only costs an extra, harmless sync later.)
    transaction.on_commit(_flush)


def _flush():
    from .services import sync_class_subjects

    ids, _pending.ids = getattr(_pending, "ids", set()), set()
    if ids:
        sync_class_subjects(ids)


@receiver(pre_save, sender=ClassSchedule)
def _remember_class_subject(sender, instance, **kwargs):
    instance._previous_class_subject_id = (
        ClassSchedule.objects.filter(pk=instance.pk).values_list("class_subject_id", flat=True).first()
        if instance.pk else None
    )


@receiver(post_save, sender=ClassSchedule)
@receiver(post_delete, sender=ClassSchedule)
def _schedule_changed(sender, instance, **kwargs):
    resync_later([instance.class_subject_id, getattr(instance, "_previous_class_subject_id", None)])


@receiver(post_save, sender=ClassSubject)
def _class_subject_changed(sender, instance, **kwargs):
    resync_later([instance.pk])


@receiver(post_save, sender=SchoolClass)
def _school_class_changed(sender, instance, created, **kwargs):
    if not created:
        resync_later(instance.class_subjects.values_list("pk", flat=True))


@receiver(post_save, sender=Bell)
def _bell_changed(sender, instance, created, **kwargs):
    if not created:
        resync_later(instance.class_schedules.values_list("class_subject_id", flat=True))
