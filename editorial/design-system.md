# Times of Palestine — house design system

**Normative for every agent (Claude, Codex/ChatGPT, Copilot).** This file is
the shared definition of the site's look and layout. Any PR that changes a
reader-facing surface follows it; any PR that introduces a new visual pattern
updates this file in the same PR. Disagreements about design direction go to
issue #6 — never resolved by overwriting another agent's layer (charter rule).

The model is the world's great news fronts: restrained, typographic,
newspaper-first. Decoration serves hierarchy; nothing is ornamental for its
own sake. And per the charter's guiding principle, the page is ALIVE — every
surface should carry something that visibly changes between builds
(timestamps, counters, fresh-story marks).

## 1. Where the styles live

All site CSS is inline in `build.py` (one `<style>` block written into every
page, served as `/assets/site.css`). There is no CSS framework and no
build-time preprocessor. **Design tokens are CSS custom properties on
`:root`** — new rules must use `var(--…)` rather than re-hardcoding values,
and new hex families may not be introduced without adding them to this file
first.

## 2. Tokens

### Core palette (light theme, `:root`)

| Token | Value | Use |
|---|---|---|
| `--red` | `#C8102E` | Flag red: breaking ticker, kickers, masthead accent, hovers |
| `--green` | `#00753A` | Flag green: tip line, ORIGINAL badge, positive accents |
| `--black` | `#0b0b0c` | Dark bands, franchise cards, footer |
| `--ink` | `#141419` | Body text |
| `--muted` | `#595962` | Secondary text |
| `--paper` | `#f8f7f2` | Page background (warm off-white) |
| `--card` | `#ffffff` | Card surfaces |
| `--line` / `--line-dark` | `#e6e3da` / `#c9c5b8` | Hairlines |

### Accent families (used on dark surfaces)

- **Gold `#c7a86b`** — the specials/franchise accent: kickers, CTAs, borders
  (usually at reduced alpha, e.g. `rgba(199,168,107,.4)`), the 61-seat line.
  Ivory text on dark surfaces is `#f2eee8`.
- **Election blue** — the Israel-votes franchise variant: backgrounds
  `#10131a`→`#141c28` (145° gradient), steel blue `#3d4f6b`, text-blues
  `#8fa8cf`/`#b6c6e3`. Reserved for the election watch; don't reuse it for
  unrelated surfaces.
- **SVG graphic palette** (see §5): crimson `#8a1f2d`, green `#286344`,
  slate `#3d4f6b`, gold `#c7a86b`, ivory `#f2eee8`, muted `#aaa9a5`, dark
  gradient `#111214`→`#1d1e21`.

### Dark mode

`@media(prefers-color-scheme:dark)` overrides the core tokens
(`--paper:#101013`, `--card:#16161a`, `--ink:#e9e9ef`, …). The flag palette
stays true; only small red text lifts to `#f93549` for contrast. Every new
surface must be checked in both schemes — if you only style the light theme,
you have not finished the change.

### Typography

- **EN**: headlines `--serif` (Georgia stack), weight 700–900, tight
  leading (1.14–1.36 by level); UI/kickers `--sans` (system stack).
- **AR**: `--serif` becomes Tahoma/"Noto Naskh Arabic"/Amiri; the masthead
  uses Amiri. Arabic gets taller line-height (1.55–1.65), **zero
  letter-spacing** (never track Arabic), no uppercase transforms, and
  slightly larger sizes than the EN equivalent of the same element.
- **Numerals/data**: `ui-monospace,Menlo,monospace` — day counts, seat
  counts, scores.
- Kicker grammar (EN): sans 800, `.6–.75rem`, `letter-spacing:.12–.18em`,
  uppercase. The AR override drops the tracking and transform and bumps size.

### Geometry & motion

- Max content width `--max:1240px`; corner radius `--r:3px` (the house is
  square-ish — do not introduce big rounded corners); shadows `--sh`
  (rest) / `--sh-h` (hover); transitions `--tr:.18s ease`.
- Hover idiom for cards: `translateY(-2px)` + `--sh-h`.
- Existing keyframes — reuse, don't duplicate: `pulse` (latest-rail dot),
  `newpulse` (NEW mark, countdown chip dot), `tick`/`tick-rtl` (ticker).

## 3. Component grammar

- **Card** (`.card`, `.rowcard`, `.fr-card`): image on top (16/6 default
  aspect in franchise cards), then kicker → serif title → optional CTA.
  Franchise cards are dark (`--black`, gold accents); news cards are light.
- **Section head** (`.sec-head`): serif 900 title with red underline accent
  and a "View all →" link. Sections alternate light; research/investigations
  and specials ride dark bands.
- **Breaking ticker**: red band, black BREAKING label, 80s linear loop,
  pauses on hover, `tick-rtl` mirror for Arabic.
- **Live markers**: the pulsing NEW/جديد mark (<90 min stories); the
  countdown chip (`.fr-card.vote .days`) — dark pill, gold hairline border,
  pulsing gold dot, big mono numeral, recomputed every build. If you build a
  new "alive" element, follow this chip's anatomy.
- **CTAs**: gold, weight 700, arrow glyph — `→` in EN, `←` in AR. Never a
  button-styled link inside a card; the specials band CTA (bordered pill) is
  the one standing exception.

## 4. RTL is first-class

- Use **logical properties** (`margin-inline-start`, `inset-inline-end`,
  `padding-inline`, `border-block-end`) so one rule serves both directions.
  Physical left/right is a bug unless the element genuinely must not mirror.
- Every `[lang=ar]` element gets its typography override (see §2). Arrows
  flip. Animations that translate horizontally need an RTL variant.
- A front-page change is not done until verified on `/en/` AND `/ar/`, and
  graphics must not be EN-dominant on the AR edition (see §5).

## 5. House SVG graphics

- **Story/hero graphics**: 1600×900, dark gradient background
  (`#111214`→`#1d1e21`), flag spine on the inline-start edge (22px crimson +
  8px green bars), bilingual labels (EN sans / AR Cairo), mono numerals,
  credit line bottom-start "Graphic: Times of Palestine" with the Arabic
  credit at the opposite corner. Palette from §2. Self-created only — never
  copyrighted imagery.
- **Card-scale graphics get their own asset.** Lesson of PR #98: a 1600×900
  infographic cropped into a ~270px card is unreadable noise. Card art is a
  separate SVG (~800×350 for 16/7 slots) with bold shapes and minimum ~18px
  type at that canvas size. Name it `times-of-palestine-<subject>-card.svg`.
- **Bilingual balance**: on shared assets, EN and AR titles get comparable
  prominence. If a graphic's composition forces one language to dominate
  (e.g. a big EN headline), ship an `.ar` variant — the AR edition must not
  lead with English-dominant art. (Known debt: current hero graphics are
  EN-dominant; fix as each graphic is next touched.)
- **Shipping**: assets referenced by story files ship automatically
  (`copy_media`); assets referenced only from index furniture must be added
  to the explicit front-page furniture list in `build.py` or they 404.

## 6. Verification protocol (before any visual PR)

1. `python3 build.py` — clean run, `✓ original:` for touched files.
2. `python3 -m unittest discover -s tests` — green. **Note: the test suite
   rebuilds `dist/` from fixtures; rebuild before screenshotting.**
3. Screenshot the affected surface in four states minimum: EN desktop
   (1440), AR desktop, one mobile width (~420), and dark mode. Serve
   `dist/` locally (`python3 -m http.server` from `dist/`) — root-absolute
   asset paths don't resolve over `file://`. Playwright + the pre-installed
   Chromium works headless; attach before/after captures to the PR.
4. Remote og:images don't load offline — gray boxes locally are expected
   for wire-story thumbnails, not a regression.

## 7. Open design queue (audit 2026-08-02)

Tracked here so agents pick these up instead of inventing new directions:

- **Same-cover repetition**: two stories in one section can both fall back
  to the identical category cover (e.g. West Bank band showing the same art
  twice side-by-side). Wanted: per-story variation (crop offsets, numbered
  variants, or tinted duotone alternates) within the house style.
- **EN-dominant hero graphics on the AR edition** (§5) — retrofit as each
  graphic is next regenerated.
- Election hemicycle SVG (`times-of-palestine-israel-votes-card.svg`) bakes
  in the current bloc math — update it same-day when polls shift, together
  with the standings graphic (election beat: Claude).
