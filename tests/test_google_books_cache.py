from unittest.mock import MagicMock, patch

import pytest

from alexandria.integrations.google_books import (
    clear_google_books_cache,
    get_book_details,
    search_books,
)

SEARCH_RESPONSE = {
    'items': [
        {
            'id': 'abc123',
            'volumeInfo': {
                'title': 'Dune',
                'authors': ['Frank Herbert'],
                'publishedDate': '1965',
                'imageLinks': {
                    'large': 'http://books.google.com/books/content?id=abc123&zoom=4&source=gbs_api',
                },
            },
        }
    ]
}

VOLUME_RESPONSE = {
    'id': 'abc123',
    'volumeInfo': {
        'title': 'Dune',
        'authors': ['Frank Herbert'],
        'publishedDate': '1965',
    },
}


def _mock_response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.reason = 'OK' if status_code == 200 else 'Too Many Requests'
    response.json.return_value = json_data or {}
    return response


@pytest.fixture(autouse=True)
def clear_cache():
    clear_google_books_cache()
    yield
    clear_google_books_cache()


@pytest.fixture(autouse=True)
def enable_cache(monkeypatch):
    monkeypatch.setenv('GOOGLE_BOOKS_CACHE_TTL_SECONDS', '3600')


@patch('alexandria.integrations.google_books.requests.get')
def test_search_books_uses_cache_on_repeat_query(mock_get):
    mock_get.return_value = _mock_response(json_data=SEARCH_RESPONSE)

    first = search_books('dune')
    second = search_books('dune')

    assert mock_get.call_count == 1
    assert first.results[0]['title'] == 'Dune'
    assert second.results[0]['title'] == 'Dune'


@patch('alexandria.integrations.google_books.requests.get')
def test_search_books_normalizes_query_for_cache(mock_get):
    mock_get.return_value = _mock_response(json_data=SEARCH_RESPONSE)

    search_books('  Dune  ')
    search_books('dune')

    assert mock_get.call_count == 1


@patch('alexandria.integrations.google_books.requests.get')
def test_get_book_details_uses_cache_after_search(mock_get):
    mock_get.return_value = _mock_response(json_data=SEARCH_RESPONSE)

    search_books('dune')
    details = get_book_details('abc123')

    assert mock_get.call_count == 1
    assert details['title'] == 'Dune'
    assert details['google_books_id'] == 'abc123'


@patch('alexandria.integrations.google_books.requests.get')
def test_search_books_does_not_cache_http_errors(mock_get):
    mock_get.return_value = _mock_response(status_code=429, json_data={'error': {'message': 'Quota exceeded'}})

    first = search_books('dune')
    second = search_books('dune')

    assert mock_get.call_count == 2
    assert first.error_message == 'Quota exceeded'
    assert second.error_message == 'Quota exceeded'


@patch('alexandria.integrations.google_books.requests.get')
def test_get_book_details_does_not_cache_http_errors(mock_get):
    mock_get.return_value = _mock_response(status_code=404, json_data={'error': {'message': 'Not found'}})

    first = get_book_details('missing')
    second = get_book_details('missing')

    assert mock_get.call_count == 2
    assert first is None
    assert second is None


@patch('alexandria.integrations.google_books.requests.get')
def test_get_book_details_caches_successful_volume_fetch(mock_get):
    mock_get.return_value = _mock_response(json_data=VOLUME_RESPONSE)

    first = get_book_details('abc123')
    second = get_book_details('abc123')

    assert mock_get.call_count == 1
    assert first['title'] == 'Dune'
    assert second['title'] == 'Dune'


@patch('alexandria.integrations.google_books.requests.get')
def test_search_books_uses_fallback_cover_when_image_links_missing(mock_get):
    mock_get.return_value = _mock_response(json_data=SEARCH_RESPONSE)

    outcome = search_books('dune')

    assert outcome.results[0]['thumbnail'].endswith('zoom=4&source=gbs_api')
    assert outcome.results[0]['isbn'] is None
