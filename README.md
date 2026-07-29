# Times of Palestine — تايمز أوف فلسطين

An independent, bilingual (English/Arabic) static digital news front page for Palestine.
It aggregates live reporting from outlets across Palestine and the region, links every story back
to its original publisher, and rebuilds itself every 3 hours. Sensitive claims are deliberately
**not** fully automated: an editor must approve the exact version before it can publish.

- **English edition:** `/en/` (LTR) · **Arabic edition:** `/ar/` (RTL, natively mirrored)
- The root `/` auto-redirects visitors based on their browser language.
- Design: Politico-style masthead & timestamped "Latest" rail, Axios-style clean cards,
  Palestinian flag palette (red `#CE1126`, green `#007A3D`, black) as restrained accents.

## How it works

`build.py` and the stdlib-only publishing modules run on Python 3.9+ with no required dependency:

1. Fetches every RSS/Atom feed in [feeds.json](feeds.json) in parallel.
2. Keeps stories from the last 72 hours; filters general outlets (Al Jazeera, MEE) to
   Palestine-related items only.
3. Validates source attribution, canonical links, UTC dates, media rights and editorial eligibility.
4. Clusters near-identical reports, records independent corroborating publishers, and caps any
   single outlet at 14 stories so no source dominates.
5. Auto-categorizes into Gaza · West Bank & Jerusalem · Politics & Diplomacy · Economy & Aid ·
   Culture & Society · Opinion & Analysis.
6. Renders bilingual pages, RSS, JSON Feed, web/news sitemaps, structured data, PWA assets and
   sanitized health output into `dist/`.

A feed that is down, blocked, rate-limited or emits an incomplete record is isolated and reported;
that record never publishes. Invalid repository configuration, invalid originals, unsafe local
media, leaked unapproved content, malformed feeds/sitemaps or broken generated links fail the
build so the last good deploy stays live.

## Run locally

```bash
python3 build.py
python3 validate_build.py dist
python3 -m http.server 8000 --directory dist
```

Then open <http://localhost:8000>.

## Deploy once — then it runs itself forever

The included GitHub Actions workflow ([.github/workflows/build.yml](.github/workflows/build.yml))
rebuilds the site from live feeds **every 3 hours** and publishes it to GitHub Pages (free hosting).
It runs the offline tests and generated-site validator before deployment. The old self-chaining
25-minute sleeping runner and unattended investigation commit path were removed.

One-time setup:

```bash
git init && git add -A && git commit -m "Times of Palestine launch"
gh repo create times-of-palestine --public --source . --push
```

Then in the GitHub repo: **Settings → Pages → Source: "GitHub Actions"**. Done.
The first run starts immediately (or trigger it from the Actions tab); after that low-risk,
fully-attributed aggregation refreshes every three hours. Flagged content waits for review.

## Publishing safety contract

Every non-original story must carry a publisher name, publisher homepage, canonical article URL,
source type, language and timezone-aware publication date. Current `exclusive: true` feed entries
are treated as attributed partner inputs; the flag never replaces the upstream publisher with
Times of Palestine and never removes the outbound source link. Google News items publish only when
their publisher article URL can be resolved.

All internal timestamps are UTC. RSS emits `GMT`; JSON Feed, health output, Google News sitemap and
structured data emit UTC ISO-8601. Reader-facing dates remain localized to `Asia/Gaza`.

### Human review

The deterministic EN/AR gate holds casualty claims, serious accusations, named security or
military subjects, public Telegram/citizen reports, repository originals, and breaking claims
without at least two independent publishers. AI triage cannot approve or bypass a hold.

```bash
# Fetch and display full pending stories only in this terminal:
python3 review.py list
python3 review.py list --lang ar

# Approve exactly the displayed version, then commit editorial/reviews.json:
python3 review.py approve <64-character-fingerprint> --reviewer "Editor name"

# Revoke an approval:
python3 review.py revoke <64-character-fingerprint>
```

The public ledger stores only an opaque fingerprint, reviewer label and UTC approval time. CI,
`health.json` and `review-queue.json` never persist pending headlines, bodies, URLs or private-tip
data. Any change to publishable text, attribution, dates or corrections changes the fingerprint
and requires a new approval. Sensitive external stories do not receive an AI-authored brief, so
the approved text is the text that publishes.

### Original investigations

`originals_gen.py` is now an explicit editor-run draft tool. It writes only to the gitignored
`.editorial-drafts/` directory and is not called by the build or CI:

```bash
ANTHROPIC_API_KEY=... python3 originals_gen.py
python3 review.py promote <topic-id> --reviewer "Editor name"
```

Promotion requires a validated English/Arabic pair and records approval for both exact versions.
Pending drafts are never included in Pages, distribution, commits or public CI output.

### Image rights

Remote feed, Telegram and OG images are not rendered or hotlinked by default. The branded flag
fallback is used instead. A story image or long-form figure may render only when its exact local
path or URL has an entry in `media-rights.json` with a rights basis, visible credit, source and
optional license URL. Local media without that record fails the build. The repository does not
download or rehost third-party media and has no general owned-media storage pipeline.

### Updates and corrections

`editorial/corrections.json` is keyed by the stable ten-character story ID shown in its generated
URL. Entries are chronological and need both language notes when the story exists in both editions:

```json
{
  "version": 1,
  "stories": {
    "0123456789": [
      {
        "at": "2026-07-29T18:30:00Z",
        "type": "correction",
        "en": "Corrected the date of the announcement.",
        "ar": "صُحح تاريخ الإعلان."
      }
    ]
  }
}
```

The history is visible on the story page. Its latest timestamp controls `dateModified`, sitemap
`lastmod` and JSON Feed modification metadata. A routine rebuild never changes `dateModified`.

### Monitoring and distribution

- `/health.json` and bilingual `/en/status.html` / `/ar/status.html` expose sanitized feed,
  validation, review, media and connector health.
- `validate_build.py` checks internal links, HTML/JSON-LD, RSS and sitemap XML, UTC timestamps,
  approved images, review-data privacy and PWA assets.
- `/en/feed.json` and `/ar/feed.json` are credential-free JSON Feed connector surfaces.
- A validated `/distribution-outbox.json` is deployed with the site; only after Pages reports a
  successful deployment do IndexNow, Telegram and the optional webhook receive those eligible
  stories.
- `DISTRIBUTION_WEBHOOK_URL` optionally enables a generic JSON webhook with stable
  `Idempotency-Key` headers. Missing credentials are reported as `disabled`, never as success.
- `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN` and `DISTRIBUTION_WEBHOOK_URL` remain external GitHub
  secrets. Tests require none of them.

### Custom domain (timesofpalestine.com)

1. Create a file named `CNAME` in the repo root containing exactly: `timesofpalestine.com`
2. At your DNS provider, point the domain at GitHub Pages
   (`A` records → 185.199.108.153 / .109. / .110. / .111.153, plus `www` CNAME → `<user>.github.io`).
3. In **Settings → Pages**, enter the custom domain and enable **Enforce HTTPS**.

## Anonymous Signal tip line

Both editions carry a "Secure Tip Line" band and a 🔒 **Send a Tip** nav link, wired to the
newsroom's Signal account **@TOP.972** — a tap-to-chat `signal.me` button plus a scannable QR
(`signal-qr.png`, kept in the repo root and copied into the site at build time) for readers on
desktop. To change the account later, update `SIGNAL_URL` / `SIGNAL_USERNAME` at the top of
[build.py](build.py) and replace `signal-qr.png` with the new share QR from the Signal app.

Tip-line copy already includes source-protection guidance ("use Signal on a personal device…").
For maximum tipster safety, consider a dedicated phone/number for the newsroom Signal account.

## Hosting at GoDaddy (timesofpalestine.com)

**Recommended — keep the automation:** host the site on GitHub Pages (free, rebuilds every 3 h)
and just point the GoDaddy **DNS** at it (README section above). GoDaddy stays your registrar;
GitHub does the serving and refreshing. This is the only zero-management option.

**Alternative — GoDaddy web hosting:** upload the contents of `dist/` (or the ready-made
`timesofpalestine-godaddy.zip`) into `public_html` via cPanel → File Manager. The site will look
identical but is a **frozen snapshot** — it only updates when you re-run `python3 build.py` and
re-upload. If your GoDaddy plan includes cPanel **cron jobs** with Python 3.9+, you can upload
`build.py` + `feeds.json` and schedule `python3 build.py` with `dist/` symlinked into
`public_html` to get the same self-updating behavior.

## How stories are ranked

Placement is decided by a score, not just the clock:

- **Recency** — up to 50 points, decaying linearly over 72 hours.
- **Editorial focus** — +30 points each for stories matching the site's priority topics:
  **Palestinian Christians** (churches, clergy, settler attacks on Christian communities) and
  **Transparency & Accountability** (corruption, nepotism, political detention — wherever it sits,
  including the Palestinian Authority).
- **Has an image** — +8 points (image stories can lead the page).
- **Bitcoin & financial freedom** — a third focus topic (+30) with its own high-placed section:
  Bitcoin adoption in Palestine and the freedom-money track (HRF / Alex Gladstein / Jack Dorsey —
  money that cannot be frozen, censored, or occupied). Fed by Bitcoin Magazine (filtered to
  rights/adoption stories, never market noise) and bilingual **TOP Radar** Google News standing
  queries that catch this coverage from any outlet on earth.
- **Research & investigations** — +22 points for think-tank papers and OSINT investigations
  (Quincy Institute, Bellingcat, MERIP, DAWN, Crisis Group, HRW, Al Jazeera Studies), which also
  decay over their own 30–45-day shelf life instead of the 72-hour news cycle. The top report
  leads a dedicated **Research & Investigations / أبحاث وتحقيقات** section — placed first on the
  page — as a full-width featured card with an extended summary: news before it becomes news.
  Mark any feed with `"research": true` to route it here.

The hero and second tier are picked by score, so a strong focus story outranks a merely newer
one. The breaking ticker and "The Latest" rail stay strictly chronological. Focus topics also get
dedicated high-placed sections (red markers) that appear whenever even one story qualifies:
*Palestinian Christians* / *مسيحيو فلسطين* and *Transparency & Accountability* / *شفافية ومساءلة*.
Tune the keyword lists (`CHRISTIANS_RX`, `ACCOUNTABILITY_RX`) and weights (`FOCUS_BOOST`) at the
top of [build.py](build.py).

## Editing the source list

Add or remove outlets in [feeds.json](feeds.json). Every entry requires `id`, `name` and an HTTP(S)
`site`. A source that can emit timezone-naive dates must declare an IANA `timezone`.

```json
{ "id": "slug", "name": "Display Name", "url": "https://…/rss", "site": "https://…", "timezone": "Asia/Gaza", "filterPalestine": true }
```

```json
{ "id": "slug", "name": "Channel Name", "type": "youtube",
  "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC…",
  "site": "https://www.youtube.com/@handle", "filterPalestineChristians": true, "maxAgeHours": 720, "cap": 4 }
```

```json
{ "id": "slug", "name": "قناة · تيليغرام", "type": "telegram", "channel": "PublicChannelName",
  "site": "https://t.me/PublicChannelName", "cap": 6 }
```

- `filterPalestine` — for general outlets: only Palestine-related stories pass.
- `filterPalestineChristians` — for foreign shows/outlets (Tucker Carlson, Religion News Service):
  only stories with Palestine/Israel context pass.
- YouTube: find a channel's ID by viewing the channel page source and searching `channelId`.
  Feeds expose only the ~15 most recent videos, so `maxAgeHours` is set high to keep topical
  interviews visible longer.
```json
{ "id": "slug", "name": "TOP Radar", "type": "gnews", "query": "bitcoin (palestine OR \"financial freedom\")",
  "hl": "en-US", "gl": "US", "ceid": "US:en", "category": "bitcoin", "site": "https://news.google.com", "cap": 6 }
```

- `gnews` — a standing Google News query (no API key): monitors the entire press for a topic and
  credits each hit to its real outlet. Optional `category` pins results to a section. Use the
  matching `hl`/`gl`/`ceid` for Arabic queries (`"hl": "ar", "gl": "PS", "ceid": "PS:ar"`).
- Telegram: works for any **public** channel via its t.me/s/ preview — no API or account needed.
  Telegram posts appear only in the **Social Pulse / نبض المنصات** section, never in the news rail.
  To surface PA-corruption discourse properly, add the specific channels you trust here — the
  accountability scoring will lift matching posts automatically.

## Editorial charter

No allegiance except to the truth — and to the people of Palestine and their God-given human
rights. All voices, no censorship, criticism wherever it is warranted — and never a personal
attack. Every headline links to and credits its original publisher, which retains all rights.
