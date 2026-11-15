# Design: Circulation Record

Alexandria's interface is a library circulation record: date-due slips, book pockets, coloured index-card stock and rubber date stamps. Every start and every finish is a stamped date. The owner's books, dates and numbers carry the pages; the look only gives them a place to land.

The source of truth for tokens and components is `static/src/app.css`. Shared Jinja pieces are in `templates/_macros.html`, shared behaviour in `static/js/app.js`.

## Rules

1. **Card stock = status.** Each status has one stock colour and nothing else uses it.
   | Status | Token | |
   |---|---|---|
   | Reading | `stock-reading` | yellow `#f2d13a` |
   | Finished | `stock-finished` | green `#7fc4a0` |
   | To read | `stock-tbr` | blue `#8fc1e6` |
   | Paused | `stock-paused` | salmon `#f29a85` |
   | Did not finish | `stock-dnf` | plain slip `#fbfaf6` |
2. **Ink = event.** Violet `ink-started` (#5236a8) means started, red `ink-finished` (#d8232a) means finished, black `ink-returned` means returned unread. Inks are never ornament, links or buttons.
3. **One tonal ramp.** Density goes through five steps, `d0` to `d4`, from paper to 58% black. Busy months, hover fills and secondary grounds use these and nothing else.
4. **Ground and type.** Paper `#f4f1ea`, slip `#fffdf8`, type `#141414`. Rules are 2px solid type. Corners are square or a 6–8px card radius; no soft shadows. The only shadow is a hard offset in type colour for a lifted record.
5. **Tabular digits everywhere.** Set on `body`.
6. **One record held at a time.** Opening a card (`[data-record]` + `[data-hold]`) dims the rest; Esc returns it.
7. **Today's date is live.** The big dater (`dater()` macro) sits at the top of the collection; once it scrolls away, the dial pinned bottom-right shows the date every action will stamp (owner only).

## Type

| Role | Face | Use |
|---|---|---|
| Dater | Big Shoulders Display 700–900 | the dater, section heads, big figures, stamps |
| UI | Archivo 400–800, width 75–100% | titles (800 at 80% width), body, buttons |
| Typewriter | IBM Plex Mono 400–700 | labels, metadata, dates, counts, notes on the record |

All three are self-hosted in `static/fonts` (latin subset, covers English, Spanish and Galician). The share-card PNG (`alexandria/services/share_card.py`) draws with the same three faces, read straight from these files.

## Components (`static/src/app.css`)

- `.top`, `.nav`, `.mark`: header. `.nav .add` is the one filled nav item.
- `.dater` / `.band`: the rubber-band dater. `.dial`: the pinned dial.
- `.sec-head`: ruled section head with a huge uppercase dater-face title, `.count` and `.aside`.
- `.stamp.{started|finished|returned}.{xs|sm|med|big}`: ink stamps; use the `stamp()` macro.
- `.pocket` > `.card` + `.pocket-sleeve`: a book that is out (reading). `.ruler` for progress, `.slip` for where stamps land and the page log, `.stepper` for page input.
- `.drawer.{reading|finished|tbr|paused|dnf|plain}` > `.drawer-tab` + `.drawer-body`: a status drawer. `.drawer-body.grid6` for a cover grid.
- `.rec` (and `.rec.row`): one book as an index card; use the `rec()` macro.
- `.cover`: 2:3 ruled cover with a typed placeholder behind it; use the `cover()` macro.
- `.tally`, `.segbar`, `.yearsel`, `.months` / `.month[data-d]` / `.days` / `.dot`: stats and calendar.
- `.btn-stamp` (filled, primary), `.btn-line` (outline), `.field` / `.input` / `.hint`: forms.
- `.flash`, `.toast`, `.modal`: feedback. Confirmations use `data-confirm="finish|delete"` with `data-action` and `data-title`.

Page-specific CSS goes in `static/src/pages/<page>.css`, inside `@layer components`.

## Accessibility

WCAG 2.1 AA: 3px type-colour focus ring with a slip halo, 44px minimum targets, `prefers-reduced-motion` turns off every transition and the stamp "thunk". Stamps and colour never carry meaning alone: every stamp has its word (STARTED, FINISHED) and every stock has its status label.

## Voice

Library circulation words, said plainly: "out now", "stamped finished", "returned unread", "filed under to read", "withdraw". No pastiche of old-fashioned prose.

## Build

`npm ci && npm run build` (or `make css`) compiles `static/src/app.css` to `static/dist/app.css`, which is git-ignored. Docker images build it in an `assets` stage. `make css-watch` rebuilds while editing templates.

## Share card (1200x630 PNG)

Rendered with Pillow in the same system: the whole card is the book's status stock colour inside a 6px ruled frame on paper, a header band (`CIRCULATION RECORD`, status tag, call number), the cover lifted with a hard offset shadow, the title in Archivo 800 at 80% width (as large as fits), the rating as figures, and a date slip with the numbers in Big Shoulders digits split by rules. The rubber stamp (`FINISHED` red, `STARTED` violet, `RETURNED UNREAD` black) lands on the slip's top edge; to-read and paused books carry no stamp. A book with no usable cover gets a typed index card. Covers pass through the same placeholder check as the rest of the app, so a provider's "image not available" is never shown.
