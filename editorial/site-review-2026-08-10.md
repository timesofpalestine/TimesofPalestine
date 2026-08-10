# External website review 2026-08-10 — newsroom response

The owner forwarded an outside review of www.timesofpalestine.com (homepage,
category page, article page, About page — desktop and mobile, prepared
2026-08-10). This file maps every item in its prioritized backlog to what the
codebase actually does, what shipped in response (PR branch
`claude/times-palestine-review-gb5qq9`), and what needs an owner decision.
Companion audit: `site-evaluation-2026-08-07.md` (in-house, overlapping
findings, several already actioned).

Overall: the review's diagnosis — "the site asks the reader to do the
editor's job" — is worth keeping in mind, but a good share of its specific
findings were already resolved in code before 2026-08-10 (dark-mode toggle,
quick search, sticky section nav with the All-Sections index, methodology
tooltips, open-data downloads, hreflang/NewsArticle/Dataset structured data,
ownership & funding disclosure on the About page). The reviewer likely saw an
older deploy or missed chrome controls. The genuinely open items are handled
below.

## Quick wins (review items 1–9)

1. **Logo/wordmark** — NOT CHANGED. The frameless stacked wordmark is the
   owner-ordered masthead register (owner orders 2026-08-06, design-system
   §3); the red cover frame is the brand-art device on og-banner and app
   icons, which cover tabs/shares/screenshots. A drawn logo mark is a brand
   decision for the owner, not an agent — route via issue #6 if wanted.
2. **Emoji icons (🌐 🔒)** — NOT CHANGED. The 🌐 glyph on the language
   toggle is a documented house convention (design-system §3). Swapping to a
   custom icon set is a design-direction change → issue #6 for the owner.
3. **Most read / trending module** — BLOCKED on analytics. The site ships
   no tracking; a privacy-first counter hook exists (`ANALYTICS_GOATCOUNTER`
   env var, one script tag) but the owner has not chosen a provider
   (also 2026-08-07 audit D2). Without it, any "most read" list would be
   fabricated. Owner decision needed.
4. **Condensed live-stats strip near the top** — ✅ SHIPPED. `.gi-strip`
   (`gaza_panel.strip()`): Gaza killed/wounded + prisoners held at the very
   top of the front page, live-updating on the ledger's existing 5-minute
   poll, linking down to the full `#numbers` ledger. Casualty restraint
   rules apply (no pulsing, no motion).
5. **Inline methodology next to the dashboard** — ✅ SHIPPED. `.gi-method`,
   a collapsed "How these figures are compiled" note under the ledger head:
   per-row sources, refresh cadence, what `+` and `?` mean, downloads.
   (Per-term legal tooltips and the open-data line already existed.)
6. **Funding/ownership disclosure + masthead page** — ALREADY DONE before
   this review: the About page carries an "Ownership & funding" section
   (privately owned and funded by the publisher, no advertising, no
   government/party/faction money) and "An automated newsroom, under
   binding rules" describing how the newsroom works; `org_jsonld` points
   `ownershipFundingInfo`/`publishingPrinciples` at it. A named human
   masthead is an owner privacy decision — not for an agent to publish.
7. **Author/desk bio blurbs on bylines** — ✅ SHIPPED. EN byline corrected
   to "By the Times of Palestine Newsdesk" (AR already correct; 2026-08-07
   audit item C7), plus a one-line `.desk-note` under every Newsdesk byline
   linking to the About page's how-our-journalism-is-made section.
8. **Newsletter signup** — BLOCKED on provider. The build already renders a
   footer link when `NEWSLETTER_URL` is set (owner decision on
   Buttondown/Listmonk/etc. pending — 2026-08-07 audit D1). No form is
   faked in the meantime; RSS/JSON feeds and the Telegram channel are the
   live follow paths and are linked in the footer.
9. **Positioning one-liner near the masthead** — ✅ SHIPPED. `.tagline`
   under the front-page wordmark, bilingual, from the string tables.

## Medium effort (10–17)

10. **Sticky section nav / jump menu** — ALREADY DONE. `nav.sections` is a
    sticky band with direct flagship links and the full-width All-Sections
    index; on phones it is one swipeable tap-height row.
11. **Dashboard higher in scroll order** — ADDRESSED via item 4's strip.
    The full ledger already sits directly after the hero zone + specials
    band (position ~4 of ~20). Re-sequencing it above the specials band is
    an editorial-hierarchy call the owner can make; the "page is alive"
    principle keeps live news at the very top.
12. **Visual differentiation between homepage sections** — OPEN, queued for
    the daily editor cycle. Existing differentiation (dark bands for
    research/specials, light sections, focus heads) is real but subtle at
    17+ sections; any new treatment must go through design-system.md.
13. **Pull quotes / callout stats / in-article hierarchy** — ALREADY DONE:
    `blockquote.pull` (gold-rule serif pull quotes with attribution line),
    `##` subheads with the story-guide outline, pacing reflow at ~70 words.
14. **"How we protect sources" explainer** — PARTIAL. The tip band and
    About contact section carry the safety guidance (personal device,
    share nothing identifying, Signal over Telegram for sensitive
    material). A standalone page overstating guarantees would be a safety
    risk; expanding the About section is the right vehicle if the owner
    wants more.
15. **WCAG audit** — OPEN standing item. Much is in place (skiplink,
    aria-expanded nav, focusable tooltips with aria-labels, ticker pause
    control, 44px touch targets, tabular numerals, reduced-motion guards);
    a formal contrast + keyboard pass belongs on the daily-editor queue.
16. **Lighthouse/PageSpeed** — OPEN standing item. Note the 2026-08-07
    audit already killed the 25 MB video re-upload; fonts are self-hosted,
    images lazy/async, CSS is one file.
17. **Structured data** — ALREADY DONE for NewsArticle + BreadcrumbList +
    Dataset + hreflang + news-sitemap; ✅ SHIPPED now: homepage ItemList
    JSON-LD of the top stories (also 2026-08-07 audit P2-12).

## Bigger projects (18–22)

18. **Editorial-tier homepage IA** — owner decision; the current spine
    (breaking/hero → specials → data → sections by priority order) is the
    charter's order. A tiered regrouping proposal can go to issue #6.
19. **Photojournalism pipeline** — ALREADY THE STANDING POLICY (covers are
    photographs, owner order 2026-08-03; photo-conversion queue in
    design-system §7; wire og:image fetch + person-photo backfill +
    `image-overrides.json`). The sampled article with an SVG cover is the
    documented stopgap for stories without a rights-cleared photo yet.
20. **Reader-support/donation flow** — owner decision (`SUPPORT_URL` hook
    already renders a footer link when set). The About page states the
    publisher funds the newsroom; if that stays the model, saying so is
    honest and sufficient.
21. **Light theme** — ALREADY DONE. Light is the default (`--paper` warm
    off-white); the 🌙 toggle cycles auto → dark → light and persists.
22. **Comments policy** — ✅ SHIPPED. The About page now states the
    no-comments policy and why, in both languages, with the channels that
    replace it.

## Verification

`python3 build.py` clean; `python3 -m unittest discover -s tests` green;
EN/AR desktop, ~420px mobile and dark-mode screenshots of the new strip,
methodology note, tagline and desk note reviewed per design-system §6.
