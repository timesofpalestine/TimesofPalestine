# Editorial calendar — dated assignments (owner-approved 2026-08-06)

The daily editor cycle reads this file EVERY morning, right after the
breaking sweep: any assignment whose window includes today and is not yet
✅ becomes a same-day assignment (both languages, charter rules). When an
assignment ships, mark it ✅ with the slug and date in the same PR. Add new
dated windows here as beats develop — this file is the single place dated
coverage lives, per editorial/content-audit-2026-08-06.md (rec. E).
Queue-fed topics stay in topics.json; this file is only for work that must
land in a specific window.

## Windows

- **Now → Sep 30 — Sports buildout (audit rec. F).** Target: at least four
  sports originals live by end of September. Two are queued in topics.json
  (`palestinian-football`, `athletes-and-travel`); the daily editor adds at
  least two more from: Gaza's athletes a year into the ceasefire, the West
  Bank Premier League season under closure, a diaspora player profile
  (celebratory register per the features order).
  - ✅ 1 of 4 — `west-bank-league-returns-2026.*` (2026-08-07): the PFA
    restarts league play in September after three suspended seasons, the
    Thousand Martyrs Cup format, OCHA closure numbers, the national-team
    pipeline. Still owed by Sep 30: three more, and a September follow-up
    once the cup draw and fixture list are published.
- **Aug 25 – Sep 1 — Third-lost-school-year package.** The queued
  `education-under-fire` topic should have published by ~Aug 13 via the
  desk; in this window verify it is live, current, and cross-linked with
  the scholarship guide, and file a school-year-start news update pegged to
  September 1 (UNICEF/PCHR numbers re-verified at writing).
- **Sep 15 – Sep 30 — Recognition, one year on (UNGA week).** The audit's
  rec. E audit piece: what recognition by the UK, France, Canada and the
  rest changed in law, trade and embassies — promised vs delivered,
  constructive framing, every claim dated and attributed. Suggested slug
  `originals/recognition-one-year-audit-2026.*`.
- **Oct 5 – Oct 12 — Ceasefire day-365 report.** The definitive one-year
  accounting, spine = the reconstruction-money tracker
  (`gaza-reconstruction-money`, plus its monthly refreshes below).
- **Oct 1 – Nov 15 — Olive harvest window.** Promote the queued
  `olive-harvest` topic when the window opens; pair the economy reporting
  with the displacement-ledger's settler-violence record.
- **Oct 13 – Oct 28 — Israeli election final stretch.** Daily tempo on the
  existing watch: polls attributed to pollster/outlet, coalition math,
  Palestinian stakes; results-night package Oct 27–28.
- **Nov 1 – Nov 29 — Palestinian election countdown.** Weekly tracker
  editions off the elections-desk launch (`palestinian-elections`), daily
  in the final week; results coverage Nov 28–29 in both languages.
- **Aug 2027 — TOP 100 next edition.** Full fresh research sweep per the
  charter; never recycle blurbs. (2026 edition is live.)

## Monthly fixtures (first week of each month)

- **Displacement ledger refresh** (`west-bank-displacement-ledger` after
  its launch): new OCHA/OHCHR month numbers, villages added by name.
  Launched 2026-08-08 as `west-bank-displacement-ledger-2026-08-08-05.*`;
  first monthly refresh due in the first week of September.
- **Reconstruction-money tracker refresh** (`gaza-reconstruction-money`
  after its launch): pledges vs transfers vs rubble, dashboard updated.

## Standing cadence targets (audit recs. F–G)

- **Real Lives:** at least one humans original per week.
  - ✅ week of Aug 3–9 — `nasrallah-neustadt-laureate-2026.*` (2026-08-08):
    Ibrahim Nasrallah, the Wehdat camp and the Neustadt Prize.
  - ✅ week of Aug 10–16 — `lahore-gaza-dentistry-graduates-2026.*`
    (2026-08-10): the 51 al-Azhar dentistry students who finished their
    degrees at the University of Lahore under the G-HOPE scholarships.
- **Arabic-first commissioning:** 2–3 originals per month reported for the
  Arabic reader first (Arab Support and Her Story are the natural homes),
  then rendered into English.
  - ✅ 1 of 3 for August — `turkey-indonesia-palestinian-student-funds-2026.*`
    (2026-08-08): the YTB–Baykar and BAZNAS scholarship funds, written in
    Arabic first and then into English.
- **Her Story pipeline:** keep at least one women-section topic in the
  active queue at all times (two added 2026-08-06).

## Standing services kept current

- **Scholarship guide** (`palestine-scholarships-guide-2026.*`): last swept
  2026-08-10 — added Pakistan's G-HOPE / Alkhidmat medical pathway (288
  Gaza students enrolled, 51 dentistry graduates in July 2026) to both
  editions. Next sweep: retire passed windows and check the Türkiye
  Bursları and Chevening openings when the autumn cycles publish.

## Production backlogs (worked down by the daily editor cycle)

- ✅ **Photoless originals — cleared 2026-08-09.** All 17 originals that
  carried no `image:` header now have an explicit lede visual (subject art
  where the house library had a match: the lobby ledger for
  `joe-kent-israel-debate-2026`, the spectrum board for
  `palestinian-4g-rollout-2027-gaza-2g`, the listed-companies board for
  `who-profits-palestinian-economy-2026-07-30-05`, the scholarship map for
  `turkey-indonesia-palestinian-student-funds-2026`; branded category
  covers elsewhere). `build.py` now reports zero "no image: header"
  warnings — keep it there: any new original ships with its own `image:`.
  These stopgap SVG covers stay in the photo-conversion queue below.
- **Photo conversion (open).** The charter's covers-are-photographs rule
  (owner order 2026-08-03) still wants rights-cleared photographs on the
  stories now carrying house SVGs. Convert opportunistically, always with a
  `media-rights.json` entry.
- **Paragraph pacing (open).** The build flags 152 paragraphs over ~70
  words across the older originals. The renderer already splits them at
  sentence boundaries for the reader, so this is a copy-desk backlog, not a
  reader-facing fault — work a few files down per cycle, newest first.

## Blocked on the owner

- **From the Archive weekly fixture (Sundays):** ready to launch the first
  time the owner supplies Palestine Times source scans (charter: only the
  owner supplies archive material). Until then this stays dormant — do not
  scrape substitutes.
