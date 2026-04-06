from flask import Blueprint, render_template

from alexandria.services.books import get_book_or_404, get_reading_and_finished_lists
from alexandria.services.stats import build_stats_context

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    reading_list, finished_list = get_reading_and_finished_lists()
    return render_template('index.html', reading=reading_list, finished=finished_list)


@bp.route('/book/<int:book_id>')
def book_detail(book_id):
    book = get_book_or_404(book_id)
    return render_template('book_detail.html', book=book)


@bp.route('/stats')
def stats():
    ctx = build_stats_context()
    return render_template('stats.html', **ctx.template_kwargs())
