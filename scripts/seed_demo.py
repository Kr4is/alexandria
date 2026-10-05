"""Seed Alexandria with a demo library.

    uv run python scripts/seed_demo.py [--reset]

Every demo row carries ``google_books_id = 'demo-<slug>'``. The script is
idempotent (existing demo rows are skipped) and ``--reset`` only ever deletes
rows carrying that marker, never user data. Respects ``DATABASE_URL``.
"""

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alexandria import create_app  # noqa: E402
from alexandria.constants import BookStatus  # noqa: E402
from alexandria.extensions import db  # noqa: E402
from alexandria.models import Book  # noqa: E402

MARKER = 'demo-'
OPEN_LIBRARY = 'https://covers.openlibrary.org/b/isbn/{}-L.jpg'

F, R, P, D, T = (BookStatus.FINISHED, BookStatus.READING, BookStatus.PAUSED,
                 BookStatus.DNF, BookStatus.TBR)

# slug, title, authors, isbn, pages, categories, year, lang, avg, status,
# rating, days_ago (finish for F, added otherwise), read_days, fmt, notes, blurb
# fmt: 'paperback' | 'hardcover' | 'ebook' | 'audiobook'
CATALOG = [
    ('hobbit', 'The Hobbit', 'J.R.R. Tolkien', '9780547928227', 300, 'Fantasy', '1937', 'en', 4.5,
     F, 4.5, 5, 9, 'hardcover', 'Re-read before the films; still the coziest adventure there is.',
     'A comfort-loving homebody is swept into a quest he never wanted. Dwarves, dragons and a '
     'ring found in the dark, told with the warmth of a fireside story.'),
    ('dune', 'Dune', 'Frank Herbert', '9780441013593', 688, 'Science Fiction', '1965', 'en', 4.3,
     F, 5, 19, 24, 'paperback', 'Politics, ecology and prophecy braided together. Dense, rewarding.',
     'On a desert planet that holds the galaxy\'s most precious resource, a young heir must survive '
     'betrayal and grow into something larger than a duke\'s son.\n\n'
     'Part ecological parable, part political thriller, it rewards slow, attentive reading.'),
    ('sapiens', 'Sapiens: A Brief History of Humankind', 'Yuval Noah Harari', '9780062316110', 464,
     'History', '2011', 'en', 4.4, F, 3.5, 52, 31, 'audiobook', None,
     'A sweeping tour of how one unremarkable ape came to dominate the planet, through '
     'agriculture, money, empires and shared fictions.'),
    ('pride', 'Pride and Prejudice', 'Jane Austen', '9780141439518', 480, 'Classics', '1813', 'en',
     4.3, F, 4.5, 58, 17, 'paperback', None,
     'Sharp-tongued Elizabeth Bennet and the proud Mr Darcy misjudge each other in a village '
     'where marriage is the main economy. Witty, brisk, endlessly quotable.'),
    ('etranger', "L'Étranger", 'Albert Camus', '9782070360024', 186, 'Philosophy', '1942', 'fr',
     4.0, F, 4.0, 97, 6, 'paperback', 'Lu en français, lentement. La dernière page reste.',
     'A detached clerk in Algiers drifts through his mother\'s funeral, a love affair and a '
     'killing on a bright beach. A short book that asks long questions about meaning.'),
    ('cien-anos', 'Cien años de soledad', 'Gabriel García Márquez', '9780307474728', 471,
     'Fiction', '1967', 'es', 4.6, F, 5, 150, 40, 'paperback',
     'Los nombres se repiten y aun así nunca me perdí. Magia pura.',
     'Seven generations of the Buendía family rise and fall in the mythical town of Macondo, '
     'where miracles are ordinary and memory is fragile.'),
    ('cosmos', 'Cosmos', 'Carl Sagan', '9780345539434', 396, 'Science', '1980', 'en', 4.5,
     F, 4.0, 163, 28, 'ebook', None,
     'A guided walk through the history of astronomy and our place in the universe, written '
     'with wonder rather than jargon.'),
    ('frankl', "Man's Search for Meaning", 'Viktor E. Frankl', '9780807014295', 184, 'Philosophy',
     '1946', 'en', 4.4, F, 5, 171, 5, 'paperback', 'Read in two sittings. Underlined half of it.',
     'A psychiatrist reflects on surviving the camps and on why people endure suffering when '
     'they can find a reason to. Brief, humane and hard to forget.'),
    ('hail-mary', 'Project Hail Mary', 'Andy Weir', '9780593135204', 496, 'Science Fiction',
     '2021', 'en', 4.5, F, 4.0, 260, 12, 'audiobook', None,
     'A lone astronaut wakes with no memory aboard a ship far from home and slowly pieces '
     'together a mission to save the Sun. Science puzzles and an unlikely friendship.'),
    ('good-omens', 'Good Omens', 'Terry Pratchett, Neil Gaiman', '9780060853983', 400, 'Fantasy',
     '1990', 'en', 4.3, F, 3.5, 340, 21, 'paperback', None,
     'An angel and a demon, comfortable on Earth, conspire to delay the apocalypse after the '
     'Antichrist is mislaid at birth. Gleefully irreverent.'),
    ('left-hand', 'The Left Hand of Darkness', 'Ursula K. Le Guin', '9780441478125', 304,
     'Science Fiction', '1969', 'en', 4.1, F, 4.0, 410, 35, 'paperback', None,
     'An envoy on a frozen world, where people have no fixed gender, struggles to understand '
     'a culture and a friend. Quiet, patient and quietly radical.'),
    ('born-a-crime', 'Born a Crime', 'Trevor Noah', '9780399588174', 304, 'Biography', '2016',
     'en', 4.6, F, 4.5, 560, 8, 'audiobook', 'Hearing it in the author\'s own voice is the way.',
     'Stories of growing up mixed-race in apartheid South Africa, told with comic timing and '
     'a deep love for the mother who raised him.'),
    ('peste', 'La Peste', 'Albert Camus', '9782070360420', 336, 'Fiction', '1947', 'fr', 4.0,
     F, 3.0, 650, 26, 'paperback', None,
     'A coastal Algerian town is sealed off as plague spreads, and ordinary people choose '
     'how to meet the absurd. Sober, humane, still timely.'),
    ('brief-history', 'A Brief History of Time', 'Stephen Hawking', '9780553380163', 212,
     'Science', '1988', 'en', 4.2, F, 2.5, 740, 45, 'paperback',
     'Lost me around black-hole thermodynamics; will retry someday.',
     'From the Big Bang to black holes, a physicist explains the biggest questions about '
     'space and time to a general audience.'),
    ('rayuela', 'Rayuela', 'Julio Cortázar', None, None, 'Fiction', '1963', 'es', 4.0,
     F, 4.0, 90, 30, 'paperback', 'Leída en el orden "salteado". Merece la pena.',
     None),
    # Currently reading
    ('quijote', 'Don Quixote', 'Miguel de Cervantes, Edith Grossman', '9780060934347', 1056,
     'Classics', '1605', 'en', 3.9, R, None, 40, 30, 'hardcover', None,
     'A country gentleman, his head full of chivalric romances, rides out to revive knighthood '
     'with a patient squire. Funny, sad and astonishingly modern for a book from 1605.'),
    ('steve-jobs', 'Steve Jobs', 'Walter Isaacson', '9781451648539', 656, 'Biography', '2011',
     'en', 4.1, R, None, 14, 10, 'ebook', None,
     'An authorised biography built on dozens of interviews, following the founder from garage '
     'tinkering through exile and return.'),
    # Paused
    ('thinking', 'Thinking, Fast and Slow', 'Daniel Kahneman', '9780374533557', 499, 'Science',
     '2011', 'en', 4.2, P, None, 120, 30, 'paperback', None,
     'A Nobel laureate lays out two modes of thought, one quick and intuitive, one slow and '
     'deliberate, and the predictable errors that follow.'),
    ('name-of-the-wind', 'The Name of the Wind', 'Patrick Rothfuss', '9780756404741', 662,
     'Fantasy', '2007', 'en', 4.5, P, None, 200, 60, 'paperback', None,
     'Kvothe, now an innkeeper, tells the true story of how he went from travelling performer '
     'to the most notorious arcanist of his age.'),
    # DNF
    ('crime-punishment', 'Crime and Punishment', 'Fyodor Dostoevsky', '9780143107637', 608,
     'Classics', '1866', 'en', 4.2, D, None, 180, 20, 'ebook',
     'Gave up at the second act; the fever-dream tone wasn\'t for this season.',
     'A destitute student convinces himself that one murder can be justified, then has to '
     'live inside the consequences.'),
    # To read
    ('guns-of-august', 'The Guns of August', 'Barbara W. Tuchman', '9780345476098', 608,
     'History', '1962', 'en', 4.3, T, None, 30, None, 'paperback', None,
     'A narrative history of the opening month of the First World War and the miscalculations '
     'that turned a crisis into a catastrophe.'),
    ('tractatus', 'Tractatus Logico-Philosophicus', 'Ludwig Wittgenstein', None, None,
     'Philosophy', '1921', 'en', 3.8, T, None, 12, None, None, None, None),
    ('fourth-wing', 'Fourth Wing', 'Rebecca Yarros', '9781649374042', 498, 'Fantasy', '2023',
     'en', 3.4, T, None, 7, None, 'ebook', None,
     'A frail cadet enters a war college where dragons choose riders and failing means dying. '
     'Fast, romantic, unapologetically popular.'),
    ('prince', 'The Prince', 'Niccolò Machiavelli', '9780140449150', 140, 'Philosophy', '1532',
     'en', 3.7, T, None, 3, None, 'paperback', None,
     'A short manual on seizing and keeping power, long mistaken for cynicism and still the '
     'founding text of political realism.'),
]


def _rows(now: datetime) -> list[dict]:
    rows = []
    for (slug, title, authors, isbn, pages, cats, year, lang, avg, status, rating,
         days_ago, read_days, fmt, notes, blurb) in CATALOG:
        when = now - timedelta(days=days_ago)
        finished = status == F
        row = {
            'google_books_id': MARKER + slug, 'title': title, 'authors': authors,
            'isbn': isbn, 'page_count': pages, 'categories': cats, 'published_year': year,
            'language': lang, 'average_rating': avg, 'status': status,
            'thumbnail': OPEN_LIBRARY.format(isbn) if isbn else None,
            'description': blurb, 'personal_rating': rating, 'personal_notes': notes,
            'date_finished': when if finished else None,
            # finished books were added well before they were finished
            'date_added': when - timedelta(days=read_days + 12 + days_ago % 40) if finished else when,
        }
        if pages and status == R:
            row['current_page'] = int(pages * 0.4)
        elif pages and status in (P, D):
            row['current_page'] = int(pages * 0.3)
        elif finished and pages:
            row['current_page'] = pages
        if read_days and status != T:
            row['date_started'] = row['date_finished'] - timedelta(days=read_days) if finished \
                else when
        if fmt:
            row['format'] = fmt
        rows.append(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Seed Alexandria with a demo library.')
    parser.add_argument('--reset', action='store_true',
                        help="delete previous demo rows (google_books_id 'demo-*') and re-seed")
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        deleted = 0
        if args.reset:
            deleted = Book.query.filter(Book.google_books_id.startswith(MARKER)).delete(
                synchronize_session=False)
            db.session.commit()

        existing = {gid for (gid,) in db.session.query(Book.google_books_id)
                    .filter(Book.google_books_id.startswith(MARKER))}
        created = skipped = 0
        by_status = Counter()
        for row in _rows(datetime.now(UTC)):
            if row['google_books_id'] in existing:
                skipped += 1
                continue
            # Columns added by other work are only set when the model has them.
            data = {k: v for k, v in row.items() if hasattr(Book, k)}
            db.session.add(Book(**data))
            created += 1
            by_status[row['status']] += 1
        db.session.commit()

        total = Book.query.filter(Book.google_books_id.startswith(MARKER)).count()

    print(f'Demo seed: deleted {deleted}, created {created}, skipped {skipped} '
          f'(demo books in library: {total})')
    for status in BookStatus.ALL:
        print(f'  {status:<9}{by_status[status]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
