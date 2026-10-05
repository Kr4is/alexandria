from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

from flask import has_request_context, request

from alexandria.constants import BookStatus
from alexandria.models import Book
from alexandria.utils.languages import LANGUAGE_NAMES


def safe_div(n: float, d: float) -> float:
    return n / d if d > 0 else 0


def as_utc(dt: datetime) -> datetime:
    """Normalize a naive or aware datetime to UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass
class StatsContext:
    # Fields below are consumed by /api/reading-activity: keep names stable.
    total_books: int
    total_pages: int
    avg_pages: int
    pages_history_labels: list
    pages_history_data: list
    reading_hours: int
    cat_labels: list
    cat_data: list
    # Page-only fields.
    longest_book: Any
    shortest_book: Any
    avg_days: int
    fastest_book: Any
    fastest_days: int
    slowest_book: Any
    slowest_days: int
    completion_rate: int
    books_by_year_month: dict
    tower_height: float
    ink_litres: float
    avg_public_rating: Any
    words_million: float
    distance_km: float
    avg_pages_per_day: float = 0.0
    avg_my_rating: Any = None
    selected_year: int | None = None
    available_years: list = field(default_factory=list)
    books_per_year: list = field(default_factory=list)
    rating_labels: list = field(default_factory=lambda: ['1', '2', '3', '4', '5'])
    my_rating_dist: list = field(default_factory=lambda: [0] * 5)
    public_rating_dist: list = field(default_factory=lambda: [0] * 5)
    top_authors: list = field(default_factory=list)
    top_categories: list = field(default_factory=list)
    languages: list = field(default_factory=list)
    decades: list = field(default_factory=list)
    highest_rated_book: Any = None
    biggest_gap_book: Any = None
    biggest_gap: float = 0.0
    most_active_month: dict | None = None
    longest_streak: dict | None = None

    def template_kwargs(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _month_label(ym: str) -> str:
    return datetime.strptime(ym, '%Y-%m').strftime('%b %Y')


def _compute_pages_history(finished_books: list) -> tuple[list, list]:
    pm_history: dict[str, int] = {}
    for b in finished_books:
        if b.page_count:
            key = b.date_finished.strftime('%Y-%m')
            pm_history[key] = pm_history.get(key, 0) + b.page_count
    sorted_keys = sorted(pm_history.keys())
    return [_month_label(k) for k in sorted_keys], [pm_history[k] for k in sorted_keys]


def reading_days(book) -> int | None:
    """Days between starting and finishing a book, or None when unknown/negative.

    ``date_started`` is preferred; ``date_added`` is the fallback proxy.
    """
    start = getattr(book, 'date_started', None) or book.date_added
    if not start or not book.date_finished:
        return None
    days = (as_utc(book.date_finished) - as_utc(start)).days
    return days if days >= 0 else None


def _compute_velocity(finished_books: list) -> tuple[int, Any, int, Any, int]:
    timed = [(b, d) for b in finished_books if (d := reading_days(b)) is not None]
    if not timed:
        return 0, None, 0, None, 0
    fastest = min(timed, key=lambda x: x[1])
    slowest = max(timed, key=lambda x: x[1])
    avg_days = int(safe_div(sum(d for _, d in timed), len(timed)))
    return avg_days, fastest[0], fastest[1], slowest[0], slowest[1]


def _compute_pace(finished_books: list) -> float:
    """Pages per day over books with both a page count and a known duration."""
    pages = days = 0
    for b in finished_books:
        d = reading_days(b)
        if b.page_count and d is not None:
            pages += b.page_count
            days += max(d, 1)
    return round(safe_div(pages, days), 1)


def _split_csv(value: str | None) -> list[str]:
    return [p.strip() for p in (value or '').split(',') if p.strip()]


def _ranked(counts: dict[str, int], limit: int) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]


def _count(items) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _compute_categories(finished_books: list) -> tuple[list, list]:
    counts = _count(c for b in finished_books for c in _split_csv(b.categories))
    ranked = _ranked(counts, len(counts))
    if len(ranked) > 5:
        return ([c[0] for c in ranked[:5]] + ['Others'],
                [c[1] for c in ranked[:5]] + [sum(c[1] for c in ranked[5:])])
    return [c[0] for c in ranked], [c[1] for c in ranked]


def rating_bucket(rating: float | None) -> int | None:
    """Map a 0-5 rating to a 1..5 star bucket (half rounds up); None if unrated."""
    if not rating or rating <= 0:
        return None
    return min(5, max(1, int(rating + 0.5)))


def _rating_distribution(values) -> list[int]:
    dist = [0] * 5
    for v in values:
        bucket = rating_bucket(v)
        if bucket:
            dist[bucket - 1] += 1
    return dist


def _avg(values: list[float]) -> Any:
    return round(sum(values) / len(values), 1) if values else None


def _compute_languages(finished_books: list) -> list[tuple[str, int]]:
    counts = _count(
        LANGUAGE_NAMES.get(b.language.lower().split('-')[0], b.language.upper())
        for b in finished_books if b.language
    )
    return _ranked(counts, len(counts))


def _is_year(value: str | None) -> bool:
    return bool(value) and len(value) == 4 and value.isascii() and value.isdigit()


def _compute_decades(finished_books: list) -> list[tuple[str, int]]:
    counts = _count(
        f'{b.published_year[:3]}0s'
        for b in finished_books if _is_year(b.published_year)
    )
    return sorted(counts.items())


def _compute_hall_of_fame(finished_books: list) -> dict:
    rated = [b for b in finished_books if b.personal_rating]
    highest = max(rated, key=lambda b: (b.personal_rating, as_utc(b.date_finished)), default=None)
    both = [b for b in rated if b.average_rating]
    gap_book = max(both, key=lambda b: abs(b.personal_rating - b.average_rating), default=None)
    gap = round(gap_book.personal_rating - gap_book.average_rating, 1) if gap_book else 0.0
    return {'highest_rated_book': highest, 'biggest_gap_book': gap_book, 'biggest_gap': gap}


def _compute_month_patterns(finished_books: list) -> tuple[dict | None, dict | None]:
    """Most active month and longest run of consecutive months with a finished book."""
    per_month = _count(b.date_finished.strftime('%Y-%m') for b in finished_books)
    if not per_month:
        return None, None
    keys = sorted(per_month)
    busiest = max(keys, key=lambda k: per_month[k])  # ties resolve to the earliest month
    most_active = {'label': _month_label(busiest), 'count': per_month[busiest]}

    def ordinal(ym: str) -> int:
        y, m = ym.split('-')
        return int(y) * 12 + int(m) - 1

    best_len, best_end, run_len = 1, keys[0], 1
    for prev, cur in zip(keys, keys[1:], strict=False):
        run_len = run_len + 1 if ordinal(cur) - ordinal(prev) == 1 else 1
        if run_len > best_len:
            best_len, best_end = run_len, cur
    start = best_end
    for _ in range(best_len - 1):
        n = ordinal(start) - 1
        start = f'{n // 12:04d}-{n % 12 + 1:02d}'
    streak = {'length': best_len, 'start': _month_label(start), 'end': _month_label(best_end)}
    return most_active, streak


def _compute_curiosities(total_pages: int) -> dict:
    # Rough, tongue-in-cheek estimates (see the "Curiosities" section).
    return {
        'tower_height': round(total_pages * 0.00005, 2),
        'ink_litres': round(total_pages / 50000, 3),
        'words_million': round(total_pages * 250 / 1_000_000, 2),
        'distance_km': round(total_pages * 3 / 1000, 2),
    }


def _requested_year() -> int | None:
    """``?year=YYYY`` of the /stats page; ignored elsewhere (e.g. the public API)."""
    if not has_request_context() or request.endpoint != 'main.stats':
        return None
    raw = request.args.get('year', '')
    return int(raw) if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 9999 else None


def build_stats_context(
    since: datetime | None = None,
    until: datetime | None = None,
    use_request_year: bool = True,
) -> StatsContext:
    """Compute the stats context, optionally scoped to a ``date_finished`` window.

    ``since``/``until`` are both optional and, when provided, are treated as a
    half-open interval ``[since, until)`` on ``Book.date_finished``. Leaving
    both unset reproduces the all-time behavior, except that on the ``/stats``
    page a ``?year=YYYY`` query param scopes the window to that calendar year
    (disable with ``use_request_year=False``).
    """
    year = _requested_year() if use_request_year and since is None and until is None else None
    if year:
        since = datetime(year, 1, 1, tzinfo=UTC)
        until = datetime(year + 1, 1, 1, tzinfo=UTC) if year < 9999 else None

    all_books = Book.query.all()
    all_finished = [b for b in all_books if b.status == BookStatus.FINISHED and b.date_finished]
    finished_books = all_finished
    if since is not None:
        since = as_utc(since)
        finished_books = [b for b in finished_books if as_utc(b.date_finished) >= since]
    if until is not None:
        until = as_utc(until)
        finished_books = [b for b in finished_books if as_utc(b.date_finished) < until]

    total_books_read = len(finished_books)
    total_pages_read = sum(b.page_count for b in finished_books if b.page_count)

    books_with_pages = [b for b in finished_books if b.page_count is not None]
    avg_days, fastest_book, fastest_days, slowest_book, slowest_days = _compute_velocity(finished_books)
    pages_history_labels, pages_history_data = _compute_pages_history(finished_books)
    cat_labels, cat_data = _compute_categories(finished_books)
    most_active, streak = _compute_month_patterns(finished_books)

    books_by_year_month: dict[str, dict[str, int]] = {}
    for b in finished_books:
        months = books_by_year_month.setdefault(b.date_finished.strftime('%Y'), {})
        month = b.date_finished.strftime('%B')
        months[month] = months.get(month, 0) + 1

    # Completion = finished share of every book I actually started (to-be-read excluded).
    started = [b for b in all_books if b.status != BookStatus.TBR]
    completion_rate = int(safe_div(len(all_finished), len(started)) * 100)

    my_ratings = [b.personal_rating for b in finished_books if b.personal_rating]
    public_ratings = [b.average_rating for b in finished_books if b.average_rating]
    author_counts = _count(a for b in finished_books for a in _split_csv(b.authors))
    category_counts = _count(c for b in finished_books for c in _split_csv(b.categories))

    return StatsContext(
        total_books=total_books_read,
        total_pages=total_pages_read,
        avg_pages=int(safe_div(total_pages_read, total_books_read)),
        pages_history_labels=pages_history_labels,
        pages_history_data=pages_history_data,
        reading_hours=int(total_pages_read * 2 / 60),
        cat_labels=cat_labels,
        cat_data=cat_data,
        longest_book=max(books_with_pages, key=lambda b: b.page_count, default=None),
        shortest_book=min(books_with_pages, key=lambda b: b.page_count, default=None),
        avg_days=avg_days,
        fastest_book=fastest_book,
        fastest_days=fastest_days,
        slowest_book=slowest_book,
        slowest_days=slowest_days,
        completion_rate=completion_rate,
        books_by_year_month=books_by_year_month,
        avg_public_rating=_avg(public_ratings),
        avg_pages_per_day=_compute_pace(finished_books),
        avg_my_rating=_avg(my_ratings),
        selected_year=year,
        available_years=sorted({b.date_finished.year for b in all_finished}, reverse=True),
        books_per_year=sorted(_count(b.date_finished.strftime('%Y') for b in all_finished).items()),
        my_rating_dist=_rating_distribution(my_ratings),
        public_rating_dist=_rating_distribution(public_ratings),
        top_authors=_ranked(author_counts, 8),
        top_categories=_ranked(category_counts, 8),
        languages=_compute_languages(finished_books),
        decades=_compute_decades(finished_books),
        most_active_month=most_active,
        longest_streak=streak,
        **_compute_hall_of_fame(finished_books),
        **_compute_curiosities(total_pages_read),
    )
