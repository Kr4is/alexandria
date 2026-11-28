"""Barcode scanning: ISBN validation, lookup fallback and the /scan routes."""
import pytest

from alexandria.integrations.google_books import SearchOutcome
from alexandria.models import Book
from alexandria.utils.isbn import normalize_isbn

DUNE = {
    'google_books_id': 'abc123', 'title': 'Dune', 'authors': 'Frank Herbert',
    'isbn': '9780441013593', 'thumbnail': None, 'description': 'Spice.',
    'page_count': 412, 'categories': 'Fiction', 'published_year': '1965',
    'language': 'en', 'average_rating': None,
}
OL_ONLY = {**DUNE, 'google_books_id': None, 'title': 'Only On Open Library', 'description': None}


@pytest.mark.parametrize('raw, expected', [
    ('9780441013593', '9780441013593'),
    ('978-0-441-01359-3', '9780441013593'),
    ('0441013597', '9780441013593'),
    ('080442957X', '9780804429573'),
    ('9780441013594', None),  # bad check digit
    ('0441013598', None),
    ('4006381333931', None),  # a valid EAN, but not a book
    ('', None),
    (None, None),
])
def test_normalize_isbn(raw, expected):
    assert normalize_isbn(raw) == expected


def _google(monkeypatch, results, error=None):
    monkeypatch.setattr('alexandria.services.isbn_lookup.search_books',
                        lambda q: SearchOutcome(results, error))


def _open_library(monkeypatch, result):
    monkeypatch.setattr('alexandria.services.isbn_lookup.open_library.lookup_isbn', lambda isbn: result)


def test_scan_pages_need_login(client):
    assert client.get('/scan').status_code == 302
    assert client.get('/scan/lookup?isbn=9780441013593').status_code == 302
    assert client.post('/add/isbn/9780441013593').status_code == 302


def test_scan_page_renders_with_local_decoder(auth_client):
    html = auth_client.get('/scan').get_data(as_text=True)
    assert 'data-start' in html and 'capture="environment"' in html
    assert '/static/js/vendor/zxing_reader.wasm' in html
    assert 'jsdelivr' not in html


def test_search_page_links_to_scanner(auth_client):
    assert 'href="/scan"' in auth_client.get('/search').get_data(as_text=True)


def test_lookup_found_offers_status_choices(monkeypatch, auth_client):
    _google(monkeypatch, [DUNE])
    html = auth_client.get('/scan/lookup?isbn=9780441013593').get_data(as_text=True)
    assert 'Dune' in html and 'action="/add/isbn/9780441013593"' in html
    assert 'name="status" value="reading"' in html


def test_lookup_invalid_isbn(auth_client):
    html = auth_client.get('/scan/lookup?isbn=1234567890123').get_data(as_text=True)
    assert 'not an ISBN' in html


def test_lookup_falls_back_to_open_library(monkeypatch, auth_client):
    _google(monkeypatch, [], error='HTTP 429')
    _open_library(monkeypatch, OL_ONLY)
    html = auth_client.get('/scan/lookup?isbn=9780441013593').get_data(as_text=True)
    assert 'Only On Open Library' in html


def test_lookup_unknown_everywhere(monkeypatch, auth_client):
    _google(monkeypatch, [])
    _open_library(monkeypatch, None)
    html = auth_client.get('/scan/lookup?isbn=9780441013593').get_data(as_text=True)
    assert 'Not in the archives' in html


def test_lookup_flags_book_already_owned(monkeypatch, auth_client, make_book):
    book_id = make_book(title='Dune', isbn='9780441013593')
    _google(monkeypatch, [])
    _open_library(monkeypatch, OL_ONLY)
    html = auth_client.get('/scan/lookup?isbn=9780441013593').get_data(as_text=True)
    assert 'In your library' in html and f'/book/{book_id}' in html
    assert 'name="status"' not in html


def test_add_by_isbn_from_google(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    res = auth_client.post('/add/isbn/9780441013593', data={'status': 'tbr'})
    assert res.status_code == 302
    with app.app_context():
        book = Book.query.filter_by(isbn='9780441013593').one()
        assert book.title == 'Dune' and book.status == 'tbr' and book.google_books_id == 'abc123'


def test_add_by_isbn_from_open_library_has_no_google_id(monkeypatch, app, auth_client):
    _google(monkeypatch, [])
    _open_library(monkeypatch, OL_ONLY)
    auth_client.post('/add/isbn/9780441013593')
    with app.app_context():
        book = Book.query.filter_by(isbn='9780441013593').one()
        assert book.google_books_id is None and book.title == 'Only On Open Library'


def test_add_by_isbn_twice_does_not_duplicate(monkeypatch, app, auth_client):
    _google(monkeypatch, [])
    _open_library(monkeypatch, OL_ONLY)
    auth_client.post('/add/isbn/9780441013593')
    auth_client.post('/add/isbn/9780441013593')
    with app.app_context():
        assert Book.query.filter_by(isbn='9780441013593').count() == 1


def test_add_by_isbn_rejects_bad_isbn(app, auth_client):
    res = auth_client.post('/add/isbn/9780441013594')
    assert res.status_code == 302 and res.headers['Location'].endswith('/scan')
    with app.app_context():
        assert Book.query.count() == 0


def _batch(client, isbn='9780441013593', **data):
    return client.post('/scan/batch', data={'isbn': isbn, **data}).get_json()


def test_batch_needs_login(client):
    assert client.post('/scan/batch', data={'isbn': '9780441013593'}).status_code == 302
    assert client.post('/scan/batch/1/undo').status_code == 302


def test_batch_adds_as_to_read_by_default(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    out = _batch(auth_client)
    assert out['result'] == 'added' and out['title'] == 'Dune' and out['url'] == f"/book/{out['book_id']}"
    with app.app_context():
        book = Book.query.one()
        assert book.status == 'tbr' and book.date_started is None


def test_batch_uses_chosen_status(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    _batch(auth_client, status='paused')
    with app.app_context():
        assert Book.query.one().status == 'paused'


def test_batch_rejects_unlisted_status(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    _batch(auth_client, status='finished')
    with app.app_context():
        assert Book.query.one().status == 'tbr'


def test_batch_reports_owned_without_duplicating(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    assert _batch(auth_client)['result'] == 'added'
    again = _batch(auth_client)
    assert again['result'] == 'owned' and again['title'] == 'Dune'
    with app.app_context():
        assert Book.query.count() == 1


def test_batch_missing_and_invalid(monkeypatch, app, auth_client):
    _google(monkeypatch, [])
    _open_library(monkeypatch, None)
    assert _batch(auth_client)['result'] == 'missing'
    assert _batch(auth_client, isbn='1234567890123')['result'] == 'invalid'
    with app.app_context():
        assert Book.query.count() == 0


def test_batch_undo_withdraws_the_book(monkeypatch, app, auth_client):
    _google(monkeypatch, [DUNE])
    book_id = _batch(auth_client)['book_id']
    assert auth_client.post(f'/scan/batch/{book_id}/undo').get_json()['result'] == 'undone'
    with app.app_context():
        assert Book.query.count() == 0
    assert auth_client.post('/scan/batch/999/undo').status_code == 404
