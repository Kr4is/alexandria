from flask import Blueprint, redirect, render_template, request, url_for

from alexandria.services.books import get_book_or_404, get_reading_and_finished_lists
from alexandria.services.calendar import build_calendar_context, get_active_months
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


@bp.route('/calendar')
def calendar():
    active = get_active_months()
    if not active:
        return render_template('calendar.html', active_months=[], current_label=None, weeks=None)

    default_year, default_month = active[0]
    try:
        year = int(request.args.get('year', default_year))
        month = int(request.args.get('month', default_month))
    except ValueError:
        return redirect(url_for('main.calendar'))

    if (year, month) not in set(active):
        return redirect(url_for('main.calendar'))

    ctx = build_calendar_context(year, month)
    return render_template('calendar.html', **ctx)
