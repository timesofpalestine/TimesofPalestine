#!/usr/bin/env python3
"""The investigations desk: one researched original report per hour, EN and AR.

Runs inside the normal build (see .github/workflows/build.yml). Every build it
asks: has a report already been written this UTC hour? If not, it takes the next
topic from topics.json, researches it with live web search, writes the report in
English, renders it in Arabic, and drops both into originals/ — which build.py
already publishes under the Times of Palestine byline with no external link-out.

Three rules make this safe enough to publish unattended:

  1. NOTHING IS PUBLISHED THAT ISN'T SOURCED. The desk must cite named,
     published sources it actually retrieved. If the research does not support a
     report, it returns INSUFFICIENT and nothing is written. Silence beats
     invention on a news site.
  2. NO ALLEGATION WITHOUT ATTRIBUTION. Claims about named living people must be
     carried on the record of a named outlet, court filing or rights
     organisation — never asserted by us — and every denial must be recorded.
  3. FAIL OPEN. Any error here is caught and logged; the news build continues
     regardless. The desk is additive, never load-bearing.

Cost: roughly one Opus research pass plus a shorter Arabic pass per report.
Set INVESTIGATIONS=off in the workflow env to pause it without a code change.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TOPICS_FILE = ROOT / "topics.json"
ORIGINALS = ROOT / "originals"
STATE_FILE = ORIGINALS / "_state.json"

MODEL = "claude-opus-5"
SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 12}
MIN_WORDS = 450          # below this it is a blurb, not a report
MIN_SOURCES = 4          # a report resting on fewer sources is not researched

DESK_SYSTEM = """You are the investigations desk of Times of Palestine, an independent \
Palestinian newsroom. You are writing an original in-depth report for publication.

RESEARCH
Use web search extensively before writing — at least six distinct searches. Search in \
several languages, not only English: Arabic and Hebrew, and where the story reaches \
further, French, Spanish, Turkish, German or Farsi. Seek primary material first: court \
filings and judgments, official statistics, budget documents, corporate registries, UN \
and OCHA data, and reports by named rights organisations (Al-Haq, B'Tselem, Yesh Din, \
HaMoked, Addameer, Amnesty, Human Rights Watch, the Independent Commission for Human \
Rights). Then established reporting by named outlets. Note where sources disagree.

EVIDENCE — THESE ARE ABSOLUTE
- Every factual claim must come from a source you actually retrieved in this session. \
Never state a figure, date, name or quotation you did not find.
- Attribute in the text, in the newsroom's voice: "according to OCHA figures", "Reuters \
reported in March", "the indictment states". A reader must always know who says a thing.
- Claims of wrongdoing about a named living person must be carried on the record of a \
named outlet, court document or rights organisation. Never assert them as our own \
finding. Where the person or institution has denied or responded, say so in the same \
passage. Where no response is on record, write that no response is on record.
- Where the record is contested, incomplete or unavailable, say so plainly. A gap \
honestly named is worth more than a gap filled in.
- Never invent a source, a link, a statistic or a quotation.

WRITING
Straight, unshowy news prose — the register of a serious wire service, not an essay. \
Open with the single most important finding. Then evidence, context, and what remains \
unknown. No first person, no rhetorical questions, no editorialising, no calls to \
action. Sober about atrocity: specific, sourced and exact does more work than \
adjectives. 700-1000 words.

OUTPUT FORMAT — follow exactly
Line 1: TITLE: <a headline of at most 12 words, one sentence, no colon-subtitle>
Line 2: DEK: <one sentence, at most 30 words, saying what the report establishes>
Then a blank line, then the body in plain paragraphs separated by blank lines. Use no \
markdown, no headings, no bullets, no bold.
Then a blank line, then a final block beginning SOURCES: and listing on separate lines \
each source you actually used, as "Outlet or organisation — what it provided".

If your research does not support a publishable report — the material is thin, \
unverifiable, or you would have to speculate — reply with the single word INSUFFICIENT \
and nothing else. That is a correct and valued outcome, not a failure."""

ARABIC_SYSTEM = """You are the Arabic desk of Times of Palestine. You will be given a \
report written by the newsroom in English. Produce the Arabic edition of it.

This is not a literal translation. Write it as an Arabic newsroom writes: natural \
Modern Standard Arabic news register, correct Palestinian and Arabic proper nouns and \
place names (القدس، الضفة الغربية، قطاع غزة، الاحتلال), Arabic conventions for numbers \
and dates. Every fact, figure, attribution and denial must survive exactly — add \
nothing, drop nothing, soften nothing.

OUTPUT FORMAT — follow exactly
Line 1: TITLE: <the Arabic headline, at most 12 words>
Line 2: DEK: <one Arabic sentence, at most 30 words>
Then a blank line, then the body in plain paragraphs separated by blank lines, no \
markdown. Then a blank line, then a final block beginning SOURCES: with the same \
source list, outlet names left in their original script."""


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _pick_topic(topics, state):
    """Next unwritten topic; once all are written, the least recently written."""
    done = state.get("done", {})
    for t in topics:
        if t["id"] not in done:
            return t
    return min(topics, key=lambda t: done.get(t["id"], ""))


def _parse(text):
    """Split the desk's output into title, dek, body and sources. None if malformed."""
    text = text.strip()
    m_title = re.search(r"^TITLE:\s*(.+)$", text, re.M)
    m_dek = re.search(r"^DEK:\s*(.+)$", text, re.M)
    m_src = re.search(r"^SOURCES:\s*(.*)$", text, re.M | re.S)
    if not (m_title and m_dek and m_src):
        return None
    body = text[m_dek.end():m_src.start()].strip()
    sources = [s.strip(" -–—•\t") for s in m_src.group(1).strip().splitlines() if s.strip()]
    body = re.sub(r"\*\*|__|^#+\s*", "", body, flags=re.M).strip()
    if len(body.split()) < MIN_WORDS or len(sources) < MIN_SOURCES:
        return None
    return {
        "title": m_title.group(1).strip().strip('"'),
        "dek": m_dek.group(1).strip().strip('"'),
        "body": body,
        "sources": sources,
    }


def _call(client, system, messages, tools=None, max_tokens=8000):
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=messages, thinking={"type": "adaptive"})
    if tools:
        kwargs["tools"] = tools
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _write_file(topic, parsed, lang, now, sources_label):
    """Emit the originals/<id>.<lang>.txt that build.py already knows how to publish."""
    body = parsed["body"] + "\n\n" + sources_label + "\n" + "\n".join(parsed["sources"])
    head = (f"title: {parsed['title']}\n"
            f"category: {topic['cat']}\n"
            f"date: {now.isoformat()}\n"
            f"maxAgeHours: 720\n")
    (ORIGINALS / f"{topic['id']}.{lang}.txt").write_text(
        head + "---\n" + body + "\n", encoding="utf-8")


def _run():
    """Write one report if this hour has not had one. Returns a status string."""
    if os.environ.get("INVESTIGATIONS", "").lower() in ("off", "0", "false"):
        return "investigations: paused by INVESTIGATIONS env"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "investigations: no API key — skipped"

    now = datetime.now(timezone.utc)
    hour = now.strftime("%Y-%m-%dT%H")
    state = _load(STATE_FILE, {})
    if state.get("last_hour") == hour:
        return f"investigations: already filed for {hour}"

    topics = (_load(TOPICS_FILE, {}) or {}).get("topics") or []
    if not topics:
        return "investigations: topics.json empty"

    import anthropic
    client = anthropic.Anthropic(api_key=re.sub(r"\s+", "", os.environ["ANTHROPIC_API_KEY"]))
    topic = _pick_topic(topics, state)
    ORIGINALS.mkdir(exist_ok=True)

    brief = (f"Report this story for publication today.\n\n"
             f"WORKING TITLE: {topic['en']}\n\n"
             f"THE REPORTING QUESTION: {topic['q']}\n\n"
             f"Research it now, then write the report.")
    english = _call(client, DESK_SYSTEM, [{"role": "user", "content": brief}],
                    tools=[SEARCH_TOOL])

    if english.strip().upper().startswith("INSUFFICIENT"):
        state.setdefault("done", {})[topic["id"]] = now.isoformat()
        state["last_hour"] = hour
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        return f"investigations: '{topic['id']}' — desk found the record too thin; nothing published"

    parsed_en = _parse(english)
    if not parsed_en:
        return f"investigations: '{topic['id']}' — output failed the sourcing checks; nothing published"

    arabic = _call(client, ARABIC_SYSTEM, [{"role": "user", "content": english}])
    parsed_ar = _parse(arabic)
    if not parsed_ar:
        return f"investigations: '{topic['id']}' — English filed but Arabic failed; nothing published"

    _write_file(topic, parsed_en, "en", now, "Sources:")
    _write_file(topic, parsed_ar, "ar", now, "المصادر:")

    state.setdefault("done", {})[topic["id"]] = now.isoformat()
    state["last_hour"] = hour
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return (f"investigations: filed '{topic['id']}' — {len(parsed_en['body'].split())} words EN, "
            f"{len(parsed_ar['body'].split())} words AR, {len(parsed_en['sources'])} sources")


def run():
    """Never raises. The investigations desk must never be able to stop the news."""
    try:
        return _run()
    except Exception as e:
        return f"investigations: stage failed ({type(e).__name__}: {e}) — news build continues"


if __name__ == "__main__":
    print(run())
