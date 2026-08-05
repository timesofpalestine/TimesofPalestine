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
| `--green-deep` | `#00602F` | Small-text green (source chips) — extra AA contrast margin on paper |
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
them. The flag palette stays true in light mode. Dark mode (design pass
2026-08-06) is charcoal-slate, not near-black: `--paper:#121417`,
`--card:#1a1d22`, `--ink:#e8eaed`, `--muted:#a3a8b2`, `--line:#2a2e35`,
`--line-dark:#3f454e`, and `--red` lifts/warms to `#d43049` on dark
surfaces (small red text may lift further to `#f93549` for contrast). Every new surface must be checked in both schemes — if you
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

- Max content width `--max:1300px`; corner radius `--r:3px` (the house is
  square-ish — do not introduce big rounded corners); shadows `--sh`
  (rest) / `--sh-h` (hover); transitions `--tr:.18s ease`.
- Hover idiom for cards: `translateY(-2px)` + `--sh-h`.
- Existing keyframes — reuse, don't duplicate: `pulse` (latest-rail dot),
  `newpulse` (NEW mark, countdown chip dot), `tick`/`tick-rtl` (ticker).

## 3. Component grammar

- **Section nav** (`nav.sections`, grouped design — owner order 2026-08-05,
  after the two-tier bar reached ~19 visible links; line-tab language of
  #117 + #118 kept): ONE sticky black band. Inline order: THE LATEST (red),
  four dropdown groups — News & Regions / «الأخبار والمناطق», In-Depth /
  «في العمق», Society & Culture / «المجتمع والثقافة», Economy & Aid /
  «الاقتصاد والإسناد» — then the gold `nav_primary` specials as top-level
  links, then the search/tip utilities anchored inline-end. Group buttons
  (`.nav-gbtn`) are uppercase line-tabs with the 2px red indicator — no
  pills, no boxes; panels (`.nav-drop`) are solid `--black` with a 2px red
  top rule, section links stacked. Panels open on hover/focus-within on
  pointer devices and on tap everywhere; the button carries
  `aria-expanded` + `aria-controls`, opening one group closes the others,
  and Escape or an outside click closes all. Non-primary gold specials
  ride at the end of the In-Depth panel. New sections join the group
  lists in `render_page` deliberately; anything not in a group still
  renders at the end of News & Regions (nothing silently vanishes).
  **On phones (≤740px)** the same bar wraps to tap-height rows (~44px)
  and panels become full-width sheets under the bar (`.nav-group` loses
  its anchor so the sticky nav positions them); the masthead slims.
- **Card** (`.card`, `.rowcard`, `.fr-card`): image on top (16:9 in
  standard story cards, 16/6 default in franchise cards), then kicker →
  serif title → optional CTA. The card kicker is the SECTION tag
  (`card_kicker`), not a source chip — rewritten wire is our copy, so the
  masthead name repeated on every card said nothing; the story page's meta
  line keeps the source per the wire-attribution protocol. Card timestamps
  are a single relative time (`8m ago` / «قبل ٨ دقائق»), with the full
  minute-level stamp in the `title` tooltip and `datetime` attr — story
  pages carry complete published/updated stamps (design pass 2026-08-06).
  Franchise cards are dark (`--black`, gold accents); news cards are light.
- **Section head** (`.sec-head`): serif 900 title with red underline accent
  and a "View all →" link. Sections alternate light; research/investigations
  and specials ride dark bands.
- **Tip band** (`.tipband`): one primary action (the Signal button);
  Telegram is a single quiet inline line (`.alt`) under the sub text, the
  QR sits small (84px) beside the button, and the safety note keeps its
  full-width hairline row (condensed 2026-08-06 — no competing buttons).
- **Palestine by the Numbers cells** (`.gi-cell`): bordered stat cards —
  `--paper` ground on the `--card` block, 1px `--line` border, 6px radius,
  the 3px red inline-start rule kept as the accent (2026-08-06).
- **Breaking ticker**: red band, black BREAKING label, 80s linear loop,
  pauses on hover and keyboard focus, `tick-rtl` mirror for Arabic. The
  seamless-loop duplicate of the track is decorative: it carries
  `aria-hidden="true" tabindex="-1"` so screen readers and the tab order
  see each headline once.
- **Live markers**: the pulsing NEW/جديد mark (<90 min stories); the
  countdown chip (`.fr-card.vote .days`) — dark pill, gold hairline border,
  pulsing gold dot, big mono numeral, recomputed every build. If you build a
  new "alive" element, follow this chip's anatomy.
- **Palestine by the Numbers = live ledger** (`section.gaza-index`,
  `gaza_panel.py`): bordered region cards (`.gi-block`), each a kicker with
  a 4px red bar (`.gi-region`), a big-numeral grid, an optional composition
  strip, and its own attribution + as-of line — GAZA (Ministry of Health
  toll), WEST BANK (UN OCHA killed/children/wounded + settler attacks),
  PRISONERS (Addameer by age and gender: total `+`-suffixed, administrative,
  Gaza-uncharged, women, children — figures live in
  `editorial/prisoners.json`, newsroom-maintained since Addameer has no API;
  the daily editor cycle refreshes it), then the humanitarian indicators.
  Live figures ride `/data/gaza-numbers.json` (prefixes: none/`wb_`/`pr_`;
  per-region `data-gi-asof` stamps); `PANEL_JS` polls every 5 minutes and
  animates revisions in place (`.gi-flash` wash). **Composition strips**
  (`.gi-comp` + `.gi-legend`): a quiet 7px stacked bar showing shares of a
  total — children (gold `#c7a86b`), women (flag red), detention categories
  (slate `#3d4f6b`), remainder neutral `var(--line)`; server-rendered
  widths, `role="img"` with a full sentence aria-label, no animation. The
  section head carries the pulsing `.gi-live` dot only when a live row is
  present.
  Restraint is binding: these are casualty figures, not a scoreboard — no
  count-up from zero, no celebratory motion; the entrance settle starts at
  96.5% of the value and everything stills under `prefers-reduced-motion`.
  Numbers use `tabular-nums`; Arabic gets Arabic-Indic digits in BOTH the
  server render and every JS rewrite. All layers fail open: an unreachable
  source omits its row, never a broken panel. GazaIndex's wider humanitarian
  indicators remain as the second row with their own attribution line.
  **Methodology tooltips** (`.gi-help` + `.gi-tip`): figures whose terms
  carry legal/statistical weight (administrative detention, the Unlawful
  Combatants Law, starvation deaths, settler-attack counting) get a 15px
  focusable "?" beside the label — tooltip on hover AND focus, note text
  duplicated as the marker's `aria-label` so screen readers hear it without
  the tooltip; notes live in `gaza_panel.TERM_NOTES`, bilingual, each naming
  its defining body. **Open data line** (`.gi-dl`): the ledger closes with
  download links to its own `/data/gaza-numbers.json` and `.csv` (CSV:
  region/key/bilingual labels/value/as-of/source per row, written by
  `payload_csv` beside the JSON every build) plus a cite-the-primary-sources
  note — the ledger is a research surface, readers may take the data.
- **Latest rail = live wire** (`aside.latest`, also the story-page "keep"
  rail): entries sit on a vertical timeline rule with a marker dot per item —
  hollow/muted at rest, red and `pulse`-ing while the story is fresh
  (`li.fresh`, <90 min), filling red + scaling on hover. Each entry is a flex
  row: `.lt-body` (inline timestamp + TOP badge, serif title, source) with an
  optional 52px square `.lt-thumb` inline-end that removes itself on image
  error. Entries stagger in with `railin` (60ms steps, `backwards` fill;
  disabled under reduced motion). Uses only logical properties — the timeline
  mirrors in RTL for free. Relative timestamps across ALL pages are kept
  ticking client-side by `_CLOCK_JS` (30s interval): it rewrites only the
  relative half of each `<time>` (mirroring `time_ago`/`ar_count` exactly,
  both languages), and retires NEW marks and fresh dots once a story crosses
  the 90-minute line. Never let a server-rendered relative time go stale in a
  new component — reuse the `<time datetime>` + `_CLOCK_JS` contract.
- **Share surfaces**: the inline `.share` row under the story body is the
  universal control; on ≥1200px viewports a floating `.share-rail` of round
  compact buttons rides fixed in the story gutter (`inset-inline-start`
  computed from the 820px column, so it mirrors to the right gutter in RTL).
  Both use the same four targets (X, Facebook, WhatsApp, Telegram); never add
  a network to one without the other.
- **Directional arrows are language-scoped**: forward is `→` in English and
  `←` in Arabic — in RTL the arrow points the way the reading flows. Arrows
  live in the per-language string tables; a hardcoded arrow in a shared
  template must be written `{"←" if lang == "ar" else "→"}`. The language
  toggle carries the 🌐 glyph everywhere it appears (nav utilities, topbar,
  backbars).
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
  carry the same three layers. The ENTIRE category-cover family ships in
  every build (furniture copy in `main()`) — onerror fallbacks reference
  covers from attribute strings `copy_media` cannot see, so a
  reference-walked subset would 404 in the reader's browser.
- **Solo section band** (`.rowcard.solo`): when a front-page section holds
  exactly one story, it renders full-width with the featured treatment —
  art at `clamp(220px,30vw,320px)`, 1.4rem serif headline, and a dek
  excerpt — never an orphan card floating in an empty strip.
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
- **Standalone service pages** (static features with reader-facing UI —
  `/sanad/` is the model): a self-contained single file, everything inline,
  no external fetches, deliberately NOT on the house tokens — the page must
  survive with the network gone, and its design budget is spent on that.
  Requirements that DO bind: bilingual EN/AR with `dir` switching, the
  Times of Palestine masthead link home, and a SPECIALS row entry so the
  service is reachable from the front page, nav and ticker. Sanad
  (`sanad/index.html`, owner directive 2026-08-04) is the health-sector
  teleconsult board: append-only event packets, four carriers (net, pasted
  text, share-sheet, BLE bridge), stale-while-revalidate `sw.js`. Its
  launch report is `originals/sanad-teleconsult-board-2026.*`; changes to
  the board route through Claude's health beat.
  **Status:** UNPUBLISHED (owner decision 2026-08-04 evening) — all
  reader-facing Sanad surfaces (band, nav, specials card, /sanad/ page)
  are removed pending redeployment; the `nav_primary` SPECIALS mechanism
  remains available for whatever earns tier-1 prominence next.
- **Reader chrome preferences** (`_THEME_JS`, applied from `<head>` on every
  template): theme (`#themetoggle`, `data-theme` on `<html>`, localStorage
  `top-theme`) and **text-only mode** (`#litetoggle` "Aa", `data-lite`,
  localStorage `top-lite`) ride together on every chrome bar — the topbar
  and every backbar. Lite mode is for unstable connections (much of the
  readership): `[data-lite]` CSS hides all imagery, embeds, the live dock
  and the QR box; because the preference is applied before the body parses,
  below-the-fold `loading="lazy"` images are never requested. The active
  toggle shows green with a green border (`aria-pressed` kept in sync). Any
  new image-bearing surface must add itself to the `[data-lite]` hide list
  in `build.py` — a surface that still downloads imagery in lite mode is a
  bug against the mode's promise.

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
- **Covers are photographs (owner order 2026-08-03)**: story covers must be
  photos; infographics live in-body. Converted so far: al-Sharaa (portrait),
  ICC/ICJ (Netanyahu portrait), Abbas succession (portrait), Saifedean
  (portrait), Dahlan backchannel (post screenshot), Washington Brief
  (Capitol). Still on graph covers pending sourced photos — the daily cycle
  converts as rights-cleared images are found: ceasefire ledger, Her Story
  launch, Mladenov, PA litigation/absence/security-chiefs, Ceuta, Chile,
  Citizen Lab, East Asia, France, Madrid, Graham, Israel lobby, Thawadi,
  arab-support ledger, embassies, business/top-companies, health-desk
  reports, bitcoin-desk reports (ChatGPT's layer — flagged, not touched).
- Election hemicycle SVG (`times-of-palestine-israel-votes-card.svg`) bakes
  in the current bloc math — update it same-day when polls shift, together
  with the standings graphic (election beat: Claude).
