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

    ``finished`` holds only the requested page of finished books (newest first);
    ``finished_by_year`` splits that same page into ``[(year, [books])]`` for shelving.
    ``this_year`` and ``counts`` summarise the whole library.
    """
    all_books = Book.query.order_by(Book.date_added.desc()).all()
    groups: dict = {s: [] for s in BookStatus.ALL}
    for book in all_books:
        if book.status in groups:
            groups[book.status].append(book)

    finished_sorted = sorted(
        groups[BookStatus.FINISHED],
        key=lambda b: b.date_finished or b.date_added,
        reverse=True,
    )
    total = len(finished_sorted)
    start = (page - 1) * per_page
    page_books = finished_sorted[start:start + per_page]

    by_year: dict = {}
    for book in page_books:
        by_year.setdefault(_shelf_year(book), []).append(book)

    groups['counts'] = {s: len(groups[s]) for s in BookStatus.ALL}
    groups['counts']['all'] = sum(groups['counts'].values())
    groups['this_year'] = _this_year_summary(finished_sorted)
    groups[BookStatus.FINISHED] = page_books
    groups['finished_by_year'] = list(by_year.items())
    groups['_finished_total'] = total
    groups['_finished_pages'] = max(1, (total + per_page - 1) // per_page)
    return groups


SORT_OPTIONS = {
    'date_added_desc': 'Recently added',
    'date_finished_desc': 'Recently finished',
    'rating_desc': 'Highest rated',
    'pages_desc': 'Longest first',
    'pages_asc': 'Shortest first',
    'title_asc': 'Title A\u2013Z',
    'title_desc': 'Title Z\u2013A',
}


def filter_books(q: str | None = None, status: str | None = None,
                 sort: str = 'date_added_desc', page: int = 1, per_page: int = 24,
                 category: str | None = None, author: str | None = None,
                 year: int | None = None, min_rating: float | None = None):
    """Search + filter + sort with pagination. Returns Flask-SQLAlchemy Pagination."""
    query = Book.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(Book.title.ilike(like), Book.authors.ilike(like))
        )
    if status and status in BookStatus.ALL:
        query = query.filter_by(status=status)
    if category:
        # categories is a comma-separated string: match whole entries, not substrings
        padded = db.literal(',').concat(db.func.replace(Book.categories, ', ', ',')).concat(',')
        query = query.filter(padded.icontains(f',{category},', autoescape=True))
    if author:
        query = query.filter(Book.authors.icontains(author, autoescape=True))
    if year:
        query = query.filter(db.extract('year', Book.date_finished) == year)
    if min_rating:
        query = query.filter(Book.personal_rating >= min_rating)

    sort_map = {
        'date_added_desc': Book.date_added.desc(),
        'title_asc': Book.title.asc(),
        'title_desc': Book.title.desc(),
        'date_finished_desc': Book.date_finished.desc().nulls_last(),
        'rating_desc': Book.personal_rating.desc().nulls_last(),
        'pages_desc': Book.page_count.desc().nulls_last(),
        'pages_asc': Book.page_count.asc().nulls_last(),
    }
    order = sort_map.get(sort, Book.date_added.desc())
    query = query.order_by(order, Book.id.desc())
    return query.paginate(page=page, per_page=per_page, error_out=False)


def get_filter_options() -> dict:
    """Distinct categories, authors and finished-years for the filter form."""
    rows = Book.query.with_entities(Book.categories, Book.authors, Book.date_finished).all()
    # keyed by lowercase: the category filter is case-insensitive, so 'fiction' == 'Fiction'
    categories: dict[str, str] = {}
    authors: dict[str, str] = {}
    years: set[int] = set()
    for cats, auths, finished in rows:
        for c in (cats or '').split(','):
            if c.strip():
                categories.setdefault(c.strip().lower(), c.strip())
        for a in (auths or '').split(','):
            if a.strip():
                authors.setdefault(a.strip().lower(), a.strip())
        if finished:
            years.add(finished.year)
    return {
        'categories': sorted(categories.values(), key=str.lower),
        'authors': sorted(authors.values(), key=str.lower),
        'years': sorted(years, reverse=True),
    }


def get_status_counts() -> dict:
    """Books per status plus an ``all`` total, using a single GROUP BY."""
    rows = db.session.query(Book.status, db.func.count(Book.id)).group_by(Book.status).all()
    counts = {s: 0 for s in BookStatus.ALL}
    counts.update({status: n for status, n in rows if status in counts})
    counts['all'] = sum(counts.values())
    return counts


def _shelf_year(book: Book) -> int | None:
    return book.date_finished.year if book.date_finished else None


def _this_year_summary(finished: list) -> dict:
    year = datetime.now(UTC).year
    done = [b for b in finished if b.date_finished and b.date_finished.year == year]
    ratings = [b.personal_rating for b in done if b.personal_rating]
    return {
        'year': year,
        'books': len(done),
        'pages': sum(b.page_count or 0 for b in done),
        'avg_rating': round(sum(ratings) / len(ratings), 1) if ratings else None,
    }


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


def add_book_from_api_details(details: dict, status: str = BookStatus.READING) -> Book:
    if status not in BookStatus.ALL:
        status = BookStatus.READING
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
        status=status,
        date_started=datetime.now(UTC) if status == BookStatus.READING else None,
    )
    db.session.add(new_book)
    db.session.commit()
    return new_book


BOOK_FORMATS = ('paper', 'ebook', 'audiobook')


MAX_PAGE = 1_000_000  # keeps absurd input inside the INTEGER column when page_count is unknown


def _clamp_page(book: Book, page: int) -> int:
    return max(0, min(page, book.page_count or MAX_PAGE))


def _apply_status_progress(book: Book, old_status: str | None, new_status: str) -> None:
    """Keep date_started / current_page coherent when a book changes status."""
    if new_status == BookStatus.READING:
        if old_status == BookStatus.FINISHED:  # re-reading: a fresh start
            book.current_page = None
            book.date_started = datetime.now(UTC)
        elif not book.date_started:
            book.date_started = datetime.now(UTC)
    elif new_status == BookStatus.FINISHED:
        if book.page_count:
            book.current_page = book.page_count
    elif new_status == BookStatus.TBR:  # not started: forget any progress
        book.current_page = None
        book.date_started = None
    elif old_status == BookStatus.FINISHED:  # reopened as paused / DNF
        book.current_page = None


def set_progress(book: Book, current_page) -> bool:
    """Record the page reached, clamped to [0, page_count]. False if not a number."""
    try:
        page = _clamp_page(book, int(str(current_page).strip()))
    except (TypeError, ValueError):
        return False
    book.current_page = page
    if page > 0 and not book.date_started:
        book.date_started = datetime.now(UTC)
    db.session.commit()
    return True


def _split_shelves(raw: str | None) -> list[str]:
    return [s.strip() for s in (raw or '').split(',') if s.strip()]


def books_on_shelf(name: str) -> list[Book]:
    """Books whose comma-separated ``shelves`` contain ``name`` (case-insensitive, exact entry)."""
    wanted = name.strip().casefold()
    if not wanted:
        return []
    # Matched in Python: SQLite's LIKE is only ASCII case-insensitive.
    # ponytail: scans every shelved book; fine for a personal library, index a shelf table if it grows.
    candidates = Book.query.filter(Book.shelves.isnot(None)).order_by(Book.title.asc()).all()
    return [b for b in candidates if wanted in (s.casefold() for s in _split_shelves(b.shelves))]


def quick_set_status(book: Book, new_status: str) -> bool:
    """Set book status without touching the full edit form. Returns True if changed."""
    if new_status not in BookStatus.ALL:
        return False
    _apply_status_progress(book, book.status, new_status)
    book.status = new_status
    if new_status == BookStatus.FINISHED:
        if not book.date_finished:
            book.date_finished = datetime.now(UTC)
    else:
        book.date_finished = None
    db.session.commit()
    return True


def mark_book_finished(book: Book) -> None:
    if book.status == BookStatus.FINISHED:
        return
    _apply_status_progress(book, book.status, BookStatus.FINISHED)
    book.status = BookStatus.FINISHED
    book.date_finished = datetime.now(UTC)
    db.session.commit()


def update_book_from_form(book: Book, form) -> list[tuple[str, str]]:
    """Apply POST form to book. Returns list of (message, category) tuples for errors."""
    flashes: list[tuple[str, str]] = []
    new_status = form.get('status')
    old_page, old_started = book.current_page, book.date_started
    if new_status in BookStatus.ALL:
        _apply_status_progress(book, book.status, new_status)
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

    _apply_reading_fields(book, form, old_page, old_started, flashes)

    db.session.commit()
    return flashes


def _apply_reading_fields(book: Book, form, old_page, old_started, flashes) -> None:
    """Apply date_started / current_page / format / shelves; each only when posted.

    A posted value equal to what was stored is not an edit, so the status-driven
    defaults from ``_apply_status_progress`` win (e.g. finished -> reading resets progress).
    """
    if 'date_started' in form:
        raw = form['date_started'].strip()
        old_str = old_started.strftime('%Y-%m-%d') if old_started else ''
        if raw != old_str:
            if not raw:
                book.date_started = datetime.now(UTC) if book.status == BookStatus.READING else None
            else:
                try:
                    book.date_started = datetime.strptime(raw, '%Y-%m-%d').replace(tzinfo=UTC)
                except ValueError:
                    flashes.append(('Invalid date format for Date Started', 'error'))

    finished_with_pages = book.status == BookStatus.FINISHED and book.page_count
    if 'current_page' in form and not finished_with_pages:
        raw = form['current_page'].strip()
        if not raw:
            if old_page is not None:
                book.current_page = None
        else:
            try:
                page = int(raw)
            except ValueError:
                flashes.append(('Invalid page number', 'error'))
            else:
                if page != old_page:
                    book.current_page = _clamp_page(book, page)

    if 'format' in form:
        fmt = form['format'].strip().lower()
        if not fmt:
            book.format = None
        elif fmt in BOOK_FORMATS:
            book.format = fmt
        else:
            flashes.append(('Unknown format', 'error'))

    if 'shelves' in form:
        names: list[str] = []
        for name in _split_shelves(form['shelves']):
            if name.casefold() not in (n.casefold() for n in names):
                names.append(name)
        joined = ', '.join(names)
        if len(joined) > 200:
            flashes.append(('Shelves list is too long (200 characters max)', 'error'))
        else:
            book.shelves = joined or None


def delete_book(book: Book) -> None:
    db.session.delete(book)
    db.session.commit()
