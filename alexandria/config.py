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

    # Covers downloaded once and served from /cover/<id>; keep it on the persistent volume.
    app.config['COVERS_DIR'] = _resolve_covers_dir(app, root)

    # Optional shared-secret bearer token for the public reading-activity API.
    # Left unset (the default), the endpoint stays fully open, matching the
    # existing /export.<fmt> route's no-auth posture.
    app.config['READING_API_TOKEN'] = os.getenv('READING_API_TOKEN') or None


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


def _resolve_covers_dir(app, root: Path) -> str:
    """``COVERS_DIR`` as an absolute path: a relative one is taken from the project root."""
    configured = os.getenv('COVERS_DIR')
    if not configured:
        return str(Path(app.instance_path) / 'covers')
    path = Path(configured)
    return str(path if path.is_absolute() else root / path)
