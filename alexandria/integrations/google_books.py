import os
import re
from dataclasses import dataclass

import requests
from loguru import logger

BASE_URL = 'https://www.googleapis.com/books/v1/volumes'


@dataclass
class SearchOutcome:
    """Google Books search result: volumes plus optional API error message."""

    results: list
    error_message: str | None = None


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


def _best_cover_url(image_links):
    """Prefer highest-resolution Google Books cover URL; bump zoom when only small thumbs exist."""
    if not image_links:
        return None
    url = (
        image_links.get('extraLarge')
        or image_links.get('large')
        or image_links.get('medium')
        or image_links.get('small')
        or image_links.get('thumbnail')
        or image_links.get('smallThumbnail')
    )
    if not url:
        return None
    url = url.replace('http://', 'https://')
    if re.search(r'[?&]zoom=1(?:&|$)', url):
        url = re.sub(r'zoom=1', 'zoom=3', url, count=1)
    return url


def _volume_info_to_result(volume_info, google_books_id):
    image_links = volume_info.get('imageLinks') or {}
    published = volume_info.get('publishedDate')
    return {
        'google_books_id': google_books_id,
        'title': volume_info.get('title'),
        'authors': ', '.join(volume_info.get('authors', [])),
        'thumbnail': _best_cover_url(image_links),
        'description': volume_info.get('description'),
        'page_count': volume_info.get('pageCount'),
        'categories': ', '.join(volume_info.get('categories', [])),
        'published_year': published[:4] if published else None,
        'language': volume_info.get('language'),
        'average_rating': volume_info.get('averageRating'),
    }


def search_books(query: str) -> SearchOutcome:
    """Search for books using the Google Books API."""
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
    return SearchOutcome(results)


def get_book_details(google_books_id):
    """Retrieve specific book details by Google Books ID."""
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
    return _volume_info_to_result(volume_info, data.get('id'))
