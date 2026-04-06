import os
from pathlib import Path

from loguru import logger

from alexandria.extensions import db
from alexandria.integrations.google_books import get_book_details
from alexandria.models import Book, User


def ensure_instance_folder(root: Path) -> None:
    instance_path = root / 'instance'
    instance_path.mkdir(parents=True, exist_ok=True)


def init_database() -> None:
    db.create_all()


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


def run_startup_bootstrap(root: Path) -> None:
    ensure_instance_folder(root)
    init_database()
    ensure_librarian_user()
    refresh_library_metadata()
