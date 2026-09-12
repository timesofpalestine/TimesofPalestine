# Full site review — 2026-09-12 (owner-requested)

Owner's order: "do a full review of the website and fix any issues that need
to be fixed — content, layout, shape, colour scheme, spacing, user
experience, leave no stone unturned."

Scope and method: both editions, every page type (front, story, section,
topic hub, search, About, 404), at 320, 390, 1024 and 1440 px, in light and
dark. Feeds are egress-blocked from the review sandbox (the proxy returns
403 to every outside host), so the wire was rebuilt from the last 150 hours
of `story-archive/` — 2,621 real stories with their real headlines, deks,
images and briefs — and the site was built, served locally and measured in
Chromium: geometry and overflow per element, WCAG contrast on every text
pair actually rendered, tap-target heights, heading order, duplicate ids,
broken local links and missing alt text. Companion audits:
`site-evaluation-2026-08-07.md`, `site-review-2026-08-10.md`,
`site-review-2026-09-03.md`.

## Verdict

The paper reads like a paper. The 4 September flow holds in both editions,
the section accents are working, RTL is genuinely first-class, and the
structural nets (no horizontal scroll at any width, no duplicate ids, no
broken local asset references, every image with alt text) came back clean
on the first pass. What the measurement found was a layer of small
regressions that a screenshot pass would not catch — one of which had cost
a whole English edition of a story — plus two platform items nobody had
looked at since the pages they refer to were deleted.

## Fixed in this review (branch `claude/website-full-review-vsd29c`)

Every item below is pinned by `tests/test_site_review_2026_09_12.py`.

### Editorial machinery

1. **The refusal screen was eating ordinary prose.** The Gaza night-workers
   report contained the sentence "…leaving bakeries unable to produce what
   is needed" — plain third-person reporting. `REFUSAL_RX` matched "unable
   to produce", the validator skipped the file as unsafe rendered markup,
   and the story published **Arabic-only**, against the first-class-editions
   rule; the build had been warning about it every ten minutes. The net now
   matches only the refusal *shape*: the phrase opening the copy or a
   sentence, or in the first person ("I'm unable to produce…"). The flagged
   sentence is also rewritten so the file reads cleanly either way.
2. **Three more section leaks** (each a new test case, never a wider rule,
   per the 6 September order):
   - a PNN reporter called **Rasha** put a Gaza gardener into Health &
     Healing — `rash` matched inside her name. Now `\brash(?:es)\b`.
   - **agriculture** put Gaza's chambers of commerce into Culture & Arts —
     `culture` matched inside the word. Now `\bculture`.
   - a Gaza school named **Kafr Qasim** put a Gaza innovation prize into
     Palestinians in Israel. A Green Line town named only in the summary no
     longer moves a story whose headline is set in Gaza or the West Bank;
     a headline that names the community or the Arab lists still routes as
     before.
   The archive follows the rules, so `refile_archived` moves the already-
   published copies into the sections that now claim them.
3. **Arabic house spellings** the build had been flagging every run:
   «تالي غوتليف» and «نوعام سولبرغ», corrected in five originals.
4. **The US Press artwork still carried the retired tagline.** The owner
   replaced "what Washington is reading" on 4 September; the franchise
   cover had not been redrawn. It now reads "the American front pages, read
   from Palestine" / «الصفحات الأولى الأميركية، مقروءة من فلسطين», at type
   sizes the overflow checker passes.
5. **One Arabic label for Economy & Aid.** The nav group said
   «الاقتصاد والإسناد» — the Arab Support section's own word — while the
   section head said «الاقتصاد والإغاثة». The section head's wording wins
   everywhere.
6. **Deks end on a sentence.** Feed summaries, Telegram post text, brief
   openings, original ledes and every card and row dek now cut at the last
   sentence end that fits (`truncate_dek`), instead of trailing off
   mid-phrase — "…in remarks carried by…" was the shape on the front page.
   Figure-tile captions keep whole clauses (`truncate_clause`).
7. **On This Day had a fortnight's hole.** Three settled dates added in both
   languages: Bashir Gemayel and the entry into West Beirut (14 September
   1982), the end of Sabra and Shatila (18 September 1982), the Cairo
   Agreement that closed Black September (27 September 1970).

### Layout, colour and spacing

8. **Split hero cropped its own infographic.** `object-fit:cover` on the
   art half was cutting the first digits off the WHO evacuation board.
   SVG art in that slot is now contained on the house black.
9. **A white void inside every lead card.** With six or seven headline rows
   beside it, the lead card's 16/9 art left about 150 px of empty card under
   the dek. The art now grows to fill whatever height the list needs, 16/9
   as the floor. The English front lost 950 px of dead space.
10. **The featured report's row was set by its photo.** A portrait og:image
    inflated the whole Research & Investigations plate; the photo now fills
    the height the body copy defines.
11. **Two-story sections were two 600 px cards** — and when neither story
    had a photo, the same category cover stood twice side by side (Israeli
    Press, US Press, Accountability all showed it). Two stories now run as
    two rows.
12. **Opinion left an empty third column** whenever only two comment pieces
    were live. The band now fits its columns to what it has.
13. **The story rail's letter tiles were unreadable.** `.rr-thumb.tile`
    never got the tile skin, so the initial rendered in page ink on the
    mid-dark section accent — 2.0:1 on Gaza crimson, 2.0:1 on
    accountability brown, 3.0:1 on Arab Support teal — and uncentred.
14. **Dark mode, two failures:** the story byline's flag green measured
    3.2:1 on the charcoal paper, and on the About page the Telegram
    *button* was being repainted green on red (2.4:1) because the dark
    green rule out-specified the button's white.
15. **The Aa lite toggle was invisible in light mode** on every story,
    section, topic and search page: it inherits colour, and the black
    backbar sets none, so it painted page-ink on black.
16. **Touch targets only applied to narrow screens.** A tablet at 1024 px
    got 22 px chrome controls. The house 44 px now keys off a touch
    pointer at any width, breadcrumbs included.
17. **The election card's gradient had replaced its background colour**, so
    its ivory type had no guaranteed ground under it.

### Platform

18. **The bare domain contradicted the rest of the site.** `/index.html` —
    where a shared link to the domain lands — declared its canonical and
    all three hreflang alternates on the apex host while every other page,
    the sitemaps, the feeds and the JSON-LD canonicalise to `www`. Two
    hostnames for the same pages split the ranking signals; the stub now
    builds from `BASE_URL`.
19. **The service worker still precached the deleted status pages.**
    `/en/status.html` and `/ar/status.html` went with the owner's order of
    4 September; the install kept requesting them (swallowing the 404s).
    The search pages take those two shell slots — the page a reader
    actually wants when the network is gone.
20. **Story pages jumped h1 → h3.** The rail's section labels were
    paragraphs; they are headings now, visually identical.

## Measured clean

- Zero horizontal overflow at 320, 390, 1024 and 1440 px, both editions,
  both themes — the 320 px column is new to this review.
- No duplicate element ids, no broken local links, no image without alt
  text across every generated page type (124 pages sampled, including 60
  story pages).
- Heading order clean everywhere after item 20.
- Every other text pair rendered on the site meets AA at its size, light
  and dark.

## Needs the owner or the desks (not changed here)

- **Six sections were stale at review time** (en: accountability, humans,
  israelipress, pal48, uspress, women; ar: accountability, economy, humans,
  israelipress, uspress, women), and the outbreak watch has an unanswered
  red signal — acute malnutrition, Gaza City, week 37. Both are the daily
  editor's same-day assignments, and both are downstream of the budget
  governor: September's ledger stands at about $211 of the $300 budget, and
  the discretionary desks pace against what is left. No agent invents
  coverage to clear a stale line, and a Health & Healing response piece
  needs live sourcing this sandbox cannot reach.
- **The prisoners ledger is 26 days old** (Addameer, 17 August). It is
  refreshed by hand from Addameer's periodic publications; the site is
  egress-blocked, so the next daily editor run with network should re-read
  `addameer.org/statistics`. The markets fallback is current (Al-Quds close
  700.82, Thursday 10 September; PEX does not trade Friday or Saturday).
- **The photo-conversion queue has not moved since 8 August** — sixteen
  reports still lead on chart or timeline covers against the
  covers-are-photographs order, and this review added
  `palestinian-ngos-designation` (no `image:` header at all) to Priority B.
  Sourcing rights-cleared frames needs Commons access.
- **Arabic-edition hero art is still English-first** for infographic ledes;
  the `-ar.svg` twins for the desk's infographics remain outstanding from
  the 7 August audit.
