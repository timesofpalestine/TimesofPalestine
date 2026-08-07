---
name: israeli-press-review
description: Daily Israeli press review for Times of Palestine — sweep the Hebrew and English Israeli press, select what matters to Palestinian readers, and publish each piece as its own bilingual original under the house contract. Use when the owner says "run the press review", "sweep the Israeli papers", "what does the Hebrew press say", or supplies a translated bulletin (e.g. an al-Masdar docx) to write up. Also runs inside the daily editor cycle each morning.
---

# Israeli press review — the daily desk

Times of Palestine reads the Israeli press so its readers don't have to.
Every run produces standalone news items — one story per source article —
in BOTH editions, plus one front-pages roundup. Owner directive 2026-08-06;
launch batch: `originals/*-2026-08-06.*` (twelve items from issue 11535 of
the al-Masdar bulletin).

## Sources to sweep — HEBREW FIRST (owner order 2026-08-07)

The desk reads the Hebrew press in Hebrew and translates in-house. Never
depend on anyone else's translation layer — not a bulletin's, not an
aggregator's. The sweep starts with the in-repo wire:

```
python3 israeli_press_fetch.py --hours 36
```

It pulls the Hebrew (and English) RSS feeds listed in
`editorial/israeli-press-feeds.json` — Ynet, Maariv, Israel Hayom, Walla,
Haaretz Hebrew, plus the English editions — and prints headline, timestamp,
summary and link per outlet, in the source language. From that digest,
select per the relevance test below, then WebFetch each chosen article's
URL and work from the full Hebrew text: lock the facts, then compose
fresh English and fresh Arabic — never chain-translate through a third
language. (The wire is fail-open; if a feed dies, WebFetch the outlet's
homepage or fall back to WebSearch. In sandboxes whose egress blocks
Israeli domains, WebSearch is the fallback and the item notes nothing —
CI runners have open egress and the wire works there.)

Also sweep the **think tanks** (label them as such, always): INSS, BESA
(Begin-Sadat), JISS, Misgav, the Moshe Dayan Center.

**Owner-supplied bulletins** (al-Masdar and similar) are a CROSS-CHECK,
not a source: use them to catch stories the wire missed, then find and
read the underlying Hebrew article and write from it. Never republish the
bulletin's translation text itself; it is someone's copyrighted work.

## What is relevant

Pick items a Palestinian reader needs: occupation and settlement policy,
army operations and their internal Israeli debate, Gaza policy and the
ceasefire file, Jerusalem, prisoners, home demolitions, the Knesset
election's Palestinian stakes (kingmaker arithmetic, annexation platforms,
Arab lists), regional files that bear on Palestinians (Lebanon, Iran,
corridors, normalization), and Israeli self-criticism with news value
(state violence, incitement, accountability reporting). Skip stories with
no Palestinian angle. When in doubt, ask: does this change what a reader
in Ramallah, Gaza or the diaspora understands about the forces deciding
their lives?

## The rules (charter, binding)

1. **One source article → one story**, `originals/<slug>.en.txt` +
   `<slug>.ar.txt`, header `title:` / `category:` / `date:` (ISO UTC, never
   future), then `---`, then body. Category: `israelipress` — the
   dedicated "Israeli Press" / «الصحافة الإسرائيلية» section (owner
   decision 2026-08-06) is the desk's home on the site.
2. **Titles**: ONE active sentence, ≤12 words, actor first, complete idea,
   both languages; Arabic verbal sentence naming the actor (or the
   colon-attribution pattern «هآرتس: …»). Never a translated EN headline.
3. **Attribution protocol**: name the outlet once inline ("the Israeli
   daily Maariv reported", «بحسب ما نشرت صحيفة معاريف»). Opinion and
   analysis are ALWAYS attributed to their author throughout ("Ben-Yishai
   wrote", "in his telling") — the paper reports the argument, it does not
   adopt it. Think-tank papers get their institutional identity and lean
   stated plainly in the body.
4. **House language**: "the occupied West Bank" / «الضفة الغربية المحتلة»,
   never "Judea and Samaria" outside a direct quote; report Israeli
   claims as claims; quote sparingly (a sentence or two of record, e.g. a
   politician's own words); write fresh copy in both languages — the
   Arabic is native journalism, never a translation of the English.
5. **Bodies**: 120–250 words per language, paragraphs of 1–3 sentences,
   no memo headings, no sources section, end on a reported fact. Banned
   diction lists apply («قام بـ», «تم»+مصدر, "delve", "underscores"…).
6. **The roundup**: one extra item, "what the front pages say", walking
   the four main dailies' leads in two or three sentences each.
7. **Verify before pushing**: run
   `TOP_FEEDS_FILE=tests/fixtures/feeds.json TOP_OFFLINE=1 TOP_ALLOW_RAW_SUMMARIES=1 python3 build.py`
   and confirm every new file passes render checks with no `⚠` diction or
   residue warnings on YOUR files. Fix flags before commit.
8. **Dedupe**: check `originals/` and the live wire before writing — if
   the newsroom already covered the event, file only what the Israeli
   press adds (the admission, the internal debate, the numbers).

## Cadence

Daily, in the morning sweep (the daily-editor cycle runs this skill's
checklist). A big news day may justify 8–12 items; a quiet one 3–5 plus
the roundup. When the owner supplies a bulletin, write up each full
article in it, as on 2026-08-06.
