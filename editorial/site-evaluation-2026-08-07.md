# Full site evaluation — 2026-08-07 (owner-requested)

Scope: content, Arabic edition, design/UX, product/growth, platform/SEO,
reliability. Method: full-corpus content audit (all 224 originals), Arabic
line-quality audit (20 files sampled against editorial/arabic-style-guide.md),
local render of both editions with screenshot review (desktop/mobile/dark),
rendered-output inspection (weight, structured data, feeds), and the day's
incident record.

## Verdict in one paragraph

The bones are excellent: headline discipline is 100% clean in both languages,
no body falls below standard, story-page SEO (NewsArticle JSON-LD, hreflang,
breadcrumbs, news-sitemap) is complete, the Arabic edition is genuinely
first-class (A−, with zero banned-diction hits corpus-wide), and the design
system reads like a real newspaper. The weaknesses are concentrated and
fixable: section imbalance (one desk produced 23% of the corpus in 48 hours
while West Bank sat dark for 9 days), standing beats treated as one-shot
launches, a legacy Arabic cohort that reads translated, a visual monotony
problem (identical category covers), zero reader-growth infrastructure
(no newsletter, no analytics, no support path), and a 25 MB self-hosted video
re-uploaded on every 10-minute deploy.

## A. Content (full audit on file, this directory)

Strengths: 81% of corpus inside 7 days; health desk exemplary; headline rules
hold at 100%; zero memo-style bodies; topics.json queue honoured in order.

1. West Bank blackout: section 9 days dark, 2 items ever, while its coverage
   lands in israelipress. 7 westbank topics queued and unwritten.
2. Standing beats freeze after launch: Washington Brief EXPIRED off the live
   site (maxAgeHours 72, no successor); election tracker frozen at 08-02 with
   the vote 11 weeks out while fresh poll coverage lands elsewhere; PA
   litigation docket, ICC/ICJ, scholarship guide, Her Story: no substantive
   edit in 4-5 days.
3. The Palestinian Table missed its first scheduled Friday (queue entry
   researched and waiting).
4. Three permanently empty sections ship on every build: sports (0 items
   ever), opinion (0), archive (0).
5. israelipress overweight: 26 items in 48h = 23% of corpus; it flooded the
   Latest rail (9 of 9 slots at audit time).
6. Long-paragraph tail in the 07-28→08-03 long-form back catalogue (8 deep
   reports with 200-290-word paragraphs) — the renderer reflows them, but
   source pacing should be fixed; four of these are the same frozen launch
   reports as item 2.
7. Investigations desk: 12:03 UTC run died on an API overloaded_error with no
   retry; queue advanced only 2 topics today.
8. image-overrides.json: placeholder cover for pid 287efd3ca4 awaiting a real
   photo since 08-03, tracked nowhere.

## B. Arabic edition (grade A−; full findings in audit output)

Strengths: zero «قام بـ» / «تم»+مصدر / «يُذكر أن» corpus-wide; all 112
headlines 7-12 words; no thin AR bodies (structural parity with EN on every
pair); correct Arabic punctuation throughout; the 08-05→08-07 daily output
meets the house standard, with gaza-clay-house, qalandiya-withdrawal-toll and
feiglin-teen-interview as models.

1. Legacy explainer cohort (≈8 files, 07-30/31: donor-aid, chile-friendship,
   east-asia-projects, madrid-culture-pact, financial-freedom…) reads as
   translated development-report prose: English pseudo-clefts, verbless
   subject-first sentences, 24-40% nominal openings. Needs the Arabic-only
   line edit it never got.
2. Sentence-lockstep with English even in good files: paragraph/subhead
   parity is ~100%, meaning the "Arabic outline first" step isn't happening;
   calques slip through («يهبط على سباق», «وأنفذ ملاحظات الكاتب إقليمية»
   with a gender slip, «الشطران معاً مهمّان» with a dropped antecedent).
3. Grammar slips cluster in calqued sentences (bergman: elided subject makes
   الغزو read as agent; maariv-imec: «إحدى أحدّ» garble; partitive
   superlative «واحدة من أكبر…» where Arabic drops the partitive).
4. Month-pair order unsettled: «تموز/يوليو» 76 vs «يوليو/تموز» 41, ~25 files
   with bare Gregorian-only months; one file mixes both orders.
5. Headline residue in the older cohort: 6 titles with literal passives or
   agentless hedges («أسماء تتبدل وخطط لا تُسحب..», «يتأجل», «تتحول عبئاً»).
6. One-sweep minors: 5 briefing-furniture subheads («أبرز النتائج» etc.);
   6 files in the 08-07 batch mix «» with straight quotes.

## C. Design & UX (from rendered screenshots)

Strengths: strong newspaper identity; clean story pages (share, listen,
breadcrumbs, pull quotes); RTL first-class; specials band works; ceasefire
ledger board is excellent; mobile AR reads natively.

1. Cover monotony: israelipress items all wear the identical category SVG —
   card walls of the same image (Keep Reading showed 4 identical covers).
   The whole section, 26 items, has zero distinct art.
2. Hero eligibility gap: an arts profile took the hero (hero_ok excludes
   social/research/opinion/culture/israelipress but NOT arts); profiles and
   features can squat the top slot on a quiet wire.
3. Breaking ticker carried a music profile as "breaking" — the ticker has no
   category discipline beyond israelipress exclusion.
4. Latest rail can be flooded by one section (9/9 israelipress) — needs a
   per-section cap (e.g. max 3-4 consecutive/total from one section).
5. AR edition hero graphics are English-dominant: house SVGs lead with the
   English title; on the Arabic front page the top image reads in English.
6. Desktop story page: wide unused right margin; a beat-context rail ("More
   on this file", the standing-beat tracker links) would add depth.
7. Byline renders as "BY TOP NEWSDESK" — should read Times of Palestine
   Newsdesk in both languages.

## D. Product & growth

1. No newsletter capture anywhere (0 references in rendered site). For a
   static site: Buttondown/Listmonk form, or "get the daily front page by
   email" built from the existing feed. This is the single biggest
   reader-retention gap.
2. No analytics at all — the newsroom is flying blind on what readers open.
   A privacy-first, cookieless counter (Plausible / GoatCounter, self-hosted
   or EU-hosted) fits the site's stance and is one script tag.
3. No support/donate path for an independent newsroom.
4. Distribution: Telegram delivery healthy (10 groups on the last live run);
   RSS + JSON feeds present both editions. WhatsApp Channel and X automation
   are absent — both are where Palestinian news audiences actually live.
5. PWA manifest exists but no install prompt/offline shell; low priority.

## E. Platform, SEO, reliability

Strengths: hreflang pairs on every story; NewsArticle + BreadcrumbList +
NewsMediaOrganization JSON-LD; news-sitemap.xml; self-hosted fonts; lazy +
async images; 0 missing alt attributes on the home page; search page with
local index; dataset JSON-LD for the Gaza ledger.

1. media/haya-washington-life-school-2026.mp4 is 25 MB — 60% of every deploy
   artifact, re-uploaded every 10 minutes (~3.6 GB/day of artifact traffic).
   Compress to ~720p (~3-4 MB) or move behind a whitelisted embed.
2. Investigations desk has no retry on overloaded_error (see A7) — one 529
   kills the run until the next DESK_HOUR.
3. Homepage JSON-LD could add an ItemList of top stories (rich-result
   eligibility); story OG images fall back to category SVGs — fine, but the
   monotony issue (C1) bleeds into social shares.
4. Incident record (today): hero-selection time-bomb test froze builds 08:45→
   10:40 (fixed #201); daily-editor auth broken since creation (fixed #202,
   #210); API credits exhausted mid-day (owner topped up + auto-reload);
   build queue wedged by a zombie "waiting" run 18:16→23:08 (unwedged; wedge
   guard shipped #213). The heartbeat now self-heals both dead and wedged
   chains; keep it.

## Priority order (owner decision required only where marked)

P0 — this week
1. Break the West Bank blackout: work the 7 queued westbank topics; route
   Israeli-press West Bank items as westbank category with israelipress
   cross-listing (or dual-section rendering).
2. Revive the standing beats as living documents: Washington Brief daily
   again (it is at zero live items), election tracker refresh with the
   Maariv/JPost numbers already published, Table Friday edition (Reem's
   California), litigation docket + ICC/ICJ sweep. Fold the long-paragraph
   cleanup into the same pass.
3. Add retry/backoff on overloaded_error to the investigations desk.
4. Latest-rail per-section cap + ticker hard-news-only filter + add arts to
   hero exclusions (features never squat).
5. Compress the 25 MB video.

P1 — this month
6. Arabic remediation: line-edit the 8-file legacy cohort; fix the 6
   headline residues and the listed grammar slips; standardize month-pair
   order to «تموز/يوليو» (majority form; update the style guide example) and
   add a validator warning for bare Gregorian months; quote-mark and
   briefing-subhead sweeps. Then: enforce "Arabic outline first" by asking
   the desk for structural divergence (different paragraph count than EN is
   a feature, not a bug).
7. Per-story art for israelipress (rotating variants or a small generator:
   outlet-neutral newspaper motifs with varying accent hues + the headline),
   and work the photo-conversion queue including override 287efd3ca4.
8. Newsletter capture + privacy-first analytics + a support page (owner
   decisions on provider/wording).
9. AR-dominant variants of house SVG ledes for the Arabic edition (flip text
   hierarchy per edition).
10. Sports/opinion/archive decision (owner): feed them (sports has 2 queued
    topics; opinion could carry the attributed-analysis overflow from the
    press desk; archive awaits Palestine Times scans) or stop rendering
    their empty sections until content exists.

P2 — nice to have
11. Story-page beat rail ("More on this file") from the standing-beat map.
12. Homepage ItemList JSON-LD; byline string fix.
13. WhatsApp Channel distribution alongside Telegram.
