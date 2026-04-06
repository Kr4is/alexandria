import pytest

from alexandria import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/test.db')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    application = create_app()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
