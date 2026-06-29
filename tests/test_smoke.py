from datetime import datetime

from alexandria.extensions import db
from alexandria.models import Book


def test_index_ok(client):
    response = client.get('/')
    assert response.status_code == 200


def test_stats_ok(client):
    response = client.get('/stats')
    assert response.status_code == 200


def test_calendar_ok(client):
    response = client.get('/calendar')
    assert response.status_code == 200


def test_calendar_with_dated_book_ok(app, client):
    with app.app_context():
        db.session.add(
            Book(
                title='Dated Journey',
                date_added=datetime(2026, 6, 15),
                date_finished=datetime(2026, 6, 20),
                status='finished',
            )
        )
        db.session.commit()

    response = client.get('/calendar')
    assert response.status_code == 200
    assert b'June 2026' in response.data
    assert b'Dated Journey' in response.data


def test_calendar_query_params_navigate(app, client):
    with app.app_context():
        db.session.add(
            Book(
                title='May Book',
                date_added=datetime(2026, 5, 10),
                status='reading',
            )
        )
        db.session.add(
            Book(
                title='June Book',
                date_added=datetime(2026, 6, 1),
                date_finished=datetime(2026, 6, 28),
                status='finished',
            )
        )
        db.session.commit()

    resp_june = client.get('/calendar?year=2026&month=6')
    assert resp_june.status_code == 200
    assert b'June 2026' in resp_june.data
    assert b'June Book' in resp_june.data
    assert b'May Book' not in resp_june.data

    resp_may = client.get('/calendar?year=2026&month=5')
    assert resp_may.status_code == 200
    assert b'May 2026' in resp_may.data
    assert b'May Book' in resp_may.data

    resp_invalid = client.get('/calendar?year=2000&month=1')
    assert resp_invalid.status_code == 302
