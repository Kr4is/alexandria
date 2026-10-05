"""Metrics and PNG share card (1200x630) for a single book."""

import hashlib
import io
import json
import math
import threading
from datetime import UTC, datetime
from pathlib import Path

import requests
from loguru import logger
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent.parent / 'static' / 'fonts'
CARD_VERSION = '1'
WIDTH, HEIGHT = 1200, 630

CREAM = '#efe3cf'
PAPER = '#f8f0e2'
INK = '#2a1d16'
GOLD = '#b8832f'
ACCENT = '#6f2a24'
WOOD = '#5a3a22'
WOOD_DARK = '#3b2415'
LEATHER = '#8a5a36'
STAR_EMPTY = '#d9c8a8'

STATUS_LABELS = {
    'reading': 'Reading now',
    'finished': 'Finished',
    'tbr': 'On the list',
    'paused': 'Paused',
    'dnf': 'Set aside',
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
            book.cover_url, book.cover_fallback_url,
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


def fetch_cover(book) -> Image.Image | None:
    """Download the cover server-side; None on any failure (offline, 404, 1x1 or tiny placeholder)."""
    for url in (book.cover_url, book.cover_fallback_url):
        if not url:
            continue
        try:
            data = _download(url)
            if not data:
                continue
            img = Image.open(io.BytesIO(data))  # lazy: size is known before decoding
            if img.width * img.height > COVER_MAX_PIXELS or min(img.size) < COVER_MIN_SIDE:
                continue
            return img.convert('RGB')
        except Exception as exc:  # noqa: BLE001 - a bad cover must never break the card
            logger.debug('share card cover fetch failed for {}: {}', url, exc)
    return None


# --- drawing -----------------------------------------------------------

_local = threading.local()  # FreeType faces are not thread-safe: one cache per thread


def _font(family: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    cache = _local.__dict__.setdefault('fonts', {})
    key = (family, size, weight)
    if key not in cache:
        if family == 'display':
            font = ImageFont.truetype(str(FONT_DIR / 'Fraunces-Variable.ttf'), size)
            font.set_variation_by_axes([min(max(size, 9), 144), weight, 0, 0])  # opsz, wght, SOFT, WONK
        else:
            font = ImageFont.truetype(str(FONT_DIR / 'EBGaramond-Variable.ttf'), size)
            font.set_variation_by_axes([weight])
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


def _fit_title(draw, title, max_width, max_lines=3):
    for size in range(60, 33, -2):
        font = _font('display', size, 700)
        lines = _wrap(draw, title, font, max_width)
        if len(lines) <= max_lines and all(draw.textlength(ln, font=font) <= max_width for ln in lines):
            return font, lines
    font = _font('display', 34, 700)
    lines = _wrap(draw, title, font, max_width)[:max_lines]
    last = lines[-1]
    while last and draw.textlength(last + '…', font=font) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip() + '…'
    return font, lines


def _spaced(draw, xy, text, font, fill, spacing=3):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _star_mask(size: int) -> Image.Image:
    s = size * 4
    pts = []
    for i in range(10):
        r = s / 2 * (1 if i % 2 == 0 else 0.42)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a) + s * 0.03))
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _draw_stars(card, x, y, rating, size=34, gap=6):
    mask = _star_mask(size)
    for i in range(5):
        sx = x + i * (size + gap)
        card.paste(STAR_EMPTY, (sx, y), mask)
        fill = max(0.0, min(1.0, rating - i))
        if fill:
            cut = mask.copy()
            ImageDraw.Draw(cut).rectangle((round(size * fill), 0, size, size), fill=0)
            card.paste(GOLD, (sx, y), cut)
    return x + 5 * (size + gap)


def _cover_panel(card, cover, book):
    """Left wooden panel with the cover (or a typographic stand-in)."""
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 420, HEIGHT), fill=WOOD_DARK)
    draw.rectangle((416, 0, 420, HEIGHT), fill=GOLD)
    box_w, box_h = 300, 450
    if cover:
        scale = min(box_w / cover.width, box_h / cover.height)
        cover = cover.resize((round(cover.width * scale), round(cover.height * scale)), Image.LANCZOS)
        w, h = cover.size
    else:
        w, h = box_w, box_h
    x, y = (416 - w) // 2, (HEIGHT - h) // 2
    shadow = Image.new('RGBA', (w + 80, h + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((40, 48, 40 + w, 48 + h), fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    card.paste(shadow, (x - 40, y - 40), shadow)
    if cover:
        card.paste(cover, (x, y))
        draw.rectangle((x - 1, y - 1, x + w, y + h), outline=GOLD, width=1)
        return
    draw.rectangle((x, y, x + w, y + h), fill=LEATHER)
    draw.rectangle((x + 14, y + 14, x + w - 14, y + h - 14), outline=GOLD, width=3)
    initial = (book.title.strip()[:1] or '?').upper()
    big = _font('display', 170, 800)
    draw.text((x + w / 2, y + h / 2 - 20), initial, font=big, fill=CREAM, anchor='mm')
    small = _font('text', 24, 500)
    draw.text((x + w / 2, y + h - 52), 'ALEXANDRIA', font=small, fill=CREAM, anchor='mm')


def render_card(book, metrics: dict | None = None, cover: Image.Image | None = None) -> tuple[bytes, bool]:
    """Render the 1200x630 PNG; returns (png, cover_used). Pass ``cover`` to skip the network fetch."""
    metrics = metrics or build_metrics(book)
    if cover is None:
        cover = fetch_cover(book)
    card = Image.new('RGB', (WIDTH, HEIGHT), PAPER)
    _cover_panel(card, cover, book)
    draw = ImageDraw.Draw(card)

    left, right = 476, WIDTH - 56
    width = right - left
    draw.rectangle((420, 0, WIDTH, 10), fill=ACCENT)

    # eyebrow
    draw.rectangle((left, 62, left + 36, 64), fill=GOLD)
    _spaced(draw, (left + 50, 48), metrics['status_label'].upper(), _font('text', 24, 600), ACCENT, 4)

    # title + author
    title_font, lines = _fit_title(draw, book.title, width)
    y = 92
    line_h = round(title_font.size * 1.12)
    for line in lines:
        draw.text((left, y), line, font=title_font, fill=INK)
        y += line_h
    if book.authors:
        author_font = _font('text', 32, 500)
        author = f'by {book.authors}'
        while draw.textlength(author, font=author_font) > width and len(author) > 4:
            author = author[:-2].rstrip() + '…'
        draw.text((left, y + 6), author, font=author_font, fill=WOOD)
        y += 54

    # ratings
    y += 14
    mine, public = metrics['my_rating'], metrics['public_rating']
    if mine:
        x = _draw_stars(card, left, y, mine)
        draw.text((x + 8, y + 17), _num(mine), font=_font('display', 34, 700), fill=INK, anchor='lm')
        x += 8 + draw.textlength(_num(mine), font=_font('display', 34, 700)) + 24
        if public:
            draw.text((x, y + 17), f'public {_num(public)}', font=_font('text', 26, 500), fill=LEATHER, anchor='lm')
    elif public:
        draw.text((left, y + 17), f'public rating {_num(public)} / 5', font=_font('text', 28, 500), fill=LEATHER, anchor='lm')

    # metrics row
    items = metrics['items'][:4]
    if items:
        row_y = 452
        draw.line((left, row_y - 18, right, row_y - 18), fill=GOLD, width=2)
        col_w = width / 4
        for i, (value, label) in enumerate(items):
            cx = left + i * col_w
            draw.text((cx, row_y), value, font=_font('display', 44, 700), fill=INK)
            draw.text((cx, row_y + 58), label.upper(), font=_font('text', 20, 600), fill=WOOD)

    # footer
    draw.text((left, 578), 'Alexandria', font=_font('display', 26, 700), fill=ACCENT)
    draw.text((right, 580), 'my personal library', font=_font('text', 24, 500), fill=LEATHER, anchor='ra')

    buf = io.BytesIO()
    card.save(buf, 'PNG', optimize=True)
    return buf.getvalue(), cover is not None
