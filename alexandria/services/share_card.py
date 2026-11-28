"""Metrics and PNG share card (1200x630) for a single book."""

import hashlib
import io
import json
import random
import threading
from datetime import UTC, datetime
from pathlib import Path

import requests
from loguru import logger
from PIL import Image, ImageChops, ImageDraw, ImageFont

from alexandria.services import cover_store
from alexandria.services.covers import is_real_cover

FONT_DIR = Path(__file__).resolve().parent.parent.parent / 'static' / 'fonts'
CARD_VERSION = '2'
WIDTH, HEIGHT = 1200, 630

# The Circulation Record palette (docs/DESIGN.md): one stock colour per status, one ink per event.
PAPER = '#f4f1ea'
SLIP = '#fffdf8'
TYPE = '#141414'
RULE_SOFT = '#cfc9bd'
STOCK = {
    'reading': '#f2d13a',
    'finished': '#7fc4a0',
    'tbr': '#8fc1e6',
    'paused': '#f29a85',
    'dnf': '#fbfaf6',
    'past': '#d6c4a0',
}
INK_STARTED = '#5236a8'
INK_FINISHED = '#d8232a'
INK_RETURNED = '#141414'

STATUS_LABELS = {
    'reading': 'Reading now',
    'finished': 'Finished',
    'tbr': 'On the list',
    'paused': 'Paused',
    'dnf': 'Set aside',
    'past': 'Read before',
}

COVER_TIMEOUT = (2, 4)
COVER_MAX_BYTES = 5 * 1024 * 1024
COVER_MAX_PIXELS = 25_000_000
COVER_MIN_SIDE = 100


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _num(value: float) -> str:
    return f'{value:g}'


def build_metrics(book, now: datetime | None = None) -> dict:
    """Concrete, shareable numbers for a book. Missing values are None."""
    now = now or datetime.now(UTC)
    pages = book.page_count or None
    finished = _utc(book.date_finished) if book.status == 'finished' else None
    days = None
    if book.status == 'reading' or finished:
        start = _utc(getattr(book, 'date_started', None) or book.date_added)
        end = finished or now
        # A book backfilled after the fact (finished before it was added) has no honest duration.
        if start and end >= start:
            days = max(1, (end - start).days)
    per_day = round(pages / days, 1) if pages and days else None
    started = _utc(getattr(book, 'date_started', None) or book.date_added) if book.status == 'reading' else None

    items = []
    if pages:
        items.append((f'{pages:,}', 'Pages'))
    if days:
        items.append((str(days), 'Day reading' if days == 1 else 'Days reading'))
    if per_day:
        items.append((_num(per_day), 'Pages / day'))
    if finished:
        items.append((f'{finished.day} {finished:%b}', f'Finished {finished.year}'))
    if len(items) < 3 and book.published_year:
        items.append((str(book.published_year), 'Published'))

    return {
        'status': book.status,
        'status_label': STATUS_LABELS.get(book.status, 'On the shelf'),
        'my_rating': book.personal_rating,
        'public_rating': round(book.average_rating, 1) if book.average_rating else None,
        'pages': pages,
        'days': days,
        'pages_per_day': per_day,
        'finished': finished,
        'started': started,
        'items': items,
    }


def describe(book, metrics: dict) -> str:
    """One-line summary used for og:description and alt text."""
    bits = [metrics['status_label']]
    if metrics['my_rating']:
        bits.append(f'rated {_num(metrics["my_rating"])}/5')
    if metrics['pages']:
        bits.append(f'{metrics["pages"]:,} pages')
    if metrics['days']:
        bits.append(f'{metrics["days"]} days')
    if metrics['pages_per_day']:
        bits.append(f'{_num(metrics["pages_per_day"])} pages/day')
    lead = f'by {book.authors}. ' if book.authors else ''
    return lead + ' · '.join(bits) + '.'


def card_etag(book, metrics: dict) -> str:
    """Hash of every input that changes the rendered card."""
    payload = json.dumps(
        [
            CARD_VERSION, book.title, book.authors, metrics['status'],
            metrics['my_rating'], metrics['public_rating'], metrics['items'],
            book.cover_url, book.cover_fallback_url, book.id,
            metrics['started'].isoformat() if metrics['started'] else None,
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# --- cover -------------------------------------------------------------

def _download(url: str) -> bytes | None:
    """GET with a hard size cap enforced while streaming."""
    with requests.get(url, timeout=COVER_TIMEOUT, stream=True, headers={'User-Agent': 'Alexandria/1.0'}) as resp:
        resp.raise_for_status()
        data = b''
        for chunk in resp.iter_content(65536):
            data += chunk
            if len(data) > COVER_MAX_BYTES:
                return None
    return data


def _usable(data: bytes | None, url: str = '') -> Image.Image | None:
    """A decodable cover that is not a provider placeholder (1x1 GIF, Google's "image not available")."""
    if not data or not is_real_cover(data, url):
        return None
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > COVER_MAX_PIXELS or min(img.size) < COVER_MIN_SIDE:
        return None
    return img.convert('RGB')


def fetch_cover(book) -> Image.Image | None:
    """The stored cover if there is one, else download it; None on any failure."""
    try:
        img = _usable(cover_store.read(book.id))
        if img:
            return img
    except Exception as exc:  # noqa: BLE001
        logger.debug('stored cover unreadable for book {}: {}', book.id, exc)
    for url in (book.remote_cover_url, book.cover_fallback_url):
        if not url:
            continue
        try:
            img = _usable(_download(url), url)
            if img:
                return img
        except Exception as exc:  # noqa: BLE001 - a bad cover must never break the card
            logger.debug('share card cover fetch failed for {}: {}', url, exc)
    return None


# --- drawing -----------------------------------------------------------

_local = threading.local()  # FreeType faces are not thread-safe: one cache per thread


def _font(family: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    """dater = Big Shoulders Display, ui = Archivo (80% width), mono = IBM Plex Mono."""
    cache = _local.__dict__.setdefault('fonts', {})
    key = (family, size, weight)
    if key not in cache:
        if family == 'dater':
            font = ImageFont.truetype(str(FONT_DIR / 'BigShouldersDisplay-700-900.woff2'), size)
            font.set_variation_by_axes([weight])
        elif family == 'ui':
            font = ImageFont.truetype(str(FONT_DIR / 'Archivo-400-800.woff2'), size)
            font.set_variation_by_axes([weight, 80])  # wght, wdth
        else:
            font = ImageFont.truetype(str(FONT_DIR / f'IBMPlexMono-{weight}.woff2'), size)
        cache[key] = font
    return cache[key]


def _chunks(draw, word, font, max_width):
    """Split a single over-wide token (long URL, CJK run) into pieces that fit."""
    out, cur = [], ''
    for ch in word:
        if cur and draw.textlength(cur + ch, font=font) > max_width:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    return out + [cur]


def _wrap(draw, text, font, max_width):
    lines, line = [], ''
    words = []
    for word in text.split():
        words += _chunks(draw, word, font, max_width) if draw.textlength(word, font=font) > max_width else [word]
    for word in words:
        trial = f'{line} {word}'.strip()
        if line and draw.textlength(trial, font=font) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    return lines


def _spaced(draw, xy, text, font, fill, spacing=3):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _fit_title(draw, title, max_width, max_height, max_lines=3):
    """Largest Archivo size whose wrapped lines fit the box; ellipsis only as a last resort."""
    for size in range(84, 43, -2):
        font = _font('ui', size, 800)
        lines = _wrap(draw, title, font, max_width)
        height = len(lines) * round(size * 1.02)
        if len(lines) <= max_lines and height <= max_height and all(
            draw.textlength(ln, font=font) <= max_width for ln in lines
        ):
            return font, lines
    font = _font('ui', 44, 800)
    lines = _wrap(draw, title, font, max_width)[:max_lines]
    last = lines[-1]
    while last and draw.textlength(last + '…', font=font) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip() + '…'
    return font, lines


def _stamp(card, center, event, date_text, ink, seed, angle=-4):
    """A rubber stamp: double rule, event over date, uneven ink, slightly rotated."""
    scale = 2  # drawn at 2x and reduced, so the edges stay smooth
    ev_font = _font('mono', 22 * scale, 700)
    dt_font = _font('dater', 54 * scale, 900)
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    ev_w = sum(probe.textlength(c, font=ev_font) + 4 * scale for c in event)
    if date_text:
        dt_w = probe.textlength(date_text, font=dt_font)
    else:  # event only: it is set large, in the date face
        ev_w, dt_w = 0, probe.textlength(event, font=_font('dater', 52 * scale, 900))
    pad = 24 * scale
    w = round(max(ev_w, dt_w) + 2 * pad)
    h = round(142 * scale) if date_text else round(86 * scale)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=14 * scale, outline=ink, width=6 * scale)
    inner = (11 * scale, 11 * scale, w - 12 * scale, h - 12 * scale)
    d.rounded_rectangle(inner, radius=8 * scale, outline=ink, width=2 * scale)
    if date_text:
        _spaced(d, ((w - ev_w) / 2, 22 * scale), event, ev_font, ink, 4 * scale)
        d.text((w / 2, h - 32 * scale), date_text, font=dt_font, fill=ink, anchor='ms')
    else:
        d.text((w / 2, h / 2), event, font=_font('dater', 52 * scale, 900), fill=ink, anchor='mm')
    # uneven ink: erase a few hundred tiny specks, the same ones every time for the same book
    rng = random.Random(seed)
    specks = Image.new('L', (w, h), 255)
    sd = ImageDraw.Draw(specks)
    for _ in range(260):
        x, y, r = rng.randrange(w), rng.randrange(h), rng.choice((1, 1, 2, 3)) * scale
        sd.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice((0, 0, 90)))
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'), specks).point(lambda v: round(v * 0.93)))
    layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    layer = layer.resize((layer.width // scale, layer.height // scale), Image.LANCZOS)
    card.paste(layer, (round(center[0] - layer.width / 2), round(center[1] - layer.height / 2)), layer)


def _typed_cover(draw, box, book):
    """No cover: a typed index card, like the placeholder on the web."""
    x, y, w, h = box
    draw.rectangle((x, y, x + w, y + h), fill=SLIP, outline=TYPE, width=4)
    for ly in range(y + 56, y + h - 8, 28):
        draw.line((x + 4, ly, x + w - 4, ly), fill=RULE_SOFT, width=2)
    title_font, author_font = _font('mono', 22, 600), _font('mono', 20, 400)
    lines = [(line, title_font) for line in _wrap(draw, book.title, title_font, w - 40)[:6]]
    if book.authors:
        lines.append(('', author_font))
        lines += [(line, author_font) for line in _wrap(draw, f'— {book.authors}', author_font, w - 40)[:2]]
    ty = y + 26
    for line, font in lines:
        draw.text((x + 20, ty), line, font=font, fill=TYPE)
        ty += 28


def _stamp_for(book, metrics):
    """Ink = event: started violet, finished red, returned black. None for to-read and paused."""
    status = metrics['status']
    if status == 'finished' and metrics['finished']:
        return 'FINISHED', f'{metrics["finished"]:%d %b %Y}'.upper(), INK_FINISHED
    if status == 'reading' and metrics['started']:
        return 'STARTED', f'{metrics["started"]:%d %b %Y}'.upper(), INK_STARTED
    if status == 'dnf':
        return 'RETURNED UNREAD', None, INK_RETURNED
    return None


def render_card(book, metrics: dict | None = None, cover: Image.Image | None = None) -> tuple[bytes, bool]:
    """Render the 1200x630 PNG; returns (png, cover_used). Pass ``cover`` to skip the network fetch."""
    metrics = metrics or build_metrics(book)
    if cover is None:
        cover = fetch_cover(book)
    status = metrics['status']
    stock = STOCK.get(status, SLIP)
    call_no = f'MS-{book.id}' if book.id else 'MS'

    card = Image.new('RGB', (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(card)
    x0, y0, x1, y1 = 20, 20, WIDTH - 20, HEIGHT - 20
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=stock, outline=TYPE, width=6)

    # header band: what this is, its status, its call number
    band_bottom = 96
    draw.line((x0 + 3, band_bottom, x1 - 3, band_bottom), fill=TYPE, width=5)
    end = _spaced(draw, (56, 47), 'CIRCULATION RECORD', _font('mono', 22, 700), TYPE, 4)
    tag = metrics['status_label'].upper()
    tag_font = _font('mono', 20, 700)
    tag_w = sum(draw.textlength(c, font=tag_font) + 3 for c in tag)
    draw.rectangle((end + 22, 40, end + 22 + tag_w + 24, 76), fill=SLIP, outline=TYPE, width=3)
    _spaced(draw, (end + 34, 47), tag, tag_font, TYPE, 3)
    draw.text((x1 - 36, 60), call_no, font=_font('dater', 50, 900), fill=TYPE, anchor='rm')

    # the book, lifted off the card with a hard offset shadow
    box_w, box_h = 270, 405
    bx, by = 64, 124
    if cover:
        scale = min(box_w / cover.width, box_h / cover.height)
        cover = cover.resize((round(cover.width * scale), round(cover.height * scale)), Image.LANCZOS)
        box_w, box_h = cover.size
    draw.rectangle((bx + 12, by + 12, bx + box_w + 12, by + box_h + 12), fill=TYPE)
    if cover:
        card.paste(cover, (bx, by))
        draw.rectangle((bx - 2, by - 2, bx + box_w + 1, by + box_h + 1), outline=TYPE, width=4)
    else:
        _typed_cover(draw, (bx, by, box_w, box_h), book)

    left, right = 400, x1 - 40
    width = right - left
    slip_top = 384

    # title and author, as large as the space above the slip allows
    has_rating = bool(metrics['my_rating'] or metrics['public_rating'])
    budget = slip_top - 124 - (40 if book.authors else 0) - (62 if has_rating else 0) - 18
    title_font, lines = _fit_title(draw, book.title, width, budget)
    line_h = round(title_font.size * 1.02)
    y = 118
    for line in lines:
        draw.text((left, y), line, font=title_font, fill=TYPE)
        y += line_h
    if book.authors:
        author_font = _font('ui', 32, 500)
        author = book.authors
        while draw.textlength(author, font=author_font) > width and len(author) > 4:
            author = author[:-2].rstrip() + '…'
        draw.text((left, y + 6), author, font=author_font, fill=TYPE)
        y += 44

    # rating as figures, never as stars
    mine, public = metrics['my_rating'], metrics['public_rating']
    if mine or public:
        ry = y + 10
        if mine:
            draw.text((left, ry + 46), _num(mine), font=_font('dater', 62, 900), fill=TYPE, anchor='ls')
            vx = left + draw.textlength(_num(mine), font=_font('dater', 62, 900)) + 8
            draw.text((vx, ry + 44), '/ 5   MY RATING', font=_font('mono', 20, 600), fill=TYPE, anchor='ls')
            if public:
                vx += draw.textlength('/ 5   MY RATING', font=_font('mono', 20, 600)) + 28
                draw.text((vx, ry + 44), f'PUBLIC {_num(public)}', font=_font('mono', 20, 400), fill=TYPE, anchor='ls')
        else:
            draw.text((left, ry + 44), f'PUBLIC RATING {_num(public)} / 5',
                      font=_font('mono', 22, 600), fill=TYPE, anchor='ls')

    # the date slip: the numbers of this book
    slip_bottom = 548
    draw.rectangle((left, slip_top, right, slip_bottom), fill=SLIP, outline=TYPE, width=5)
    draw.text((left + 24, slip_top + 22), f'DATE SLIP · {call_no}', font=_font('mono', 18, 600), fill=TYPE, anchor='lm')
    for dx in range(left + 20, right - 20, 14):
        draw.line((dx, slip_top + 42, dx + 7, slip_top + 42), fill=TYPE, width=2)
    items = metrics['items'][:4]
    if items:
        col_w = width / 4
        for i, (value, label) in enumerate(items):
            cx = left + i * col_w + (24 if i == 0 else 22)
            if i:
                draw.line((left + i * col_w, slip_top + 54, left + i * col_w, slip_bottom - 16), fill=TYPE, width=2)
            draw.text((cx, slip_bottom - 52), value, font=_font('dater', 62, 900), fill=TYPE, anchor='ls')
            draw.text((cx, slip_bottom - 22), label.upper(), font=_font('mono', 16, 600), fill=TYPE, anchor='ls')

    # the stamp lands on the slip's top-right corner
    stamp = _stamp_for(book, metrics)
    if stamp:
        event, date_text, ink = stamp
        _stamp(card, (right - 150, slip_top - 36), event, date_text, ink, seed=book.id or len(book.title))

    # footer
    draw.text((56, 582), 'ALEXANDRIA', font=_font('dater', 30, 900), fill=TYPE, anchor='ls')
    draw.text((x1 - 36, 582), 'A PERSONAL LIBRARY', font=_font('mono', 18, 600), fill=TYPE, anchor='rs')

    buf = io.BytesIO()
    card.save(buf, 'PNG', optimize=True)
    return buf.getvalue(), cover is not None
