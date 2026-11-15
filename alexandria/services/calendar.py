import calendar
from collections import defaultdict

from alexandria.constants import BookStatus
from alexandria.models import Book


WEEKDAY_HEADERS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


def _event_for(book: Book, kind: str) -> dict:
    return {'book': book, 'kind': kind}


def start_date(book):
    """The day a book was started: ``date_started``, else ``date_added`` for a
    book that has left the to-read pile. A wish-list book has not been started."""
    if book.date_started:
        return book.date_started
    if book.status != BookStatus.TBR:
        return book.date_added
    return None


def book_events(book) -> list[tuple]:
    """[(date, 'started' | 'finished')] for one book."""
    events = []
    started = start_date(book)
    if started:
        events.append((started.date(), 'started'))
    if book.date_finished:
        events.append((book.date_finished.date(), 'finished'))
    return events


def density(n: int) -> int:
    """Stamps in a month -> step on the d0..d4 ramp: 0, 1, 2, 3-4, 5+."""
    return 0 if n <= 0 else 1 if n == 1 else 2 if n == 2 else 3 if n <= 4 else 4


def get_active_months() -> list[tuple[int, int]]:
    """Return all (year, month) tuples that have at least one book event, newest first."""
    active: set[tuple[int, int]] = set()
    for book in Book.query.all():
        for d, _kind in book_events(book):
            active.add((d.year, d.month))
    return sorted(active, reverse=True)


def build_calendar_context(year: int, month: int) -> dict:
    """Single DB query — builds grid + full navigation context for one month."""
    cal = calendar.Calendar(firstweekday=6)
    events_by_date = defaultdict(list)
    active_set: set[tuple[int, int]] = set()

    year_counts = defaultdict(lambda: {'started': 0, 'finished': 0})

    for book in Book.query.all():
        for d, kind in book_events(book):
            events_by_date[d].append(_event_for(book, kind))
            active_set.add((d.year, d.month))
            if d.year == year:
                year_counts[d.month][kind] += 1

    active_months = sorted(active_set, reverse=True)
    current_idx = active_months.index((year, month)) if (year, month) in active_months else None

    prev_month = (
        active_months[current_idx + 1]
        if current_idx is not None and current_idx + 1 < len(active_months)
        else None
    )
    next_month = (
        active_months[current_idx - 1]
        if current_idx is not None and current_idx > 0
        else None
    )

    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_cells = []
        for day in week:
            in_month = day.month == month
            week_cells.append(
                {
                    'day': day.day if in_month else None,
                    'date': day,
                    'in_month': in_month,
                    'events': events_by_date.get(day, []) if in_month else [],
                }
            )
        weeks.append(week_cells)

    # The year at a glance: one cell per month, shaded by how many stamps it holds.
    year_strip = []
    for m in range(1, 13):
        c = year_counts.get(m, {'started': 0, 'finished': 0})
        total = c['started'] + c['finished']
        year_strip.append({
            'year': year,
            'month': m,
            'abbr': calendar.month_abbr[m],
            'label': f'{calendar.month_name[m]} {year}',
            'started': c['started'],
            'finished': c['finished'],
            'density': density(total),
            'active': (year, m) in active_set,
            'selected': m == month,
        })

    return {
        'year_strip': year_strip,
        'current_year': year,
        'current_month': month,
        'current_label': f'{calendar.month_name[month]} {year}',
        'weekday_headers': WEEKDAY_HEADERS,
        'weeks': weeks,
        'prev_month': prev_month,
        'next_month': next_month,
        'active_months': [
            {
                'year': y,
                'month': m,
                'label': f'{calendar.month_name[m]} {y}',
                'key': f'{y}-{m:02d}',
                'selected': y == year and m == month,
            }
            for y, m in active_months
        ],
    }
