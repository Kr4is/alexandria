import os
import re
import time
from dataclasses import dataclass

import requests
from loguru import logger

from alexandria.utils.covers import pick_cover_url

BASE_URL = 'https://www.googleapis.com/books/v1/volumes'

_search_cache: dict[str, tuple[float, 'SearchOutcome']] = {}
_volume_cache: dict[str, tuple[float, dict]] = {}


@dataclass
class SearchOutcome:
    """Google Books search result: volumes plus optional API error message."""

    results: list
    error_message: str | None = None


def _cache_ttl_seconds() -> int:
    raw = os.getenv('GOOGLE_BOOKS_CACHE_TTL_SECONDS', '3600').strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 3600


def _normalize_query(query: str) -> str:
    return re.sub(r'\s+', ' ', query.strip().lower())


def _cache_get(cache: dict, key: str):
    entry = cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        del cache[key]
        return None
    return value


def _cache_set(cache: dict, key: str, value) -> None:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return
    cache[key] = (time.monotonic() + ttl, value)


def clear_google_books_cache() -> None:
    """Clear in-memory caches (primarily for tests)."""
    _search_cache.clear()
    _volume_cache.clear()


def _seed_volume_cache(results: list) -> None:
    for book in results:
        google_books_id = book.get('google_books_id')
        if google_books_id:
            _cache_set(_volume_cache, google_books_id, book)


def _optional_api_key_params():
    key = os.getenv('GOOGLE_BOOKS_API_KEY', '').strip()
    return {'key': key} if key else {}


def _http_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
        err = data.get('error') or {}
        if isinstance(err, dict) and err.get('message'):
            return err['message']
    except Exception:
        pass
    if response.reason:
        return f'{response.status_code} {response.reason}'
    return f'HTTP {response.status_code}'


def _extract_isbn(volume_info) -> str | None:
    identifiers = volume_info.get('industryIdentifiers') or []
    for preferred in ('ISBN_13', 'ISBN_10'):
        for item in identifiers:
            if item.get('type') == preferred and item.get('identifier'):
                return item['identifier']
    return None


def _volume_info_to_result(volume_info, google_books_id):
    published = volume_info.get('publishedDate')
    isbn = _extract_isbn(volume_info)
    image_links = volume_info.get('imageLinks') or {}
    return {
        'google_books_id': google_books_id,
        'title': volume_info.get('title'),
        'authors': ', '.join(volume_info.get('authors', [])),
        'isbn': isbn,
        'thumbnail': pick_cover_url(image_links, google_books_id, isbn),
        'description': volume_info.get('description'),
        'page_count': volume_info.get('pageCount'),
        'categories': ', '.join(volume_info.get('categories', [])),
        'published_year': published[:4] if published else None,
        'language': volume_info.get('language'),
        'average_rating': volume_info.get('averageRating'),
    }


def search_books(query: str) -> SearchOutcome:
    """Search for books using the Google Books API."""
    cache_key = _normalize_query(query)
    cached = _cache_get(_search_cache, cache_key)
    if cached is not None:
        return cached

    params = {'q': query, 'maxResults': 10, **_optional_api_key_params()}
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
    except requests.RequestException as e:
        logger.warning('Google Books search request failed: {}', e)
        return SearchOutcome([], error_message='Could not reach Google Books. Check your network connection.')

    if response.status_code != 200:
        msg = _http_error_message(response)
        logger.warning('Google Books search HTTP {}: {}', response.status_code, msg)
        return SearchOutcome([], error_message=msg)

    data = response.json()
    results = []
    for item in data.get('items', []):
        volume_info = item.get('volumeInfo', {})
        results.append(_volume_info_to_result(volume_info, item.get('id')))
    outcome = SearchOutcome(results)
    _cache_set(_search_cache, cache_key, outcome)
    _seed_volume_cache(results)
    return outcome


def get_book_details(google_books_id):
    """Retrieve specific book details by Google Books ID."""
    cached = _cache_get(_volume_cache, google_books_id)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f'{BASE_URL}/{google_books_id}',
            params=_optional_api_key_params(),
            timeout=30,
        )
    except requests.RequestException as e:
        logger.warning('Google Books volume request failed: {}', e)
        return None

    if response.status_code != 200:
        logger.warning(
            'Google Books volume HTTP {}: {}',
            response.status_code,
            _http_error_message(response),
        )
        return None
    data = response.json()
    volume_info = data.get('volumeInfo', {})
    result = _volume_info_to_result(volume_info, data.get('id'))
    _cache_set(_volume_cache, google_books_id, result)
    return result
