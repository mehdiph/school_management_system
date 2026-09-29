"""
Profile pictures: server-side checks and re-encoding.

An upload is accepted only if Pillow can actually decode it as a JPEG,
PNG or WebP of at most ``MAX_BYTES``. It is then turned upright
(EXIF orientation), centre-cropped to a square, resized to ``SIZE`` px
and re-encoded as a fresh JPEG. Re-encoding drops every bit of metadata
(EXIF GPS position from phone cameras included) and anything that was
hiding in the original file.
"""

import io
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 2 * 1024 * 1024
SIZE = 256
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
#: Refuse absurd dimensions before decoding the pixels (decompression bombs).
MAX_PIXELS = 40_000_000

MSG_TOO_BIG = "حجم تصویر نباید بیشتر از ۲ مگابایت باشد."
MSG_BAD_TYPE = "فقط تصویر JPG، PNG یا WebP پذیرفته می‌شود."
MSG_NOT_IMAGE = "این فایل یک تصویر سالم نیست."


def validate_avatar(uploaded):
    """Raises ValidationError unless ``uploaded`` is a real JPG/PNG/WebP within limits."""

    if uploaded.size > MAX_BYTES:
        raise ValidationError(MSG_TOO_BIG, code="avatar_too_big")

    extension = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(MSG_BAD_TYPE, code="avatar_bad_type")

    try:
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ValidationError(MSG_BAD_TYPE, code="avatar_bad_type")
            if image.width * image.height > MAX_PIXELS:
                raise ValidationError(MSG_NOT_IMAGE, code="avatar_not_image")
            image.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(MSG_NOT_IMAGE, code="avatar_not_image")
    finally:
        uploaded.seek(0)


def process_avatar(uploaded):
    """A validated upload -> ``ContentFile`` of a SIZE x SIZE JPEG with a random name."""

    uploaded.seek(0)
    with Image.open(uploaded) as image:
        image = ImageOps.exif_transpose(image)
        image = ImageOps.fit(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)

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
