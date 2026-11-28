"""Resolve a scanned or typed ISBN to book details: Google Books first, Open Library second."""
from alexandria.integrations import open_library
from alexandria.integrations.google_books import search_books
from alexandria.utils.isbn import normalize_isbn


def lookup_by_isbn(raw) -> tuple[str | None, dict | None]:
    """Return ``(isbn13, details)``. ``isbn13`` is None for an invalid ISBN; ``details`` None when unknown."""
    isbn = normalize_isbn(raw)
    if not isbn:
        return None, None
    outcome = search_books(f'isbn:{isbn}')  # an API error here must not block the fallback
    if outcome.results:
        details = dict(outcome.results[0])
        details['isbn'] = details.get('isbn') or isbn
        return isbn, details
    return isbn, open_library.lookup_isbn(isbn)
