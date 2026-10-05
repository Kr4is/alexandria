"""Book detail page: per-book metrics, external links, rendering."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from alexandria.constants import BookStatus
from alexandria.services.book_metrics import book_metrics, library_average_pages
from alexandria.utils.external_links import external_links

NOW = datetime(2026, 6, 30, tzinfo=UTC)


def ns(**kw):
    base = dict(status='reading', page_count=None, date_added=None, date_finished=None,
                personal_rating=None, average_rating=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestBookMetrics:
    def test_finished_book(self):
        b = ns(status='finished', page_count=300, date_added=NOW - timedelta(days=20),
               date_finished=NOW - timedelta(days=10), personal_rating=4.5, average_rating=4.0)
        m = book_metrics(b, library_avg_pages=200, now=NOW)
        assert m['days_reading'] == 10
        assert m['pages_per_day'] == 30.0
        assert m['progress_pct'] == 100
        assert m['pages_left'] == 0
        assert m['vs_avg_pages'] == 50
        assert m['rating_delta'] == 0.5
        assert m['year_read'] == 2026
        assert m['reading_hours_estimate'] == 10.0

    def test_date_started_wins_over_date_added(self):
        b = ns(date_added=NOW - timedelta(days=50), date_started=NOW - timedelta(days=5))
        assert book_metrics(b, now=NOW)['days_reading'] == 5

    def test_reading_with_progress(self):
        b = ns(page_count=400, current_page=100, date_added=NOW - timedelta(days=10))
        m = book_metrics(b, now=NOW)
        assert m['progress_pct'] == 25
        assert m['pages_left'] == 300
        assert m['pages_per_day'] == 10.0

    def test_progress_clamped_and_naive_datetimes(self):
        b = ns(page_count=100, current_page=250, date_added=datetime(2026, 6, 29))
        m = book_metrics(b, now=NOW)
        assert m['progress_pct'] == 100
        assert m['pages_left'] == 0
        assert m['days_reading'] == 1

    def test_missing_data_is_none(self):
        m = book_metrics(ns(), now=NOW)
        assert all(v is None for v in m.values())

    def test_tbr_has_no_reading_days(self):
        b = ns(status='tbr', page_count=200, date_added=NOW - timedelta(days=30))
        m = book_metrics(b, library_avg_pages=250, now=NOW)
        assert m['days_reading'] is None
        assert m['pages_per_day'] is None
        assert m['vs_avg_pages'] == -20

    def test_same_day_finish_does_not_divide_by_zero(self):
        b = ns(status='finished', page_count=120, date_added=NOW, date_finished=NOW)
        m = book_metrics(b, now=NOW)
        assert m['days_reading'] == 0
        assert m['pages_per_day'] == 120.0

    def test_library_average(self, app, make_book):
        with app.app_context():
            assert library_average_pages() is None
        make_book(status=BookStatus.FINISHED, page_count=100)
        make_book(status=BookStatus.FINISHED, page_count=300)
        make_book(status=BookStatus.READING, page_count=900)
        make_book(status=BookStatus.FINISHED, page_count=None)
        with app.app_context():
            assert library_average_pages() == 200.0


class TestExternalLinks:
    def test_isbn_links(self):
        links = external_links(ns(isbn='978-0-14-143951-8', google_books_id='abc', title='T', authors='A'))
        urls = {link['label']: link['url'] for link in links}
        assert urls['Google Books'] == 'https://books.google.com/books?id=abc'
        assert urls['Open Library'] == 'https://openlibrary.org/isbn/9780141439518'
        assert urls['Goodreads'] == 'https://www.goodreads.com/book/isbn/9780141439518'
        assert urls['WorldCat'] == 'https://search.worldcat.org/search?q=bn:9780141439518'
        assert urls['LibraryThing'] == 'https://www.librarything.com/isbn/9780141439518'
        assert all({'label', 'url', 'icon_hint'} <= set(link) for link in links)

    def test_search_fallback_is_url_encoded(self):
        links = external_links(ns(isbn=None, title='Dune & Co', authors='Frank Herbert'))
        assert [link['label'] for link in links] == ['Open Library (search)', 'Goodreads (search)']
        assert links[0]['url'] == 'https://openlibrary.org/search?q=Dune+%26+Co+Frank+Herbert'

    def test_invalid_isbn_falls_back_to_search(self):
        links = external_links(ns(isbn='123', title='X', authors=None))
        assert links[0]['url'] == 'https://openlibrary.org/search?q=X'

    def test_nothing_known(self):
        assert external_links(ns(isbn=None, title=None, authors=None)) == []

    def test_dict_input(self):
        assert external_links({'isbn': '0141439513'})[0]['url'] == 'https://openlibrary.org/isbn/0141439513'


class TestBookDetailPage:
    def test_anonymous_page_renders_metrics_links_share(self, client, make_book):
        bid = make_book(title='Dune', authors='Frank Herbert', isbn='9780441013593', status=BookStatus.FINISHED,
                        page_count=688, date_finished=datetime.now(UTC), personal_rating=5, average_rating=4.2)
        html = client.get(f'/book/{bid}').get_data(as_text=True)
        assert 'MS-' in html
        assert 'This book in numbers' in html
        assert 'https://openlibrary.org/isbn/9780441013593' in html
        assert 'rel="noopener noreferrer"' in html
        assert f'href="/book/{bid}/share"' in html
        assert 'Discard Volume' not in html
        assert f'/progress/{bid}' not in html

    def test_book_without_any_data_renders(self, client, make_book):
        bid = make_book(status=BookStatus.TBR)
        resp = client.get(f'/book/{bid}')
        assert resp.status_code == 200
        assert 'openlibrary.org/search?q=' in resp.get_data(as_text=True)

    def test_owner_sees_actions_and_progress_form(self, auth_client, make_book):
        bid = make_book(status=BookStatus.READING, page_count=300)
        html = auth_client.get(f'/book/{bid}').get_data(as_text=True)
        assert 'Close Chapter' in html
        assert 'Discard Volume' in html
        assert f'action="/progress/{bid}"' in html
        assert 'name="current_page"' in html

    def test_no_progress_form_for_finished(self, auth_client, make_book):
        bid = make_book(status=BookStatus.FINISHED, page_count=300)
        html = auth_client.get(f'/book/{bid}').get_data(as_text=True)
        assert f'/progress/{bid}' not in html
