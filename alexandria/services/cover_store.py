"""Covers kept on disk next to the database, served from ``/cover/<id>``.

No schema change: a book has a local cover when ``<COVERS_DIR>/<id>.jpg``
exists. Without it everything falls back to the provider URLs.
"""

import io
import os
from pathlib import Path

from flask import current_app, has_app_context
from loguru import logger
from PIL import Image

MAX_HEIGHT = 900
JPEG_QUALITY = 88


def covers_dir() -> Path:
    return Path(current_app.config['COVERS_DIR'])


def path_for(book_id: int) -> Path:
    return covers_dir() / f'{int(book_id)}.jpg'


def local_url(book_id: int) -> str | None:
    """``/cover/<id>?v=<mtime>`` (the version busts caches when the file changes)."""
    if not has_app_context():
        return None
    try:
        mtime = int(path_for(book_id).stat().st_mtime)
    except OSError:
        return None
    return f'/cover/{int(book_id)}?v={mtime}'


def read(book_id: int) -> bytes | None:
    if not has_app_context():
        return None
    try:
        return path_for(book_id).read_bytes()
    except OSError:
        return None


def save(book_id: int, data: bytes) -> bool:
    """Store ``data`` as a JPEG no taller than MAX_HEIGHT. Never raises."""
    try:
        img = Image.open(io.BytesIO(data)).convert('RGB')
        if img.height > MAX_HEIGHT:
            img = img.resize((round(img.width * MAX_HEIGHT / img.height), MAX_HEIGHT), Image.LANCZOS)
        target = path_for(book_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.tmp')
        img.save(tmp, 'JPEG', quality=JPEG_QUALITY, optimize=True)
        os.replace(tmp, target)  # atomic: readers never see half a file
        return True
    except Exception as exc:  # noqa: BLE001 - a cover is never worth failing a request for
        logger.warning('could not store cover for book {}: {}', book_id, exc)
        return False


def delete(book_id: int) -> None:
    try:
        path_for(book_id).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning('could not remove cover for book {}: {}', book_id, exc)
