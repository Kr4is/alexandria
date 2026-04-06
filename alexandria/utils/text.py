import html as html_lib
import re


def strip_book_description_html(raw):
    if not raw:
        return ''
    t = html_lib.unescape(str(raw))
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'</p\s*>', '\n\n', t, flags=re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()
