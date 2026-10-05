# Design system

## Direction

Alexandria should feel like a personal library, not a spreadsheet of books. The
interface borrows from three physical things:

- **Wooden shelves**: the collection stands on dark wood shelves with the book
  covers as spines and faces, so the home page reads as a room you walk into.
- **The catalog card**: book detail pages are laid out like a library catalog
  card, with ruled lines, typewriter-like labels and tidy fields.
- **Ex libris**: the bookplate stamped inside a cover. It informs the logo, the
  share card and the small ornamental details (borders, seals, rules).

The mood is warm and tactile: coffee, paper and autumn. No cold greys, no
neon, no glass. Decoration serves the metaphor; information stays legible.

## Palette

| Token | Hex | Use |
| :--- | :--- | :--- |
| cream | `#efe3cf` | Page background |
| paper | `#f8f0e2` | Cards, catalog card, share card surface |
| ink | `#2a1d16` | Body text, headings |
| brass | `#b8832f` | Accents, focus rings, seals, primary highlights |
| oxblood | `#6f2a24` | Destructive actions, dnf status, strong emphasis |
| moss | `#4a5d3a` | Finished status, positive indicators |
| wood | `#5a3a22` | Shelf boards, primary dark surfaces |
| wood (deep) | `#3b2415` | Shelf shadow, header, footer |
| leather | `#8a5a36` | Secondary buttons, borders on paper |
| rust | `#b4532a` | Reading status, charts, warm highlights |

Guidance:

- Text on cream or paper is always ink (or wood for secondary text), never
  brass or leather.
- Brass is for accents and large or bold elements; do not use it for small body
  text on cream.
- Status colours: reading is rust, finished is moss, to-read is brass, paused is
  leather, abandoned is oxblood. Never rely on colour alone; pair it with a
  label or icon.

## Typography

| Role | Font | Notes |
| :--- | :--- | :--- |
| Display | **Fraunces** | Headings, shelf labels, big numbers in stats. Its soft, wonky serifs give the "old press" character. |
| Text | **EB Garamond** | Body copy, descriptions, notes, forms |

Rules:

- Body text is at least 16px; the smallest text anywhere (captions, badges,
  chart labels) is 12px.
- Use Fraunces for anything that is a title or a number you want to be
  remembered; use EB Garamond for everything you read.
- Keep line length around 60 to 75 characters for descriptions and notes.
- Small caps and letter-spacing are fine for catalog-card labels, but keep them
  at 12px or larger.

## Components

- **Shelf**: a row of covers resting on a wooden plank (wood to deep wood
  gradient with a subtle top highlight and a cast shadow). Covers keep their
  aspect ratio; missing covers fall back to a leather-bound placeholder with the
  title set in Fraunces.
- **Book cover tile**: lifts slightly on hover and focus; a thin progress bar
  under reading books shows `current_page / page_count`.
- **Catalog card**: paper surface, ruled lines, brass top rule, field labels in
  small caps. Used for the book detail page.
- **Share card**: a self-contained paper card with an ex libris border, cover,
  title, author, rating and two or three key metrics. Designed to look right as
  a screenshot at a fixed aspect ratio.
- **Status badge**: pill with the status colour, always with a text label.
- **Stat tile**: Fraunces number over a small EB Garamond caption; the year
  selector sits above the stats grid.
- **Buttons**: primary is wood with cream text, secondary is outlined leather,
  destructive is oxblood. All have visible hover, focus and disabled states.
- **Forms**: paper inputs with a leather border and a brass focus ring; labels
  are always visible, never placeholder-only.
- **Charts**: warm single-hue or rust, brass and moss series on paper; every
  chart has a text equivalent (a number, table or label).

## Accessibility

- **Text size**: nothing below 12px; body text 16px or larger.
- **Contrast**: text and meaningful UI meet WCAG AA (4.5:1 for normal text, 3:1
  for large text and component boundaries). Ink on cream or paper and cream on
  wood or oxblood pass comfortably; check any new pairing before using it.
- **Touch targets**: interactive elements are at least 44 by 44px, including
  icon-only buttons and the controls on book tiles.
- **Focus**: every interactive element has a visible focus ring (brass, 2px or
  thicker, with offset). Focus is never removed without a replacement.
- **Reduced motion**: decorative motion (hover lifts, page transitions, card
  entrance) is disabled under `prefers-reduced-motion: reduce`. No information is
  conveyed by motion alone.
- **Colour independence**: status, rating and chart meaning is always repeated in
  text.
- **Semantics**: images of covers have alt text with the title; headings follow a
  logical order; forms have associated labels.
