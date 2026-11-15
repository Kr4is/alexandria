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
    book = SimpleNamespace(id=1, remote_cover_url='https://x/y.png', cover_fallback_url=None)
    assert share_card.fetch_cover(book) is None
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


# --- the Circulation Record card -----------------------------------------------

def _book(**kw):
    defaults = dict(id=7, title='A Book', authors='A. Writer', page_count=300, published_year='2001',
                    date_added=datetime.now(UTC) - timedelta(days=30), date_started=None, date_finished=None,
                    average_rating=4.0, personal_rating=None, status='tbr')
    defaults.update(kw)
    return SimpleNamespace(**defaults)


@pytest.mark.parametrize('status,expected', [
    ('finished', ('FINISHED', share_card.INK_FINISHED)),
    ('reading', ('STARTED', share_card.INK_STARTED)),
    ('dnf', ('RETURNED UNREAD', share_card.INK_RETURNED)),
    ('tbr', None),
    ('paused', None),
])
def test_stamp_follows_the_event_and_its_ink(status, expected):
    now = datetime.now(UTC)
    book = _book(status=status, date_finished=now - timedelta(days=2), date_started=now - timedelta(days=9))
    stamp = share_card._stamp_for(book, share_card.build_metrics(book))
    assert (stamp[0], stamp[2]) == expected if expected else stamp is None


def test_reading_card_carries_the_start_date():
    book = _book(status='reading', date_started=datetime(2026, 10, 6, tzinfo=UTC))
    stamp = share_card._stamp_for(book, share_card.build_metrics(book))
    assert stamp[1] == '06 OCT 2026'


@pytest.mark.parametrize('status', ['reading', 'finished', 'tbr', 'paused', 'dnf'])
def test_every_status_renders_at_card_size(status):
    now = datetime.now(UTC)
    book = _book(status=status, personal_rating=4.5, date_finished=now, date_started=now - timedelta(days=5),
                 title='A very long title that has to wrap onto several lines and still fit the card')
    png, used = share_card.render_card(book, cover=Image.new('RGB', (300, 450), 'navy'))
    assert used is True
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


def test_card_without_cover_draws_the_typed_index_card(monkeypatch):
    monkeypatch.setattr(share_card, 'fetch_cover', lambda book: None)
    png, used = share_card.render_card(_book())
    assert used is False
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


def test_google_image_not_available_is_not_used_as_a_cover(monkeypatch):
    monkeypatch.setattr(share_card.requests, 'get', lambda *a, **k: _response(_png((128, 170))))
    book = SimpleNamespace(id=None, remote_cover_url='https://books.google.com/books/content?id=x',
                           cover_fallback_url=None)
    assert share_card.fetch_cover(book) is None


def test_etag_depends_on_the_card_design_inputs(app, make_book):
    now = datetime.now(UTC)
    book = make_book(title='Reading', status='reading', date_started=now - timedelta(days=3))
    with app.app_context():
        b = db.session.get(Book, book)
        first = share_card.card_etag(b, share_card.build_metrics(b))
        b.date_started = now - timedelta(days=8)
        assert share_card.card_etag(b, share_card.build_metrics(b)) != first
