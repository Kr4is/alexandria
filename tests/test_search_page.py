"""Render tests for the /search page states."""
from alexandria.integrations.google_books import SearchOutcome

RESULT = {
    'google_books_id': 'abc123', 'title': 'Dune', 'authors': 'Frank Herbert',
    'isbn': '9780441013593', 'thumbnail': None, 'description': 'Spice.',
    'page_count': 412, 'categories': 'Fiction, Science', 'published_year': 1965,
    'language': 'en', 'average_rating': 4.5,
}


def _search(monkeypatch, auth_client, outcome, q='dune'):
    monkeypatch.setattr('alexandria.blueprints.books.search_books', lambda _q: outcome)
    return auth_client.get(f'/search?q={q}').get_data(as_text=True)


def test_initial_state_has_no_results(auth_client):
    html = auth_client.get('/search').get_data(as_text=True)
    assert 'Find a book for your shelves' in html
    assert 'name="status"' not in html


def test_result_card_has_metadata_and_status_selector(monkeypatch, auth_client):
    html = _search(monkeypatch, auth_client, SearchOutcome([RESULT]))
    assert 'Frank Herbert' in html and '1965' in html and '412' in html
    assert 'English' in html
    assert 'action="/add/abc123"' in html
    for status in ('reading', 'tbr', 'paused'):
        assert f'name="status" value="{status}"' in html
    assert 'value="finished"' not in html


def test_owned_result_has_no_status_selector(monkeypatch, auth_client, make_book):
    make_book(title='Dune', google_books_id='abc123')
    html = _search(monkeypatch, auth_client, SearchOutcome([RESULT]))
    assert 'In your library' in html
    assert 'name="status"' not in html


def test_no_results_state(monkeypatch, auth_client):
    html = _search(monkeypatch, auth_client, SearchOutcome([]), q='zzzz')
    assert 'Nothing on the shelves' in html


def test_api_error_state(monkeypatch, auth_client):
    html = _search(monkeypatch, auth_client, SearchOutcome([], 'HTTP 429'))
    assert 'Archives unreachable' in html and 'GOOGLE_BOOKS_API_KEY' in html
    assert 'Nothing on the shelves' not in html
