import csv
import io
import json

from flask import Blueprint, Response, redirect, render_template, request, url_for

from alexandria.models import Book
from alexandria.services.books import (
    filter_books,
    get_book_or_404,
    get_collection_lists,
    get_reading_and_finished_lists,
)
from alexandria.services.calendar import build_calendar_context, get_active_months
from alexandria.services.stats import build_stats_context

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    sort = request.args.get('sort', 'date_added_desc')
    page = request.args.get('page', 1, type=int)
    per_page = 24

    if q or status_filter:
        pagination = filter_books(
            q=q or None,
            status=status_filter or None,
            sort=sort,
            page=page,
            per_page=per_page,
        )
        return render_template(
            'index.html',
            filtered=True,
            books=pagination.items,
            pagination=pagination,
            q=q,
            status_filter=status_filter,
            sort=sort,
        )

    groups = get_collection_lists(page=page, per_page=per_page)
    return render_template(
        'index.html',
        filtered=False,
        reading=groups['reading'],
        finished=groups['finished'],
        tbr=groups['tbr'],
        paused=groups['paused'],
        dnf=groups['dnf'],
        finished_total=groups['_finished_total'],
        finished_pages=groups['_finished_pages'],
        current_page=page,
        q='',
        status_filter='',
        sort=sort,
    )


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


@bp.route('/export.<fmt>')
def export(fmt: str):
    """Export the full book collection as CSV or JSON."""
    books = Book.query.order_by(Book.date_added.desc()).all()
    data = [b.to_dict() for b in books]

    if fmt == 'json':
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        return Response(
            payload,
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename="library.json"'},
        )

    if fmt == 'csv':
        if not data:
            fields = ['id', 'title', 'authors', 'status', 'date_added', 'date_finished',
                      'page_count', 'language', 'categories', 'published_year',
                      'average_rating', 'description', 'thumbnail']
        else:
            fields = list(data[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
        return Response(
            buf.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename="library.csv"'},
        )

    return redirect(url_for('main.index'))
