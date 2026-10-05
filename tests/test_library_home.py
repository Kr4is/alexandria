from datetime import UTC, datetime, timedelta

from alexandria.blueprints import main
from alexandria.constants import BookStatus
from alexandria.services.books import filter_books, get_collection_lists, get_filter_options


def _finished(make_book, title, days_ago=5, **kw):
    return make_book(
        title=title, status=BookStatus.FINISHED,
        date_finished=datetime.now(UTC) - timedelta(days=days_ago), **kw,
    )


def test_empty_library_renders_empty_state(client):
    html = client.get('/').get_data(as_text=True)
    assert 'The shelves are bare' in html
    assert 'No books finished yet this year' in html


def test_reading_hero_without_progress_has_no_bar(client, make_book):
    make_book(title='Plain Reader', page_count=300)
    html = client.get('/').get_data(as_text=True)
    assert 'Plain Reader' in html
    assert 'role="progressbar"' not in html


def test_reading_hero_progress_bar(client, make_book, monkeypatch):
    make_book(title='Deep Reader', page_count=200)
    real = main.get_collection_lists

    def with_progress(**kwargs):
        groups = real(**kwargs)
        for book in groups['reading']:
            book.current_page = 50  # plain attribute: works with or without the DB column
        return groups

    monkeypatch.setattr(main, 'get_collection_lists', with_progress)
    html = client.get('/').get_data(as_text=True)
    assert 'aria-valuenow="25"' in html
    assert 'page 50 of 200' in html


def test_hostile_query_params_do_not_500(client, make_book):
    make_book(title='Anything', status=BookStatus.FINISHED, date_finished=datetime.now(UTC))
    for qs in ('year=99999999999999999999', 'page=99999999999999999999', 'rating=nan',
               'rating=inf', 'status=bogus', 'q=%25%5F', 'category=%25'):
        assert client.get(f'/?{qs}').status_code == 200, qs


def test_later_pages_only_list_finished_shelves(client, make_book):
    for i in range(30):
        _finished(make_book, f'Book {i:02d}', days_ago=i + 1)
    make_book(title='Reading Now')
    make_book(title='Wish Item', status=BookStatus.TBR)
    page2 = client.get('/?page=2').get_data(as_text=True)
    assert 'Reading Now' not in page2 and 'Wish Item' not in page2
    assert 'Book 29' in page2
    page1 = client.get('/').get_data(as_text=True)
    assert 'Reading Now' in page1 and 'Wish Item' in page1


def test_this_year_summary(app, make_book):
    _finished(make_book, 'A', page_count=100, personal_rating=4.0)
    _finished(make_book, 'B', page_count=250, personal_rating=5.0)
    make_book(title='Old', status=BookStatus.FINISHED,
              date_finished=datetime.now(UTC) - timedelta(days=800), page_count=999)
    with app.app_context():
        data = get_collection_lists()
    assert data['this_year']['books'] == 2
    assert data['this_year']['pages'] == 350
    assert data['this_year']['avg_rating'] == 4.5
    assert data['counts']['finished'] == 3
    years = [y for y, _ in data['finished_by_year']]
    assert years == sorted(years, reverse=True)
    assert data['_finished_total'] == 3


def test_filters_and_sorts(app, make_book):
    this_year = datetime.now(UTC).year
    _finished(make_book, 'Dune', authors='Frank Herbert', categories='Fiction, Science Fiction',
              page_count=688, personal_rating=5.0)
    _finished(make_book, 'Emma', authors='Jane Austen', categories='Fiction, Classics',
              page_count=474, personal_rating=3.0)
    make_book(title='Sapiens', authors='Yuval Harari', categories='History',
              status=BookStatus.TBR, page_count=464)
    with app.app_context():
        def titles(**kw):
            return [b.title for b in filter_books(**kw).items]

        assert set(titles(category='Fiction')) == {'Dune', 'Emma'}
        assert titles(category='Science Fiction') == ['Dune']
        assert titles(category='Science') == []
        assert titles(author='austen') == ['Emma']
        assert len(titles(year=this_year)) == 2
        assert titles(year=1999) == []
        assert titles(min_rating=4) == ['Dune']
        assert titles(sort='pages_desc')[0] == 'Dune'
        assert titles(sort='pages_asc')[0] == 'Sapiens'
        assert titles(sort='rating_desc')[:2] == ['Dune', 'Emma']
        assert titles(sort='title_asc') == ['Dune', 'Emma', 'Sapiens']
        assert titles(status='tbr') == ['Sapiens']
        opts = get_filter_options()
        assert 'Classics' in opts['categories'] and 'Jane Austen' in opts['authors']
        assert opts['years'] == [this_year]


def test_index_filter_pagination(client, make_book):
    for i in range(30):
        _finished(make_book, f'Book {i:02d}', days_ago=i + 1, categories='Fiction')
    html = client.get('/?category=Fiction&sort=title_asc').get_data(as_text=True)
    assert 'Book 00' in html and 'Book 29' not in html
    assert 'aria-current="page"' in html
    assert 'category=Fiction' in html and 'page=2' in html
    page2 = client.get('/?category=Fiction&sort=title_asc&page=2').get_data(as_text=True)
    assert 'Book 29' in page2
    assert client.get('/?page=2').status_code == 200
    assert client.get('/?year=abc&rating=x&sort=bogus').status_code == 200


def test_grouped_view_has_shelves_per_status_and_is_read_only(client, make_book):
    _finished(make_book, 'Done')
    make_book(title='Wanted', status=BookStatus.TBR)
    make_book(title='Stalled', status=BookStatus.PAUSED)
    make_book(title='Dropped', status=BookStatus.DNF)
    html = client.get('/').get_data(as_text=True)
    for text in ('Up next', 'Finished in', 'Paused', 'Did not finish', 'Wanted', 'Stalled', 'Dropped'):
        assert text in html
    assert 'class="bk-actions"' not in html
    assert 'data-delete-url="' not in html


def test_authenticated_sees_actions(auth_client, make_book):
    make_book(title='Wanted', status=BookStatus.TBR)
    make_book(title='Stalled', status=BookStatus.PAUSED)
    make_book(title='Now', status=BookStatus.READING)
    html = auth_client.get('/').get_data(as_text=True)
    assert 'js-open-finish-modal' in html
    assert 'js-open-delete-modal' in html
    assert 'Resume' in html and 'Start' in html and 'DNF' in html
    assert 'class="bk-actions"' in html
    assert 'name="status" value="reading"' in html
