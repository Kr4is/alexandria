import re

OPEN_LIBRARY_COVER = 'https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg'

_GOOGLE_SIZE_ORDER = (
    'extraLarge',
    'large',
    'medium',
    'small',
    'thumbnail',
    'smallThumbnail',
)


def sanitize_google_cover_url(url: str | None) -> str | None:
    """Remove ephemeral Google Books tokens; keep zoom/resolution from the API."""
    if not url:
        return None
    url = url.replace('http://', 'https://')
    url = re.sub(r'[&?]imgtk=[^&]*', '', url)
    url = re.sub(r'&&+', '&', url)
    url = url.replace('?&', '?')
    return url.rstrip('&?') or None


def best_cover_from_image_links(image_links: dict | None) -> str | None:
    if not image_links:
        return None
    for key in _GOOGLE_SIZE_ORDER:
        url = image_links.get(key)
        if url:
            sanitized = sanitize_google_cover_url(url)
            if sanitized:
                return sanitized
    return None


def google_books_cover_url(google_books_id: str | None, zoom: int = 1) -> str | None:
    if not google_books_id:
        return None
    return (
        f'https://books.google.com/books/content?id={google_books_id}'
        f'&printsec=frontcover&img=1&zoom={zoom}&source=gbs_api'
    )


def open_library_cover_url(isbn: str | None) -> str | None:
    if not isbn:
        return None
    return OPEN_LIBRARY_COVER.format(isbn=isbn)


def pick_cover_url(
    image_links: dict | None,
    google_books_id: str | None = None,
    isbn: str | None = None,
) -> str | None:
    """Choose the best cover URL when fetching metadata from Google Books."""
    google = best_cover_from_image_links(image_links)
    if google:
        return google
    open_library = open_library_cover_url(isbn)
    if open_library:
        return open_library
    return google_books_cover_url(google_books_id)


def resolve_cover_url(
    thumbnail: str | None = None,
    google_books_id: str | None = None,
    isbn: str | None = None,
) -> str | None:
    """Resolve a cover URL for display from stored book fields."""
    if thumbnail and 'books.google.com' in thumbnail:
        return sanitize_google_cover_url(thumbnail)
    if google_books_id:
        return google_books_cover_url(google_books_id, zoom=1)
    if isbn:
        return open_library_cover_url(isbn)
    if thumbnail and 'openlibrary.org' in thumbnail:
        return thumbnail
    return sanitize_google_cover_url(thumbnail)


def resolve_cover_fallback_url(
    thumbnail: str | None = None,
    google_books_id: str | None = None,
    isbn: str | None = None,
) -> str | None:
    """Fallback when the primary cover fails to load or is a 1×1 Open Library placeholder."""
    if thumbnail and 'openlibrary.org' in thumbnail and google_books_id:
        return google_books_cover_url(google_books_id, zoom=1)
    if isbn and google_books_id and thumbnail and 'books.google.com' in thumbnail:
        return google_books_cover_url(google_books_id, zoom=1)
    return None
