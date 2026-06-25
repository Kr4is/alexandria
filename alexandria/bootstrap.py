import os
from pathlib import Path

from loguru import logger
from sqlalchemy import inspect, text

from alexandria.extensions import db
from alexandria.integrations.google_books import get_book_details
from alexandria.models import Book, User


def ensure_instance_folder(root: Path) -> None:
    instance_path = root / 'instance'
    instance_path.mkdir(parents=True, exist_ok=True)


def init_database() -> None:
    db.create_all()
    ensure_book_schema()


def ensure_book_schema() -> None:
    inspector = inspect(db.engine)
    if 'book' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('book')}
    if 'isbn' not in columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE book ADD COLUMN isbn VARCHAR(20)'))


def ensure_librarian_user() -> None:
    admin_user = os.getenv('LIBRARIAN_USERNAME', 'admin')
    admin_pass = os.getenv('LIBRARIAN_PASSWORD', 'alexandria')
    existing_user = User.query.filter_by(username=admin_user).first()
    if not existing_user:
        admin = User(username=admin_user)
        admin.set_password(admin_pass)
        db.session.add(admin)
        db.session.commit()


def refresh_library_metadata() -> None:
    try:
        logger.info('--- Starting Library Metadata Refresh ---')
        books = Book.query.all()
        count = 0
        for book in books:
            if book.google_books_id:
                details = get_book_details(book.google_books_id)
                if details:
                    book.title = details['title']
                    book.authors = details['authors']
                    book.isbn = details.get('isbn')
                    book.thumbnail = details['thumbnail']
                    book.description = details['description']
                    book.page_count = details['page_count']
                    book.categories = details['categories']
                    book.published_year = details['published_year']
                    book.language = details['language']
                    book.average_rating = details['average_rating']
                    count += 1
        if count > 0:
            db.session.commit()
            logger.info(f'--- Refreshed metadata for {count} books ---')
        else:
            logger.info('--- No books needed updating or library is empty ---')
    except Exception as e:
        logger.warning(f'Warning: Metadata refresh encountered an error: {e}')


def _refresh_on_startup_enabled() -> bool:
    return os.getenv('REFRESH_LIBRARY_METADATA_ON_STARTUP', '').strip().lower() in (
        '1',
        'true',
        'yes',
    )


def run_startup_bootstrap(root: Path) -> None:
    ensure_instance_folder(root)
    init_database()
    ensure_librarian_user()
    if _refresh_on_startup_enabled():
        refresh_library_metadata()
