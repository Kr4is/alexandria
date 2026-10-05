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
    import math

    from alexandria.constants import BookStatus
    from alexandria.services.books import SORT_OPTIONS, get_filter_options, get_status_counts

    default_sort = 'date_added_desc'
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    if status_filter not in BookStatus.ALL:
        status_filter = ''
    category = request.args.get('category', '').strip()
    author = request.args.get('author', '').strip()
    year = request.args.get('year', type=int)
    if year is not None and not 1 <= year <= 9999:
        year = None
    rating = request.args.get('rating', type=float)
    if rating is not None and not (math.isfinite(rating) and 0 < rating <= 5):
        rating = None
    sort = request.args.get('sort', default_sort)
    if sort not in SORT_OPTIONS:
        sort = default_sort
    page = min(max(1, request.args.get('page', 1, type=int)), 100_000)
    per_page = 24

    # Active filters (empty ones dropped), reused to build pagination links.
    qargs = {
        k: v for k, v in {
            'q': q, 'status': status_filter, 'category': category, 'author': author,
            'year': year, 'rating': rating,
            'sort': sort if sort != default_sort else '',
        }.items() if v not in (None, '')
    }
    common = {
        'q': q, 'status_filter': status_filter, 'category': category, 'author': author,
        'year': year, 'rating': rating, 'sort': sort, 'qargs': qargs,
        'sort_options': SORT_OPTIONS, 'options': get_filter_options(), 'page': page,
    }

    if qargs:
        pagination = filter_books(
            q=q or None,
            status=status_filter or None,
            sort=sort,
            page=page,
            per_page=per_page,
            category=category or None,
            author=author or None,
            year=year,
            min_rating=rating,
        )
        return render_template(
            'index.html', filtered=True, books=pagination.items, pagination=pagination,
            counts=get_status_counts(), **common,
        )

    groups = get_collection_lists(page=page, per_page=per_page)
    return render_template(
        'index.html',
        filtered=False,
        reading=groups['reading'],
        finished=groups['finished'],
        finished_by_year=groups['finished_by_year'],
        tbr=groups['tbr'],
        paused=groups['paused'],
        dnf=groups['dnf'],
        finished_total=groups['_finished_total'],
        finished_pages=groups['_finished_pages'],
        this_year=groups['this_year'],
        counts=groups['counts'],
        **common,
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
