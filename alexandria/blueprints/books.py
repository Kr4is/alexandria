from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from alexandria.integrations.google_books import SearchOutcome, get_book_details, search_books
from alexandria.services import books as book_service

bp = Blueprint('books', __name__)


def _search_redirect_q():
    return request.form.get('q', '') or request.args.get('q', '')


@bp.route('/search')
@login_required
def search():
    query = request.args.get('q')
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
    if book_service.book_by_google_id(google_books_id):
        flash('This volume is already in your collection.', 'info')
        return redirect(url_for('books.search', q=_search_redirect_q()))
    details = get_book_details(google_books_id)
    if details:
        book_service.add_book_from_api_details(details)
        flash('Volume added to your collection.', 'success')
    else:
        flash('Could not retrieve volume details from the archives.', 'error')
    return redirect(url_for('books.search', q=_search_redirect_q()))


@bp.route('/finish/<int:book_id>', methods=['POST'])
@login_required
def finish_book(book_id):
    book = book_service.get_book_or_404(book_id)
    book_service.mark_book_finished(book)
    flash('Chapter closed — voyage recorded as complete.', 'success')
    return redirect(url_for('main.index'))


@bp.route('/edit/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = book_service.get_book_or_404(book_id)
    if request.method == 'POST':
        for message, category in book_service.update_book_from_form(book, request.form):
            flash(message, category)
        flash('Book details updated successfully.', 'success')
        return redirect(url_for('main.book_detail', book_id=book.id))
    return render_template('edit_book.html', book=book)


@bp.route('/delete/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    book = book_service.get_book_or_404(book_id)
    book_service.delete_book(book)
    flash('Volume removed from the archives.', 'success')
    return redirect(url_for('main.index'))
