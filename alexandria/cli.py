"""Command line tools: ``flask covers repair``."""

import time

import click
from loguru import logger

from alexandria.extensions import db
from alexandria.models import Book
from alexandria.services import cover_store
from alexandria.services.covers import find_cover

PAUSE_SECONDS = 0.3  # be polite to the cover providers


def register_cli(app):
    @app.cli.group('covers')
    def covers():
        """Cover tools."""

    @covers.command('repair')
    @click.option('--apply', 'apply_', is_flag=True, help='Save covers and new URLs. Without it nothing changes.')
    @click.option('--no-search', is_flag=True, help='Only try the stored URL and the other provider.')
    def repair(apply_, no_search):
        """Store every cover locally and fix the books whose cover does not load.

        Books that already have a stored cover are skipped. For the rest it
        finds a working cover: the current one is stored as is, a different URL
        (other provider or a title search) also replaces the saved URL. A title
        search only accepts an exact title (accents, case and subtitle ignored)
        with a shared author surname, so check the list before using --apply.
        """
        stored, to_store, changes, missing = 0, [], [], []
        for book in Book.query.order_by(Book.id).all():
            if cover_store.path_for(book.id).is_file():
                stored += 1
                continue
            match = find_cover(book, search=not no_search)
            if match is None:
                missing.append(book)
            elif match.source == 'current':
                to_store.append((book, match))
            else:
                changes.append((book, match))
            time.sleep(PAUSE_SECONDS)

        for book, match in changes:
            note = f' (matched "{match.matched_title}")' if match.matched_title else ''
            click.echo(f'#{book.id} {book.title}: {match.source} -> {match.url}{note}')
        for book in missing:
            click.echo(f'#{book.id} {book.title}: no cover found')
        click.echo(
            f'{stored} already stored, {len(to_store)} to store, '
            f'{len(changes)} to change, {len(missing)} without a cover.'
        )

        if not to_store and not changes:
            return
        if not apply_:
            click.echo('Dry run. Run again with --apply to save these.')
            return
        for book, match in changes:
            book.thumbnail = match.url
        db.session.commit()
        saved = sum(cover_store.save(book.id, match.data) for book, match in to_store + changes)
        logger.info('covers repair: {} changed, {} stored', len(changes), saved)
        click.echo(f'Changed {len(changes)} URLs, stored {saved} covers.')
