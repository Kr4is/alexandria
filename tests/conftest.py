from datetime import UTC, datetime

import pytest

from alexandria import create_app
from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book


@pytest.fixture(autouse=True)
def no_cover_lookups(monkeypatch):
    """Adding a book looks up covers on the network; tests never do."""
    monkeypatch.setattr('alexandria.services.books.improve_cover', lambda book: False)
    monkeypatch.setenv('STORE_COVERS_ON_STARTUP', '0')  # tests never start background work


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/test.db')
    monkeypatch.setenv('COVERS_DIR', str(tmp_path / 'covers'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    monkeypatch.setenv('LIBRARIAN_USERNAME', 'admin')
    monkeypatch.setenv('LIBRARIAN_PASSWORD', 'testpass')
    application = create_app()
    application.config['WTF_CSRF_ENABLED'] = False
    application.config['RATELIMIT_ENABLED'] = False
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Test client pre-logged-in as librarian."""
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'})
    return c


@pytest.fixture
def make_book(app):
    """Factory that creates and commits a Book, returning its id."""
    def _factory(**kwargs):
        defaults = {
            'title': 'Test Book',
            'authors': 'Test Author',
            'status': BookStatus.READING,
            'date_added': datetime.now(UTC),
        }
        defaults.update(kwargs)
        with app.app_context():
            book = Book(**defaults)
            db.session.add(book)
            db.session.commit()
            return book.id
    return _factory
