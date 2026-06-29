import calendar
from collections import defaultdict

from alexandria.models import Book


WEEKDAY_HEADERS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


def _event_for(book: Book, kind: str) -> dict:
    return {'book': book, 'kind': kind}


def get_active_months() -> list[tuple[int, int]]:
    """Return all (year, month) tuples that have at least one book event, newest first."""
    active: set[tuple[int, int]] = set()
    for book in Book.query.all():
        if book.date_added:
            d = book.date_added.date()
            active.add((d.year, d.month))
        if book.date_finished:
            d = book.date_finished.date()
            active.add((d.year, d.month))
    return sorted(active, reverse=True)


def build_calendar_context(year: int, month: int) -> dict:
    """Single DB query — builds grid + full navigation context for one month."""
    cal = calendar.Calendar(firstweekday=6)
    events_by_date = defaultdict(list)
    active_set: set[tuple[int, int]] = set()

    for book in Book.query.all():
        if book.date_added:
            d = book.date_added.date()
            events_by_date[d].append(_event_for(book, 'started'))
            active_set.add((d.year, d.month))
        if book.date_finished:
            d = book.date_finished.date()
            events_by_date[d].append(_event_for(book, 'finished'))
            active_set.add((d.year, d.month))

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

    return {
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
