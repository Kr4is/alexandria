from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request

from alexandria.constants import BookStatus
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
    return auth_header[len('Bearer '):] == token


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
