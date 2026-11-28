"""ISBN parsing and check-digit validation (what a book's barcode encodes)."""
import re


def _clean(raw) -> str:
    return re.sub(r'[\s-]', '', str(raw or '')).upper()


def _isbn10_ok(s: str) -> bool:
    if not re.fullmatch(r'\d{9}[\dX]', s):
        return False
    total = sum((10 - i) * (10 if c == 'X' else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def _isbn13_ok(s: str) -> bool:
    if not re.fullmatch(r'97[89]\d{10}', s):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s[:12]))
    return (10 - total % 10) % 10 == int(s[12])


def isbn10_to_13(isbn10: str) -> str:
    body = '978' + isbn10[:9]
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(body))
    return body + str((10 - total % 10) % 10)


def normalize_isbn(raw) -> str | None:
    """Return a valid ISBN-13 for an ISBN-10 or ISBN-13 (hyphens allowed), else None."""
    s = _clean(raw)
    if len(s) == 10 and _isbn10_ok(s):
        return isbn10_to_13(s)
    if len(s) == 13 and _isbn13_ok(s):
        return s
    return None
