"""Command line tools: ``flask covers repair``."""

import time

import click
from loguru import logger

from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services.covers import find_cover

PAUSE_SECONDS = 0.3  # be polite to the cover providers


def register_cli(app):
    @app.cli.group('covers')
    def covers():
        """Cover tools."""

    @covers.command('repair')
    @click.option('--apply', 'apply_', is_flag=True, help='Write the new cover URLs. Without it nothing changes.')
    @click.option('--no-search', is_flag=True, help='Only try the stored URL and the other provider.')
    def repair(apply_, no_search):
        """Find working covers for books whose cover does not load.

        Books whose current cover already works are left alone. A title search
        only accepts an exact title (accents, case and subtitle ignored) with a
        shared author surname, so check the list before using --apply.
        """
        books = Book.query.order_by(Book.id).all()
        changes, missing, fine = [], [], 0
        for book in books:
            match = find_cover(book, search=not no_search)
            if match is None:
                missing.append(book)
            elif match.source == 'current':
                fine += 1
            else:
                changes.append((book, match))
            time.sleep(PAUSE_SECONDS)

        for book, match in changes:
            note = f' (matched "{match.matched_title}")' if match.matched_title else ''
            click.echo(f'#{book.id} {book.title}: {match.source} -> {match.url}{note}')
        for book in missing:
            click.echo(f'#{book.id} {book.title}: no cover found')
        click.echo(f'{fine} fine, {len(changes)} to change, {len(missing)} without a cover.')

        if not changes:
            return
        if not apply_:
            click.echo('Dry run. Run again with --apply to save these.')
            return
        for book, match in changes:
            book.thumbnail = match.url
        db.session.commit()
        logger.info('covers repair: updated {} books', len(changes))
        click.echo(f'Saved {len(changes)} covers.')
