import io
from types import SimpleNamespace

from PIL import Image

from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import cover_store, covers, share_card
from alexandria.services import books as book_service


def jpeg(size=(300, 450)):
    buf = io.BytesIO()
    Image.new('RGB', size, 'navy').save(buf, 'PNG')
    return buf.getvalue()


def make_book(**kw):
    book = Book(title='Local Book', authors='A. Writer', isbn='9780000000001', **kw)
    db.session.add(book)
    db.session.commit()
    return book


def test_save_normalises_to_a_capped_jpeg(app):
    with app.app_context():
        assert cover_store.save(7, jpeg((1200, 3000)))
        img = Image.open(cover_store.path_for(7))
        assert img.format == 'JPEG' and img.height == cover_store.MAX_HEIGHT


def test_save_rejects_garbage_without_raising(app):
    with app.app_context():
        assert cover_store.save(7, b'nope') is False
        assert not cover_store.path_for(7).exists()


def test_cover_url_is_local_when_stored_and_remote_otherwise(app):
    with app.app_context():
        book = make_book()
        assert book.cover_url == book.remote_cover_url
        assert book.cover_url.startswith('https://')
        cover_store.save(book.id, jpeg())
        assert book.cover_url.startswith(f'/cover/{book.id}?v=')
        assert book.remote_cover_url.startswith('https://')  # API and exports stay absolute
        assert book.to_dict()['thumbnail'].startswith('https://')


def test_cover_route_serves_the_file_and_revalidates(app, client):
    with app.app_context():
        book = make_book()
        cover_store.save(book.id, jpeg())
        book_id = book.id
    resp = client.get(f'/cover/{book_id}')
    assert resp.status_code == 200 and resp.mimetype == 'image/jpeg'
    assert 'max-age=31536000' in resp.headers['Cache-Control']
    again = client.get(f'/cover/{book_id}', headers={'If-None-Match': resp.headers['ETag']})
    assert again.status_code == 304


def test_cover_route_404_without_a_file(client):
    assert client.get('/cover/999').status_code == 404


def test_templates_use_the_local_cover(app, client):
    with app.app_context():
        book = make_book(status='finished')
        cover_store.save(book.id, jpeg())
        book_id = book.id
    assert f'/cover/{book_id}?v=' in client.get('/').get_data(as_text=True)


def test_share_card_reads_the_stored_cover_without_the_network(app, monkeypatch):
    def boom(*a, **k):
        raise AssertionError('network used')

    monkeypatch.setattr(share_card.requests, 'get', boom)
    with app.app_context():
        book = make_book()
        cover_store.save(book.id, jpeg())
        assert share_card.fetch_cover(book) is not None


def test_deleting_a_book_removes_its_cover(app):
    with app.app_context():
        book = make_book()
        cover_store.save(book.id, jpeg())
        path = cover_store.path_for(book.id)
        book_service.delete_book(book)
        assert not path.exists()


def test_improve_cover_stores_the_file(app, monkeypatch):
    data = jpeg()
    match = covers.CoverMatch('https://covers.openlibrary.org/x.jpg', 'search', data=data)
    monkeypatch.setattr(covers, 'find_cover', lambda book, **k: match)
    with app.app_context():
        book = make_book()
        assert covers.improve_cover(book) is True
        assert cover_store.path_for(book.id).is_file()
        assert db.session.get(Book, book.id).thumbnail == 'https://covers.openlibrary.org/x.jpg'


def test_share_card_helper_survives_a_book_without_an_id(app):
    with app.app_context():
        assert share_card.fetch_cover(SimpleNamespace(id=None, remote_cover_url=None, cover_fallback_url=None)) is None


def test_relative_covers_dir_is_taken_from_the_project_root(tmp_path, monkeypatch):
    from alexandria import create_app

    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/t.db')
    monkeypatch.setenv('SECRET_KEY', 'x')
    monkeypatch.setenv('COVERS_DIR', 'instance/test-covers-relative')
    app = create_app()
    root = app.config['COVERS_DIR']
    assert root.endswith('instance/test-covers-relative') and root.startswith('/')
    with app.app_context():
        book = make_book()
        cover_store.save(book.id, jpeg())
        book_id = book.id
    try:
        assert app.test_client().get(f'/cover/{book_id}').status_code == 200
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)
