from alexandria.integrations import open_library


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_maps_open_library_data(monkeypatch):
    payload = {'ISBN:9780441013593': {
        'title': 'Dune', 'authors': [{'name': 'Frank Herbert'}], 'number_of_pages': 412,
        'publish_date': 'August 1, 1990', 'subjects': [{'name': 'Fiction'}],
        'cover': {'large': 'https://covers.openlibrary.org/b/id/1-L.jpg'},
    }}
    monkeypatch.setattr(open_library.requests, 'get', lambda *a, **k: FakeResponse(payload))
    r = open_library.lookup_isbn('9780441013593')
    assert r['title'] == 'Dune' and r['authors'] == 'Frank Herbert'
    assert r['published_year'] == '1990' and r['page_count'] == 412 and r['google_books_id'] is None


def test_empty_response_is_none(monkeypatch):
    monkeypatch.setattr(open_library.requests, 'get', lambda *a, **k: FakeResponse({}))
    assert open_library.lookup_isbn('9780441013593') is None


def test_network_error_is_none(monkeypatch):
    def boom(*a, **k):
        raise open_library.requests.ConnectionError('down')
    monkeypatch.setattr(open_library.requests, 'get', boom)
    assert open_library.lookup_isbn('9780441013593') is None
