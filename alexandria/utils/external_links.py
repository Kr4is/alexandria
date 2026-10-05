"""Outbound links to other catalogs for a given book."""
import re
from urllib.parse import quote, quote_plus


def _clean_isbn(value):
    cleaned = re.sub(r'[^0-9Xx]', '', str(value or ''))
    return cleaned.upper() if len(cleaned) in (10, 13) else ''


def external_links(book):
    """Return [{label, url, icon_hint}] for catalogs we can link to.

    With an ISBN every catalog gets a direct link; without one, Open Library and
    Goodreads fall back to a title+author search. Works with a Book or a dict.
    """
    get = (lambda k: book.get(k)) if isinstance(book, dict) else (lambda k: getattr(book, k, None))
    links = []

    gid = get('google_books_id')
    if gid:
        links.append({'label': 'Google Books',
                      'url': f'https://books.google.com/books?id={quote(str(gid), safe="")}',
                      'icon_hint': 'google'})

    isbn = _clean_isbn(get('isbn'))
    if isbn:
        links += [
            {'label': 'Open Library', 'url': f'https://openlibrary.org/isbn/{isbn}', 'icon_hint': 'openlibrary'},
            {'label': 'Goodreads', 'url': f'https://www.goodreads.com/book/isbn/{isbn}', 'icon_hint': 'goodreads'},
            {'label': 'WorldCat', 'url': f'https://search.worldcat.org/search?q=bn:{isbn}', 'icon_hint': 'worldcat'},
            {'label': 'LibraryThing', 'url': f'https://www.librarything.com/isbn/{isbn}', 'icon_hint': 'librarything'},
        ]
    else:
        query = ' '.join(p for p in (get('title'), get('authors')) if p).strip()
        if query:
            q = quote_plus(query)
            links += [
                {'label': 'Open Library (search)', 'url': f'https://openlibrary.org/search?q={q}',
                 'icon_hint': 'openlibrary'},
                {'label': 'Goodreads (search)', 'url': f'https://www.goodreads.com/search?q={q}',
                 'icon_hint': 'goodreads'},
            ]
    return links
