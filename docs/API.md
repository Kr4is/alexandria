# JSON API

Alexandria exposes a small, read-only JSON API. All endpoints are `GET`, return
`application/json` and live under `/api`.

The machine-readable description is served at `GET /api/openapi.json`.

## Authentication

Authentication is optional and controlled by the `READING_API_TOKEN` environment
variable.

- **Unset (default)**: every endpoint is open.
- **Set**: every `/api/*` request must send `Authorization: Bearer <token>`. A missing or
  wrong token returns `401`.

```bash
export TOKEN=change-me
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/stats
```

The token protects the `/api/*` endpoints only. The `/export.csv` and
`/export.json` routes are separate and are not covered by it, so keep the
instance behind a reverse proxy or private network if the data is sensitive.

The examples below omit the header for brevity.

## Errors

Errors use a single shape and the matching HTTP status:

```json
{"error": "Unauthorized"}
```

| Status | Meaning |
| :--- | :--- |
| `400` | Invalid query parameter (for example a malformed date or year) |
| `401` | Token required and missing or wrong |
| `404` | Book not found |

## Endpoints

### `GET /api/reading-activity`

Books finished in a period, plus the books currently being read and aggregate
stats for that period.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `since` | `YYYY-MM-DD` | Inclusive lower bound on `date_finished`. Default: no lower bound |
| `until` | `YYYY-MM-DD` | Exclusive upper bound on `date_finished`. Default: no upper bound |

`since` must be earlier than `until`. Omitting both returns all-time data.

```bash
curl "http://localhost:5000/api/reading-activity?since=2026-01-01&until=2027-01-01"
```

```json
{
  "period": {"since": "2026-01-01", "until": "2027-01-01"},
  "books_finished": [ { "id": 12, "title": "...", "status": "finished" } ],
  "currently_reading": [ { "id": 31, "title": "...", "status": "reading" } ],
  "stats": {
    "books_finished_count": 14,
    "total_pages": 4210,
    "avg_pages_per_book": 301,
    "reading_hours": 140.3,
    "categories": {"labels": ["Fiction"], "data": [9]},
    "pages_history": {"labels": ["2026-01"], "data": [620]}
  }
}
```

Each book is the object described under [Book object](#book-object).

### `GET /api/books`

Paginated, filterable list of books.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `status` | string | One of `reading`, `finished`, `tbr`, `paused`, `dnf` |
| `q` | string | Free-text search over title and authors |
| `category` | string | Filter by category |
| `year` | `YYYY` | Books finished in that year |
| `sort` | string | `date_added_desc` (default), `title_asc`, `title_desc`, `date_finished_desc`, `rating_desc` |
| `page` | integer | 1-based page number. Default `1` |
| `per_page` | integer | Page size. Default `24`, maximum `100` |

```bash
curl "http://localhost:5000/api/books?status=finished&year=2026&sort=rating_desc&per_page=5"
```

```json
{
  "items": [ { "id": 12, "title": "...", "status": "finished" } ],
  "page": 1,
  "per_page": 5,
  "total": 14,
  "pages": 3
}
```

`items` contains [book objects](#book-object); `pages` is the total number of
pages for the given `per_page`.

### `GET /api/books/<id>`

One book, with external links and computed metrics.

```bash
curl http://localhost:5000/api/books/12
```

```json
{
  "id": 12,
  "title": "The Name of the Rose",
  "authors": "Umberto Eco",
  "status": "finished",
  "page_count": 536,
  "current_page": 536,
  "date_started": "2026-02-01",
  "date_finished": "2026-02-20",
  "personal_rating": 4.5,
  "average_rating": 4.1,
  "external_links": {
    "open_library": "https://openlibrary.org/...",
    "goodreads": "https://www.goodreads.com/...",
    "worldcat": "https://search.worldcat.org/..."
  },
  "metrics": {
    "days_reading": 19,
    "pages_per_day": 28.2,
    "progress_pct": 100,
    "my_rating": 4.5,
    "public_rating": 4.1
  }
}
```

| Field | Description |
| :--- | :--- |
| `external_links` | Map of provider name to URL, built from the ISBN or title. Which providers are present depends on the book's data. |
| `metrics.days_reading` | Days between `date_started` and `date_finished` (or today while reading) |
| `metrics.pages_per_day` | Pages read divided by days reading |
| `metrics.progress_pct` | `current_page` over `page_count`, as a percentage |
| `metrics.my_rating` | Your `personal_rating` |
| `metrics.public_rating` | The public `average_rating` |

Metrics that cannot be computed (for example no `page_count`) are `null`.

Unknown ids return `404 {"error": "..."}`.

### `GET /api/stats`

Aggregated reading stats for one year.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `year` | `YYYY` | Year to summarise (four digits) |

```bash
curl "http://localhost:5000/api/stats?year=2026"
```

The response mirrors what the stats page shows for that year: books and pages
finished, average pages per book, reading hours, category breakdown and pages
history. An invalid `year` returns `400`.

### `GET /api/openapi.json`

The OpenAPI document describing every endpoint above.

```bash
curl http://localhost:5000/api/openapi.json
```

## Book object

Shared by every endpoint that returns books.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | integer | Book id |
| `title` | string | Title |
| `authors` | string | Authors, comma separated |
| `thumbnail` | string | Resolved cover URL |
| `description` | string | Description, if known |
| `page_count` | integer | Number of pages |
| `categories` | string | Categories, comma separated |
| `published_year` | string | Publication year |
| `language` | string | Language code |
| `average_rating` | number | Public rating |
| `status` | string | `reading`, `finished`, `tbr`, `paused` or `dnf` |
| `date_added` | string | `YYYY-MM-DD` |
| `date_started` | string | `YYYY-MM-DD` or `null` |
| `date_finished` | string | `YYYY-MM-DD` or `null` |
| `current_page` | integer | Reading progress, or `null` |
| `format` | string | `paper`, `ebook`, `audiobook` or `null` |
| `shelves` | string | Comma-separated custom shelves, or `null` |
| `personal_rating` | number | Your rating, or `null` |
| `personal_notes` | string | Your private notes, or `null` |

Note that the API is public when no token is configured, so `personal_notes` is
visible to anyone who can reach the server. Set `READING_API_TOKEN` if the
instance is exposed to the internet.
