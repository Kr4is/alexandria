from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from alexandria.blueprints import auth, books, main
from alexandria.bootstrap import run_startup_bootstrap
from alexandria.config import configure_app
from alexandria.extensions import db, login_manager
from alexandria.filters import register_template_filters


def create_app() -> Flask:
    load_dotenv()
    root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(root / 'templates'),
        static_folder=str(root / 'static'),
    )
    configure_app(app, root)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    register_template_filters(app)

    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(books.bp)

    with app.app_context():
        run_startup_bootstrap(root)

    return app
