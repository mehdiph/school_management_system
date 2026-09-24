"""
Remove uploaded images from MEDIA_ROOT once nothing points at them:
when a row's image is replaced or cleared, and when the row is deleted.

Files are removed with ``transaction.on_commit`` so a rolled-back save
never leaves a row pointing at a file that is already gone.
"""

from django.db import models, transaction
from django.db.models.signals import post_delete, pre_save

from .models import (
    FeatureCard,
    HeroSlide,
    LandingPage,
    LandingTeacher,
    LearningPoint,
    SiteSettings,
)

MODELS_WITH_IMAGES = (SiteSettings, LandingPage, HeroSlide, FeatureCard, LearningPoint, LandingTeacher)


def _file_fields(model):
    return [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]


def _delete_on_commit(storage, name):
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def delete_replaced_files(sender, instance, raw=False, **kwargs):
    if raw or instance.pk is None:
        return

    old = sender._default_manager.filter(pk=instance.pk).first()
    if old is None:
        return

    for field in _file_fields(sender):
        old_file = getattr(old, field.name)
        new_file = getattr(instance, field.name)
        if old_file and old_file.name != new_file.name:
            _delete_on_commit(old_file.storage, old_file.name)


def delete_files_of_deleted_row(sender, instance, **kwargs):
    for field in _file_fields(sender):
        file = getattr(instance, field.name)
        if file:
            _delete_on_commit(file.storage, file.name)


def connect():
    for model in MODELS_WITH_IMAGES:
        pre_save.connect(delete_replaced_files, sender=model, dispatch_uid=f"website-replace-{model.__name__}")
        post_delete.connect(delete_files_of_deleted_row, sender=model, dispatch_uid=f"website-delete-{model.__name__}")
