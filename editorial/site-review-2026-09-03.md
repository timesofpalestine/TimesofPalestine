# Full site review — 2026-09-03 (owner-requested)

Scope: content, colour, layout, topics and platform, both editions. Method:
local render of the full originals corpus (feeds are egress-blocked from
the review sandbox, so the wire layer was the fixture set), Playwright
screenshots of the fronts, story, section, topic, search, About and
corrections pages at desktop, phone (390px) and dark scheme, geometry and
overflow measurement in the browser, a contrast pass over the palette
pairs used for small text, the section-freshness ledger, the budget
governor's status line, and a read of the recent originals in both
languages. Companion audits: `site-evaluation-2026-08-07.md`,
`site-review-2026-08-10.md`.

## Verdict

The bones still hold: the chrome reads as a newspaper in both editions,
story pages are clean, dark mode and RTL are first-class, the recent copy
(Ketziot indictment, the West Bank fire crews, the Morocco field hospital)
is at the house standard in English and in native Arabic. The defects were
concentrated in machinery that had drifted since the 1-2 September design
pass, and in reference data nobody was refreshing.

## Fixed in this review (PR branch `claude/website-full-review-vi22sv`)

1. **Cards rendered near-square, covers letterboxed.** The `width="640"
   height="360"` attributes added to card art for CLS were winning over
   `aspect-ratio:16/9`, so every card image was a fixed 360px tall (taller
   than wide at four columns) and the solo section row's art ran 320×360.
   Fix: `height:auto` on card, row and hero images; the attributes stay as
   layout hints. Design-system §2 records the rule; a test pins it.
2. **Horizontal scroll on phones (EN front).** The solo row's
   `clamp(220px…)` art beside its headline overflowed a 390px viewport.
   The row now stacks under 560px.
3. **The TOP 100 and the Scholarship Map had fallen off the site.** The
   originals cap (200, newest first) dropped the two oldest live originals
   the day the corpus reached 200 — and with them their specials cards,
   nav links and ticker entries. Pinned originals (standing pages,
   SPECIALS-required reports, the election tracker) now ride outside the
   cap.
4. **The Dima Barakat campaign pin had expired.** The file carried no
   `maxAgeHours`, so the 336-hour default retired it on 2 September and the
   campaign card left the front, the nav and the ticker — against the
   owner's order that no agent removes the pin. The file is now pinned for
   a year; the pin comes down only by the owner's word.
5. **No top story on a quiet stretch.** `render_page` left the hero empty
   whenever nothing qualified inside 18 hours (the desks had not filed for
   25 hours). A last-resort fallback now takes the freshest hard-news
   Palestine story with art; features and standing pages still never lead.
6. **The election tracker was three weeks stale and off the front.** Its
   336-hour shelf life had expired on 25 August, taking the vote card with
   it. Refreshed with the late-August polls (Kan/Kantar 30 Aug, Haaretz 26
   Aug, Maariv-Lazar 19-20 Aug) and the Smotrich-Feiglin technical bloc of
   1 September, in both languages, newest reading first; marked `standing`
   with a shelf life past election night. The running-file pattern now
   matches "Likud", "Yashar" and "Eisenkot" so the EN hub ships alongside
   the AR one.
7. **Prisoners ledger twenty weeks old.** `editorial/prisoners.json` was
   dated 14 April; Addameer's 17 August figures (9,400 held, 3,198 without
   charge, 1,358 Gaza detainees as "unlawful combatants", 92 women, 370
   children) replace it.
8. **On This Day was empty most days.** September had four dates, October
   two. Fourteen settled dates added (both languages), Khartoum 1967 to
   Madrid 1991.
9. **Reader-facing copy that contradicted owner decisions.** The Field
   Reports note promised human approval before publication (the gate
   defaults to publish, review tracking is internal); rewritten. The README
   still described developing-report labels and outlet links; rewritten.
   Section and topic pages advertised `ar_PS` while the rest of the site
   uses `ar_AR`; unified.
10. **Dark-mode small red text under AA.** `--red` (#d43049) on the dark
    paper measures 3.8:1; View-all links, search chips, the story-guide
    title and the NEW mark now lift to `#f93549` like the kickers. The tip
    band's safety line lifts from 4.4:1 to above 4.5:1.

Everything else measured clean: light-mode text pairs 5.5:1 or better,
section accents 4.9:1 or better on white, zero broken local asset
references across every generated page, the validator green.

## Needs the owner (not changed)

- **The budget governor has zeroed every discretionary desk.** The
  wire's projected September cost (about $139) exceeds the $150 budget's
  92% ceiling, so the investigations desk, the daily editor, the
  Washington Brief and the weekly maintenance all skip with a $0 purse —
  which is why nine EN sections and four AR sections were stale at review
  time and no desk had filed for a day. `monthly_budget_usd` is the owner's
  knob; `python3 budget_ledger.py --forecast` shows what each level buys.
  Until it moves, the paper runs on the wire alone.
- **Arabic-edition hero art is English-first** for infographic ledes (the
  split hero shows the English title inside the art beside the Arabic
  headline). Known since the 7 August audit; needs `-ar.svg` twins for the
  desk's infographics.
- **Photo-conversion queue** (`editorial/photo-queue.md`): the sixteen
  chart-cover slugs listed on 8 August are still on chart covers.
