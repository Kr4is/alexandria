<p align="center">
  <img src="static/logo.svg" width="120" alt="Alexandria Logo">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
</p>

# Alexandria &mdash; Your Personal Private Library

Alexandria is a self-hosted reading tracker that feels like a personal library
rather than a list of rows. Your books stand on wooden shelves, every volume has
a catalog card, and your year of reading is summarised in numbers you can
actually share. Metadata and covers come from the Google Books API; everything
else lives in a single SQLite file that you own.

It is a small, deliberately boring Flask application (server-rendered Jinja,
SQLite, one container) built to be easy to run, easy to read and easy to
extend.

## Features

**Library**

- **Wooden shelves**: the home page renders your collection as books on shelves,
  grouped by what you are reading, have finished, plan to read, paused or
  abandoned. Custom shelves (tags) let you organise beyond reading status.
- **Reading progress**: log the current page and start date; progress bars and
  "days reading" update as you go.
- **Catalog card**: each book has a detail page styled as a library catalog
  card, with description, categories, your private notes and rating.
- **Formats**: mark a book as paper, ebook or audiobook.
- **Status workflow**: `reading`, `finished`, `tbr`, `paused`, `dnf`, with quick
  status changes and a one-click "finish" action.
- **Calendar**: a month view of what you started and finished.

**Metrics and sharing**

- **Per-book metrics**: days reading, pages per day, progress percentage, your
  rating versus the public rating.
- **Share cards**: a clean, self-contained card for a finished book that you can
  post or screenshot.
- **Richer stats** with a **year selector**: books and pages per year, reading
  velocity, category breakdown, pages history and a few reading curiosities.

**Discovery and integration**

- **Archive search**: find and add books through Google Books (cached, with an
  optional API key).
- **External links**: jump from any book to Open Library, Goodreads, WorldCat
  and others, built from its ISBN or title.
- **Public JSON API**: read-only endpoints for books, per-book metrics, stats and
  reading activity, with an OpenAPI document and optional bearer-token
  protection. See [docs/API.md](docs/API.md).
- **CSV / JSON export** of the whole collection at `/export.csv` and
  `/export.json`.

**Operations**

- **Secure by default**: login with configured librarian credentials, CSRF
  protection, rate-limited login, secure session cookies in production.
- **Migrations** with Flask-Migrate / Alembic, applied automatically by the
  Docker entrypoint.
- **CI** that runs lint and tests, plus a multi-arch (amd64/arm64) image
  published to `ghcr.io`.
- **Demo data**: `scripts/seed_demo.py` fills an empty database with a believable
  library so you can explore every screen immediately.

## Tech stack and design decisions

| Layer | Choice |
| :--- | :--- |
| Language / runtime | Python 3.13, managed with [uv](https://github.com/astral-sh/uv) |
| Web | Flask 3, blueprints, Jinja2 templates |
| Persistence | SQLite via Flask-SQLAlchemy, Alembic migrations (Flask-Migrate) |
| Auth / safety | Flask-Login, Flask-WTF (CSRF), Flask-Limiter |
| Styling | Tailwind CSS (CDN) with a small custom design system |
| External data | Google Books API via `requests`, in-memory TTL cache |
| Serving | gunicorn (single worker), Docker, Docker Compose |
| Quality | pytest, pytest-cov, ruff, GitHub Actions |

**Why Flask + server-rendered Jinja.** The app is read-mostly, single-user and
content-heavy. Server rendering keeps every page a plain URL that works without
a build step or client-side state, makes the pages trivially testable with
Flask's test client, and keeps the whole stack in one language. The few
interactive bits are small, local enhancements rather than a SPA.

**Why SQLite.** One user, one file, zero operations. Backups are a file copy and
the Docker volume is a single directory. The data model is small and relational
enough that SQLite is a feature, not a compromise.

**Why a single gunicorn worker.** SQLite allows one writer at a time, and the
Google Books caches are in-process dictionaries. One worker means no write
contention, no migration races and a coherent cache. Concurrency is not the
bottleneck for a personal library; the entrypoint runs `flask db upgrade` before
gunicorn starts for the same reason. If you ever need more throughput, move to
PostgreSQL first and raise the worker count second.

**Why Tailwind via CDN.** There is no Node toolchain in the project, so a fresh
clone runs with `uv` alone and the templates stay the single source of truth for
styling. The trade-off is real: the browser downloads and runs the Tailwind
runtime, you need network access to the CDN, and you cannot purge unused CSS.
For a self-hosted app with a handful of pages that is an acceptable price; a
compiled stylesheet is the natural upgrade if the app is ever served at scale.
The design tokens are documented in [docs/DESIGN.md](docs/DESIGN.md).

More detail, including the request flow and data model, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quickstart

### Docker (recommended)

```bash
cp .env.example .env     # then edit SECRET_KEY and the librarian credentials
docker compose up -d
```

Open `http://localhost:5000`. The database lives in `./instance`, which is
mounted into the container. Migrations run automatically on start.

> `docker-compose.yml` also starts Adminer on port 8081 for direct database
> access. Remove or restrict it before exposing the host to the internet.

A prebuilt multi-arch image is published to `ghcr.io/kr4is/alexandria` on every
push to `master`.

### Local development

Requires [uv](https://github.com/astral-sh/uv) and Python 3.13.

```bash
cp .env.example .env
make install run
```

Without `make`, the equivalent commands are `uv sync --group dev`,
`uv run python app.py` and `uv run pytest`.

Then open `http://localhost:5000` and sign in with the librarian credentials
from your `.env` (defaults: `admin` / `alexandria`).

### Make targets

| Target | What it does |
| :--- | :--- |
| `make install` | Install runtime and dev dependencies with `uv sync --group dev` |
| `make run` | Start the development server |
| `make test` | Run the pytest suite |
| `make lint` | Run ruff |
| `make cov` | Run the tests with a coverage report |
| `make seed` | Load demo data with `scripts/seed_demo.py` |
| `make docker` | Build and start the Docker Compose stack |

### Demo data

To explore the interface with a full shelf instead of an empty one:

```bash
make seed
```

`scripts/seed_demo.py` creates a varied library (reading, finished across
several years, to-read, paused and abandoned books, with progress, ratings and
shelves) so the shelves, calendar, stats and share cards all have something to
show.

## Configuration

Alexandria is configured with environment variables. Copy the template to get
started:

```bash
cp .env.example .env
```

| Variable | Description | Default |
| :--- | :--- | :--- |
| `APP_NAME` | The title of your library | `Alexandria` |
| `SECRET_KEY` | Security key for session encryption. Always change it in production | `default-key-for-dev` |
| `LIBRARIAN_USERNAME` | Admin login username (the user is created or updated on startup) | `admin` |
| `LIBRARIAN_PASSWORD` | Admin login password | `alexandria` |
| `GOOGLE_BOOKS_API_KEY` | Optional API key for Google Books (avoids shared anonymous quota / HTTP 429) | _(unset)_ |
| `GOOGLE_BOOKS_CACHE_TTL_SECONDS` | In-memory cache TTL for search and volume lookups (0 disables caching) | `3600` |
| `REFRESH_LIBRARY_METADATA_ON_STARTUP` | Refresh all library metadata from Google Books on startup (1 API call per book) | `false` |
| `DATABASE_URL` | SQLite database URI | `sqlite:///instance/alexandria.db` |
| `READING_API_TOKEN` | Optional bearer token for the public JSON API. Unset leaves the API open | _(unset)_ |
| `FLASK_ENV` | Set to `production` to mark session cookies as `Secure` (serve over HTTPS) | _(unset)_ |
| `ADMINER_PASSWORD` | Password for the optional Adminer service in `docker-compose.yml` | _(see `.env.example`)_ |

> `docker-compose.yml` forwards only the variables listed in its `environment:`
> section. Make sure `READING_API_TOKEN` and `FLASK_ENV` are listed there if you
> rely on them in Docker.

## API

Alexandria exposes a small read-only JSON API:

| Endpoint | Purpose |
| :--- | :--- |
| `GET /api/reading-activity` | Books finished in a period plus what you are reading now |
| `GET /api/books` | Filterable, sortable, paginated book list |
| `GET /api/books/<id>` | One book with external links and per-book metrics |
| `GET /api/stats` | Aggregated stats for a year |
| `GET /api/openapi.json` | OpenAPI description of the API |

Set `READING_API_TOKEN` to require `Authorization: Bearer <token>`. Full
parameters, response shapes and `curl` examples are in
[docs/API.md](docs/API.md).

## Testing and CI

```bash
make test        # pytest
make cov         # pytest with coverage
make lint        # ruff
```

The suite covers the services (stats, calendar, book metrics, share cards), the
Google Books client and its cache, cover URL resolution, template filters,
authentication, the book blueprints and the JSON API, each test against its own
temporary SQLite database, with the Google Books API mocked.

GitHub Actions runs lint and tests on every push and pull request, and builds
and publishes the multi-arch container image to `ghcr.io` from `master`.

## Project structure

```text
alexandria/              Application package
  __init__.py            create_app(): wiring, blueprints, error handlers, CLI
  config.py              Environment-driven settings
  extensions.py          db, login manager, CSRF, rate limiter, migrate
  models.py              User and Book models
  bootstrap.py           Startup: instance dir, librarian user, optional refresh
  blueprints/            HTTP layer: main, auth, books, api, share
  services/              Domain logic: books, stats, calendar, book_metrics, share_card
  integrations/          Google Books client (with TTL cache)
  utils/                 Cover URL resolution, language names, text helpers
  filters.py             Jinja template filters
docs/                    ARCHITECTURE.md, API.md, DESIGN.md
migrations/              Alembic environment and versions
scripts/seed_demo.py     Demo library generator
static/                  Logo, favicon and static assets
templates/               Jinja2 templates
tests/                   pytest suite
.github/workflows/       CI and image publishing
app.py                   Entry shim (gunicorn target `app:app`, `python app.py`)
Makefile                 install, run, test, lint, cov, seed, docker
Dockerfile               Multi-stage build on python:3.13-slim
docker-compose.yml       App plus optional Adminer
docker-entrypoint.sh     Runs migrations, then gunicorn with one worker
instance/                SQLite database (a volume in Docker)
```

`main.py`, `api.py` and `models.py` at the repository root are thin
backward-compatible shims; import from `alexandria` in new code.

## Roadmap

- **Open Library description enrichment**: fill missing or poor descriptions
  from Open Library when Google Books has none.
- **README screenshots from the demo seed**: capture the shelves, catalog card,
  stats and share card from `scripts/seed_demo.py` data.
- **Docker healthcheck**: add a `HEALTHCHECK` to the image and Compose service.
- **Multi-user support**: per-user libraries instead of a single librarian.

---
*Catalogued with care, 2026.*
