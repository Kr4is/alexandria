from datetime import UTC, datetime

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book


def get_reading_and_finished_lists():
    reading_list = Book.query.filter_by(status=BookStatus.READING).order_by(Book.date_added.desc()).all()
    finished_list = Book.query.filter_by(status=BookStatus.FINISHED).order_by(Book.date_finished.desc()).all()
    return reading_list, finished_list


def get_collection_lists(page: int = 1, per_page: int = 24) -> dict:
    """Return all books grouped by status for the index page.

    The ``finished`` key is a Flask-SQLAlchemy Pagination object;
    all others are plain lists.
    """
    all_books = Book.query.order_by(Book.date_added.desc()).all()
    groups: dict[str, list] = {s: [] for s in BookStatus.ALL}
    for book in all_books:
        if book.status in groups:
            groups[book.status].append(book)

    # Sort finished by date_finished descending, then paginate in Python
    finished_sorted = sorted(
        groups[BookStatus.FINISHED],
        key=lambda b: b.date_finished or b.date_added,
        reverse=True,
    )
    total = len(finished_sorted)
    start = (page - 1) * per_page
    groups[BookStatus.FINISHED] = finished_sorted[start:start + per_page]
    groups['_finished_total'] = total
    groups['_finished_pages'] = max(1, (total + per_page - 1) // per_page)
    return groups


def filter_books(q: str | None = None, status: str | None = None,
                 sort: str = 'date_added_desc', page: int = 1, per_page: int = 24):
    """Full-text + status filter with pagination. Returns Flask-SQLAlchemy Pagination."""
    query = Book.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(Book.title.ilike(like), Book.authors.ilike(like))
        )
    if status and status in BookStatus.ALL:
        query = query.filter_by(status=status)

    sort_map = {
        'date_added_desc': Book.date_added.desc(),
        'title_asc': Book.title.asc(),
        'title_desc': Book.title.desc(),
        'date_finished_desc': Book.date_finished.desc().nulls_last(),
    }
    order = sort_map.get(sort, Book.date_added.desc())
    query = query.order_by(order)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def get_book_or_404(book_id: int):
    return db.get_or_404(Book, book_id)


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
        isbn=details.get('isbn'),
        description=details['description'],
        page_count=details.get('page_count'),
        categories=details['categories'],
        published_year=details.get('published_year'),
        language=details.get('language'),
        average_rating=details.get('average_rating'),
        status=BookStatus.READING,
    )
    db.session.add(new_book)
    db.session.commit()
    return new_book


def mark_book_finished(book: Book) -> None:
    if book.status == BookStatus.FINISHED:
        return
    book.status = BookStatus.FINISHED
    book.date_finished = datetime.now(UTC)
    db.session.commit()


def update_book_from_form(book: Book, form) -> list[tuple[str, str]]:
    """Apply POST form to book. Returns list of (message, category) tuples for errors."""
    flashes: list[tuple[str, str]] = []
    new_status = form.get('status')
    if new_status in BookStatus.ALL:
        book.status = new_status
        if new_status == BookStatus.READING:
            book.date_finished = None

    date_added_str = form.get('date_added')
    if date_added_str:
        try:
            book.date_added = datetime.strptime(date_added_str, '%Y-%m-%d').replace(tzinfo=UTC)
        except ValueError:
            flashes.append(('Invalid date format for Date Added', 'error'))

    date_finished_str = form.get('date_finished')
    if date_finished_str:
        try:
            book.date_finished = datetime.strptime(date_finished_str, '%Y-%m-%d').replace(tzinfo=UTC)
        except ValueError:
            flashes.append(('Invalid date format for Date Finished', 'error'))
    elif new_status != BookStatus.READING:
        book.date_finished = None

    personal_rating_str = form.get('personal_rating', '').strip()
    if personal_rating_str:
        try:
            rating = float(personal_rating_str)
            if 1.0 <= rating <= 5.0:
                book.personal_rating = rating
            else:
                flashes.append(('Rating must be between 1 and 5', 'error'))
        except ValueError:
            flashes.append(('Invalid rating value', 'error'))
    else:
        book.personal_rating = None

    book.personal_notes = form.get('personal_notes', '').strip() or None

    db.session.commit()
    return flashes


def delete_book(book: Book) -> None:
    db.session.delete(book)
    db.session.commit()
