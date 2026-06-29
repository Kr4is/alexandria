"""CRUD route tests for books."""
from datetime import UTC, datetime

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book


def test_finish_book_sets_status_and_date(app, auth_client, make_book):
    book_id = make_book(title='Voyage', status=BookStatus.READING)
    resp = auth_client.post(f'/finish/{book_id}', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book.status == BookStatus.FINISHED
        assert book.date_finished is not None


def test_finish_book_idempotent(app, auth_client, make_book):
    """Finishing an already-finished book does not change the date."""
    fixed_date = datetime(2025, 1, 1, tzinfo=UTC)
    book_id = make_book(title='Done', status=BookStatus.FINISHED,
                        date_finished=fixed_date)
    auth_client.post(f'/finish/{book_id}')
    with app.app_context():
        book = db.session.get(Book, book_id)
        # SQLite strips tz info; compare date portion only
        assert book.date_finished.replace(tzinfo=None) == fixed_date.replace(tzinfo=None)


def test_edit_book_reading_clears_date_finished(app, auth_client, make_book):
    book_id = make_book(title='Rereading', status=BookStatus.FINISHED,
                        date_finished=datetime(2025, 6, 1, tzinfo=UTC))
    auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING,
        'date_added': '2025-01-01',
        'date_finished': '',
    })
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book.status == BookStatus.READING
        assert book.date_finished is None


def test_edit_book_invalid_date_flashes_error(auth_client, make_book):
    book_id = make_book()
    resp = auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING,
        'date_added': 'not-a-date',
        'date_finished': '',
    }, follow_redirects=True)
    assert b'Invalid date format' in resp.data
    assert b'updated successfully' not in resp.data


def test_edit_book_valid_data_flashes_success(auth_client, make_book):
    book_id = make_book()
    resp = auth_client.post(f'/edit/{book_id}', data={
        'status': BookStatus.READING,
        'date_added': '2025-06-01',
        'date_finished': '',
    }, follow_redirects=True)
    assert b'updated successfully' in resp.data


def test_delete_book(app, auth_client, make_book):
    book_id = make_book(title='To Delete')
    resp = auth_client.post(f'/delete/{book_id}', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(Book, book_id) is None


def test_delete_nonexistent_book_returns_404(auth_client):
    resp = auth_client.post('/delete/99999')
    assert resp.status_code == 404
