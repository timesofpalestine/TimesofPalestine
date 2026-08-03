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

Dark rules are written ONCE (`_DARK_RULES` in `build.py`) and emitted twice:
under `@media(prefers-color-scheme:dark)` scoped to
`html:not([data-theme=light])`, and under `html[data-theme=dark]`. A 🌙
toggle in the topbar/backbar cycles auto → dark → light, stored in
`localStorage` and restored before first paint. Never write dark styles
directly into a media query — add them to `_DARK_RULES` so the toggle sees
them. The flag palette stays true; only small red text lifts to `#f93549`
for contrast. Every new surface must be checked in both schemes — if you
only style the light theme, you have not finished the change.

### Pull quotes & data callouts

`> ` lines in a story body render as `blockquote.pull`: large serif on a
gold inline-start rule, capped at the reading measure; a second `> ` line
renders as the smaller sans attribution. Use for a survivor's words or one
load-bearing statistic — one or two per story, never as decoration.

### Typography

- **EN**: headlines `--serif` (Georgia stack), weight 700–900, tight
  leading (1.14–1.36 by level); UI/kickers `--sans` (system stack).
- **AR**: both `--serif` and `--sans` lead with **"Noto Kufi Arabic"**
  (self-hosted variable font in `/fonts/`, OFL) — the house Arabic face,
  matching the modern low-contrast Kufi register of Al Jazeera's front
  (whose own typeface is legally exclusive and must never be copied in).
  Fallbacks: Tahoma / "Noto Naskh Arabic" / Amiri. The masthead uses Noto
  Kufi Arabic too. Arabic gets taller line-height (1.55–1.65), **zero
  letter-spacing** (never track Arabic), no uppercase transforms, and
  slightly larger sizes than the EN equivalent of the same element.
- **Numerals/data**: `ui-monospace,Menlo,monospace` — day counts, seat
  counts, scores. Percentage indicators (e.g., the Gaza-in-numbers strip)
  carry a 4px flag-red context bar under the figure (`.gi-bar`: rgba red
  track, solid `--red` fill sized `inline-size:<pct>%`) so a critical rate
  reads at a glance; the pattern is CSS-only and RTL-safe.
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

- **Section nav** (`nav.sections`, merged design of #117 + #118): sticky
  black band of minimalist uppercase line-tabs (2px bottom indicator on
  hover — no pills, no boxes), organized as TWO tiers (`.n1`/`.n2`).
  Tier 1 is the hard-news spine (THE LATEST · Gaza · West Bank · Her
  Story · Politics · Economy · Accountability), heavier and brighter,
  reading geography → people → power → money → accountability. Tier 2
  carries the desks and standing features, smaller and muted, with the
  gold specials clustered and the search/tip utilities anchored
  inline-end. Each row is a single horizontally scrollable strip at every
  width with an RTL-aware edge-fade cue — never wrapped, never clipped.
  New sections join the tier lists in `render_page` deliberately — never
  appended to the pile; anything not in a tier list still renders at the
  end of tier 2 (nothing silently vanishes).
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
- **No dead ends**: every secondary page leads back into the paper. Section
  pages append a "More from Times of Palestine" band (newest 8 stories from
  other sections); the search page renders section-browse chips
  (`.browse`). A new page type must offer an equivalent way onward.
- **No dead space**: a failed image must never leave a void. Remote images
  are verified at build time (`remote_image_ok`), swapped to the category
  cover on error AND when a hotlink wall serves a tiny placeholder that
  "loads" (`naturalWidth<200` guard in `lede_fallback_attrs`), and the
  hero's base is dark (`#141419`) so its white overlay headline stays
  readable even if every fallback fails. Any new large image surface must
  carry the same three layers.
- **Reading measure**: story body text (`.story .summary`) caps at 42.5rem
  (~75 characters per line); headlines and lede media keep the full column.
- **CTAs**: gold, weight 700, arrow glyph — `→` in EN, `←` in AR. Never a
  button-styled link inside a card; the specials band CTA (bordered pill) is
  the one standing exception.
- **Live-TV pill** (`.livefab` + `.livedock`): a fixed, compact pulsing red
  pill (bottom inline-start, RTL-aware) on editions with a configured stream
  (`LIVE_TV` in `build.py`; Arabic carries Al Jazeera's live broadcast).
  It carries a small ✕ that hides it for the browsing session
  (sessionStorage) so it never squats over content against the reader's
  will. Tapping the pill docks a corner mini-player — youtube-nocookie
  iframe created only on tap, closable, pill returns on close — so during
  major breaking news the reader watches instantly from any page while
  continuing to read. Enable another edition by filling its stream id;
  never autoload the iframe.
- **Listen button** (`.listenbtn`, story pages): house pill under the
  timestamps that reads the story aloud via the Web Speech API — device
  voices only, no third-party audio service, both languages. States:
  Listen → Pause → Resume, labels from `data-*`. Hidden until JS confirms
  support; text chunks ≤220 chars to dodge long-utterance stalls. If a
  richer narration pipeline ever lands (recorded/neural audio), it replaces
  the engine behind this same button, not the button.
- **Image crops keep faces.** Every cover-cropped slot biases toward the
  upper third (`object-position:50% 22%`; story ledes 18%) because news
  photography puts faces above center. Remote wire images additionally get
  orientation handling via `lede_fallback_attrs`: an `onload` check tags
  portrait images (Telegram video posters, Wikimedia head-shots) with
  `.portrait` — small card slots crop them at `50% 15%`, while the BIG
  16/9 surfaces (story lede, hero) switch to `object-fit:contain` on the
  house-black backdrop, because no crop position can fit a face into the
  band a wide slot cuts from a tall photo. Curated local photos (specials)
  use a hand-set `focus` per asset instead. If you add a new surface that
  cover-crops reader photos, wire it through the same helpers — never ship
  a dead-center crop.

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

- ~~**Same-cover repetition**~~ — resolved 2026-08-02: every category cover
  now has a mirrored `-b` variant (`times-of-palestine-cover-<cat>-b.svg`,
  chevrons from the inline-end edge, text block start-aligned at x≥130 —
  inside the 16/10 slot's side-crop safe zone). The build alternates A/B
  per category across originals and wire backfill, so adjacent photoless
  stories read as a designed pair. New categories must ship BOTH variants.
- **EN-dominant hero graphics on the AR edition** (§5) — retrofit as each
  graphic is next regenerated.
- Election hemicycle SVG (`times-of-palestine-israel-votes-card.svg`) bakes
  in the current bloc math — update it same-day when polls shift, together
  with the standings graphic (election beat: Claude).
