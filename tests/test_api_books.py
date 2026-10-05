"""Tests for /api/books, /api/books/<id>, /api/stats and /api/openapi.json."""
from datetime import UTC, datetime, timedelta

import pytest

from alexandria.constants import BookStatus


def _dt(year, month=1, day=1):
    return datetime(year, month, day, tzinfo=UTC)


@pytest.fixture
def library(make_book):
    """Five books with varied status/category/year; returns title -> id."""
    specs = [
        dict(title='Dune', authors='Frank Herbert', categories='Fiction / Sci-Fi', status=BookStatus.FINISHED,
             date_added=_dt(2024, 12, 1), date_finished=_dt(2025, 1, 10), page_count=400, personal_rating=5.0,
             isbn='9780441013593', google_books_id='gb-dune'),
        dict(title='Emma', authors='Jane Austen', categories='Fiction / Classic', status=BookStatus.FINISHED,
             date_added=_dt(2023, 5, 1), date_finished=_dt(2024, 6, 1), page_count=300, personal_rating=3.5),
        dict(title='Cosmos', authors='Carl Sagan', categories='Science', status=BookStatus.READING,
             date_added=_dt(2025, 2, 1), page_count=500),
        dict(title='Atomic Habits', authors='James Clear', categories='Self-help', status=BookStatus.TBR,
             date_added=_dt(2025, 3, 1)),
        dict(title='Ulysses', authors='James Joyce', categories='Fiction / Classic', status=BookStatus.DNF,
             date_added=_dt(2025, 4, 1), personal_rating=1.0),
    ]
    return {s['title']: make_book(**s) for s in specs}


def _titles(response):
    return [b['title'] for b in response.get_json()['items']]


class TestListBooks:
    def test_defaults(self, client, library):
        data = client.get('/api/books').get_json()
        assert (data['page'], data['per_page'], data['total'], data['pages']) == (1, 24, 5, 1)
        assert _titles(client.get('/api/books')) == ['Ulysses', 'Atomic Habits', 'Cosmos', 'Dune', 'Emma']

    def test_items_carry_links_and_metrics(self, client, library):
        item = client.get('/api/books?q=dune').get_json()['items'][0]
        assert 'external_links' in item and 'metrics' in item

    def test_status_filter(self, client, library):
        assert _titles(client.get('/api/books?status=finished&sort=title_asc')) == ['Dune', 'Emma']

    def test_invalid_status(self, client, library):
        response = client.get('/api/books?status=nope')
        assert response.status_code == 400
        assert 'status' in response.get_json()['error']

    def test_search_title_and_author(self, client, library):
        assert _titles(client.get('/api/books?q=herbert')) == ['Dune']
        assert _titles(client.get('/api/books?q=JAMES&sort=title_asc')) == ['Atomic Habits', 'Ulysses']

    def test_search_wildcards_are_literal(self, client, library):
        assert client.get('/api/books?q=%25').get_json()['total'] == 0
        assert client.get('/api/books?category=_').get_json()['total'] == 0

    def test_category_filter(self, client, library):
        assert _titles(client.get('/api/books?category=classic&sort=title_asc')) == ['Emma', 'Ulysses']

    def test_year_filter_uses_finished_year(self, client, library):
        assert _titles(client.get('/api/books?year=2025')) == ['Dune']
        assert _titles(client.get('/api/books?year=2024')) == ['Emma']

    def test_year_filter_boundaries(self, client, make_book):
        make_book(title='NewYear', status=BookStatus.FINISHED, date_finished=_dt(2025, 1, 1))
        make_book(title='NewYearEve', status=BookStatus.FINISHED, date_finished=datetime(2024, 12, 31, 23, 59))
        assert _titles(client.get('/api/books?year=2025')) == ['NewYear']

    @pytest.mark.parametrize('sort, expected', [
        ('title_asc', ['Atomic Habits', 'Cosmos', 'Dune', 'Emma', 'Ulysses']),
        ('title_desc', ['Ulysses', 'Emma', 'Dune', 'Cosmos', 'Atomic Habits']),
        ('date_finished_desc', ['Dune', 'Emma']),
        ('rating_desc', ['Dune', 'Emma', 'Ulysses']),
    ])
    def test_sorts(self, client, library, sort, expected):
        assert _titles(client.get(f'/api/books?sort={sort}'))[:len(expected)] == expected

    def test_invalid_sort(self, client, library):
        assert client.get('/api/books?sort=random').status_code == 400

    def test_pagination(self, client, library):
        data = client.get('/api/books?sort=title_asc&per_page=2&page=3').get_json()
        assert [b['title'] for b in data['items']] == ['Ulysses']
        assert (data['total'], data['pages'], data['page'], data['per_page']) == (5, 3, 3, 2)

    def test_page_past_end_is_empty(self, client, library):
        data = client.get('/api/books?page=9').get_json()
        assert data['items'] == [] and data['total'] == 5

    def test_per_page_clamped_to_100(self, client, library):
        assert client.get('/api/books?per_page=500').get_json()['per_page'] == 100

    @pytest.mark.parametrize('query', ['page=0', 'page=x', 'page=99999999999999999999', 'per_page=0', 'per_page=-1', 'year=abc', 'year=0'])
    def test_invalid_numeric_params(self, client, library, query):
        response = client.get(f'/api/books?{query}')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_empty_library(self, client):
        data = client.get('/api/books').get_json()
        assert data == {'items': [], 'page': 1, 'per_page': 24, 'total': 0, 'pages': 0}


class TestGetBook:
    def test_unknown_id(self, client):
        response = client.get('/api/books/9999')
        assert response.status_code == 404
        assert 'error' in response.get_json()

    def test_links_for_isbn_and_google_id(self, client, library):
        data = client.get(f"/api/books/{library['Dune']}").get_json()
        urls = {link['name']: link['url'] for link in data['external_links']}
        assert urls == {
            'Google Books': 'https://books.google.com/books?id=gb-dune',
            'Open Library': 'https://openlibrary.org/isbn/9780441013593',
            'Goodreads': 'https://www.goodreads.com/book/isbn/9780441013593',
            'WorldCat': 'https://search.worldcat.org/search?q=bn:9780441013593',
        }

    def test_no_links_without_identifiers(self, client, library):
        assert client.get(f"/api/books/{library['Emma']}").get_json()['external_links'] == []

    def test_finished_metrics(self, client, library):
        data = client.get(f"/api/books/{library['Dune']}").get_json()
        assert data['title'] == 'Dune'
        assert data['metrics'] == {
            'days_reading': 40,
            'pages_per_day': 10.0,
            'progress_pct': 100,
            'my_rating': 5.0,
            'public_rating': None,
        }

    def test_reading_metrics_without_progress_data(self, client, make_book):
        book_id = make_book(date_added=datetime.now(UTC) - timedelta(days=5, hours=1), page_count=300)
        metrics = client.get(f'/api/books/{book_id}').get_json()['metrics']
        assert metrics['days_reading'] == 5
        assert metrics['progress_pct'] is None
        assert metrics['pages_per_day'] is None

    def test_finished_without_page_count(self, client, make_book):
        book_id = make_book(status=BookStatus.FINISHED, date_added=_dt(2025, 1, 1), date_finished=_dt(2025, 1, 11))
        metrics = client.get(f'/api/books/{book_id}').get_json()['metrics']
        assert metrics['days_reading'] == 10
        assert metrics['progress_pct'] == 100
        assert metrics['pages_per_day'] is None

    def test_tbr_has_no_elapsed_metrics(self, client, library):
        metrics = client.get(f"/api/books/{library['Atomic Habits']}").get_json()['metrics']
        assert metrics['days_reading'] is None
        assert metrics['pages_per_day'] is None
        assert metrics['progress_pct'] is None

    def test_huge_id_is_404(self, client):
        assert client.get('/api/books/99999999999999999999').status_code == 404


class TestStats:
    STAT_KEYS = {'books_finished_count', 'total_pages', 'avg_pages_per_book', 'reading_hours',
                 'categories', 'pages_history', 'avg_days', 'completion_rate', 'seasons'}

    def test_all_time(self, client, library):
        data = client.get('/api/stats').get_json()
        assert self.STAT_KEYS <= data.keys()
        assert data['year'] is None
        assert data['books_finished_count'] == 2
        assert data['total_pages'] == 700
        assert data['completion_rate'] == 40

    def test_year_scoped(self, client, library):
        data = client.get('/api/stats?year=2025').get_json()
        assert data['year'] == 2025
        assert data['books_finished_count'] == 1
        assert data['total_pages'] == 400
        assert data['seasons']['Winter'] == 1

    def test_empty_year(self, client, library):
        assert client.get('/api/stats?year=1999').get_json()['books_finished_count'] == 0

    @pytest.mark.parametrize('year', ['abc', '0', '-5', '10000', '2025-01'])
    def test_invalid_year(self, client, year):
        response = client.get(f'/api/stats?year={year}')
        assert response.status_code == 400
        assert 'error' in response.get_json()


class TestAuth:
    @pytest.fixture(autouse=True)
    def _token(self, app):
        app.config['READING_API_TOKEN'] = 'secret'

    @pytest.mark.parametrize('path', ['/api/books', '/api/books/1', '/api/stats'])
    def test_requires_bearer_token(self, client, library, path):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.get(path, headers={'Authorization': 'Bearer secret'}).status_code == 200

    def test_unknown_id_with_token_is_404(self, client):
        response = client.get('/api/books/9999', headers={'Authorization': 'Bearer secret'})
        assert response.status_code == 404

    def test_openapi_spec_is_public(self, client):
        assert client.get('/api/openapi.json').status_code == 200


class TestOpenApi:
    def test_structure(self, client):
        spec = client.get('/api/openapi.json').get_json()
        assert spec['openapi'].startswith('3.0')
        assert set(spec['paths']) == {
            '/api/reading-activity', '/api/books', '/api/books/{id}', '/api/stats', '/api/openapi.json',
        }
        assert spec['components']['securitySchemes']['bearerAuth'] == {'type': 'http', 'scheme': 'bearer'}

    def test_security_is_optional_on_data_endpoints(self, client):
        spec = client.get('/api/openapi.json').get_json()
        for path in ('/api/reading-activity', '/api/books', '/api/books/{id}', '/api/stats'):
            assert spec['paths'][path]['get']['security'] == [{}, {'bearerAuth': []}]
        assert 'security' not in spec['paths']['/api/openapi.json']['get']

    def test_books_parameters(self, client):
        spec = client.get('/api/openapi.json').get_json()
        names = {p['name'] for p in spec['paths']['/api/books']['get']['parameters']}
        assert names == {'status', 'q', 'category', 'year', 'sort', 'page', 'per_page'}

    def test_all_refs_resolve(self, client):
        spec = client.get('/api/openapi.json').get_json()
        schemas = spec['components']['schemas']

        def refs(node):
            if isinstance(node, dict):
                if '$ref' in node:
                    yield node['$ref']
                for value in node.values():
                    yield from refs(value)
            elif isinstance(node, list):
                for value in node:
                    yield from refs(value)

        for ref in refs(spec):
            assert ref.rsplit('/', 1)[-1] in schemas
