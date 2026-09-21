"""Shared image upload handling (wishlist item photos, profile photos)."""
import os
import uuid

from flask import current_app

ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_PHOTO_BYTES = 4 * 1024 * 1024  # 4MB


def save_photo(photo, subdir):
    """Validate and store an uploaded image under static/uploads/<subdir>/.
    Returns the path relative to static/. Raises ValueError with a
    plain-language message when the file isn't acceptable."""
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError("Photos must be a JPG, PNG, WEBP, or GIF file.")
    photo.seek(0, os.SEEK_END)
    size = photo.tell()
    photo.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise ValueError("Photos must be smaller than 4MB.")
    upload_dir = os.path.join(current_app.static_folder, "uploads", subdir)
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    photo.save(os.path.join(upload_dir, filename))
    return f"uploads/{subdir}/{filename}"


def remove_photo(rel_path):
    """Best-effort delete of a previously saved upload (never raises)."""
    if not rel_path or not rel_path.startswith("uploads/"):
        return
    try:
        os.remove(os.path.join(current_app.static_folder, rel_path))
    except OSError:
        pass
