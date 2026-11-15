import io
import json

import pytest
from PIL import Image

from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import covers


def _png(size):
    buf = io.BytesIO()
    Image.new('RGB', size, 'white').save(buf, 'PNG')
    return buf.getvalue()


REAL = _png((300, 450))
GOOGLE_PLACEHOLDER = _png((128, 170))
PIXEL = _png((1, 1))
OL = 'https://covers.openlibrary.org/b/isbn/{}-L.jpg'


def fake_web(monkeypatch, routes):
    """routes: substring of URL -> bytes (or None for 404). Unlisted URLs 404."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        for part, body in routes.items():
            if part in url:
                return body
        return None

    monkeypatch.setattr(covers, '_get', fake_get)
    return calls


def book(**kw):
    defaults = dict(title='Outcomes Over Output', authors='Joshua Seiden', isbn='9781393721772', google_books_id='abc',
                    thumbnail=OL.format('9781393721772'))
    defaults.update(kw)
    return Book(**defaults)


def test_google_placeholder_is_not_a_cover():
    assert covers.is_real_cover(REAL, 'https://books.google.com/x')
    assert not covers.is_real_cover(GOOGLE_PLACEHOLDER, 'https://books.google.com/x')
    assert covers.is_real_cover(_png((128, 170)), 'https://example.org/x') is True


def test_one_pixel_gif_and_garbage_are_not_covers():
    assert not covers.is_real_cover(PIXEL, OL.format('1'))
    assert not covers.is_real_cover(b'not an image')
    assert not covers.is_real_cover(None)


def test_title_normalisation_ignores_case_accents_and_subtitle():
    assert covers.normalize_title("L'Étranger") == covers.normalize_title('l etranger')
    assert covers.normalize_title('Sapiens: A Brief History of Humankind') == 'sapiens'
    assert covers.normalize_title('Outcomes Over Output') != covers.normalize_title(
        "Summary of Josh Seiden's Outcomes over Output"
    )


def test_current_cover_that_works_is_kept(monkeypatch):
    fake_web(monkeypatch, {'covers.openlibrary.org': REAL})
    match = covers.find_cover(book())
    assert match.source == 'current'


def test_falls_back_to_the_other_provider(monkeypatch):
    fake_web(monkeypatch, {'covers.openlibrary.org': PIXEL, 'books.google.com': REAL})
    match = covers.find_cover(book())
    assert match.source == 'fallback' and 'books.google.com' in match.url


def test_search_finds_another_edition_with_a_cover(monkeypatch):
    docs = {'docs': [
        {'title': "Summary of Josh Seiden's Outcomes over Output", 'cover_i': 1},
        {'title': 'Outcomes Over Output', 'author_name': ['Joshua Seiden'], 'cover_i': 15265474},
    ]}
    fake_web(monkeypatch, {
        'covers.openlibrary.org/b/id/15265474': REAL,
        'covers.openlibrary.org/b/isbn': PIXEL,
        'books.google.com': GOOGLE_PLACEHOLDER,
        'openlibrary.org/search.json': json.dumps(docs).encode(),
    })
    match = covers.find_cover(book())
    assert match.source == 'search'
    assert match.url.endswith('/b/id/15265474-L.jpg')


def test_search_rejects_a_different_author(monkeypatch):
    docs = {'docs': [{'title': 'Outcomes Over Output', 'author_name': ['Someone Else'], 'cover_i': 9}]}
    fake_web(monkeypatch, {
        'covers.openlibrary.org/b/id/9': REAL,
        'openlibrary.org/search.json': json.dumps(docs).encode(),
    })
    assert covers.find_cover(book()) is None


def test_no_search_flag_skips_the_title_lookup(monkeypatch):
    calls = fake_web(monkeypatch, {})
    assert covers.find_cover(book(), search=False) is None
    assert not any('search.json' in c for c in calls)


def test_improve_cover_never_raises(app, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('network down')

    monkeypatch.setattr(covers, 'find_cover', boom)
    with app.app_context():
        b = book()
        db.session.add(b)
        db.session.commit()
        assert covers.improve_cover(b) is False


def test_improve_cover_stores_the_working_url(app, monkeypatch):
    fake_web(monkeypatch, {'covers.openlibrary.org': PIXEL, 'books.google.com': REAL})
    with app.app_context():
        b = book()
        db.session.add(b)
        db.session.commit()
        assert covers.improve_cover(b) is True
        assert 'books.google.com' in Book.query.first().thumbnail


@pytest.fixture
def cli_library(app, monkeypatch):
    docs = {'docs': [{'title': 'Outcomes Over Output', 'author_name': ['Joshua Seiden'], 'cover_i': 15265474}]}
    fake_web(monkeypatch, {
        'b/id/15265474': REAL,
        'isbn/9780000000001': REAL,
        'isbn/': PIXEL,
        'books.google.com': GOOGLE_PLACEHOLDER,
        'openlibrary.org/search.json': json.dumps(docs).encode(),
    })
    monkeypatch.setattr('alexandria.cli.PAUSE_SECONDS', 0)
    with app.app_context():
        db.session.add_all([
            book(),
            Book(title='Fine Book', authors='A. Writer', isbn='9780000000001'),
            Book(title='Nothing Anywhere', authors='Nobody', isbn='9780000000002'),
        ])
        db.session.commit()
    return app


def test_repair_is_a_dry_run_by_default(cli_library, tmp_path):
    result = cli_library.test_cli_runner().invoke(args=['covers', 'repair'])
    assert result.exit_code == 0, result.output
    assert 'Outcomes Over Output: search' in result.output
    assert 'Nothing Anywhere: no cover found' in result.output
    assert '0 already stored, 1 to store, 1 to change, 1 without a cover' in result.output
    assert 'Dry run' in result.output
    with cli_library.app_context():
        assert Book.query.filter_by(title='Outcomes Over Output').one().thumbnail == OL.format('9781393721772')
    assert not (tmp_path / 'covers').exists()


def test_repair_apply_stores_covers_and_changes_only_what_needs_it(cli_library, tmp_path):
    result = cli_library.test_cli_runner().invoke(args=['covers', 'repair', '--apply'])
    assert 'Changed 1 URLs, stored 2 covers.' in result.output
    with cli_library.app_context():
        seiden = Book.query.filter_by(title='Outcomes Over Output').one()
        fine = Book.query.filter_by(title='Fine Book').one()
        assert seiden.thumbnail.endswith('15265474-L.jpg')
        assert fine.thumbnail is None  # its URL worked: only the file is added
        assert (tmp_path / 'covers' / f'{seiden.id}.jpg').is_file()
        assert (tmp_path / 'covers' / f'{fine.id}.jpg').is_file()


def test_repair_skips_books_that_already_have_a_stored_cover(cli_library):
    runner = cli_library.test_cli_runner()
    runner.invoke(args=['covers', 'repair', '--apply'])
    again = runner.invoke(args=['covers', 'repair'])
    assert '2 already stored, 0 to store, 0 to change, 1 without a cover' in again.output
