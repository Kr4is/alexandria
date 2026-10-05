import hmac
from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services.stats import as_utc, build_stats_context

bp = Blueprint('api', __name__)


def _parse_date_param(raw: str | None, name: str) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` query param into a UTC-aware datetime, or None."""
    if raw is None or raw == '':
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').replace(tzinfo=UTC)
    except ValueError:
        raise ValueError(f"Invalid '{name}' value {raw!r}; expected format YYYY-MM-DD.") from None


def _check_authorized() -> bool:
    """Return True if the request is allowed through.

    When READING_API_TOKEN is unset, the endpoint stays fully open (matching
    the existing public /export.<fmt> route). When set, a matching
    'Authorization: Bearer <token>' header is required.
    """
    token = current_app.config.get('READING_API_TOKEN')
    if not token:
        return True
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    return hmac.compare_digest(auth_header[len('Bearer '):].encode(), token.encode())


@bp.route('/api/reading-activity')
def reading_activity():
    """Public, read-only summary of reading activity for a period.

    Query params:
      since: YYYY-MM-DD (inclusive) - defaults to no lower bound.
      until: YYYY-MM-DD (exclusive) - defaults to no upper bound.

    Both are optional; omitting both returns all-time finished books plus the
    current currently-reading snapshot.
    """
    if not _check_authorized():
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        since = _parse_date_param(request.args.get('since'), 'since')
        until = _parse_date_param(request.args.get('until'), 'until')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if since is not None and until is not None and since >= until:
        return jsonify({'error': "'since' must be earlier than 'until'."}), 400

    stats = build_stats_context(since=since, until=until)

    all_books = Book.query.all()
    finished_in_period = [
        b for b in all_books
        if b.status == BookStatus.FINISHED
        and b.date_finished
        and (since is None or as_utc(b.date_finished) >= since)
        and (until is None or as_utc(b.date_finished) < until)
    ]
    finished_in_period.sort(key=lambda b: b.date_finished, reverse=True)

    currently_reading = [b for b in all_books if b.status == BookStatus.READING]
    currently_reading.sort(key=lambda b: b.date_added, reverse=True)

    return jsonify({
        'period': {
            'since': since.strftime('%Y-%m-%d') if since else None,
            'until': until.strftime('%Y-%m-%d') if until else None,
        },
        'books_finished': [b.to_dict() for b in finished_in_period],
        'currently_reading': [b.to_dict() for b in currently_reading],
        'stats': {
            'books_finished_count': stats.total_books,
            'total_pages': stats.total_pages,
            'avg_pages_per_book': stats.avg_pages,
            'reading_hours': stats.reading_hours,
            'categories': {
                'labels': stats.cat_labels,
                'data': stats.cat_data,
            },
            'pages_history': {
                'labels': stats.pages_history_labels,
                'data': stats.pages_history_data,
            },
        },
    })


# ---------------------------------------------------------------------------
# Books, single book, stats
# ---------------------------------------------------------------------------

SORTS = {
    'date_added_desc': lambda: Book.date_added.desc(),
    'title_asc': lambda: func.lower(Book.title).asc(),
    'title_desc': lambda: func.lower(Book.title).desc(),
    'date_finished_desc': lambda: Book.date_finished.desc().nulls_last(),
    'rating_desc': lambda: Book.personal_rating.desc().nulls_last(),
}
MAX_PER_PAGE = 100
MAX_PAGE = 1_000_000  # keeps OFFSET far inside SQLite's 64-bit integer range


def _error(message: str, status: int):
    return jsonify({'error': message}), status


def _int_param(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    """Read an integer query param, raising ValueError (message is client-safe) when invalid."""
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"Invalid '{name}' value {raw!r}; expected an integer.") from None
    if value < minimum or (maximum is not None and value > maximum):
        bound = f'between {minimum} and {maximum}' if maximum is not None else f'>= {minimum}'
        raise ValueError(f"Invalid '{name}' value {value}; must be {bound}.")
    return value


def _year_bounds(year: int) -> tuple[datetime, datetime]:
    return datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)


def _external_links(book: Book) -> list[dict]:
    links = []
    if book.google_books_id:
        links.append({'name': 'Google Books',
                      'url': f'https://books.google.com/books?id={book.google_books_id}'})
    if book.isbn:
        links += [
            {'name': 'Open Library', 'url': f'https://openlibrary.org/isbn/{book.isbn}'},
            {'name': 'Goodreads', 'url': f'https://www.goodreads.com/book/isbn/{book.isbn}'},
            {'name': 'WorldCat', 'url': f'https://search.worldcat.org/search?q=bn:{book.isbn}'},
        ]
    return links


def _book_metrics(book: Book) -> dict:
    start = getattr(book, 'date_started', None) or book.date_added
    end = book.date_finished or datetime.now(UTC)
    # Elapsed time is only meaningful for books that are being or have been read.
    active = book.status in (BookStatus.READING, BookStatus.FINISHED)
    days = max((as_utc(end) - as_utc(start)).days, 0) if start and active else None

    current_page = getattr(book, 'current_page', None)
    pages_read = book.page_count if book.status == BookStatus.FINISHED else current_page
    pages_per_day = round(pages_read / max(days, 1), 1) if pages_read and days is not None else None

    if book.status == BookStatus.FINISHED:
        progress = 100
    elif current_page and book.page_count:
        progress = min(round(current_page / book.page_count * 100), 100)
    else:
        progress = None

    return {
        'days_reading': days,
        'pages_per_day': pages_per_day,
        'progress_pct': progress,
        'my_rating': book.personal_rating,
        'public_rating': book.average_rating,
    }


def _book_payload(book: Book) -> dict:
    return {**book.to_dict(), 'external_links': _external_links(book), 'metrics': _book_metrics(book)}


def _filtered_books_query(args):
    query = Book.query
    if args.get('status'):
        query = query.filter(Book.status == args['status'])
    if args.get('q'):
        q = args['q']
        query = query.filter(or_(Book.title.icontains(q, autoescape=True),
                                 Book.authors.icontains(q, autoescape=True)))
    if args.get('category'):
        query = query.filter(Book.categories.icontains(args['category'], autoescape=True))
    return query


@bp.route('/api/books')
def list_books():
    """Paginated, filterable list of books (see /api/openapi.json)."""
    if not _check_authorized():
        return _error('Unauthorized', 401)

    status = request.args.get('status')
    if status and status not in BookStatus.ALL:
        return _error(f"Invalid 'status' value {status!r}; expected one of {', '.join(BookStatus.ALL)}.", 400)
    sort = request.args.get('sort') or 'date_added_desc'
    if sort not in SORTS:
        return _error(f"Invalid 'sort' value {sort!r}; expected one of {', '.join(SORTS)}.", 400)
    try:
        year = _int_param('year', 0, 1, 9998)
        page = _int_param('page', 1, 1, MAX_PAGE)
        per_page = _int_param('per_page', 24, 1)
    except ValueError as exc:
        return _error(str(exc), 400)
    per_page = min(per_page, MAX_PER_PAGE)

    query = _filtered_books_query(request.args)
    if year:
        since, until = _year_bounds(year)
        query = query.filter(Book.date_finished >= since.replace(tzinfo=None),
                             Book.date_finished < until.replace(tzinfo=None))
    total = query.count()
    books = (query.order_by(SORTS[sort](), Book.id.desc())
             .offset((page - 1) * per_page).limit(per_page).all())
    return jsonify({
        'items': [_book_payload(b) for b in books],
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': -(-total // per_page),
    })


@bp.route('/api/books/<int:book_id>')
def get_book(book_id: int):
    if not _check_authorized():
        return _error('Unauthorized', 401)
    book = db.session.get(Book, book_id) if book_id < 2**63 else None
    if book is None:
        return _error('Book not found', 404)
    return jsonify(_book_payload(book))


@bp.route('/api/stats')
def stats():
    """Aggregate reading stats, all-time or for one finished year."""
    if not _check_authorized():
        return _error('Unauthorized', 401)
    try:
        year = _int_param('year', 0, 1, 9998)
    except ValueError as exc:
        return _error(str(exc), 400)
    since, until = _year_bounds(year) if year else (None, None)
    ctx = build_stats_context(since=since, until=until)
    return jsonify({
        'year': year or None,
        'books_finished_count': ctx.total_books,
        'total_pages': ctx.total_pages,
        'avg_pages_per_book': ctx.avg_pages,
        'reading_hours': ctx.reading_hours,
        'categories': {'labels': ctx.cat_labels, 'data': ctx.cat_data},
        'pages_history': {'labels': ctx.pages_history_labels, 'data': ctx.pages_history_data},
        'avg_days': ctx.avg_days,
        'completion_rate': ctx.completion_rate,
        'seasons': ctx.seasons,
    })


# ---------------------------------------------------------------------------
# OpenAPI document
# ---------------------------------------------------------------------------

def _query_param(name: str, schema: dict, description: str) -> dict:
    return {'name': name, 'in': 'query', 'required': False, 'schema': schema, 'description': description}


def _json_response(description: str, schema: dict) -> dict:
    return {'description': description, 'content': {'application/json': {'schema': schema}}}


def _error_ref(description: str) -> dict:
    return _json_response(description, _ref('Error'))


def _ref(name: str) -> dict:
    return {'$ref': f'#/components/schemas/{name}'}


def _op(summary: str, parameters: list, ok: dict, extra: dict | None = None, secured: bool = True) -> dict:
    responses = {'200': ok, **(extra or {})}
    op = {'summary': summary, 'parameters': parameters, 'responses': responses}
    if secured:
        responses['401'] = _error_ref('Missing or invalid bearer token (only when READING_API_TOKEN is set).')
        # An empty requirement object marks the bearer token as optional.
        op['security'] = [{}, {'bearerAuth': []}]
    return op


_STR = {'type': 'string'}
_NULLABLE_STR = {'type': 'string', 'nullable': True}
_INT = {'type': 'integer'}
_NUM = {'type': 'number', 'nullable': True}
_INT_NULL = {'type': 'integer', 'nullable': True}
_YEAR = {'type': 'integer', 'minimum': 1, 'maximum': 9998}
_DATE_NULL = {'type': 'string', 'format': 'date', 'nullable': True}


def _labelled(data: dict) -> dict:
    return {'type': 'object', 'properties': {'labels': {'type': 'array', 'items': _STR},
                                             'data': {'type': 'array', 'items': data}}}


def _openapi_schemas() -> dict:
    book = {
        'type': 'object',
        'properties': {
            'id': _INT, 'title': _STR, 'authors': _NULLABLE_STR, 'thumbnail': _NULLABLE_STR,
            'description': _NULLABLE_STR, 'page_count': _INT_NULL, 'categories': _NULLABLE_STR,
            'published_year': _NULLABLE_STR, 'language': _NULLABLE_STR, 'average_rating': _NUM,
            'status': {'type': 'string', 'enum': list(BookStatus.ALL)},
            'date_added': _DATE_NULL, 'date_finished': _DATE_NULL,
            'personal_rating': _NUM, 'personal_notes': _NULLABLE_STR,
        },
    }
    stats_props = {
        'books_finished_count': _INT, 'total_pages': _INT, 'avg_pages_per_book': _INT, 'reading_hours': _INT,
        'categories': _labelled(_INT), 'pages_history': _labelled(_INT),
    }
    return {
        'Error': {'type': 'object', 'required': ['error'], 'properties': {'error': _STR}},
        'Book': book,
        'ExternalLink': {'type': 'object', 'properties': {'name': _STR, 'url': {'type': 'string', 'format': 'uri'}}},
        'BookMetrics': {'type': 'object', 'properties': {
            'days_reading': _INT_NULL, 'pages_per_day': _NUM, 'progress_pct': _INT_NULL,
            'my_rating': _NUM, 'public_rating': _NUM}},
        'BookDetail': {'allOf': [_ref('Book'), {'type': 'object', 'properties': {
            'external_links': {'type': 'array', 'items': _ref('ExternalLink')},
            'metrics': _ref('BookMetrics')}}]},
        'BookList': {'type': 'object', 'properties': {
            'items': {'type': 'array', 'items': _ref('BookDetail')},
            'page': _INT, 'per_page': _INT, 'total': _INT, 'pages': _INT}},
        'ReadingStats': {'type': 'object', 'properties': stats_props},
        'Stats': {'type': 'object', 'properties': {
            'year': _INT_NULL, **stats_props, 'avg_days': _INT, 'completion_rate': _INT,
            'seasons': {'type': 'object', 'additionalProperties': _INT}}},
        'ReadingActivity': {'type': 'object', 'properties': {
            'period': {'type': 'object', 'properties': {'since': _DATE_NULL, 'until': _DATE_NULL}},
            'books_finished': {'type': 'array', 'items': _ref('Book')},
            'currently_reading': {'type': 'array', 'items': _ref('Book')},
            'stats': _ref('ReadingStats')}},
    }


def _openapi_paths() -> dict:
    date = {'type': 'string', 'format': 'date'}
    bad = {'400': _error_ref('Invalid query parameter.')}
    return {
        '/api/reading-activity': {'get': _op(
            'Reading activity for a period',
            [_query_param('since', date, 'Inclusive lower bound on finish date (YYYY-MM-DD).'),
             _query_param('until', date, 'Exclusive upper bound on finish date (YYYY-MM-DD).')],
            _json_response('Finished books, currently reading and stats.', _ref('ReadingActivity')), bad)},
        '/api/books': {'get': _op(
            'List books',
            [_query_param('status', {'type': 'string', 'enum': list(BookStatus.ALL)}, 'Filter by status.'),
             _query_param('q', _STR, 'Case-insensitive match on title or authors.'),
             _query_param('category', _STR, 'Case-insensitive match on categories.'),
             _query_param('year', _YEAR, 'Finished year.'),
             _query_param('sort', {'type': 'string', 'enum': list(SORTS), 'default': 'date_added_desc'},
                          'Sort order.'),
             _query_param('page', {'type': 'integer', 'minimum': 1, 'maximum': MAX_PAGE, 'default': 1}, 'Page number.'),
             _query_param('per_page', {'type': 'integer', 'minimum': 1, 'default': 24},
                          f'Items per page; values above {MAX_PER_PAGE} are clamped to {MAX_PER_PAGE}.')],
            _json_response('A page of books.', _ref('BookList')), bad)},
        '/api/books/{id}': {'get': _op(
            'Get one book with external links and metrics',
            [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Book id.'}],
            _json_response('The book.', _ref('BookDetail')),
            {'404': _error_ref('Unknown book id.')})},
        '/api/stats': {'get': _op(
            'Aggregate reading stats',
            [_query_param('year', _YEAR, 'Restrict to books finished in this year; all-time when omitted.')],
            _json_response('Reading statistics.', _ref('Stats')), bad)},
        '/api/openapi.json': {'get': _op(
            'This OpenAPI document', [], _json_response('The OpenAPI 3.0 specification.', {'type': 'object'}),
            secured=False)},
    }


def build_openapi_spec() -> dict:
    return {
        'openapi': '3.0.3',
        'info': {
            'title': 'Alexandria API',
            'version': '1.0.0',
            'description': 'Read-only JSON API for the Alexandria personal library. '
                           'When READING_API_TOKEN is configured, send it as a bearer token.',
        },
        'paths': _openapi_paths(),
        'components': {
            'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer'}},
            'schemas': _openapi_schemas(),
        },
    }


@bp.route('/api/openapi.json')
def openapi_spec():
    return jsonify(build_openapi_spec())
