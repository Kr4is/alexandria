import os
from pathlib import Path


def configure_app(app, root: Path) -> None:
    """Load settings from environment onto ``app.config``."""
    app.config['APP_NAME'] = os.getenv('APP_NAME', 'Alexandria')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-key-for-dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_uri(root)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'

    app.config['WTF_CSRF_ENABLED'] = True


def _resolve_database_uri(root: Path) -> str:
    db_url = os.getenv('DATABASE_URL')
    if db_url and db_url.startswith('sqlite:///'):
        db_path = db_url.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = str(root / db_path)
        return f'sqlite:///{db_path}'
    if db_url:
        return db_url
    return f"sqlite:///{root / 'instance' / 'alexandria.db'}"
