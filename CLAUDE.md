# Times of Palestine — newsroom charter for AI agents

Multiple AI agents (ChatGPT/Codex, GitHub Copilot, Claude) work on this repo on
behalf of the owner. This file records the owner's standing decisions. **Do not
undo another agent's layer to make your own change** — graft your change onto
what is there, and when two approaches conflict, open a PR and let the owner
decide rather than force-replacing files.

## GUIDING PRINCIPLE — the page is alive (owner directive 2026-07-30)

Times of Palestine is a DYNAMIC news site: every visit, every refresh should
show fresh information. Given the weight of the name, the standard is the
world's great news fronts — The Times, the NYT. Every agent applies this to
everything it builds:

- The top story follows the news cycle (freshest-window hero selection) and
  is never a multi-day-old feature. Nothing reader-facing may "squat".
- The site builds and deploys every 10 minutes; changes that slow the refresh
  chain or cache staleness into the reader's view are regressions.
- Fresh stories carry the pulsing NEW/جديد mark (under 90 minutes);
  timestamps are minute-level and honest; the breaking ticker stays
  chronological.
- Features, research and archive material keep their prominence in their own
  sections — never at the expense of the live top of the page.
- When adding any surface (section, page, widget), ask: what makes this feel
  alive an hour from now? If nothing does, redesign it.

## Owner decisions currently in force (2026-07-29)

1. **The AI newsroom is ON — deliberately.** The build uses the Anthropic API
   in two places, and the owner has approved the cost (~$150–200/month):
   - **Briefs desk** (`build.py`, `claude-haiku-4-5`): every wire item is
     rewritten in-house before publication. Wire-first policy: an item
     publishes only when its rewrite exists, is complete, and passes the
     refusal screen. Never publish raw truncated feed summaries as articles.
   - **Investigations desk** (`originals_gen.py`, `claude-opus-5` + web
     search): files at most 3 researched bilingual reports/day at 05/12/19 UTC
     (`DESK_HOURS`). Owner-approved cadence — don't raise it without asking.
   - In `.github/workflows/build.yml` this requires: the
     `pip install anthropic` step, `ANTHROPIC_API_KEY` on the build step,
     `permissions: contents: write` (the desk commits its reports), and
     `INVESTIGATIONS: ${{ vars.INVESTIGATIONS }}`. **Do not remove these.**
     To pause the desk, set the `INVESTIGATIONS` repo variable to `off` —
     never hardcode `off` in the workflow.
2. **Telegram delivery** (`telegram_publish.py`, tests, delivery cache) is
   Codex's layer. Keep it; don't fold it back into `build.py`.
3. **Editorial rules:** no sources/bibliography sections in articles —
   attribution lives inline in the prose. Report the issue, never the
   individual. Both language editions are first-class; verify rendering
   changes in `/en/` and `/ar/`. Use constructive, good-faith framing for
   civic, cultural, diplomatic, humanitarian and institutional initiatives:
   give clear credit for worthwhile intentions, commitments and delivered
   work supported by the record; never imply bad faith merely because funding,
   governance or implementation details are still being developed. Distinguish
   what is promised, funded, underway, completed and still needed, and present
   pending work as the next practical stage. This tone rule does not suppress
   verified harm, material failures or accountability reporting; it requires
   precise evidence and fair language rather than cynicism or insinuation
   (owner decision 2026-07-30, given via ChatGPT and confirmed directly to
   Claude the same day).
   **Arabic quality (owner decision 2026-07-30):** the Arabic edition is
   written fresh as native Arabic journalism — the register of الجزيرة نت /
   عرب 48 — never translationese; a reader must not sense English syntax
   underneath. Headlines especially: composed fresh using Arabic front-page
   patterns (verbal sentences, the two-dot pivot «بعد كذا.. حدث كذا», colon
   attribution, direct questions), never a translated English headline.
   Before writing Arabic, study native headlines from the site's Arabic wire
   feeds as register models. Lock facts and evidence first, then structure the
   Arabic for an Arabic reader rather than preserving English word order.
   Every edition gets a separate Arabic-only line edit and read-aloud pass;
   follow `editorial/arabic-style-guide.md`. Arabic headlines should normally
   be 6–10 words, use an active construction and name the responsible actor
   or institution whenever the reporting identifies one; never hide a known
   actor behind passive or agentless wording. Applies to every agent.
   **Wire attribution protocol (owner decision 2026-07-30):** a rewritten
   story is OUR copy. The source outlet is named exactly once, inline, in
   the prose ("…, the Ma'an news agency reported"). No byline credit-links,
   no "read the full story at …" buttons, no outlet links or outlet chips on
   story pages or cards — reader-facing source identity is Times of
   Palestine. JSON-LD `isBasedOn`/`citation` metadata keeps the machine-
   readable source record. Dek-fallback pages (briefs layer down, source's
   own summary as body) are the one exception and keep the outlet link.
4. **Publishing safety:** event-level dedupe (one incident, one article) and
   the completeness gate (no mid-sentence bodies) in `build.py` are
   owner-requested. Markdown-residue in an original skips that article with a
   loud warning; schema and missing-media errors fail the build. Editorial
   gating must default to publish — never to holding coverage behind
   per-story manual approval, and NEVER with reader-facing labels
   ("developing report", "awaiting review" etc.) on any story (owner
   decision 2026-07-30). Review tracking is internal-only
   (review-queue.json).
5. **Story imagery: keep photos (owner decision 2026-07-30).** Aggregated
   stories fetch and display upstream social-preview images (og:image); story
   cards must not go photoless. Any rights-strict mode (self-owned assets
   only) is an opt-in flag, default OFF.
   **Photo-desk override (owner order 2026-08-03):** a specific story's
   image can be replaced editorially via `editorial/image-overrides.json`
   (pid → `"cover"`, a local `/media/` asset, or a rights-cleared URL) —
   the override holds through every rebuild. Use it when a wire frame is
   unusable (faces cut, graphic content); never leave a story photoless.
6. **Zero third-party Python deps in the build path** except `anthropic`
   (installed in CI). `build.py`/`longform.py` stay stdlib-only otherwise.
7. **Never commit** `__pycache__/`, `dist/`, cache/state JSON — see
   `.gitignore`. Never commit secrets; `TELEGRAM_BOT_TOKEN` and
   `ANTHROPIC_API_KEY` live in GitHub secrets only.
8. **Bitcoin dispatch desk (owner-approved 2026-08-02, Copilot PR #9):**
   `bitcoin_dispatch.py` + `.github/workflows/bitcoin-dispatch.yml` file an
   OpenAI-powered bilingual original on the financial-freedom beat every
   48 h. Requires the `OPENAI_API_KEY` repo secret (skips gracefully without
   it). Pause via the Actions tab; the script is fail-open and must never
   block the news build.
9. **Daily editor-in-chief cycle (owner directive 2026-08-01):** Claude runs
   `.github/workflows/daily-editor.yml` each morning (06:30 UTC), choosing and
   shipping 3–5 improvements a day across editorial, design, platform and the
   franchises, via a `claude/daily-editor-<date>` PR merged on green CI. Other
   agents: expect a daily PR with this prefix; don't revert its layers —
   disagreements go to issue #6. To pause the cycle, disable the workflow in
   the Actions tab (don't delete the file).

## Division of labor (suggested, not exclusive)

- **Codex/ChatGPT:** Telegram delivery, workflow reliability, tests.
- **Copilot:** renderer/validator hardening via PRs (reviewed before merge).
- **Claude:** the AI newsroom layers (briefs, investigations desk), editorial
  pipeline, dedupe/completeness gates, the annual **TOP 100**
  (`originals/palestine-top100-<year>.*` — Times of Palestine's list of the
  100 most influential Palestinians worldwide, published each August; owner
  directive 2026-08-01; refresh the research sweep fully each edition, never
  recycle the prior year's blurbs), and the daily **Washington Brief**
  (`originals/washington-brief-*` + matching SVGs in `originals/media/`) —
  a scheduled deep-research report on DC's Iran/Israel/Mideast thinking for a
  Palestinian audience. Other agents: don't create files with that prefix or
  duplicate the DC-policy beat.

Improving each other's areas is welcome — via PR, with the existing layer kept
working.

## PA litigation docket (owner directive 2026-08-02)

Standing beat: track lawsuits against the PA/PLO worldwide — the revived US
terror-judgment cases (Sokolow $655.5M, Fuld, PSJVTA suits), Israeli court
judgments enforced via clearance-revenue deductions, the prisoner-payments
audit that decides both, and any European enforcement or conditionality
proceedings. Launch report: `originals/pa-litigation-docket-2026.*`. The
daily editor cycle sweeps this docket; significant developments are covered
same-day in both languages. Claude's beat.

## Israeli election watch (owner directive 2026-08-02)

Standing beat through the 27 October 2026 Knesset election: the coalitions
forming and collapsing, who leads, who gains, who falls, and the names —
Eisenkot/Yashar, Netanyahu/Likud, Bennett–Lapid/Beyachad, Golan/Democrats,
Liberman, Gantz, Ben Gvir, Smotrich, Deri, and the Arab lists (Mansour
Abbas/Ra'am, Odeh–Tibi/Hadash-Ta'al) whose seats both blocs need and refuse.
Always frame the Palestinian stakes: annexation, Gaza policy, the kingmaker
paradox facing Palestinian citizens of Israel. Launch report:
`originals/israel-election-2026-*`. The daily editor cycle sweeps this beat;
significant poll shifts, mergers and coalition moves are covered same-day in
both languages, with numbers attributed to the specific pollster/outlet.
Claude's beat — other agents route election story ideas via issue #6.

## International justice watch (owner directive 2026-08-02)

Standing beat: the ICC and ICJ files on Palestine, with the arrest warrant
for Benjamin Netanyahu at the center. Track: the ICC warrants for Netanyahu
and Gallant (appeals, member-state compliance and travel, the US sanctions
campaign against the court's prosecutor, deputies and judges, Hungary-style
withdrawals); the ICJ's South Africa v. Israel genocide case (pleadings,
interventions, hearings), the occupation and aid advisory opinions, and
Nicaragua v. Germany. Keep the two courts distinct for readers (state
disputes at the ICJ, individual criminal liability at the ICC) and always
attribute filings and rulings to the specific chamber and date. The courts'
official channels (@CIJ_ICJ, @IntlCrimCourt) are Tier-1 watchlist accounts;
significant developments are covered same-day in both languages. Launch
report: `originals/icc-icj-netanyahu-warrant-2026.*`. Claude's beat — story
ideas from other agents route via issue #6.

## Scholarship guide (owner directive 2026-08-02)

Standing reader service: `originals/palestine-scholarships-guide-2026.*`
maps scholarship programs for Palestinian students worldwide (bachelor's
to PhD, all fields) and is pinned on the front page via the SPECIALS band.
The daily editor cycle keeps it current — new windows added, passed
deadlines retired, both languages, links verified. Deadlines are always
phrased as verify-at-source. Claude's beat; other agents may PR additions
with sources.

## SANAD — bitchat for medicine (owner north star, 2026-08-04)

The owner's guiding principle, verbatim in spirit: **SANAD is bitchat for
medicine — an app that works and runs purely for medical cases and helps
doctors and patients talk to each other worldwide to solve medical issues.
That is the problem we are in love with and the problem we want to solve.**
Every Sanad decision is measured against this sentence. War zone first:
hospitals and patients in Gaza, where internet and even phone service come
and go.

Current surfaces:
- **`/sanad/` web board** (live, static feature): offline-first single-file
  case board; four carriers; end-to-end sealed reply threads on bitchat's
  model; ward-team quick start (install bitchat → everyone joins `#sanad`
  → post → share); official bitchat download links with impostor warning.
  Front-page prominence is charter-protected (`.sanad-band`, tier-1 nav).
  **Outbreak watch** (owner directive 2026-08-04): `outbreak_watch.py`
  scans every build's wire (both languages) for diseases spreading in
  Gaza/West Bank and population-level supply failures, and publishes
  deterministic SANAD case events at `/sanad/watch.json` — the page pulls
  them online, the mesh relays them offline, experts answer on the board.
  Signal rule: the disease must be named in the headline/dek with a
  spread/emergency context word; never break the news build (fail-open).
- **The SANAD app** (`sanad-app/`, in build): a native app on bitchat's
  open-source design (public domain), rebuilt around the medical case —
  triage board not chat rooms, SND1 packet interop with the web board,
  Bluetooth mesh + internet when it exists. Roadmap: issue #149.

Standing rules: trust is professional referral (owner decision 2026-08-04 —
NO licence-verification gate, ever); no names/IDs/faces ride a packet;
"not a medical service" on every screen; a missing key or feature must
never block advice — care outranks secrecy. Claude's beat; other agents
PR under charter rules, disagreements to issue #6.

## HER STORY — Palestinian women's accounts (owner directive 2026-08-03)

Standing section, key `women` ("Her Story" / «حكايتها»), modelled on More
to Her Story: women and girls are the SUBJECT, not the illustration. It
covers what Palestinian women survived and what they carry — violence
against women (UN-documented sexual and gender-based violence in
detention, at checkpoints and by settlers), widowhood and female-headed
households, birth and maternal care under siege, detention of women and
girls, and the work women do to hold families and institutions together.
Wire items route in automatically (`WOMEN_RX`: a female subject plus a
her-story context, or a strong solo signal like أسيرة/femicide/midwife).

Section rules, binding on every agent:
- **Consent and safety first.** Never name a survivor of sexual violence
  without explicit consent; never publish an account in a form that could
  identify her against her wishes. An anonymous account still runs —
  silence protects only whoever caused the harm.
- **Report the issue, never the individual** (charter rule, enforced hard
  here): no spectacle, no grief as raw material. Her words lead; our
  summary follows.
- **Attribute every finding** to the specific UN body/report and date.
- Both editions always; Arabic is written fresh, never translated.
- Women journalists inside Palestine are invited to file; their bylines
  run on their own work. Launch report:
  `originals/her-story-palestinian-women-2026.*`. Claude's beat; open to
  all agents under these rules.

## Arab support monitor (owner directive 2026-08-02)

Standing division: what Arab countries are doing to help Palestinians —
politically, economically, financially, in aid, education and culture.
Section key `arabaid` ("Arab Support" / «الإسناد العربي»), fed by dedicated
radar feeds (`radar-arab-support`, `radar-arab-support-ar`) and an
actor-plus-assistance categorization rule, so wire items land in the section
automatically. The daily editor cycle sweeps the beat: summit pledges and
whether they disburse, reconstruction financing, medical corridors and field
hospitals, scholarship programs for Gaza students, cultural initiatives —
covered in both languages with the charter's constructive-framing rule
(credit delivered work precisely; distinguish promised, funded, underway,
completed and still needed). Launch report:
`originals/arab-support-monitor-2026.*`. Open to all agents under charter
rules; keep pledges attributed and dated.

## Breaking-news watchlist (owner directive 2026-08-01)

`editorial/x-watchlist.md` is the newsroom's tiered list of the X/Twitter
(and named Facebook/Instagram) accounts that break Palestine news first.
Every automated editorial run sweeps Tier 1 before other work; an uncovered
Tier-1 item from the last 24 hours is the day's first assignment. Posts are
claims, not facts — attribute, translate precisely, and say what remains
unconfirmed. Any agent may improve the list via PR.

## House design system (owner directive 2026-08-02)

`editorial/design-system.md` is the normative definition of the site's look
and layout for EVERY agent. Any reader-facing visual change follows it: use
the `:root` tokens (no new hex families without adding them to that file
first), keep RTL first-class via logical properties, follow the house SVG
style, and run its verification protocol (EN + AR, mobile, dark mode
screenshots) before the PR. A PR that introduces a new visual pattern
updates the design system in the same PR. Design disagreements go to
issue #6, never resolved by overwriting.

## Coordination & beats in motion (owner directive 2026-07-30)

- **Standing coordination thread: issue #6** — story ideas for each other,
  beat-cadence notes, cross-desk requests. The Washington Brief posts a
  daily cadence check and DC-sourced story ideas there. ChatGPT/Codex:
  keep a steady filing cadence on your beats and check #6 for ideas.
- **HEALTH beat (new):** `category: health`, section "Health & Healing" /
  «الصحة والتعافي». Owner directive: the Gaza war's damage to population
  health, covered with a solutions lens — prosthetics, cancer corridors,
  telemedicine, children's mental health, dialysis/chronic care, maternal
  care, vaccination recovery, rehabilitation. Eight topics queued in
  topics.json; Palestine Health Wire feed feeds the section. Open to all
  agents under the charter rules.

## Asking each other for help (owner directive 2026-07-30)

When an agent hits a problem it cannot solve — a bug outside its expertise,
a layer it doesn't own, a design question — it ASKS the others instead of
guessing or force-changing someone else's code:

- Open a GitHub issue titled `help: <short problem>` with the symptom, the
  exact error or repro, what was already tried, and which layer it touches.
- Mention `@copilot` to bring in Copilot (it responds to issue/PR mentions
  and can file a PR), or address Codex for its layers (Telegram delivery,
  workflow reliability, tests) — Codex reads this file and the repo issues.
- Claude runs the newsroom layers; issues touching briefs, dedupe, the
  desks or editorial gates should be labeled for Claude and left unmerged
  until reviewed.
- The owner reads the issues; disagreements between agents end there, with
  the owner deciding. Never resolve a disagreement by overwriting.

## Palestine Times archive (rights on record)

The owner declared to Claude on 2026-07-30 that they FULLY OWN the rights to
the Palestine Times — the English-language Palestinian daily launched in
Ramallah on 2006-11-27 that ceased publication in 2007 (Library of Congress
item 2007330052) — including its title and archive. Times of Palestine is its
revival. Archive republication rules:
- Archive pieces use `category: archive` (section "From the Archive" /
  «من الأرشيف»), carry their ORIGINAL publication date in `date:`, a very
  large `maxAgeHours` (e.g. 999999), and never masquerade as new reporting.
- Never alter the original text beyond format cleanup; note the original
  byline inline where known ("By <name>, Palestine Times, <date>").
- Only the owner supplies archive source material (scans, PDFs, text). No
  agent scrapes third-party sites for it.

## How any agent publishes an article (the contract)

The site is fully cloud-automated: push a valid file to `originals/` on `main`
and the hourly GitHub Actions build validates, renders, deploys, and delivers
it to Telegram. No human machine involved. The contract:

1. File: `originals/<slug>.<en|ar>.txt` — publish BOTH languages as
   first-class editions. Header, then `---`, then body:
   `title:` / `category:` (one of: gaza westbank politics economy
   accountability research bitcoin diaspora arts sports social opinion news
   humans health archive arabaid) / `date:` (ISO 8601 UTC, never future) /
   optional `maxAgeHours:`.
   **Headline rule (owner decision 2026-07-30, validator-enforced):** every
   title is ONE short complete sentence — aim for 9-10 words, hard cap 12,
   never a trailing ellipsis, never raw feed/post text as a title. The
   briefs desk composes its own short headline for every wire story.
   **NO PASSIVE TITLES — EVER (owner decision 2026-07-30,
   validator-enforced, both languages):** every title is active voice and
   says precisely WHO did WHAT to WHOM — the actor the reporting identifies
   is the grammatical subject. Never passive ("was killed", «قُتل»,
   «استُهدف»), and never agentless hedges that hide a known actor ("changes
   hands", "comes under fire", "faces pressure"). "Israel registers West
   Bank land weekly", never "West Bank land changes hands through a weekly
   administrative routine". In Arabic: جملة فعلية بالمبني للمعلوم تسمّي
   الفاعل صراحةً. The validator skips originals and refuses briefs whose
   titles trip the passive/agentless net.
2. Body Markdown subset ONLY: `##` subheads, `**bold**`, `*italic*`,
   backtick code, `- ` bullets, `1. ` lists, pipe tables, `[text](url)`
   links, `> ` pull quotes / data callouts (consecutive `> ` lines form one
   quote; a second line renders as the smaller attribution — use for a
   survivor's words or a key statistic, sparingly, 1–2 per story),
   **Pacing (owner order 2026-08-03): paragraphs are 1–3 sentences, never
   past ~70 words — the renderer splits longer prose at sentence boundaries
   on every surface, originals included — and machine diction (the briefs
   desk's banned lists, «أسلم» for «سلّم», «قام بـ», «تم»+مصدر, "delve",
   "underscores"…) is flagged loudly at build for the daily editor.**
   `![caption](file.svg)` images (file must exist in
   `originals/media/`). Anything else prints literally and the article is
   SKIPPED by the validator. No footnotes, no sources sections — attribution
   inline in prose. Never end mid-sentence. NEWSPAPER copy, never a briefing
   memo (owner decision 2026-07-30, validator-enforced): no "What is
   unresolved / Unanswered questions / Key takeaways / Conclusion / Bottom
   line"-style sections and never a list of questions — unknowns are
   reported as prose sentences in wire-service register. Internal editorial
   notes ("verify before publication") must never appear in a body.
3. Graphics: self-created SVGs in `originals/media/`, house dark style with
   bilingual labels (see existing `times-of-palestine-*.svg`). Never
   copyrighted images.
   **Lede visual protocol (owner decision 2026-07-30):** every original
   carries an `image:` header. Priority: (1) a rights-cleared REAL photo or
   screenshot of the subject (public domain, CC, official press kit,
   open-source assets) saved to `originals/media/` with a
   `media-rights.json` entry (asset, rightsBasis, credit, licenseUrl);
   (2) a house SVG illustration of the subject (`times-of-palestine-*.svg`,
   auto-owned, no manifest entry). An original's `image:` may also be a
   remote rights-cleared URL (e.g. a Wikimedia Commons
   `Special:FilePath/<name>?width=640` portrait) when that EXACT URL has a
   `media-rights.json` entry — it is verified live at build time, and an
   optional `imageFallback:` header (usually the report's house SVG) takes
   over if the remote image is dead, before the generic category cover.
   **Covers are photographs (owner order 2026-08-03):** a story's COVER must
   be a photo, centered and well-fitted — never a chart, timeline or
   figures board. Infographics belong IN the body (`![…](file.svg)`), where
   they are welcome. When no rights-cleared photo can be sourced, the house
   SVG stays as a stopgap and the report joins the photo-conversion queue
   that the daily editor cycle works through; franchise covers (TOP 100,
   the scholarship map) are brand art, not charts, and are exempt. An original's `image:` may also be a
   remote rights-cleared URL (e.g. a Wikimedia Commons
   `Special:FilePath/<name>?width=640` portrait) when that EXACT URL has a
   `media-rights.json` entry — it is verified live at build time, and an
   optional `imageFallback:` header (usually the report's house SVG) takes
   over if the remote image is dead, before the generic category cover. Text-only desk reports fall back to the
   branded category covers automatically — never the bare flag placeholder.
   **Visual-first (owner decision 2026-07-30): no article runs as dead
   text.** Every story ships a visual — real photo, subject illustration
   (the Bitchat-style house SVG is the model), or infographic. The
   investigations desk auto-generates a subject illustration per report;
   photoless wire items receive category covers; deep reports carry
   in-body infographics.
   **Video (embeds only, never hosted):** `!video[caption](url)` on its own
   line. Whitelisted hosts ONLY: YouTube watch/shorts/youtu.be URLs (renders
   as the privacy youtube-nocookie player), public Telegram post URLs
   (`https://t.me/<channel>/<id>`), public Instagram reels/posts
   (`https://www.instagram.com/reel/<id>/` — tracking params are stripped),
   or a direct https `.mp4`. Any other host
   falls through as literal text and the validator SKIPS the article.
   Telegram-sourced wire stories automatically embed their source post —
   don't hand-embed those.
4. Before pushing, run `python3 build.py` and confirm `✓ original:` for your
   files. Push with fetch/rebase/retry — this repo receives frequent commits.
5. Respect beats: `washington-brief-*` is Claude's; crypto/financial-freedom
   is ChatGPT's; check `topics.json` and recent originals to avoid duplicating
   the investigations desk or another agent's coverage.
