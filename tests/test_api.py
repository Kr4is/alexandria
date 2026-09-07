"""Tests for the public GET /api/reading-activity endpoint."""
from datetime import UTC, datetime

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book


def _add_book(**kwargs):
    defaults = {
        'title': 'Untitled',
        'status': BookStatus.READING,
        'date_added': datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    book = Book(**defaults)
    db.session.add(book)
    db.session.commit()
    return book


class TestReadingActivityNoAuth:
    def test_no_token_configured_is_public(self, client):
        response = client.get('/api/reading-activity')
        assert response.status_code == 200

    def test_empty_collection_returns_empty_lists(self, client):
        response = client.get('/api/reading-activity')
        data = response.get_json()
        assert data['books_finished'] == []
        assert data['currently_reading'] == []
        assert data['stats']['books_finished_count'] == 0
        assert data['stats']['total_pages'] == 0


class TestReadingActivityFiltering:
    def test_books_finished_in_period_included(self, app, client):
        with app.app_context():
            _add_book(
                title='In Period',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 3, 15, tzinfo=UTC),
                page_count=200,
            )
            _add_book(
                title='Before Period',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 1, 1, tzinfo=UTC),
                page_count=100,
            )
            _add_book(
                title='After Period',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 5, 1, tzinfo=UTC),
                page_count=150,
            )

        response = client.get('/api/reading-activity?since=2026-03-01&until=2026-04-01')
        assert response.status_code == 200
        data = response.get_json()
        titles = {b['title'] for b in data['books_finished']}
        assert titles == {'In Period'}
        assert data['stats']['books_finished_count'] == 1
        assert data['stats']['total_pages'] == 200

    def test_until_is_exclusive(self, app, client):
        with app.app_context():
            _add_book(
                title='On Boundary',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 4, 1, tzinfo=UTC),
                page_count=50,
            )

        response = client.get('/api/reading-activity?since=2026-03-01&until=2026-04-01')
        data = response.get_json()
        assert data['books_finished'] == []

    def test_since_is_inclusive(self, app, client):
        with app.app_context():
            _add_book(
                title='On Start Boundary',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 3, 1, tzinfo=UTC),
                page_count=50,
            )

        response = client.get('/api/reading-activity?since=2026-03-01&until=2026-04-01')
        data = response.get_json()
        titles = {b['title'] for b in data['books_finished']}
        assert titles == {'On Start Boundary'}

    def test_no_period_returns_all_finished_books(self, app, client):
        with app.app_context():
            _add_book(
                title='Old One',
                status=BookStatus.FINISHED,
                date_finished=datetime(2020, 1, 1, tzinfo=UTC),
                page_count=10,
            )

        response = client.get('/api/reading-activity')
        data = response.get_json()
        titles = {b['title'] for b in data['books_finished']}
        assert 'Old One' in titles


class TestReadingActivityCurrentlyReading:
    def test_currently_reading_is_not_period_filtered(self, app, client):
        with app.app_context():
            _add_book(
                title='Mid Read',
                status=BookStatus.READING,
                date_added=datetime(2020, 1, 1, tzinfo=UTC),
            )

        response = client.get('/api/reading-activity?since=2026-01-01&until=2026-02-01')
        data = response.get_json()
        titles = {b['title'] for b in data['currently_reading']}
        assert 'Mid Read' in titles

    def test_finished_books_excluded_from_currently_reading(self, app, client):
        with app.app_context():
            _add_book(
                title='Done Reading',
                status=BookStatus.FINISHED,
                date_finished=datetime(2026, 1, 1, tzinfo=UTC),
                page_count=10,
            )

        response = client.get('/api/reading-activity')
        data = response.get_json()
        titles = {b['title'] for b in data['currently_reading']}
        assert 'Done Reading' not in titles


class TestReadingActivityValidation:
    def test_invalid_since_returns_400(self, client):
        response = client.get('/api/reading-activity?since=not-a-date')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_invalid_until_returns_400(self, client):
        response = client.get('/api/reading-activity?until=2026-99-99')
        assert response.status_code == 400

    def test_since_after_until_returns_400(self, client):
        response = client.get('/api/reading-activity?since=2026-05-01&until=2026-01-01')
        assert response.status_code == 400


class TestReadingActivityTokenGate:
    def test_configured_token_rejects_missing_auth(self, app, client):
        app.config['READING_API_TOKEN'] = 'secret-token'
        try:
            response = client.get('/api/reading-activity')
            assert response.status_code == 401
        finally:
            app.config['READING_API_TOKEN'] = None

    def test_configured_token_rejects_wrong_token(self, app, client):
        app.config['READING_API_TOKEN'] = 'secret-token'
        try:
            response = client.get(
                '/api/reading-activity',
                headers={'Authorization': 'Bearer wrong-token'},
            )
            assert response.status_code == 401
        finally:
            app.config['READING_API_TOKEN'] = None

    def test_configured_token_accepts_correct_bearer(self, app, client):
        app.config['READING_API_TOKEN'] = 'secret-token'
        try:
            response = client.get(
                '/api/reading-activity',
                headers={'Authorization': 'Bearer secret-token'},
            )
            assert response.status_code == 200
        finally:
            app.config['READING_API_TOKEN'] = None
