"""Unit tests for Jinja template filters."""
import pytest

from alexandria.filters import register_template_filters
from alexandria.models import Book


@pytest.fixture
def filters(app):
    """Returns a dict of filter callables extracted from the app."""
    register_template_filters(app)
    return {name: f for name, f in app.jinja_env.filters.items()
            if name in ('categories_list', 'language_display', 'cover_for', 'cover_fallback_for')}


class TestCategoriesListFilter:
    def test_empty_string_returns_empty_list(self, filters):
        assert filters['categories_list']('') == []

    def test_none_returns_empty_list(self, filters):
        assert filters['categories_list'](None) == []

    def test_single_category(self, filters):
        assert filters['categories_list']('Fiction') == ['Fiction']

    def test_multiple_categories_trimmed(self, filters):
        result = filters['categories_list']('Fiction, History , Science')
        assert result == ['Fiction', 'History', 'Science']

    def test_trailing_comma(self, filters):
        result = filters['categories_list']('Fiction,')
        assert result == ['Fiction']


class TestLanguageDisplayFilter:
    def test_known_code_returns_name(self, filters):
        result = filters['language_display']('en')
        assert 'English' in result

    def test_unknown_code_returns_uppercase(self, filters):
        result = filters['language_display']('xx')
        assert result == 'XX'

    def test_none_returns_empty_string(self, filters):
        assert filters['language_display'](None) == ''

    def test_lang_tag_strips_region(self, filters):
        result = filters['language_display']('en-US')
        assert 'English' in result


class TestCoverForFilter:
    def test_book_object_uses_cover_url(self, app, filters):
        with app.app_context():
            book = Book(title='Cover Test', thumbnail='https://example.com/thumb.jpg')
            result = filters['cover_for'](book)
            assert result == 'https://example.com/thumb.jpg'

    def test_dict_without_data_returns_none_or_empty(self, filters):
        result = filters['cover_for']({'thumbnail': None, 'google_books_id': None, 'isbn': None})
        assert not result
