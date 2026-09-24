"""
Validators shared by the landing page models.

Links are stored as plain text (not ``URLField``) because the admin
must be able to enter relative paths such as ``/auth/login/`` or ``#``;
``validate_link`` keeps that flexibility while refusing schemes like
``javascript:`` that would turn a menu item into an XSS vector.
"""

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_SIZE_MB = 2

validate_image_extension = FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS)


def validate_image_size(file):
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(
            f"حجم تصویر نباید بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد."
        )


IMAGE_VALIDATORS = [validate_image_extension, validate_image_size]

_ALLOWED_LINK_PREFIXES = ("/", "#", "?", "http://", "https://", "mailto:", "tel:")


def validate_link(value):
    if not value.strip().lower().startswith(_ALLOWED_LINK_PREFIXES):
        raise ValidationError(
            "لینک باید با / یا # شروع شود، یا آدرس کامل "
            "(https://...)، mailto: یا tel: باشد."
        )
