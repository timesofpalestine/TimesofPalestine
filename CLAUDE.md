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

## Breaking-news watchlist (owner directive 2026-08-01)

`editorial/x-watchlist.md` is the newsroom's tiered list of the X/Twitter
(and named Facebook/Instagram) accounts that break Palestine news first.
Every automated editorial run sweeps Tier 1 before other work; an uncovered
Tier-1 item from the last 24 hours is the day's first assignment. Posts are
claims, not facts — attribute, translate precisely, and say what remains
unconfirmed. Any agent may improve the list via PR.

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
   humans) / `date:` (ISO 8601 UTC, never future) / optional `maxAgeHours:`.
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
   links, `![caption](file.svg)` images (file must exist in
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
   auto-owned, no manifest entry). Text-only desk reports fall back to the
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
