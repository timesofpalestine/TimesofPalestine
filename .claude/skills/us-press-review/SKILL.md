---
name: us-press-review
description: Daily US press and think-tank review for Times of Palestine — sweep the American papers and Washington's think tanks, select what matters to Palestinian readers, and publish each piece as its own bilingual original under the house contract. Use when the owner says "run the US press review", "sweep the American papers", "what is Washington reading/saying", or asks what the US press says about Palestine. Also runs inside the daily editor cycle each morning, beside the Israeli press review.
---

# US press review — the daily desk

Times of Palestine reads the American press and Washington's think tanks so
its readers don't have to. Every run produces standalone news items — one
story per source article or paper — in BOTH editions, plus one roundup of
what Washington is reading. Owner directive 2026-08-11; sibling desk to the
Israeli press review (2026-08-06), same discipline throughout.

## Sources to sweep

Start with the in-repo wire (same fetcher as the Israeli desk, its own
source list):

```
python3 israeli_press_fetch.py --feeds editorial/us-press-feeds.json --hours 36
```

It pulls the papers — NYT, Washington Post, WSJ, Politico, The Hill,
Axios, Foreign Policy, The Atlantic, The Intercept, Foreign Affairs — and
the **think tanks**: Brookings, Carnegie, CSIS, the Washington Institute
(WINEP), the Quincy Institute/Responsible Statecraft, CFR, FDD, the
Middle East Institute, the Arab Center Washington DC. From the digest,
select per the relevance test below, then WebFetch each chosen piece and
work from the full text: lock the facts, then compose fresh English and
fresh Arabic. (The wire is fail-open; if a feed dies, WebFetch the
outlet's site or fall back to WebSearch. Paywalled full text: work from
what is openly available and attribute precisely — never fabricate what
sits behind a wall.)

**Label think tanks as think tanks, every time**, with their institutional
identity and lean stated plainly in the body ("the Washington Institute,
founded in the orbit of the pro-Israel lobby", "the Quincy Institute,
which argues for US military restraint", "FDD, a hawkish shop close to
sanctions policy"). A think-tank paper is an argument with an address,
never neutral research.

## What is relevant

Pick items a Palestinian reader needs: administration policy on
Gaza/West Bank/Jerusalem and the ceasefire file; Congress (appropriations,
NDAA provisions touching Israel, resolutions, hearings); arms transfers
and military aid; the ICC/ICJ files as Washington fights them (sanctions
on the court, warrant diplomacy); UNRWA and humanitarian funding;
recognition-of-Palestine diplomacy as Washington reacts; normalization
tracks; the Iran file where it decides Gaza and Lebanon policy; the
opening American debate over Israel's role in US policy (reported with its
counter-voices — the Joe Kent beat routes its items here); polling that
moves policy; and American self-criticism with news value (leaks,
whistleblowers, State/Pentagon dissent channels). Skip stories with no
Palestinian angle. When in doubt, ask: does this change what a reader in
Ramallah, Gaza or the diaspora understands about the capital that arms,
funds and shields the occupation?

## The rules (charter, binding)

1. **One source piece → one story**, `originals/<slug>.en.txt` +
   `<slug>.ar.txt`, header `title:` / `image:` / `category:` / `date:`
   (ISO UTC, never future), then `---`, then body. Category: `uspress` —
   the dedicated "US Press" / «الصحافة الأميركية» section is the desk's
   home on the site. Every item carries an `image:` header. Default:
   `image: /media/times-of-palestine-us-press.svg` — the section's house
   SVG in `originals/media/` (no media-rights entry needed for house
   SVGs). Use a rights-cleared photo instead only when one is available
   WITH a `media-rights.json` entry.
2. **Titles**: ONE active sentence, ≤12 words, actor first, complete
   idea, both languages; Arabic verbal sentence naming the actor (or the
   colon-attribution pattern «نيويورك تايمز: …»). Never a translated EN
   headline.
3. **Attribution protocol**: name the outlet once inline ("the New York
   Times reported", «بحسب ما نشرت صحيفة واشنطن بوست»). Opinion and
   analysis are ALWAYS attributed to their author throughout — the paper
   reports the argument, it does not adopt it. Think-tank material per
   the labelling rule above.
4. **House language**: "the occupied West Bank" / «الضفة الغربية
   المحتلة»; report US officials' claims as claims; quote sparingly (a
   sentence or two of record); write fresh copy in both languages — the
   Arabic is native journalism (الجزيرة نت register), never a
   translation of the English.
5. **Bodies**: 120–250 words per language, paragraphs of 1–3 sentences,
   no memo headings, no sources section, end on a reported fact. Banned
   diction lists apply («قام بـ», «تم»+مصدر, "delve", "underscores"…).
6. **The roundup**: one extra item, "what Washington is reading" — the
   day's American front pages and the loudest think-tank argument, two
   or three sentences each.
7. **Verify before pushing**: run
   `TOP_FEEDS_FILE=tests/fixtures/feeds.json TOP_OFFLINE=1 TOP_ALLOW_RAW_SUMMARIES=1 python3 build.py`
   and confirm every new file passes render checks with no `⚠` diction
   or residue warnings on YOUR files. Fix flags before commit.
8. **Dedupe and beat boundaries**: check `originals/` and the live wire
   before writing — if the newsroom already covered the event, file only
   what the American press adds (the leak, the internal debate, the
   numbers). The **Washington Brief** (`originals/washington-brief-*`)
   remains the desk's own synthesized daily research report — the review
   covers individual source pieces and never replaces it. **Joe Kent**
   items live under his standing beat's discipline. Crypto/financial
   freedom stays ChatGPT's.

## Cadence

Daily, in the morning sweep (the daily-editor cycle runs this skill
beside the Israeli press review). A big Washington day may justify 6–10
items; a quiet one 2–4 plus the roundup. Never zero without saying so in
the cadence note.
