from datetime import UTC, datetime

from alexandria.extensions import db
from alexandria.models import Book


def get_reading_and_finished_lists():
    reading_list = Book.query.filter_by(status='reading').order_by(Book.date_added.desc()).all()
    finished_list = Book.query.filter_by(status='finished').order_by(Book.date_finished.desc()).all()
    return reading_list, finished_list


def get_book_or_404(book_id: int):
    return Book.query.get_or_404(book_id)


def library_google_books_ids() -> set:
    rows = (
        Book.query.with_entities(Book.google_books_id)
        .filter(Book.google_books_id.isnot(None))
        .all()
    )
    return {r[0] for r in rows if r[0]}


def book_by_google_id(google_books_id: str):
    return Book.query.filter_by(google_books_id=google_books_id).first()


def add_book_from_api_details(details: dict) -> Book:
    new_book = Book(
        google_books_id=details['google_books_id'],
        title=details['title'],
        authors=details['authors'],
        thumbnail=details['thumbnail'],
        description=details['description'],
        page_count=details.get('page_count'),
        categories=details['categories'],
        published_year=details.get('published_year'),
        language=details.get('language'),
        average_rating=details.get('average_rating'),
        status='reading',
    )
    db.session.add(new_book)
    db.session.commit()
    return new_book


def mark_book_finished(book: Book) -> None:
    book.status = 'finished'
    book.date_finished = datetime.now(UTC)
    db.session.commit()


def update_book_from_form(book: Book, form) -> list[str]:
    """Apply POST form to book. Returns list of flash (message, category) tuples for errors."""
    flashes = []
    new_status = form.get('status')
    if new_status in ('reading', 'finished'):
        book.status = new_status

    date_added_str = form.get('date_added')
    if date_added_str:
        try:
            book.date_added = datetime.strptime(date_added_str, '%Y-%m-%d')
        except ValueError:
            flashes.append(('Invalid date format for Date Added', 'error'))

    date_finished_str = form.get('date_finished')
    if date_finished_str:
        try:
            book.date_finished = datetime.strptime(date_finished_str, '%Y-%m-%d')
        except ValueError:
            flashes.append(('Invalid date format for Date Finished', 'error'))
    else:
        book.date_finished = None

    db.session.commit()
    return flashes


def delete_book(book: Book) -> None:
    db.session.delete(book)
    db.session.commit()
