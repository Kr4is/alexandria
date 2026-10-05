from datetime import datetime

from flask import render_template

from alexandria.extensions import db
from alexandria.models import Book


def _add_books(app):
    with app.app_context():
        db.session.add_all([
            Book(title='Alpha', authors='A. Writer', date_added=datetime(2026, 6, 3),
                 date_finished=datetime(2026, 6, 20), status='finished'),
            Book(title='Beta', date_added=datetime(2026, 6, 3), status='reading'),
            Book(title='Gamma', date_added=datetime(2026, 5, 9), status='reading'),
        ])
        db.session.commit()


def test_calendar_empty_state(client):
    html = client.get('/calendar').get_data(as_text=True)
    assert 'The journal is still blank' in html
    assert 'month-select' not in html


def test_calendar_month_summary_and_select(app, client):
    _add_books(app)
    html = client.get('/calendar?year=2026&month=6').get_data(as_text=True)
    assert 'Finished: Alpha' in html and 'Started: Beta' in html
    assert 'Gamma' not in html
    assert 'name="month_key"' in html
    assert 'name="year" value="2026"' in html and 'name="month" value="6"' in html
    assert 'Active days' in html
    assert 'Previous month' in html


def test_login_form_fields(client):
    html = client.get('/login').get_data(as_text=True)
    for needle in ('name="username"', 'name="password"', 'name="csrf_token"',
                   'autofocus', 'autocomplete="username"', 'autocomplete="current-password"'):
        assert needle in html


def test_login_wrong_password_flashes_error(client):
    resp = client.post('/login', data={'username': 'admin', 'password': 'nope'})
    assert resp.status_code == 200
    assert b'Invalid username or password' in resp.data


def test_404_page(client):
    resp = client.get('/definitely-not-here')
    assert resp.status_code == 404
    assert b"isn't on the shelf" in resp.data


def test_500_template_is_standalone(app):
    with app.test_request_context('/'):
        html = render_template('500.html')
    assert 'A book slipped off the shelf' in html
    assert 'href="/"' in html
