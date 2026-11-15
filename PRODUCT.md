# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Flask 3 with server-rendered Jinja templates, SQLite, single gunicorn worker (unchanged backend). Chosen for the redesign (2026-11-14): keep Flask and server rendering, and add a front-end build step for project CSS and JS (Tailwind CLI or Vite) instead of loading Tailwind from a CDN. No single-page app; pages stay plain URLs.

## Users

- **The owner (librarian):** one person who logs in to run their own reading life: adds books found through Google Books search, logs the current page, starts, pauses, finishes or abandons books, rates them and keeps private notes.
- **Visitors:** friends and people the owner shares links with, browsing without an account. They see the collection, a book's catalogue page, stats and the calendar, and receive share cards for finished books. The interface must impress them as much as it serves the owner.

## Product Purpose

A self-hosted personal library and reading tracker. It records what the owner reads and turns it into something worth looking at and sharing: a collection that feels like a library, per-book metrics, yearly stats and a reading calendar. Success: the owner keeps it up to date because doing so is quick and pleasant, and visitors come away impressed by the library.

## Positioning

It is one person's own library, self-hosted, with the data in a single SQLite file they own. Not a social network, not a store, no recommendations engine: the library is the product, and it is meant to be shown.

## Operating Context

- Owner tasks, all treated as important: updating reading progress and status, browsing the collection (shelves, filters, notes, ratings), reading their numbers (stats with a year selector, calendar of started and finished books), and sharing (share card per finished book, public links).
- Metadata and covers come from Google Books and Open Library; some books have no cover or a placeholder image.
- Statuses: reading, finished, to-be-read (wish list), paused, did not finish. Custom shelves (tags). Formats: paper, ebook, audiobook.
- Read-only JSON API and CSV/JSON export exist alongside the UI.

## Capabilities and Constraints

- Routes: collection `/`, book `/book/<id>`, stats `/stats`, calendar `/calendar`, search and add `/search`, edit, custom shelf `/shelf/<name>`, share `/book/<id>/share` and `/book/<id>/card.png`, login.
- Anonymous visitors must never see private fields (personal notes) or management controls.
- Interface languages: English, Spanish and Galician (confirmed 2026-11-14). Today the UI is English-only; translations are new work.
- Single user, single worker, SQLite: no multi-user features.
- Undecided: language selection mechanism (browser preference, switcher, or both).

## Brand Commitments

- The product is a library. That theme is binding; everything else about the current look (palette, type, logo, wood shelves, catalogue card, 3D books, piles) may be replaced. The owner wants it more modern and more impressive than today.
- Name: Alexandria.

## Evidence on Hand

- Demo library: `scripts/seed_demo.py` (24 real titles with Open Library covers, a mix of statuses, two years of history).
- No testimonials, user counts or public claims exist; none may be invented.

## Product Principles

1. Logging a page or finishing a book takes seconds; impressiveness never slows the owner down.
2. The library is for showing: every public page should hold up when a visitor lands on it from a shared link.
3. The owner's data is the content: covers, titles, dates and numbers carry the pages, not decoration.
4. Private stays private: notes and controls exist only for the logged-in owner.

## Accessibility & Inclusion

WCAG 2.1 AA as the working standard (contrast, visible focus, 44px touch targets, reduced motion respected), carried over from the existing project.
