"""The 'Read before' status: read in the past, never tracked, so it never gets a date."""
from datetime import UTC, datetime

from alexandria.constants import BookStatus
from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import books as book_service
from alexandria.services.book_metrics import book_metrics
from alexandria.services.calendar import book_events, start_date
from alexandria.services.stats import build_stats_context

PAST = BookStatus.PAST


def test_status_is_registered():
    assert PAST == 'past' and PAST in BookStatus.ALL


def test_import_day_never_becomes_a_start_date(app, make_book):
    book_id = make_book(status=PAST)  # date_added is today, as after an import
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert start_date(book) is None
        assert book_events(book) == []
        assert book_metrics(book)['days_reading'] is None


def test_stats_and_calendar_ignore_past_reads(app, make_book):
    make_book(status=BookStatus.FINISHED, date_started=datetime(2026, 1, 2, tzinfo=UTC),
              date_finished=datetime(2026, 1, 20, tzinfo=UTC), page_count=300)
    with app.app_context():
        before = build_stats_context()
    for _ in range(5):
        make_book(status=PAST, page_count=400)
    with app.app_context():
        after = build_stats_context()
        assert after.completion_rate == before.completion_rate == 100
        assert after.total_books == before.total_books == 1
        assert after.total_pages == before.total_pages == 300
        started = sum(m['started'] for m in after.roll_months)
        assert started == sum(m['started'] for m in before.roll_months) == 1


def test_calendar_page_has_no_events_for_past_only_library(auth_client, make_book):
    make_book(status=PAST)
    assert auth_client.get('/calendar').status_code == 200
    assert auth_client.get('/stats').status_code == 200


def test_moving_into_past_forgets_dates_and_progress(app, make_book):
    book_id = make_book(status=BookStatus.READING, date_started=datetime(2026, 3, 1, tzinfo=UTC),
                        current_page=50, page_count=300)
    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book_service.quick_set_status(book, PAST)
        assert book.status == PAST
        assert book.date_started is None and book.current_page is None and book.date_finished is None


def test_finished_book_moved_to_past_loses_its_finish_date(app, make_book):
    book_id = make_book(status=BookStatus.FINISHED, date_started=datetime(2026, 3, 1, tzinfo=UTC),
                        date_finished=datetime(2026, 3, 9, tzinfo=UTC))
    with app.app_context():
        book = db.session.get(Book, book_id)
        book_service.quick_set_status(book, PAST)
        assert book.date_finished is None and book.date_started is None


def test_reading_a_past_book_again_is_a_fresh_start(app, make_book):
    book_id = make_book(status=PAST, current_page=120)
    with app.app_context():
        book = db.session.get(Book, book_id)
        book_service.quick_set_status(book, BookStatus.READING)
        assert book.date_started is not None and book.current_page is None


def test_adding_as_past_sets_no_dates(app):
    details = {'google_books_id': 'x1', 'title': 'Old', 'authors': 'A', 'thumbnail': None,
               'description': None, 'categories': '', 'isbn': '9780441013593'}
    with app.app_context():
        book = book_service.add_book_from_api_details(details, status=PAST)
        assert book.status == PAST and book.date_started is None


def test_counts_and_filter_include_past(app, auth_client, make_book):
    make_book(title='Old Favourite', status=PAST)
    with app.app_context():
        assert book_service.get_status_counts()[PAST] == 1
        assert book_service.get_collection_lists()['counts'][PAST] == 1
    html = auth_client.get('/?status=past').get_data(as_text=True)
    assert 'Old Favourite' in html


def test_home_shows_a_read_before_drawer(auth_client, make_book):
    make_book(title='Old Favourite', status=PAST)
    html = auth_client.get('/').get_data(as_text=True)
    assert 'Read before' in html and 'Old Favourite' in html


def test_book_page_is_honest_about_the_missing_dates(auth_client, make_book):
    book_id = make_book(status=PAST)
    html = auth_client.get(f'/book/{book_id}').get_data(as_text=True)
    assert 'Read before' in html
    assert 'data-confirm="finish"' not in html.split('<main')[1]  # no button that would date it today
    assert 'Started' not in html.split('bk-slip-body')[1].split('</section>')[0]


def test_share_card_page_and_png_do_not_crash(auth_client, make_book):
    book_id = make_book(status=PAST)
    assert auth_client.get(f'/book/{book_id}/share').status_code == 200
    assert auth_client.get(f'/book/{book_id}/card.png').status_code == 200


def test_api_accepts_the_status(auth_client, make_book):
    make_book(status=PAST)
    res = auth_client.get('/api/books?status=past')
    assert res.status_code == 200 and res.get_json()['total'] == 1


def test_edit_form_offers_the_status(auth_client, make_book):
    book_id = make_book(status=BookStatus.TBR)
    html = auth_client.get(f'/edit/{book_id}').get_data(as_text=True)
    assert 'value="past"' in html
