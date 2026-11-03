import uuid
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_PHOTO_BYTES = 2 * 1024 * 1024
# A small file can still decode to an enormous bitmap, so pixels are capped too.
MAX_PHOTO_PIXELS = 25_000_000
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {
    "JPEG": {"extension": "jpg", "options": {"quality": 90}},
    "PNG": {"extension": "png", "options": {}},
    "WEBP": {"extension": "webp", "options": {"quality": 90}},
}
INVALID_PHOTO_MESSAGE = "Upload a valid JPEG, PNG or WebP image."


def validate_profile_photo(photo):
    # Stored photos are left alone so an unrelated profile save can't fail on them.
    if getattr(photo, "_committed", True):
        return

    if photo.size > MAX_PHOTO_BYTES:
        raise ValidationError("Photo must be 2 MB or smaller.")

    if Path(photo.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValidationError(INVALID_PHOTO_MESSAGE)

    photo.seek(0)
    try:
        with Image.open(photo, formats=tuple(ALLOWED_FORMATS)) as image:
            width, height = image.size
            if width * height > MAX_PHOTO_PIXELS:
                raise ValidationError("Photo dimensions are too large.")
            image.load()
    except ValidationError:
        raise
    except Exception as error:
        # Pillow raises many exception types for corrupt or unrecognised files.
        raise ValidationError(INVALID_PHOTO_MESSAGE) from error
    finally:
        photo.seek(0)


def reencode_profile_photo(photo):
    """Return a metadata-free copy of the upload as (uuid filename, content)."""
    photo.seek(0)
    with Image.open(photo, formats=tuple(ALLOWED_FORMATS)) as image:
        image_format = image.format
        upright = ImageOps.exif_transpose(image)
        has_alpha = image_format != "JPEG" and (
            upright.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
        )
        clean = upright.convert("RGBA" if has_alpha else "RGB")
        clean.info = {}

    settings = ALLOWED_FORMATS[image_format]
    buffer = BytesIO()
    clean.save(buffer, format=image_format, **settings["options"])
    return f"{uuid.uuid4().hex}.{settings['extension']}", ContentFile(buffer.getvalue())
