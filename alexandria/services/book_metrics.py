"""Per-book reading metrics. Pure functions plus one library-wide query."""
from datetime import UTC, datetime

from sqlalchemy import func

from alexandria.constants import BookStatus
from alexandria.models import Book
from alexandria.services.stats import as_utc

MINUTES_PER_PAGE = 2  # same heuristic as the stats page


def library_average_pages():
    """Average page_count of finished books, or None when there are none."""
    avg = (
        Book.query.with_entities(func.avg(Book.page_count))
        .filter(Book.status == BookStatus.FINISHED, Book.page_count > 0)
        .scalar()
    )
    return float(avg) if avg else None


def _rating(value):
    return float(value) if value else None


def book_metrics(book, library_avg_pages=None, now=None):
    """Metrics dict for one book; every value is None when it cannot be computed."""
    now = now or datetime.now(UTC)
    status = getattr(book, 'status', None)
    finished = status == BookStatus.FINISHED
    pages = getattr(book, 'page_count', None) or None
    current = getattr(book, 'current_page', None) or None
    finished_at = getattr(book, 'date_finished', None)
    started_at = getattr(book, 'date_started', None) or getattr(book, 'date_added', None)

    days_reading = None
    if started_at and status != BookStatus.TBR:
        end = as_utc(finished_at) if finished_at else now
        days_reading = max((end - as_utc(started_at)).days, 0)

    pages_read = pages if finished else current
    pages_per_day = None
    if pages_read and days_reading is not None:
        pages_per_day = round(pages_read / max(days_reading, 1), 1)

    progress_pct = None
    if finished:
        progress_pct = 100
    elif pages and current:
        progress_pct = max(0, min(100, round(current * 100 / pages)))

    pages_left = 0 if finished else (max(pages - current, 0) if pages and current else None)

    vs_avg_pages = None
    if pages and library_avg_pages:
        vs_avg_pages = round((pages - library_avg_pages) * 100 / library_avg_pages)

    mine = _rating(getattr(book, 'personal_rating', None))
    public = _rating(getattr(book, 'average_rating', None))

    return {
        'days_reading': days_reading,
        'pages_per_day': pages_per_day,
        'progress_pct': progress_pct,
        'pages_left': pages_left,
        'vs_avg_pages': vs_avg_pages,
        'my_rating': mine,
        'public_rating': public,
        'rating_delta': round(mine - public, 1) if mine and public else None,
        'year_read': as_utc(finished_at).year if finished_at else None,
        'reading_hours_estimate': round(pages * MINUTES_PER_PAGE / 60, 1) if pages else None,
    }
