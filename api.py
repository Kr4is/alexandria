import requests

BASE_URL = "https://www.googleapis.com/books/v1/volumes"

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
            results.append({
                'google_books_id': item.get('id'),
                'title': volume_info.get('title'),
                'authors': ", ".join(volume_info.get('authors', [])),
                'thumbnail': volume_info.get('imageLinks', {}).get('thumbnail'),
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
        return {
            'google_books_id': data.get('id'),
            'title': volume_info.get('title'),
            'authors': ", ".join(volume_info.get('authors', [])),
            'thumbnail': volume_info.get('imageLinks', {}).get('thumbnail'),
            'description': volume_info.get('description'),
            'page_count': volume_info.get('pageCount'),
            'categories': ", ".join(volume_info.get('categories', [])),
            'published_year': volume_info.get('publishedDate', '')[:4] if volume_info.get('publishedDate') else None,
            'language': volume_info.get('language'),
            'average_rating': volume_info.get('averageRating'),
        }
    return None
