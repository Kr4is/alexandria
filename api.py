import re
import requests

BASE_URL = "https://www.googleapis.com/books/v1/volumes"


def _best_cover_url(image_links):
    """Prefer highest-resolution Google Books cover URL; bump zoom when only small thumbs exist."""
    if not image_links:
        return None
    url = (
        image_links.get("extraLarge")
        or image_links.get("large")
        or image_links.get("medium")
        or image_links.get("small")
        or image_links.get("thumbnail")
        or image_links.get("smallThumbnail")
    )
    if not url:
        return None
    # Prefer HTTPS
    url = url.replace("http://", "https://")
    # Request sharper image when URL uses zoom=1 (common on thumbnail)
    if re.search(r"[?&]zoom=1(?:&|$)", url):
        url = re.sub(r"zoom=1", "zoom=3", url, count=1)
    return url


def search_books(query):
    """
    Search for books using the Google Books API.
    """
    params = {
        'q': query,
        'maxResults': 10
    }
    response = requests.get(BASE_URL, params=params)
    if response.status_code == 200:
        data = response.json()
        items = data.get('items', [])
        results = []
        for item in items:
            volume_info = item.get('volumeInfo', {})
            image_links = volume_info.get('imageLinks') or {}
            results.append({
                'google_books_id': item.get('id'),
                'title': volume_info.get('title'),
                'authors': ", ".join(volume_info.get('authors', [])),
                'thumbnail': _best_cover_url(image_links),
                'description': volume_info.get('description'),
                'page_count': volume_info.get('pageCount'),
                'categories': ", ".join(volume_info.get('categories', [])),
                'published_year': volume_info.get('publishedDate', '')[:4] if volume_info.get('publishedDate') else None,
                'language': volume_info.get('language'),
                'average_rating': volume_info.get('averageRating'),
            })
        return results
    return []

def get_book_details(google_books_id):
    """
    Retrieve specific book details by Google Books ID.
    """
    response = requests.get(f"{BASE_URL}/{google_books_id}")
    if response.status_code == 200:
        data = response.json()
        volume_info = data.get('volumeInfo', {})
        image_links = volume_info.get('imageLinks') or {}
        return {
            'google_books_id': data.get('id'),
            'title': volume_info.get('title'),
            'authors': ", ".join(volume_info.get('authors', [])),
            'thumbnail': _best_cover_url(image_links),
            'description': volume_info.get('description'),
            'page_count': volume_info.get('pageCount'),
            'categories': ", ".join(volume_info.get('categories', [])),
            'published_year': volume_info.get('publishedDate', '')[:4] if volume_info.get('publishedDate') else None,
            'language': volume_info.get('language'),
            'average_rating': volume_info.get('averageRating'),
        }
    return None
