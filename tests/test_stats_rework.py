"""Tests for the reworked stats computations and the /stats page."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import stats as S
from alexandria.services.stats import build_stats_context


def add(**kw):
    kw.setdefault('title', 'T')
    kw.setdefault('status', BookStatus.FINISHED)
    book = Book(**kw)
    db.session.add(book)
    db.session.commit()
    return book


def fin(y, m, d=15, **kw):
    kw.setdefault('date_added', datetime(y, m, 1))
    return add(date_finished=datetime(y, m, d), **kw)


class TestEmptyAndMissingData:
    def test_empty_collection_new_fields(self, app):
        with app.app_context():
            ctx = build_stats_context()
            assert ctx.total_books == 0
            assert ctx.avg_pages_per_day == 0
            assert ctx.available_years == [] and ctx.books_per_year == []
            assert ctx.my_rating_dist == [0] * 5 and ctx.public_rating_dist == [0] * 5
            assert ctx.top_authors == [] and ctx.languages == [] and ctx.decades == []
            assert ctx.most_active_month is None and ctx.longest_streak is None
            assert ctx.highest_rated_book is None and ctx.biggest_gap_book is None
            assert ctx.longest_book is None and ctx.fastest_book is None
            assert ctx.avg_my_rating is None and ctx.avg_public_rating is None
            assert ctx.completion_rate == 0

    def test_books_without_pages_or_ratings(self, app):
        with app.app_context():
            fin(2025, 3, title='Bare')
            ctx = build_stats_context()
            assert ctx.total_books == 1 and ctx.total_pages == 0
            assert ctx.avg_pages_per_day == 0
            assert ctx.pages_history_data == []
            assert ctx.most_active_month == {'label': 'Mar 2025', 'count': 1}
            assert ctx.highest_rated_book is None

    def test_finished_without_date_is_ignored(self, app):
        with app.app_context():
            add(title='No date', page_count=100)
            assert build_stats_context().total_books == 0

    def test_api_fields_still_present(self, app):
        with app.app_context():
            ctx = build_stats_context()
            for name in ('total_books', 'total_pages', 'avg_pages', 'reading_hours', 'cat_labels',
                         'cat_data', 'pages_history_labels', 'pages_history_data'):
                assert hasattr(ctx, name)
            assert set(ctx.template_kwargs()) >= {'total_books', 'selected_year', 'available_years'}


class TestVelocity:
    def test_prefers_date_started_over_date_added(self):
        b = SimpleNamespace(date_started=datetime(2025, 1, 10), date_added=datetime(2024, 1, 1),
                            date_finished=datetime(2025, 1, 20))
        assert S.reading_days(b) == 10

    def test_falls_back_to_date_added_without_attribute(self):
        b = SimpleNamespace(date_added=datetime(2025, 1, 1), date_finished=datetime(2025, 1, 6))
        assert S.reading_days(b) == 5

    def test_none_date_started_falls_back(self):
        b = SimpleNamespace(date_started=None, date_added=datetime(2025, 1, 1),
                            date_finished=datetime(2025, 1, 4))
        assert S.reading_days(b) == 3

    def test_negative_or_missing_dates_are_unknown(self):
        book = SimpleNamespace(date_added=datetime(2025, 2, 1), date_finished=datetime(2025, 1, 1))
        assert S.reading_days(book) is None
        assert S.reading_days(SimpleNamespace(date_added=None, date_finished=datetime(2025, 1, 1))) is None

    def test_naive_and_aware_mix(self):
        b = SimpleNamespace(date_added=datetime(2025, 1, 1), date_finished=datetime(2025, 1, 3, tzinfo=UTC))
        assert S.reading_days(b) == 2

    def test_fastest_slowest_and_average(self, app):
        with app.app_context():
            fast = fin(2025, 1, 3, title='Fast')       # added 1st -> 2 days
            slow = fin(2025, 1, 21, title='Slow')      # 20 days
            ctx = build_stats_context()
            assert ctx.fastest_book.id == fast.id and ctx.fastest_days == 2
            assert ctx.slowest_book.id == slow.id and ctx.slowest_days == 20
            assert ctx.avg_days == 11

    def test_no_valid_intervals(self):
        assert S._compute_velocity([]) == (0, None, 0, None, 0)


class TestPace:
    def test_pages_per_day(self, app):
        with app.app_context():
            fin(2025, 1, 11, page_count=300)   # 10 days
            fin(2025, 2, 11, page_count=100)   # 10 days
            fin(2025, 3, 11)                   # no pages: excluded
            assert build_stats_context().avg_pages_per_day == 20.0

    def test_same_day_counts_as_one_day(self, app):
        with app.app_context():
            add(page_count=50, date_added=datetime(2025, 1, 5), date_finished=datetime(2025, 1, 5))
            assert build_stats_context().avg_pages_per_day == 50.0


class TestRatings:
    @pytest.mark.parametrize('value,bucket', [
        (None, None), (0, None), (-1, None), (0.4, 1), (1, 1), (1.5, 2), (2.4, 2), (4.5, 5), (5, 5), (7, 5),
    ])
    def test_bucket(self, value, bucket):
        assert S.rating_bucket(value) == bucket

    def test_distribution_and_averages(self, app):
        with app.app_context():
            fin(2025, 1, personal_rating=5, average_rating=4.0)
            fin(2025, 2, personal_rating=3, average_rating=3.6)
            fin(2025, 3, personal_rating=3)
            fin(2025, 4)
            ctx = build_stats_context()
            assert ctx.my_rating_dist == [0, 0, 2, 0, 1]
            assert ctx.public_rating_dist == [0, 0, 0, 2, 0]
            assert ctx.avg_my_rating == 3.7
            assert ctx.avg_public_rating == 3.8

    def test_hall_of_fame_rating_records(self, app):
        with app.app_context():
            top = fin(2025, 1, title='Top', personal_rating=5, average_rating=4.9)
            gap = fin(2025, 2, title='Gap', personal_rating=1, average_rating=4.0)
            fin(2025, 3, title='Unrated public only', average_rating=1.0)
            ctx = build_stats_context()
            assert ctx.highest_rated_book.id == top.id
            assert ctx.biggest_gap_book.id == gap.id
            assert ctx.biggest_gap == -3.0

    def test_gap_requires_both_ratings(self, app):
        with app.app_context():
            fin(2025, 1, personal_rating=4)
            ctx = build_stats_context()
            assert ctx.biggest_gap_book is None and ctx.biggest_gap == 0.0
            assert ctx.highest_rated_book is not None


class TestBreakdowns:
    def test_top_authors_split_and_ranked(self, app):
        with app.app_context():
            fin(2025, 1, authors='Ann, Bob')
            fin(2025, 2, authors='Bob')
            fin(2025, 3, authors=None)
            assert build_stats_context().top_authors == [('Bob', 2), ('Ann', 1)]

    def test_top_authors_limited_to_eight(self, app):
        with app.app_context():
            for i in range(10):
                fin(2025, 1, authors=f'Author {i}')
            assert len(build_stats_context().top_authors) == 8

    def test_categories_and_cat_buckets_unchanged(self, app):
        with app.app_context():
            for i in range(7):
                fin(2025, 1, categories=f'Cat{i}')
            fin(2025, 2, categories='Cat0, Cat1')
            ctx = build_stats_context()
            assert ctx.top_categories[0][0] in ('Cat0', 'Cat1') and ctx.top_categories[0][1] == 2
            assert ctx.cat_labels[-1] == 'Others' and len(ctx.cat_labels) == 6
            assert sum(ctx.cat_data) == 9

    def test_languages_named_and_grouped(self, app):
        with app.app_context():
            fin(2025, 1, language='en')
            fin(2025, 2, language='EN-us')
            fin(2025, 3, language='es')
            fin(2025, 4, language='xx')
            fin(2025, 5)
            assert build_stats_context().languages == [('English', 2), ('Spanish', 1), ('XX', 1)]

    def test_decades_sorted_chronologically_and_ignore_bad_years(self, app):
        with app.app_context():
            fin(2025, 1, published_year='1999')
            fin(2025, 2, published_year='1901')
            fin(2025, 3, published_year='2005')
            fin(2025, 4, published_year='n/a')
            fin(2025, 5)
            assert build_stats_context().decades == [('1900s', 1), ('1990s', 1), ('2000s', 1)]


class TestMonthPatterns:
    def test_most_active_and_streak_across_year_boundary(self, app):
        with app.app_context():
            for y, m in [(2024, 11), (2024, 12), (2025, 1), (2025, 1), (2025, 3)]:
                fin(y, m)
            ctx = build_stats_context()
            assert ctx.most_active_month == {'label': 'Jan 2025', 'count': 2}
            assert ctx.longest_streak == {'length': 3, 'start': 'Nov 2024', 'end': 'Jan 2025'}

    def test_streak_picks_longest_run(self, app):
        with app.app_context():
            for y, m in [(2025, 1), (2025, 2), (2025, 5), (2025, 6), (2025, 7), (2025, 9)]:
                fin(y, m)
            streak = build_stats_context().longest_streak
            assert streak == {'length': 3, 'start': 'May 2025', 'end': 'Jul 2025'}

    def test_single_month_streak(self, app):
        most, streak = S._compute_month_patterns([SimpleNamespace(date_finished=datetime(2025, 6, 2))])
        assert streak == {'length': 1, 'start': 'Jun 2025', 'end': 'Jun 2025'}
        assert most['count'] == 1

    def test_tie_resolves_to_earliest_month(self, app):
        with app.app_context():
            fin(2025, 5)
            fin(2025, 2)
            assert build_stats_context().most_active_month['label'] == 'Feb 2025'


class TestYearScope:
    def seed(self):
        fin(2024, 12, page_count=100)
        fin(2025, 1, page_count=200)
        fin(2025, 12, 31, page_count=300)
        fin(2026, 1, page_count=400)

    def test_explicit_window_keeps_all_years_available(self, app):
        with app.app_context():
            self.seed()
            ctx = build_stats_context(since=datetime(2025, 1, 1, tzinfo=UTC), until=datetime(2026, 1, 1, tzinfo=UTC))
            assert ctx.total_pages == 500
            assert ctx.available_years == [2026, 2025, 2024]
            assert ctx.books_per_year == [('2024', 1), ('2025', 2), ('2026', 1)]
            assert ctx.selected_year is None

    def test_request_year_applies_only_on_stats_page(self, app, client):
        with app.app_context():
            self.seed()
        html = client.get('/stats?year=2025').get_data(as_text=True)
        assert '2025 in books' in html
        assert 'aria-current="page"' in html
        assert 'A life in books' in client.get('/stats').get_data(as_text=True)
        assert 'A life in books' in client.get('/stats?year=abc').get_data(as_text=True)

    def test_request_year_scopes_context(self, app):
        with app.app_context():
            self.seed()
        with app.test_request_context('/stats?year=2025'):
            ctx = build_stats_context()
            assert ctx.selected_year == 2025 and ctx.total_pages == 500
            assert build_stats_context(use_request_year=False).total_books == 4

    def test_api_ignores_year_param(self, app, client):
        with app.app_context():
            self.seed()
        base = client.get('/api/reading-activity').get_json()
        with_year = client.get('/api/reading-activity?year=2025').get_json()
        assert base == with_year
        assert base['stats']['books_finished_count'] == 4
        assert set(base['stats']) == {'books_finished_count', 'total_pages', 'avg_pages_per_book',
                                      'reading_hours', 'categories', 'pages_history'}

    def test_year_without_books_shows_empty_state(self, client, app):
        with app.app_context():
            self.seed()
        html = client.get('/stats?year=1999').get_data(as_text=True)
        assert 'No books finished in 1999' in html


class TestPage:
    def test_empty_database_renders(self, client):
        html = client.get('/stats').get_data(as_text=True)
        assert 'Your ledger is empty' in html
        assert 'Download CSV' in html

    def test_populated_page_renders_sections(self, client, app):
        with app.app_context():
            fin(2025, 1, page_count=250, authors='Ann', categories='Fiction', language='en',
                published_year='1990', personal_rating=4, average_rating=3.5)
        html = client.get('/stats').get_data(as_text=True)
        for text in ('Hall of Fame', 'Curiosities', 'Top authors', 'Publication decades',
                     'Your ratings vs. the public', 'ratingChart', 'Download JSON'):
            assert text in html
        for removed in ('Solo vs Co-op', 'Favorite Day', 'Golden Era', 'Polyglot'):
            assert removed not in html

    def test_completion_rate_excludes_tbr(self, app):
        with app.app_context():
            fin(2025, 1)
            add(title='Wishlist', status=BookStatus.TBR, date_finished=None)
            add(title='Abandoned', status=BookStatus.DNF, date_finished=None)
            assert build_stats_context().completion_rate == 50


class TestRobustness:
    def test_odd_year_params_do_not_crash(self, client):
        for raw in ('%C2%B2', '0', '99999', '-1', ''):
            assert client.get(f'/stats?year={raw}').status_code == 200

    def test_short_published_year_is_not_a_decade(self, app):
        with app.app_context():
            fin(2025, 1, published_year='99')
            fin(2025, 2, published_year='1990')
            assert build_stats_context().decades == [('1990s', 1)]

    def test_rating_tie_between_naive_and_aware_dates(self, app):
        with app.app_context():
            add(title='Naive', personal_rating=4, date_added=datetime(2025, 1, 1), date_finished=datetime(2025, 2, 1))
            add(title='Aware', personal_rating=4, date_added=datetime(2025, 1, 1, tzinfo=UTC),
                date_finished=datetime(2025, 3, 1, tzinfo=UTC))
            assert build_stats_context().highest_rated_book.title == 'Aware'
