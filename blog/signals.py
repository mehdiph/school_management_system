"""
Uploaded files of the blog are removed once nothing points at them, with
the website app's handlers (``website.signals``): when an image is
replaced or cleared, and when its row is deleted. Files go after commit.
"""

from django.db.models.signals import post_delete, pre_save

from website.signals import delete_files_of_deleted_row, delete_replaced_files

from .models import BlogAuthor, BlogPage, Post, PostImage

MODELS_WITH_IMAGES = (BlogPage, BlogAuthor, Post, PostImage)


def connect():
    for model in MODELS_WITH_IMAGES:
        pre_save.connect(delete_replaced_files, sender=model, dispatch_uid=f"blog-replace-{model.__name__}")
        post_delete.connect(delete_files_of_deleted_row, sender=model, dispatch_uid=f"blog-delete-{model.__name__}")
