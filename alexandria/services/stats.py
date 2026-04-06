from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any

from alexandria.models import Book


def safe_div(n: float, d: float) -> float:
    return n / d if d > 0 else 0


def get_season(date) -> str:
    month = date.month
    if month in (12, 1, 2):
        return 'Winter'
    if month in (3, 4, 5):
        return 'Spring'
    if month in (6, 7, 8):
        return 'Summer'
    return 'Autumn'


@dataclass
class StatsContext:
    total_books: int
    total_pages: int
    avg_pages: int
    avg_pages_month: int
    avg_pages_year: int
    pages_history_labels: list
    pages_history_data: list
    longest_book: Any
    shortest_book: Any
    avg_days: int
    fastest_book: Any
    fastest_days: int
    slowest_book: Any
    slowest_days: int
    reading_hours: int
    completion_rate: int
    seasons: dict
    diversity: int
    books_by_year_month: dict
    cat_labels: list
    cat_data: list
    tower_height: float
    ink_litres: float
    most_read_decade: str
    favorite_day: str
    num_languages: int
    avg_public_rating: Any
    solo_ratio: int
    words_million: float
    oldest_book: Any
    distance_km: float

    def template_kwargs(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def build_stats_context() -> StatsContext:
    all_books = Book.query.all()
    finished_books = [b for b in all_books if b.status == 'finished' and b.date_finished]

    total_books_read = len(finished_books)
    total_pages_read = sum(b.page_count for b in finished_books if b.page_count)
    avg_pages_per_book = int(safe_div(total_pages_read, total_books_read))

    if finished_books:
        first_finish = min(b.date_finished for b in finished_books)
        days_active = (datetime.now(UTC) - first_finish.replace(tzinfo=UTC)).days + 1
        months_active = max(days_active / 30, 1)
        years_active = max(days_active / 365, 1)
    else:
        months_active = 1
        years_active = 1

    avg_pages_per_month = int(total_pages_read / months_active)
    avg_pages_per_year = int(total_pages_read / years_active)

    pm_history = {}
    for b in finished_books:
        if b.page_count:
            key = b.date_finished.strftime('%Y-%m')
            pm_history[key] = pm_history.get(key, 0) + b.page_count

    sorted_keys = sorted(pm_history.keys())
    pages_history_labels = [datetime.strptime(k, '%Y-%m').strftime('%b %Y') for k in sorted_keys]
    pages_history_data = [pm_history[k] for k in sorted_keys]

    books_with_pages = [b for b in finished_books if b.page_count is not None]
    longest_book = max(books_with_pages, key=lambda b: b.page_count) if books_with_pages else None
    shortest_book = min(books_with_pages, key=lambda b: b.page_count) if books_with_pages else None

    valid_intervals = []
    book_velocities = []
    for b in finished_books:
        if b.date_added and b.date_finished:
            days = (b.date_finished - b.date_added).days
            if days >= 0:
                valid_intervals.append(days)
                book_velocities.append((b, days))

    avg_days_per_book = int(safe_div(sum(valid_intervals), len(valid_intervals)))
    fastest_book = min(book_velocities, key=lambda x: x[1])[0] if book_velocities else None
    slowest_book = max(book_velocities, key=lambda x: x[1])[0] if book_velocities else None
    fastest_days = min(valid_intervals) if valid_intervals else 0
    slowest_days = max(valid_intervals) if valid_intervals else 0

    total_reading_hours = int(total_pages_read * 2 / 60)
    completion_rate = int(safe_div(total_books_read, len(all_books)) * 100)

    seasons = {'Winter': 0, 'Spring': 0, 'Summer': 0, 'Autumn': 0}
    for b in finished_books:
        seasons[get_season(b.date_finished)] += 1

    unique_categories = set()
    for b in all_books:
        if b.categories:
            for cat in b.categories.split(','):
                unique_categories.add(cat.strip())
    diversity_count = len(unique_categories)

    books_by_year_month = {}
    for book in finished_books:
        year = book.date_finished.strftime('%Y')
        month = book.date_finished.strftime('%B')
        if year not in books_by_year_month:
            books_by_year_month[year] = {}
        books_by_year_month[year][month] = books_by_year_month[year].get(month, 0) + 1

    tower_height = round(total_pages_read * 0.00005, 2)
    ink_litres = round(total_pages_read / 50000, 3)

    decade_counts = {}
    for b in finished_books:
        if b.published_year and b.published_year.isdigit():
            decade = f'{b.published_year[:3]}0s'
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
    most_read_decade = max(decade_counts.items(), key=lambda x: x[1])[0] if decade_counts else 'N/A'

    day_counts = {}
    for b in finished_books:
        day = b.date_finished.strftime('%A')
        day_counts[day] = day_counts.get(day, 0) + 1
    favorite_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else 'Unknown'

    lang_counts = {}
    for b in finished_books:
        if b.language:
            lang_counts[b.language] = lang_counts.get(b.language, 0) + 1
    num_languages = len(lang_counts)

    ratings = [b.average_rating for b in finished_books if b.average_rating]
    avg_public_rating = round(sum(ratings) / len(ratings), 1) if ratings else 'N/A'

    solo_count = 0
    coop_count = 0
    for b in finished_books:
        if b.authors:
            if ',' in b.authors:
                coop_count += 1
            else:
                solo_count += 1
    solo_ratio = int(solo_count / total_books_read * 100) if total_books_read else 0

    total_words = total_pages_read * 250
    words_million = round(total_words / 1000000, 2)

    valid_years = [b for b in finished_books if b.published_year and b.published_year.isdigit()]
    oldest_book = min(valid_years, key=lambda b: int(b.published_year)) if valid_years else None

    distance_km = round(total_pages_read * 3 / 1000, 2)

    category_counts = {}
    for book in finished_books:
        if book.categories:
            cats = [c.strip() for c in book.categories.split(',')]
            for cat in cats:
                category_counts[cat] = category_counts.get(cat, 0) + 1

    sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_cats) > 5:
        top_cats_labels = [c[0] for c in sorted_cats[:5]] + ['Others']
        top_cats_data = [c[1] for c in sorted_cats[:5]] + [sum(c[1] for c in sorted_cats[5:])]
    else:
        top_cats_labels = [c[0] for c in sorted_cats]
        top_cats_data = [c[1] for c in sorted_cats]

    return StatsContext(
        total_books=total_books_read,
        total_pages=total_pages_read,
        avg_pages=avg_pages_per_book,
        avg_pages_month=avg_pages_per_month,
        avg_pages_year=avg_pages_per_year,
        pages_history_labels=pages_history_labels,
        pages_history_data=pages_history_data,
        longest_book=longest_book,
        shortest_book=shortest_book,
        avg_days=avg_days_per_book,
        fastest_book=fastest_book,
        fastest_days=fastest_days,
        slowest_book=slowest_book,
        slowest_days=slowest_days,
        reading_hours=total_reading_hours,
        completion_rate=completion_rate,
        seasons=seasons,
        diversity=diversity_count,
        books_by_year_month=books_by_year_month,
        cat_labels=top_cats_labels,
        cat_data=top_cats_data,
        tower_height=tower_height,
        ink_litres=ink_litres,
        most_read_decade=most_read_decade,
        favorite_day=favorite_day,
        num_languages=num_languages,
        avg_public_rating=avg_public_rating,
        solo_ratio=solo_ratio,
        words_million=words_million,
        oldest_book=oldest_book,
        distance_km=distance_km,
    )
