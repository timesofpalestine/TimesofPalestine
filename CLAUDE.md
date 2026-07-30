# Times of Palestine — newsroom charter for AI agents

Multiple AI agents (ChatGPT/Codex, GitHub Copilot, Claude) work on this repo on
behalf of the owner. This file records the owner's standing decisions. **Do not
undo another agent's layer to make your own change** — graft your change onto
what is there, and when two approaches conflict, open a PR and let the owner
decide rather than force-replacing files.

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

## Division of labor (suggested, not exclusive)

- **Codex/ChatGPT:** Telegram delivery, workflow reliability, tests.
- **Copilot:** renderer/validator hardening via PRs (reviewed before merge).
- **Claude:** the AI newsroom layers (briefs, investigations desk), editorial
  pipeline, dedupe/completeness gates, and the daily **Washington Brief**
  (`originals/washington-brief-*` + matching SVGs in `originals/media/`) —
  a scheduled deep-research report on DC's Iran/Israel/Mideast thinking for a
  Palestinian audience. Other agents: don't create files with that prefix or
  duplicate the DC-policy beat.

Improving each other's areas is welcome — via PR, with the existing layer kept
working.

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
   (`https://t.me/<channel>/<id>`), or a direct https `.mp4`. Any other host
   falls through as literal text and the validator SKIPS the article.
   Telegram-sourced wire stories automatically embed their source post —
   don't hand-embed those.
4. Before pushing, run `python3 build.py` and confirm `✓ original:` for your
   files. Push with fetch/rebase/retry — this repo receives frequent commits.
5. Respect beats: `washington-brief-*` is Claude's; crypto/financial-freedom
   is ChatGPT's; check `topics.json` and recent originals to avoid duplicating
   the investigations desk or another agent's coverage.
