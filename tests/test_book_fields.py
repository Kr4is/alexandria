"""Reading-progress fields: current_page, date_started, format, shelves."""
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from flask_migrate import upgrade

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import books as svc


def _get(app, book_id):
    with app.app_context():
        book = db.session.get(Book, book_id)
        db.session.expunge(book)
        return book


# ── model ────────────────────────────────────────────────────────────────────

def test_to_dict_includes_new_fields(app, make_book):
    book_id = make_book(current_page=12, date_started=datetime(2025, 3, 4, tzinfo=UTC),
                        format='ebook', shelves='Favourites')
    data = _get(app, book_id).to_dict()
    assert data['current_page'] == 12
    assert data['date_started'] == '2025-03-04'
    assert data['format'] == 'ebook'
    assert data['shelves'] == 'Favourites'
    assert data['title'] == 'Test Book'  # existing keys kept


# ── services ─────────────────────────────────────────────────────────────────

def test_quick_set_status_reading_sets_date_started_once(app, make_book):
    book_id = make_book(status=BookStatus.TBR)
    with app.app_context():
        book = db.session.get(Book, book_id)
        svc.quick_set_status(book, BookStatus.READING)
        first = book.date_started
        assert first is not None
        svc.quick_set_status(book, BookStatus.PAUSED)
        svc.quick_set_status(book, BookStatus.READING)
        assert book.date_started == first


def test_quick_set_status_finished_fills_current_page(app, make_book):
    book_id = make_book(page_count=300, current_page=40)
    with app.app_context():
        book = db.session.get(Book, book_id)
        svc.quick_set_status(book, BookStatus.FINISHED)
        assert book.current_page == 300


def test_quick_set_status_tbr_resets_progress(app, make_book):
    book_id = make_book(page_count=300, current_page=40, date_started=datetime(2025, 1, 1, tzinfo=UTC))
    with app.app_context():
        book = db.session.get(Book, book_id)
        svc.quick_set_status(book, BookStatus.TBR)
        assert book.current_page is None
        assert book.date_started is None


def test_reopening_finished_book_resets_progress(app, make_book):
    book_id = make_book(status=BookStatus.FINISHED, page_count=300, current_page=300,
                        date_finished=datetime(2025, 1, 1, tzinfo=UTC))
    with app.app_context():
        book = db.session.get(Book, book_id)
        svc.quick_set_status(book, BookStatus.READING)
        assert book.current_page is None
        assert book.date_finished is None


@pytest.mark.parametrize('raw, expected', [(50, 50), ('75', 75), (-5, 0), (9999, 200), (' 10 ', 10)])
def test_set_progress_clamps(app, make_book, raw, expected):
    book_id = make_book(page_count=200)
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert svc.set_progress(book, raw) is True
        assert book.current_page == expected


@pytest.mark.parametrize('raw', ['', 'abc', None, '1.5'])
def test_set_progress_rejects_garbage(app, make_book, raw):
    book_id = make_book(page_count=200, current_page=7)
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert svc.set_progress(book, raw) is False
        assert book.current_page == 7


def test_set_progress_without_page_count_is_capped(app, make_book):
    book_id = make_book()
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert svc.set_progress(book, 5000)
        assert book.current_page == 5000
        assert svc.set_progress(book, 10 ** 30)
        assert book.current_page == svc.MAX_PAGE


def test_rereading_finished_book_restarts_date_started(app, make_book):
    book_id = make_book(status=BookStatus.FINISHED, date_started=datetime(2020, 1, 1, tzinfo=UTC))
    with app.app_context():
        book = db.session.get(Book, book_id)
        svc.quick_set_status(book, BookStatus.READING)
        assert book.date_started.year > 2020


def test_shelf_name_with_slash(client, make_book):
    make_book(title='Slashy', shelves='Sci-Fi/Fantasy')
    resp = client.get('/shelf/Sci-Fi/Fantasy')
    assert resp.status_code == 200
    assert b'Slashy' in resp.data


def test_books_on_shelf_is_case_insensitive_and_exact(app, make_book):
    make_book(title='A', shelves='Favourites, Sci-Fi')
    make_book(title='B', shelves='favourites')
    make_book(title='C', shelves='Favourites Extra')
    make_book(title='D', shelves=None)
    with app.app_context():
        assert [b.title for b in svc.books_on_shelf('FAVOURITES')] == ['A', 'B']
        assert [b.title for b in svc.books_on_shelf(' sci-fi ')] == ['A']
        assert svc.books_on_shelf('Fav') == []
        assert svc.books_on_shelf('') == []


def test_books_on_shelf_non_ascii_case(app, make_book):
    make_book(title='Ñ', shelves='Ñandú')
    with app.app_context():
        assert len(svc.books_on_shelf('ñandú')) == 1


# ── POST /progress ───────────────────────────────────────────────────────────

def test_progress_route_saves_and_redirects_to_referrer(app, auth_client, make_book):
    book_id = make_book(page_count=200)
    resp = auth_client.post(f'/progress/{book_id}', data={'current_page': '120'},
                            headers={'Referer': 'http://localhost/'})
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'http://localhost/'
    assert _get(app, book_id).current_page == 120


def test_progress_route_defaults_to_detail_and_flashes(auth_client, make_book):
    book_id = make_book(page_count=200)
    resp = auth_client.post(f'/progress/{book_id}', data={'current_page': '50'})
    assert resp.headers['Location'].endswith(f'/book/{book_id}')
    page = auth_client.get(f'/book/{book_id}')
    assert b'Bookmark moved to page 50' in page.data


def test_progress_route_invalid_value_flashes_error(app, auth_client, make_book):
    book_id = make_book(page_count=200, current_page=3)
    resp = auth_client.post(f'/progress/{book_id}', data={'current_page': 'x'}, follow_redirects=True)
    assert b'does not look right' in resp.data
    assert _get(app, book_id).current_page == 3


def test_progress_route_requires_login(client, make_book):
    book_id = make_book()
    resp = client.post(f'/progress/{book_id}', data={'current_page': '5'})
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_progress_route_unknown_book_404(auth_client):
    assert auth_client.post('/progress/9999', data={'current_page': '5'}).status_code == 404


# ── edit form ────────────────────────────────────────────────────────────────

def test_edit_form_renders_new_fields(auth_client, make_book):
    book_id = make_book(page_count=100, format='audiobook', shelves='Lent')
    html = auth_client.get(f'/edit/{book_id}').data.decode()
    for name in ('date_started', 'current_page', 'format', 'shelves'):
        assert f'name="{name}"' in html
    assert 'value="audiobook" selected' in html
    assert 'value="Lent"' in html


def test_edit_form_saves_new_fields(app, auth_client, make_book):
    book_id = make_book(page_count=200)
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING, 'date_added': '2025-01-01', 'date_finished': '',
        'date_started': '2025-02-03', 'current_page': '80', 'format': 'ebook',
        'shelves': ' Favourites ,, sci-fi, FAVOURITES ',
    })
    book = _get(app, book_id)
    assert book.date_started.strftime('%Y-%m-%d') == '2025-02-03'
    assert book.current_page == 80
    assert book.format == 'ebook'
    assert book.shelves == 'Favourites, sci-fi'


def test_edit_form_clamps_page_and_clears_blank_fields(app, auth_client, make_book):
    book_id = make_book(page_count=200, current_page=10, format='paper', shelves='X')
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING, 'current_page': '999'})
    assert _get(app, book_id).current_page == 200
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING, 'current_page': '', 'format': '', 'shelves': ''})
    book = _get(app, book_id)
    assert (book.current_page, book.format, book.shelves) == (None, None, None)


def test_edit_form_without_new_fields_keeps_them(app, auth_client, make_book):
    book_id = make_book(page_count=200, current_page=10, format='paper', shelves='X',
                        date_started=datetime(2025, 1, 1, tzinfo=UTC))
    auth_client.post(f'/edit/{book_id}', data={'status': BookStatus.READING, 'date_added': '2025-01-01'})
    book = _get(app, book_id)
    assert (book.current_page, book.format, book.shelves) == (10, 'paper', 'X')
    assert book.date_started is not None


def test_edit_form_invalid_values_flash_errors(app, auth_client, make_book):
    book_id = make_book(page_count=200)
    resp = auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING, 'date_started': 'nope', 'current_page': 'abc',
        'format': 'scroll', 'shelves': 'x' * 250}, follow_redirects=True)
    for msg in (b'Invalid date format for Date Started', b'Invalid page number',
                b'Unknown format', b'Shelves list is too long'):
        assert msg in resp.data
    book = _get(app, book_id)
    assert book.format is None and book.shelves is None


def test_edit_form_moving_to_reading_sets_date_started(app, auth_client, make_book):
    book_id = make_book(status=BookStatus.TBR)
    auth_client.post(f'/edit/{book_id}', data={'status': BookStatus.READING, 'date_started': ''})
    assert _get(app, book_id).date_started is not None


def test_edit_form_finished_pins_page_to_page_count(app, auth_client, make_book):
    book_id = make_book(page_count=300, current_page=10)
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.FINISHED, 'current_page': '10', 'date_finished': '2025-05-05'})
    assert _get(app, book_id).current_page == 300


def test_edit_form_finished_to_reading_with_prefilled_page_resets(app, auth_client, make_book):
    book_id = make_book(status=BookStatus.FINISHED, page_count=300, current_page=300,
                        date_finished=datetime(2025, 5, 5, tzinfo=UTC))
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING, 'current_page': '300', 'date_finished': '2025-05-05'})
    assert _get(app, book_id).current_page is None


def test_finish_route_fills_current_page(app, auth_client, make_book):
    book_id = make_book(page_count=250, current_page=5)
    auth_client.post(f'/finish/{book_id}')
    assert _get(app, book_id).current_page == 250


# ── shelf page ───────────────────────────────────────────────────────────────

def test_shelf_page_is_public_and_lists_books(client, make_book):
    make_book(title='Dune', shelves='Sci-Fi, Favourites')
    make_book(title='Emma', shelves='Classics')
    resp = client.get('/shelf/sci-fi')
    assert resp.status_code == 200
    assert b'Dune' in resp.data
    assert b'Emma' not in resp.data
    assert b'1 volume' in resp.data


def test_unknown_shelf_shows_empty_state(client):
    resp = client.get('/shelf/nothing')
    assert resp.status_code == 200
    assert b'This shelf is empty' in resp.data


def test_shelf_name_is_escaped(client):
    resp = client.get('/shelf/%3Cscript%3Ealert(1)')
    assert b'<script>alert' not in resp.data
    assert b'&lt;script&gt;alert(1)' in resp.data


# ── export ───────────────────────────────────────────────────────────────────

def test_csv_export_has_new_columns(client, make_book):
    make_book(shelves='A', format='paper')
    header = client.get('/export.csv').data.decode().splitlines()[0]
    for col in ('current_page', 'date_started', 'format', 'shelves'):
        assert col in header


# ── migration ────────────────────────────────────────────────────────────────

def test_migration_upgrades_previous_head_and_backfills_date_started(app):
    with app.app_context():
        db.drop_all()  # startup create_all() built the new schema; rebuild the old one
        upgrade(revision='a1b2c3d4e5f6')
        cols = {c['name'] for c in sa.inspect(db.engine).get_columns('book')}
        assert 'date_started' not in cols
        db.session.execute(sa.text(
            "INSERT INTO book (title, status, date_added, personal_rating) "
            "VALUES ('Old', 'reading', '2024-05-06 07:08:09.000000', 4.5)"))
        db.session.execute(sa.text(
            "INSERT INTO book (title, status, date_added) VALUES ('Older', 'tbr', '2023-01-02 00:00:00.000000')"))
        db.session.commit()

        upgrade()

        cols = {c['name'] for c in sa.inspect(db.engine).get_columns('book')}
        assert {'current_page', 'date_started', 'format', 'shelves'} <= cols
        rows = {b.title: b for b in Book.query.all()}
        assert len(rows) == 2
        assert rows['Old'].personal_rating == 4.5
        assert rows['Old'].date_started == rows['Old'].date_added == datetime(2024, 5, 6, 7, 8, 9)
        assert rows['Older'].date_started is None  # wish-list books haven't started
        assert rows['Old'].current_page is None


def test_migrations_run_on_database_already_created_by_create_all(app):
    """Startup create_all() runs before `flask db upgrade`; the chain must tolerate that."""
    with app.app_context():
        upgrade()
        assert Book.query.count() == 0
