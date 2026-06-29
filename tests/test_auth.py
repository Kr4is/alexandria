"""Authentication route tests."""
import pytest


def test_login_correct_credentials_redirects(client):
    resp = client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/' in resp.headers['Location']


def test_login_wrong_password_shows_error(client):
    resp = client.post('/login', data={'username': 'admin', 'password': 'wrong'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert b'Invalid username or password' in resp.data


def test_login_wrong_username_shows_error(client):
    resp = client.post('/login', data={'username': 'nobody', 'password': 'testpass'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert b'Invalid username or password' in resp.data


def test_protected_route_redirects_anonymous(client):
    resp = client.get('/search', follow_redirects=False)
    assert resp.status_code == 302
    assert 'login' in resp.headers['Location'].lower()


def test_authenticated_user_can_access_search(auth_client):
    resp = auth_client.get('/search')
    assert resp.status_code == 200


def test_logout_redirects_to_index(auth_client):
    resp = auth_client.post('/logout', follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/'


def test_logout_ends_session(auth_client):
    auth_client.post('/logout')
    resp = auth_client.get('/search', follow_redirects=False)
    assert resp.status_code == 302
    assert 'login' in resp.headers['Location'].lower()


def test_rate_limiting_on_login(app, tmp_path, monkeypatch):
    """11th POST to /login within a minute triggers 429."""
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/rate_test.db')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    monkeypatch.setenv('LIBRARIAN_USERNAME', 'admin')
    monkeypatch.setenv('LIBRARIAN_PASSWORD', 'testpass')
    from alexandria import create_app
    rate_app = create_app()
    rate_app.config['WTF_CSRF_ENABLED'] = False
    # Leave RATELIMIT_ENABLED at default (True)
    c = rate_app.test_client()
    for _ in range(10):
        c.post('/login', data={'username': 'x', 'password': 'x'})
    resp = c.post('/login', data={'username': 'x', 'password': 'x'})
    assert resp.status_code == 429
