"""Store a local cover for every book that has a working one but no file yet.

Runs once per process, in the background, after the first request, so the app
never waits on it and CLI commands (migrations, tests) never trigger it.

It only stores covers whose provider URL is already validated for that very
book (the stored URL or the other provider). A title search can pick the wrong
edition, so that stays a human decision: ``flask covers repair``.
"""

import os
import threading
import time

from loguru import logger

from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import cover_store
from alexandria.services.covers import find_cover

PAUSE_SECONDS = 0.3
LOCK_NAME = '.backfill.lock'
LOCK_MAX_AGE = 3600  # a lock older than this is a crashed run
_start_lock = threading.Lock()


def _take_lock() -> bool:
    """One backfill at a time across processes sharing the volume (e.g. a rolling update)."""
    path = cover_store.covers_dir() / LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if time.time() - path.stat().st_mtime > LOCK_MAX_AGE:
            path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def _release_lock() -> None:
    (cover_store.covers_dir() / LOCK_NAME).unlink(missing_ok=True)


def backfill() -> dict:
    """Needs an app context. Returns counts: stored, unresolved (no working cover, or not savable)."""
    counts = {'stored': 0, 'unresolved': 0}
    if not _take_lock():
        return counts
    try:
        for book in Book.query.order_by(Book.id).all():
            if cover_store.path_for(book.id).is_file():
                continue
            match = find_cover(book, search=False)
            if match and cover_store.save(book.id, match.data):
                counts['stored'] += 1
            else:
                counts['unresolved'] += 1
            time.sleep(PAUSE_SECONDS)
    finally:
        _release_lock()
        db.session.remove()
    if counts['stored'] or counts['unresolved']:
        logger.info(
            'cover backfill: stored {stored}, {unresolved} without a working cover '
            '(run `flask covers repair` to look for another edition)',
            **counts,
        )
    return counts


def _run(app) -> None:
    try:
        with app.app_context():
            backfill()
    except Exception as exc:  # noqa: BLE001 - background work must never take the app down
        logger.warning('cover backfill failed: {}', exc)


def start_once(app) -> bool:
    """Start the background backfill the first time it is called for this app."""
    if app.extensions.get('cover_backfill_started'):  # every request lands here: stay cheap
        return False
    with _start_lock:
        if app.extensions.get('cover_backfill_started'):
            return False
        app.extensions['cover_backfill_started'] = True
    threading.Thread(target=_run, args=(app,), name='cover-backfill', daemon=True).start()
    return True
