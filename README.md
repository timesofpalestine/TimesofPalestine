# Times of Palestine — تايمز أوف فلسطين

An independent, bilingual (English/Arabic), fully automated digital news front page for Palestine.
It aggregates live reporting from outlets across Palestine and the region, links every story back
to its original publisher, and rebuilds itself every 25 minutes with **zero human management**.

- **English edition:** `/en/` (LTR) · **Arabic edition:** `/ar/` (RTL, natively mirrored)
- The root `/` auto-redirects visitors based on their browser language.
- Design: Politico-style masthead & timestamped "Latest" rail, Axios-style clean cards,
  Palestinian flag palette (red `#CE1126`, green `#007A3D`, black) as restrained accents.

## How it works

`build.py` (pure Python 3.9+, **no dependencies**) does everything:

1. Fetches every RSS/Atom feed in [feeds.json](feeds.json) in parallel.
2. Keeps stories from the last 72 hours; filters general outlets (Al Jazeera, MEE) to
   Palestine-related items only.
3. Dedupes near-identical headlines, caps any single outlet at 14 stories so no source dominates.
4. Auto-categorizes into Gaza · West Bank & Jerusalem · Politics & Diplomacy · Economy & Aid ·
   Culture & Society · Opinion & Analysis.
5. Renders `dist/en/index.html`, `dist/ar/index.html`, and the language-detecting `dist/index.html`.

A feed that is down, blocked, or rate-limited is simply skipped — the build never breaks because
of one source. If *every* feed fails, the build exits non-zero so the last good deploy stays live.

## Run locally

```bash
python3 build.py
python3 -m http.server 8000 --directory dist
```

Then open <http://localhost:8000>.

## Deploy once — then it runs itself forever

The included GitHub Actions workflow ([.github/workflows/build.yml](.github/workflows/build.yml))
rebuilds the site from live feeds and publishes it to GitHub Pages (free hosting). It runs continuously through a self-dispatch chain that waits 25 minutes between runs.

One-time setup:

```bash
git init && git add -A && git commit -m "Times of Palestine launch"
gh repo create times-of-palestine --public --source . --push
```

Then in the GitHub repo: **Settings → Pages → Source: "GitHub Actions"**. Done.
The first run starts immediately (or trigger it from the Actions tab); after that it refreshes
itself every 3 hours with no human involvement.

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

**Recommended — keep the automation:** host the site on GitHub Pages (free, rebuilds roughly every 25 minutes)
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

Add or remove outlets in [feeds.json](feeds.json). Three source types:

```json
{ "id": "slug", "name": "Display Name", "url": "https://…/rss", "site": "https://…", "filterPalestine": true }
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
