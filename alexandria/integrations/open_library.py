"""Open Library lookup by ISBN: the fallback when Google Books has no match."""
import re

import requests
from loguru import logger

BOOKS_URL = 'https://openlibrary.org/api/books'


def _year(publish_date) -> str | None:
    match = re.search(r'\b(\d{4})\b', publish_date or '')
    return match.group(1) if match else None


def _volume_to_result(isbn: str, data: dict) -> dict:
    cover = data.get('cover') or {}
    return {
        'google_books_id': None,
        'title': data.get('title'),
        'authors': ', '.join(a.get('name', '') for a in data.get('authors') or [] if a.get('name')),
        'isbn': isbn,
        'thumbnail': cover.get('large') or cover.get('medium'),
        'description': None,
        'page_count': data.get('number_of_pages'),
        'categories': ', '.join(s.get('name', '') for s in (data.get('subjects') or [])[:5] if s.get('name')),
        'published_year': _year(data.get('publish_date')),
        'language': None,
        'average_rating': None,
    }


def lookup_isbn(isbn: str) -> dict | None:
    """Return a book dict shaped like the Google Books results, or None."""
    try:
        response = requests.get(
            BOOKS_URL,
            params={'bibkeys': f'ISBN:{isbn}', 'jscmd': 'data', 'format': 'json'},
            timeout=15,
        )
        response.raise_for_status()
        data = (response.json() or {}).get(f'ISBN:{isbn}')
    except (requests.RequestException, ValueError) as e:
        logger.warning('Open Library lookup failed: {}', e)
        return None
    if not data or not data.get('title'):
        return None
    return _volume_to_result(isbn, data)
