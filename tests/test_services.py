"""Unit tests for service layer: stats and calendar."""
from datetime import UTC, datetime

import pytest

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services.calendar import build_calendar_context, get_active_months
from alexandria.services.stats import build_stats_context


class TestBuildStatsContext:
    def test_empty_collection_does_not_raise(self, app):
        with app.app_context():
            ctx = build_stats_context()
            assert ctx.total_books == 0
            assert ctx.total_pages == 0

    def test_mixed_naive_aware_datetimes_no_type_error(self, app):
        with app.app_context():
            db.session.add(Book(
                title='Naive Dates',
                status=BookStatus.FINISHED,
                date_added=datetime(2024, 1, 1),          # naive
                date_finished=datetime(2024, 3, 1),        # naive
                page_count=200,
            ))
            db.session.add(Book(
                title='Aware Dates',
                status=BookStatus.FINISHED,
                date_added=datetime(2024, 4, 1, tzinfo=UTC),   # aware
                date_finished=datetime(2024, 6, 1, tzinfo=UTC),
                page_count=300,
            ))
            db.session.commit()
            ctx = build_stats_context()
            assert ctx.total_books == 2


class TestGetActiveMonths:
    def test_returns_descending_order(self, app):
        with app.app_context():
            db.session.add(Book(title='B1', date_added=datetime(2024, 3, 1, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.add(Book(title='B2', date_added=datetime(2025, 7, 1, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.commit()
            months = get_active_months()
            assert months[0] >= months[-1]  # newest first

    def test_empty_collection(self, app):
        with app.app_context():
            assert get_active_months() == []


class TestBuildCalendarContext:
    def test_prev_next_navigation(self, app):
        with app.app_context():
            db.session.add(Book(title='May', date_added=datetime(2026, 5, 10, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.add(Book(title='June', date_added=datetime(2026, 6, 15, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.add(Book(title='July', date_added=datetime(2026, 7, 20, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.commit()
            ctx = build_calendar_context(2026, 6)
            assert ctx['prev_month'] == (2026, 5)
            assert ctx['next_month'] == (2026, 7)

    def test_no_prev_for_oldest_month(self, app):
        with app.app_context():
            db.session.add(Book(title='Only', date_added=datetime(2026, 1, 1, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.commit()
            ctx = build_calendar_context(2026, 1)
            assert ctx['prev_month'] is None

    def test_no_next_for_newest_month(self, app):
        with app.app_context():
            db.session.add(Book(title='Only', date_added=datetime(2026, 1, 1, tzinfo=UTC),
                                status=BookStatus.READING))
            db.session.commit()
            ctx = build_calendar_context(2026, 1)
            assert ctx['next_month'] is None
