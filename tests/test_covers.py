from alexandria.utils.covers import (
    best_cover_from_image_links,
    google_books_cover_url,
    open_library_cover_url,
    pick_cover_url,
    resolve_cover_fallback_url,
    resolve_cover_url,
    sanitize_google_cover_url,
)


def test_sanitize_google_cover_url_strips_imgtk_and_preserves_zoom():
    url = (
        'http://books.google.com/books/content?id=abc'
        '&printsec=frontcover&img=1&zoom=6&edge=curl'
        '&imgtk=ephemeral-token&source=gbs_api'
    )
    assert sanitize_google_cover_url(url) == (
        'https://books.google.com/books/content?id=abc'
        '&printsec=frontcover&img=1&zoom=6&edge=curl&source=gbs_api'
    )


def test_best_cover_from_image_links_prefers_largest_size():
    links = {
        'thumbnail': 'http://books.google.com/books/content?id=abc&zoom=1&source=gbs_api',
        'large': 'http://books.google.com/books/content?id=abc&zoom=4&source=gbs_api',
    }
    assert best_cover_from_image_links(links).endswith('zoom=4&source=gbs_api')


def test_pick_cover_url_prefers_google_over_open_library():
    links = {'large': 'http://books.google.com/books/content?id=abc&zoom=4&source=gbs_api'}
    assert pick_cover_url(links, 'abc', '9788497353373').endswith('zoom=4&source=gbs_api')


def test_pick_cover_url_uses_open_library_when_google_missing():
    assert pick_cover_url({}, 'abc', '9786073825054') == open_library_cover_url('9786073825054')


def test_resolve_cover_url_uses_stored_google_thumbnail():
    stored = 'https://books.google.com/books/content?id=abc&zoom=6&source=gbs_api'
    assert resolve_cover_url(thumbnail=stored, google_books_id='abc', isbn='9788497353373') == stored


def test_resolve_cover_url_uses_stored_open_library_thumbnail_over_constructed_google_url():
    # The stored OpenLibrary thumbnail must be used as-is; constructing a Google Books
    # URL from google_books_id would often return a 1×1 placeholder image.
    ol_url = 'https://covers.openlibrary.org/b/isbn/9788497353373-L.jpg'
    assert resolve_cover_url(
        thumbnail=ol_url,
        google_books_id='abc',
        isbn='9788497353373',
    ) == ol_url


def test_resolve_cover_fallback_url_for_open_library_primary():
    assert resolve_cover_fallback_url(
        thumbnail='https://covers.openlibrary.org/b/isbn/9788497353373-L.jpg',
        google_books_id='abc',
        isbn='9788497353373',
    ) == google_books_cover_url('abc')
