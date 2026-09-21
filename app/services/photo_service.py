"""Shared image upload handling (wishlist item photos, profile photos).

Uploads are decoded with Pillow (so the file really has to be an image),
straightened by their EXIF rotation, and re-saved smaller: gift photos fit
inside WISHLIST_MAX_SIDE, profile photos are cropped to a square."""
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # the file as uploaded; what we store is far smaller
WISHLIST_MAX_SIDE = 1200            # px, longest side of a gift photo
AVATAR_SIZE = 512                   # px, profile photos are AVATAR_SIZE x AVATAR_SIZE
JPEG_QUALITY = 85


def save_photo(photo, subdir, square=False):
    """Validate, shrink and store an uploaded image under static/uploads/<subdir>/.
    `square` crops it to a centred square (profile photos). Returns the path
    relative to static/. Raises ValueError with a plain-language message when
    the file isn't acceptable."""
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError("Photos must be a JPG, PNG, WEBP, or GIF file.")
    photo.seek(0, os.SEEK_END)
    size = photo.tell()
    photo.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"Photos must be smaller than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")
    try:
        img = ImageOps.exif_transpose(Image.open(photo))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file doesn't look like a photo. Please choose a JPG, PNG, WEBP, or GIF.")
    if square:
        # Faces sit a little above the middle, so bias the crop upward.
        img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    else:
        img.thumbnail((WISHLIST_MAX_SIDE, WISHLIST_MAX_SIDE), Image.Resampling.LANCZOS)

    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    upload_dir = os.path.join(current_app.static_folder, "uploads", subdir)
    os.makedirs(upload_dir, exist_ok=True)
    if has_alpha:
        filename = f"{uuid.uuid4().hex}.png"
        img.convert("RGBA").save(os.path.join(upload_dir, filename), "PNG", optimize=True)
    else:
        filename = f"{uuid.uuid4().hex}.jpg"
        img.convert("RGB").save(os.path.join(upload_dir, filename), "JPEG",
                                quality=JPEG_QUALITY, optimize=True, progressive=True)
    return f"uploads/{subdir}/{filename}"


def remove_photo(rel_path):
    """Best-effort delete of a previously saved upload (never raises)."""
    if not rel_path or not rel_path.startswith("uploads/"):
        return
    try:
        os.remove(os.path.join(current_app.static_folder, rel_path))
    except OSError:
        pass
