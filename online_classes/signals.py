"""
Uploaded images are removed once nothing points at them, with the website
app's handlers (``website.signals``): when an image is replaced or cleared,
and when its row is deleted. Files go after commit.
"""

from django.db.models.signals import post_delete, pre_save

from website.signals import delete_files_of_deleted_row, delete_replaced_files

from .models import Announcement, OnlinePlatform

MODELS_WITH_IMAGES = (OnlinePlatform, Announcement)


def connect():
    for model in MODELS_WITH_IMAGES:
        pre_save.connect(delete_replaced_files, sender=model, dispatch_uid=f"online-replace-{model.__name__}")
        post_delete.connect(delete_files_of_deleted_row, sender=model, dispatch_uid=f"online-delete-{model.__name__}")
