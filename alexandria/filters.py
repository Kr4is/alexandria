import re

from alexandria.utils.languages import LANGUAGE_NAMES
from alexandria.utils.text import strip_book_description_html


def register_template_filters(app):
    @app.template_filter('book_plaintext')
    def book_plaintext_filter(value):
        return strip_book_description_html(value)

    @app.template_filter('book_paragraphs')
    def book_paragraphs_filter(value):
        text = strip_book_description_html(value)
        if not text:
            return []
        return [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]

    @app.template_filter('categories_list')
    def categories_list_filter(value):
        if not value:
            return []
        return [c.strip() for c in str(value).split(',') if c.strip()]

    @app.template_filter('language_display')
    def language_display_filter(code):
        if not code:
            return ''
        c = str(code).lower().split('-')[0]
        return LANGUAGE_NAMES.get(c, str(code).upper())
