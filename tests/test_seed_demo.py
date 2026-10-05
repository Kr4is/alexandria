from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from scripts.seed_demo import MARKER, main

EXPECTED = {
    BookStatus.FINISHED: 15,
    BookStatus.READING: 2,
    BookStatus.PAUSED: 2,
    BookStatus.DNF: 1,
    BookStatus.TBR: 4,
}


def _demo(app):
    with app.app_context():
        return Book.query.filter(Book.google_books_id.startswith(MARKER)).all()


def test_seed_creates_expected_counts(app, capsys):
    assert main([]) == 0
    books = _demo(app)
    for status, n in EXPECTED.items():
        assert sum(b.status == status for b in books) == n
    assert 'created 24' in capsys.readouterr().out

    finished = [b for b in books if b.status == BookStatus.FINISHED]
    assert all(b.personal_rating for b in finished)
    assert len({b.personal_rating for b in finished}) > 3
    assert all(b.date_added < b.date_finished for b in finished)
    assert {b.language for b in books} >= {'en', 'es', 'fr'}
    assert any(not b.isbn and not b.page_count and not b.description for b in books)


def test_seed_is_idempotent(app, capsys):
    main([])
    capsys.readouterr()
    main([])
    assert 'created 0' in capsys.readouterr().out
    assert len(_demo(app)) == 24


def test_reset_only_removes_demo_rows(app, make_book):
    user_id = make_book(title='My Own Book', google_books_id='real-id-1')
    main([])
    with app.app_context():
        demo = Book.query.filter_by(google_books_id=MARKER + 'dune').one()
        demo.title = 'Edited'
        db.session.commit()

    main(['--reset'])

    with app.app_context():
        assert db.session.get(Book, user_id).title == 'My Own Book'
        assert Book.query.filter_by(google_books_id=MARKER + 'dune').one().title == 'Dune'
        assert Book.query.count() == 25
