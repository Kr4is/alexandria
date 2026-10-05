import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import requests
from PIL import Image

from alexandria.blueprints import share as share_bp
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import share_card


def _png(size=(200, 300), color=(120, 40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]


def _response(content: bytes):
    return _FakeResponse(content)


@pytest.fixture(autouse=True)
def _clear_render_cache():
    share_bp._RENDERED.clear()


@pytest.fixture
def finished_book(make_book):
    now = datetime.now(UTC)
    return make_book(
        title='Pride and Prejudice',
        authors='Jane Austen',
        isbn='9780141439518',
        status='finished',
        page_count=300,
        average_rating=4.1,
        personal_rating=4.5,
        date_added=now - timedelta(days=40),
        date_finished=now - timedelta(days=10),
    )


@pytest.fixture
def cover_ok(monkeypatch):
    monkeypatch.setattr(share_card.requests, 'get', lambda *a, **k: _response(_png()))


def test_share_page_is_public_with_open_graph(client, finished_book, cover_ok):
    resp = client.get(f'/book/{finished_book}/share')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'property="og:title"' in html
    assert 'Pride and Prejudice' in html
    assert f'http://localhost/book/{finished_book}/share' in html
    assert f'http://localhost/book/{finished_book}/card.png?v=' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert 'Pages / day' in html


def test_unknown_book_404(client):
    assert client.get('/book/999/share').status_code == 404
    assert client.get('/book/999/card.png').status_code == 404


def test_card_png_headers_and_dimensions(client, finished_book, cover_ok):
    resp = client.get(f'/book/{finished_book}/card.png')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert resp.headers['Cache-Control'] == 'public, max-age=3600'
    assert resp.headers['ETag']
    assert Image.open(io.BytesIO(resp.data)).size == (1200, 630)


def test_card_png_honours_if_none_match(client, finished_book, cover_ok):
    first = client.get(f'/book/{finished_book}/card.png')
    second = client.get(
        f'/book/{finished_book}/card.png', headers={'If-None-Match': first.headers['ETag']}
    )
    assert second.status_code == 304
    assert second.headers['Cache-Control'] == 'public, max-age=3600'
    assert second.data == b''


def test_etag_changes_with_inputs(app, client, finished_book, cover_ok):
    before = client.get(f'/book/{finished_book}/card.png').headers['ETag']
    with app.app_context():
        db.session.get(Book, finished_book).personal_rating = 2.0
        db.session.commit()
    assert client.get(f'/book/{finished_book}/card.png').headers['ETag'] != before


def test_card_falls_back_when_network_fails(client, finished_book, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError('offline')

    monkeypatch.setattr(share_card.requests, 'get', boom)
    resp = client.get(f'/book/{finished_book}/card.png')
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(resp.data)).size == (1200, 630)
    # degraded card must not be pinned by validators or long caches
    assert 'ETag' not in resp.headers
    assert resp.headers['Cache-Control'] == 'public, max-age=60'


@pytest.mark.parametrize('size', [(1, 1), (60, 90)])
def test_card_ignores_placeholder_cover(client, finished_book, monkeypatch, size):
    monkeypatch.setattr(share_card.requests, 'get', lambda *a, **k: _response(_png(size)))
    assert share_card.fetch_cover(SimpleNamespace(cover_url='https://x/y.png', cover_fallback_url=None)) is None
    assert client.get(f'/book/{finished_book}/card.png').status_code == 200


def test_card_survives_corrupt_cover(client, finished_book, monkeypatch):
    monkeypatch.setattr(share_card.requests, 'get', lambda *a, **k: _response(b'not an image'))
    assert client.get(f'/book/{finished_book}/card.png').status_code == 200


def test_card_with_unbroken_title(client, make_book, cover_ok):
    book_id = make_book(title='Supercalifragilistic' * 12, authors='X', status='tbr')
    resp = client.get(f'/book/{book_id}/card.png')
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(resp.data)).size == (1200, 630)


def test_card_without_cover_or_rating(client, make_book):
    book_id = make_book(title='A' * 150, authors=None, status='tbr')
    resp = client.get(f'/book/{book_id}/card.png')
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(resp.data)).size == (1200, 630)
    assert client.get(f'/book/{book_id}/share').status_code == 200


def test_metrics_finished_book():
    now = datetime(2026, 1, 31, tzinfo=UTC)
    book = SimpleNamespace(
        status='finished', page_count=300, personal_rating=4.5, average_rating=4.0,
        published_year='1813', date_added=now - timedelta(days=50),
        date_started=now - timedelta(days=40), date_finished=now - timedelta(days=10),
    )
    m = share_card.build_metrics(book, now=now)
    assert m['days'] == 30
    assert m['pages_per_day'] == 10.0
    assert dict((label, value) for value, label in m['items'])['Pages'] == '300'
    assert m['finished'].day == 21


def test_metrics_reading_uses_now_and_naive_dates():
    now = datetime(2026, 1, 31, tzinfo=UTC)
    book = SimpleNamespace(
        status='reading', page_count=100, personal_rating=None, average_rating=None,
        published_year=None, date_added=datetime(2026, 1, 21), date_finished=None,
    )
    m = share_card.build_metrics(book, now=now)
    assert (m['days'], m['pages_per_day'], m['finished']) == (10, 10.0, None)


def test_metrics_backfilled_book_has_no_duration():
    now = datetime(2026, 1, 31, tzinfo=UTC)
    book = SimpleNamespace(
        status='finished', page_count=400, personal_rating=None, average_rating=None,
        published_year=None, date_added=now, date_finished=now - timedelta(days=30),
    )
    m = share_card.build_metrics(book, now=now)
    assert m['days'] is None and m['pages_per_day'] is None


def test_metrics_tbr_has_no_reading_time():
    book = SimpleNamespace(
        status='tbr', page_count=464, personal_rating=None, average_rating=None,
        published_year='2011', date_added=datetime(2026, 1, 1), date_finished=None,
    )
    m = share_card.build_metrics(book)
    assert m['days'] is None and m['pages_per_day'] is None
