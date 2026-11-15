"""Find a cover that really exists for a book.

Providers answer a missing cover with a placeholder instead of an error: Open
Library with a 1x1 GIF, Google Books with a 128x170 "image not available" PNG.
Everything here downloads the image and checks it before it is trusted.
"""

import io
import json
import re
import unicodedata
from dataclasses import dataclass, field

import requests
from loguru import logger
from PIL import Image

from alexandria.services import cover_store
from alexandria.utils.covers import resolve_cover_fallback_url, resolve_cover_url

TIMEOUT = (5, 10)  # repair runs unattended: be patient. Adding a book passes a shorter one.
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MIN_SIDE = 100
GOOGLE_PLACEHOLDER_SIZE = (128, 170)
USER_AGENT = 'Alexandria/1.0'
OPEN_LIBRARY_SEARCH = 'https://openlibrary.org/search.json'
OPEN_LIBRARY_COVER_ID = 'https://covers.openlibrary.org/b/id/{cover_id}-L.jpg'


@dataclass
class CoverMatch:
    url: str
    source: str  # current | fallback | search
    matched_title: str | None = None
    data: bytes | None = field(default=None, repr=False)  # the validated image


def _get(url: str, params: dict | None = None, timeout=TIMEOUT) -> bytes | None:
    """GET with a size cap enforced while streaming; None on any failure or 4xx/5xx.

    A timeout is retried once: the providers are slow to connect now and then.
    """
    for attempt in (1, 2):
        try:
            return _get_once(url, params, timeout)
        except requests.Timeout as exc:
            logger.debug('cover request timed out for {} (attempt {}): {}', url, attempt, exc)
    return None


def _get_once(url: str, params, timeout) -> bytes | None:
    try:
        with requests.get(
            url, params=params, timeout=timeout, stream=True, headers={'User-Agent': USER_AGENT}
        ) as resp:
            if resp.status_code != 200:
                return None
            data = b''
            for chunk in resp.iter_content(65536):
                data += chunk
                if len(data) > MAX_BYTES:
                    return None
            return data
    except requests.RequestException as exc:
        if isinstance(exc, requests.Timeout):
            raise
        logger.debug('cover request failed for {}: {}', url, exc)
        return None


def is_real_cover(data: bytes | None, url: str = '') -> bool:
    """True for a decodable image that is not a provider placeholder."""
    if not data:
        return False
    try:
        img = Image.open(io.BytesIO(data))
        size = img.size
    except Exception:  # noqa: BLE001 - anything undecodable is not a cover
        return False
    if size[0] * size[1] > MAX_PIXELS or min(size) < MIN_SIDE:
        return False
    return not ('books.google' in url and size == GOOGLE_PLACEHOLDER_SIZE)


def fetch_valid(url: str | None, timeout=TIMEOUT) -> bytes | None:
    """The image bytes if ``url`` serves a real cover, else None."""
    if not url:
        return None
    data = _get(url, timeout=timeout)
    return data if is_real_cover(data, url) else None


def validate(url: str | None, timeout=TIMEOUT) -> bool:
    return fetch_valid(url, timeout) is not None


# --- title / author matching ------------------------------------------------

def _fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '').casefold()
    return ''.join(c for c in text if not unicodedata.combining(c))


def normalize_title(title: str) -> str:
    """Casefold, drop accents and any subtitle, keep letters and digits only."""
    main = re.split(r'\s*[:—]\s*|\s+-\s+', _fold(title), maxsplit=1)[0]
    return re.sub(r'[^a-z0-9]+', ' ', main).strip()


def _surnames(authors: str | None) -> set[str]:
    names = set()
    for part in re.split(r',|&|;|\band\b|\by\b', _fold(authors or '')):
        tokens = re.sub(r'[^a-z0-9 ]+', ' ', part).split()
        if tokens:
            names.add(tokens[-1])
    return names


def _same_book(book, doc: dict) -> bool:
    """Exact title after normalisation, and a shared author surname when both sides have one."""
    if normalize_title(doc.get('title', '')) != normalize_title(book.title):
        return False
    wanted = _surnames(book.authors)
    found = _surnames(', '.join(doc.get('author_name') or []))
    return not wanted or not found or bool(wanted & found)


def _search_open_library(book, timeout) -> CoverMatch | None:
    # Title only: author spellings differ ("Josh" vs "Joshua"); the surname check below does the filtering.
    params = {'title': book.title, 'fields': 'title,author_name,cover_i', 'limit': 30}
    raw = _get(OPEN_LIBRARY_SEARCH, params=params, timeout=timeout)
    if not raw:
        return None
    try:
        docs = json.loads(raw).get('docs', [])
    except ValueError:
        return None
    for doc in docs:
        if not doc.get('cover_i') or not _same_book(book, doc):
            continue
        url = OPEN_LIBRARY_COVER_ID.format(cover_id=doc['cover_i'])
        data = fetch_valid(url, timeout=timeout)
        if data:
            return CoverMatch(url, 'search', doc.get('title'), data)
    return None


def find_cover(book, search: bool = True, timeout=TIMEOUT) -> CoverMatch | None:
    """First cover that validates: stored, other provider, then an Open Library title search."""
    current = resolve_cover_url(book.thumbnail, book.google_books_id, book.isbn)
    data = fetch_valid(current, timeout=timeout)
    if data:
        return CoverMatch(current, 'current', data=data)
    fallback = resolve_cover_fallback_url(book.thumbnail, book.google_books_id, book.isbn)
    data = fetch_valid(fallback, timeout=timeout)
    if data:
        return CoverMatch(fallback, 'fallback', data=data)
    return _search_open_library(book, timeout) if search else None


def improve_cover(book) -> bool:
    """Used when a book is added: keep a working cover on disk, and store its URL if it differs.

    Never raises; a failure leaves the book exactly as it was.
    """
    from alexandria.extensions import db

    try:
        match = find_cover(book, timeout=(1.5, 2.5))
        if not match:
            return False
        if match.source != 'current':
            book.thumbnail = match.url
            db.session.commit()
        cover_store.save(book.id, match.data)
        return True
    except Exception as exc:  # noqa: BLE001 - adding a book must not depend on covers
        db.session.rollback()
        logger.warning('cover lookup failed for {}: {}', book.title, exc)
    return False
