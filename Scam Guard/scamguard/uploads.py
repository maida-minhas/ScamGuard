import os
import secrets

from flask import current_app

from scamguard.db import db
from scamguard.models import File, User

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
MAX_PROOF_SIZE = 5 * 1024 * 1024


def save_upload(file_storage, uploader: User) -> File | None:
    """Validate and persist an uploaded proof file.

    Returns None when the upload is missing, empty, has a disallowed
    extension, exceeds MAX_PROOF_SIZE, or cannot be written.
    """
    if file_storage is None or not file_storage.filename:
        return None

    filename = file_storage.filename
    if "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None

    stream = file_storage.stream
    try:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
    except (OSError, ValueError, AttributeError):
        return None
    if size <= 0 or size > MAX_PROOF_SIZE:
        return None

    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    stored_name = f"{secrets.token_hex(8)}.{ext}"
    try:
        file_storage.save(os.path.join(folder, stored_name))
    except OSError:
        return None

    stored = File(
        uploader_id=uploader.id,
        stored_name=stored_name,
        original_name=filename[:255],
        mime_type=file_storage.mimetype or "application/octet-stream",
        size=size,
    )
    db.session.add(stored)
    db.session.commit()
    return stored
