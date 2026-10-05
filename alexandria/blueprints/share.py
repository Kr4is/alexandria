from collections import OrderedDict

from flask import Blueprint, Response, render_template, request

from alexandria.extensions import limiter
from alexandria.services.books import get_book_or_404
from alexandria.services.share_card import build_metrics, card_etag, describe, render_card

bp = Blueprint('share', __name__)

CACHE_CONTROL = 'public, max-age=3600'
DEGRADED_CACHE_CONTROL = 'public, max-age=60'
_RENDERED: OrderedDict[str, bytes] = OrderedDict()  # etag -> png; tiny per-process LRU
_RENDERED_MAX = 32


@bp.route('/book/<int:book_id>/share')
def book_share(book_id):
    """Public, standalone share page (no login)."""
    book = get_book_or_404(book_id)
    metrics = build_metrics(book)
    return render_template(
        'share_book.html',
        book=book,
        m=metrics,
        etag=card_etag(book, metrics),
        description=describe(book, metrics),
    )


@bp.route('/book/<int:book_id>/card.png')
@limiter.limit('30 per minute')
def card_png(book_id):
    """Public 1200x630 PNG share card; ETag lets crawlers revalidate without a render."""
    book = get_book_or_404(book_id)
    metrics = build_metrics(book)
    etag = card_etag(book, metrics)

    if request.if_none_match.contains(etag):
        resp = Response(status=304)
        resp.set_etag(etag)
        resp.headers['Cache-Control'] = CACHE_CONTROL
        return resp

    png = _RENDERED.get(etag)
    if png is None:
        png, cover_used = render_card(book, metrics)
        if not cover_used and (book.cover_url or book.cover_fallback_url):
            # Cover host failed: serve the typographic card briefly, without an ETag,
            # so crawlers and browsers retry soon instead of pinning the degraded image.
            resp = Response(png, mimetype='image/png')
            resp.headers['Cache-Control'] = DEGRADED_CACHE_CONTROL
            return resp
        _RENDERED[etag] = png
        while len(_RENDERED) > _RENDERED_MAX:
            _RENDERED.popitem(last=False)
    resp = Response(png, mimetype='image/png')
    resp.set_etag(etag)
    resp.headers['Cache-Control'] = CACHE_CONTROL
    return resp
