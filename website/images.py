"""
Photos of people on the public site: re-encoded when they are uploaded.

Website images are otherwise stored byte for byte, and a photo taken with
a phone can carry its GPS position (and more) in its EXIF data. A newly
uploaded photo of a person is decoded, turned upright, scaled down to fit
``MAX_SIDE`` and saved as a fresh JPEG, which keeps no metadata and
nothing else that was hiding in the original file. Unlike account avatars
(``accounts/avatars.py``) the picture is not cropped: portraits keep their
shape.
"""

import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_SIDE = 900

PUBLIC_PHOTO_HELP = (
    "این عکس در سایت عمومی نمایش داده می‌شود؛ فقط عکسی بگذارید که اجازه انتشارش را دارید. "
    "عکس پروفایل حساب کاربری هیچ‌وقت خودکار نمایش داده نمی‌شود."
)
METADATA_HELP = "اطلاعات همراه عکس (مثل موقعیت مکانی گوشی) هنگام ذخیره حذف می‌شود."


def reencode(uploaded, max_side=MAX_SIDE):
    """An uploaded image -> ``ContentFile`` of an upright, metadata-free JPEG with a random name."""

    uploaded.seek(0)
    with Image.open(uploaded) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True, progressive=True)

    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def reencode_new_photo(instance, field_name):
    """
    Replace a just-uploaded (not yet stored) file in ``field_name`` by its
    re-encoded copy. Call from ``save()``: files already in storage, and
    empty fields, are left alone.
    """

    photo = getattr(instance, field_name)
    if photo and not photo._committed:
        setattr(instance, field_name, reencode(photo.file))
