from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from alexandria.constants import BookStatus
from alexandria.extensions import limiter
from alexandria.integrations.google_books import SearchOutcome, get_book_details, search_books
from alexandria.services import books as book_service
from alexandria.services.isbn_lookup import lookup_by_isbn

bp = Blueprint('books', __name__)


@bp.route('/search')
@login_required
def search():
    query = (request.args.get('q') or '').strip()
    outcome = search_books(query) if query else SearchOutcome([])
    return render_template(
        'search.html',
        results=outcome.results,
        search_api_error=outcome.error_message,
        query=query,
        library_google_ids=book_service.library_google_books_ids(),
    )


@bp.route('/add/<google_books_id>', methods=['POST'])
@login_required
def add_book(google_books_id):
    existing = book_service.book_by_google_id(google_books_id)
    if existing:
        flash('This volume is already in your collection.', 'info')
        return redirect(url_for('main.book_detail', book_id=existing.id))
    status = request.form.get('status', BookStatus.READING)
    details = get_book_details(google_books_id)
    if details:
        book = book_service.add_book_from_api_details(details, status=status)
        flash('Volume added to your collection.', 'success')
        return redirect(url_for('main.book_detail', book_id=book.id))
    flash('Could not retrieve volume details from the archives.', 'error')
    return redirect(url_for('main.index'))


@bp.route('/scan')
@login_required
def scan():
    return render_template('scan.html')


@bp.route('/scan/lookup')
@login_required
@limiter.limit('60 per minute')
def scan_lookup():
    """HTML fragment for one scanned ISBN: the book found, or why there is none."""
    isbn, details = lookup_by_isbn(request.args.get('isbn', ''))
    existing = book_service.find_existing(isbn, details)
    return render_template('_scan_result.html', isbn=isbn, book=details, existing=existing)


@bp.route('/add/isbn/<isbn>', methods=['POST'])
@login_required
def add_by_isbn(isbn):
    isbn, details = lookup_by_isbn(isbn)
    if not details:
        flash('Could not find that ISBN in the archives.', 'error')
        return redirect(url_for('books.scan'))
    existing = book_service.find_existing(isbn, details)
    if existing:
        flash('This volume is already in your collection.', 'info')
        return redirect(url_for('main.book_detail', book_id=existing.id))
    status = request.form.get('status', BookStatus.READING)
    book = book_service.add_book_from_api_details(details, status=status)
    flash('Volume added to your collection.', 'success')
    return redirect(url_for('main.book_detail', book_id=book.id))


BATCH_STATUSES = (BookStatus.TBR, BookStatus.PAST, BookStatus.READING, BookStatus.PAUSED)


@bp.route('/scan/batch', methods=['POST'])
@login_required
@limiter.limit('120 per minute')
def scan_batch():
    """Batch scanning: add one ISBN straight away and report what happened as JSON."""
    raw = request.form.get('isbn', '')
    isbn, details = lookup_by_isbn(raw)
    if not isbn:
        return jsonify(result='invalid', isbn=raw[:20])
    existing = book_service.find_existing(isbn, details)
    if existing:
        return jsonify(result='owned', isbn=isbn, book_id=existing.id,
                       title=existing.title, authors=existing.authors or '',
                       url=url_for('main.book_detail', book_id=existing.id))
    if not details:
        return jsonify(result='missing', isbn=isbn)
    status = request.form.get('status', BookStatus.TBR)
    if status not in BATCH_STATUSES:
        status = BookStatus.TBR
    book = book_service.add_book_from_api_details(details, status=status)
    return jsonify(result='added', isbn=isbn, book_id=book.id, title=book.title,
                   authors=book.authors or '', url=url_for('main.book_detail', book_id=book.id))


@bp.route('/scan/batch/<int:book_id>/undo', methods=['POST'])
@login_required
def scan_batch_undo(book_id):
    book_service.delete_book(book_service.get_book_or_404(book_id))
    return jsonify(result='undone', book_id=book_id)


@bp.route('/status/<int:book_id>', methods=['POST'])
@login_required
def set_status(book_id):
    book = book_service.get_book_or_404(book_id)
    new_status = request.form.get('status', '')
    changed = book_service.quick_set_status(book, new_status)
    if changed:
        labels = {
            BookStatus.READING: 'Checked out: now reading.',
            BookStatus.FINISHED: 'Stamped finished.',
            BookStatus.TBR: 'Filed under to read.',
            BookStatus.PAUSED: 'Reading paused.',
            BookStatus.DNF: 'Returned unread.',
            BookStatus.PAST: 'Filed as read before.',
        }
        flash(labels.get(new_status, 'Status updated.'), 'success')
    return redirect(request.referrer or url_for('main.index'))


@bp.route('/progress/<int:book_id>', methods=['POST'])
@login_required
def set_progress(book_id):
    book = book_service.get_book_or_404(book_id)
    if book_service.set_progress(book, request.form.get('current_page', '')):
        flash(f'Bookmark moved to page {book.current_page}.', 'success')
    else:
        flash('That page number does not look right.', 'error')
    return redirect(request.referrer or url_for('main.book_detail', book_id=book.id))


@bp.route('/shelf/<path:name>')
def shelf(name):
    return render_template('shelf.html', name=name.strip(), books=book_service.books_on_shelf(name))


@bp.route('/finish/<int:book_id>', methods=['POST'])
@login_required
def finish_book(book_id):
    book = book_service.get_book_or_404(book_id)
    book_service.mark_book_finished(book)
    flash('Stamped finished.', 'success')
    return redirect(url_for('main.index'))


@bp.route('/edit/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = book_service.get_book_or_404(book_id)
    if request.method == 'POST':
        errors = book_service.update_book_from_form(book, request.form)
        for message, category in errors:
            flash(message, category)
        if not errors:
            flash('Book details updated successfully.', 'success')
        return redirect(url_for('main.book_detail', book_id=book.id))
    return render_template('edit_book.html', book=book, formats=book_service.BOOK_FORMATS)


@bp.route('/delete/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    book = book_service.get_book_or_404(book_id)
    book_service.delete_book(book)
    flash('Withdrawn from the library.', 'success')
    return redirect(url_for('main.index'))
