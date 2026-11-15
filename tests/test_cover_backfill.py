import io
import threading

from PIL import Image

from alexandria import create_app
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import cover_backfill, cover_store, covers


def image():
    buf = io.BytesIO()
    Image.new('RGB', (300, 450), 'teal').save(buf, 'PNG')
    return buf.getvalue()


def add_books(*titles):
    for title in titles:
        db.session.add(Book(title=title, authors='A. Writer', isbn='9780000000001'))
    db.session.commit()


def fake_find(results):
    """results: title -> CoverMatch | None."""
    def find(book, search=True, **kw):
        assert search is False, 'the background backfill must never run a title search'
        return results.get(book.title)

    return find


def test_backfill_stores_working_covers_only(app, monkeypatch):
    monkeypatch.setattr(cover_backfill, 'PAUSE_SECONDS', 0)
    match = covers.CoverMatch('https://x/y.jpg', 'current', data=image())
    monkeypatch.setattr(cover_backfill, 'find_cover', fake_find({'Has Cover': match}))
    with app.app_context():
        add_books('Has Cover', 'No Cover')
        counts = cover_backfill.backfill()
        assert counts == {'stored': 1, 'unresolved': 1}
        has = Book.query.filter_by(title='Has Cover').one()
        no = Book.query.filter_by(title='No Cover').one()
        assert cover_store.path_for(has.id).is_file()
        assert not cover_store.path_for(no.id).exists()


def test_backfill_skips_books_that_already_have_a_file(app, monkeypatch):
    monkeypatch.setattr(cover_backfill, 'PAUSE_SECONDS', 0)

    def boom(*a, **k):
        raise AssertionError('should not look anything up')

    monkeypatch.setattr(cover_backfill, 'find_cover', boom)
    with app.app_context():
        add_books('Stored')
        cover_store.save(Book.query.one().id, image())
        assert cover_backfill.backfill() == {'stored': 0, 'unresolved': 0}


def test_backfill_does_not_overlap_another_run(app, monkeypatch):
    monkeypatch.setattr(cover_backfill, 'find_cover', lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    with app.app_context():
        add_books('Book')
        assert cover_backfill._take_lock()
        assert cover_backfill.backfill() == {'stored': 0, 'unresolved': 0}  # another run holds the lock
        cover_backfill._release_lock()


def test_backfill_releases_its_lock(app, monkeypatch):
    monkeypatch.setattr(cover_backfill, 'PAUSE_SECONDS', 0)
    monkeypatch.setattr(cover_backfill, 'find_cover', fake_find({}))
    with app.app_context():
        add_books('Book')
        cover_backfill.backfill()
        assert not (cover_store.covers_dir() / cover_backfill.LOCK_NAME).exists()


def test_start_once_starts_a_single_thread(app, monkeypatch):
    started = []
    monkeypatch.setattr(threading.Thread, 'start', lambda self: started.append(self.name))
    assert cover_backfill.start_once(app) is True
    assert cover_backfill.start_once(app) is False
    assert started == ['cover-backfill']


def test_first_request_triggers_it_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/t.db')
    monkeypatch.setenv('SECRET_KEY', 'x')
    monkeypatch.setenv('COVERS_DIR', str(tmp_path / 'covers'))
    calls = []
    monkeypatch.setattr(cover_backfill, 'start_once', lambda app: calls.append(1))

    monkeypatch.setenv('STORE_COVERS_ON_STARTUP', '0')
    create_app().test_client().get('/login')
    assert calls == []

    monkeypatch.setenv('STORE_COVERS_ON_STARTUP', '1')
    app = create_app()
    app.test_client().get('/login')
    app.test_client().get('/login')
    assert len(calls) == 2  # the hook runs per request; start_once itself is what dedupes
