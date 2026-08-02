#!/usr/bin/env python3
"""Bitcoin & financial-freedom desk: one researched EN/AR report every 48 hours.

Uses the OpenAI Responses API with web search to research and file bilingual
reports on the bitcoin/financial-freedom/Palestinian-economy beat. Filed to
originals/ so the main twice-hourly build publishes them without human intervention.

Beat scope:
  - Bitcoin and cryptocurrency adoption in Palestine
  - Financial access restrictions (correspondent banking, PayPal, frozen accounts)
  - The shekel cash crisis in the West Bank
  - HRF / Gladstein research on financial freedom
  - Monetary Authority of Palestine (PMA) policies
  - Alternative payment systems and economic sovereignty

Three rules (same as the investigations desk):
  1. NOTHING IS PUBLISHED THAT ISN'T SOURCED — every factual claim attributed inline.
  2. THE ISSUE, NEVER THE INDIVIDUAL.
  3. FAIL OPEN — a failure never stops the news build.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).parent
TOPICS_FILE = ROOT / "topics.json"
ORIGINALS = ROOT / "originals"
STATE_FILE = ORIGINALS / "_bitcoin_state.json"

MODEL = "gpt-4o"
MIN_WORDS = 450
MIN_SOURCES = 4
MIN_HOURS_BETWEEN_DISPATCHES = 48

# Only pick from the bitcoin category queue; economy topics belong to the investigations desk
BEAT_CATEGORIES = ("bitcoin",)

DESK_SYSTEM = """You are the bitcoin and financial-freedom correspondent of Times of \
Palestine, an independent bilingual Palestinian newsroom. You are writing an original \
in-depth report on the bitcoin/financial-freedom/Palestinian-economy beat.

BEAT SCOPE
Your beat covers how Palestinians engage with money, savings and financial systems \
under occupation: bitcoin and cryptocurrency adoption in Gaza and the West Bank; the \
effects of correspondent banking withdrawal (Israeli banks, international transfers); \
PayPal exclusion and frozen accounts; the shekel cash glut and liquidity crises; \
alternative payment systems; what researchers at the Human Rights Foundation (HRF), \
Gladstein, and the Monetary Authority of Palestine (PMA) have documented. The story is \
always economic sovereignty — not speculation, price movements, or investment advice.

RESEARCH
Use web search extensively before writing — at least six distinct searches. Seek named \
primary sources first: PMA reports, World Bank data, IMF assessments, HRF publications, \
court records, published interviews with named Palestinians describing their experience. \
Then established reporting from named outlets. Search in English and Arabic. Note where \
sources disagree.

EVIDENCE — THESE ARE ABSOLUTE
- Every factual claim must come from a source you actually retrieved in this session. \
Never state a figure, date, name or quotation you did not find.
- Attribute in the text, in the newsroom's voice: "according to PMA data", "HRF reported \
in June", "the World Bank found". A reader must always know who says a thing.
- Where the record is contested, incomplete or unavailable, say so plainly.
- Never invent a source, a link, a statistic or a quotation.

WHO THE REPORTING IS ABOUT — READ THIS TWICE
Report the issue, never the individual. The subject is a system, a policy, a pattern or \
an institution: a banking exclusion regime, a payment system barrier, a regulatory gap, \
a documented adoption trend. Never a person's character or guilt.
- Name a person only where the name IS the public record: an official acting in their \
official capacity, a researcher quoted in their own published work, a party to a \
published case.
- Never assemble an accusation. Do not imply guilt by juxtaposition or insinuation.

WRITING
Straight news prose — the register of a serious wire service. Open with the single most \
important finding. Then evidence, context, what remains unknown. No first person, no \
rhetorical questions, no editorialising, no investment or financial advice. 700-1000 \
words.

WHAT NEVER APPEARS IN A PUBLISHED ARTICLE
No sources list, no footnote markers, no methodology note, no right-of-reply notice, no \
corrections policy, no image credits, no briefing-memo apparatus: no "What is \
unresolved", "Unanswered questions", "Key takeaways", "Conclusion", "Bottom line" — \
what is unknown is reported in prose sentences, the way a newspaper writes it. No \
sentence about the article itself.

OUTPUT FORMAT — follow exactly
Begin your reply with TITLE: — no preamble, no "I'll research this now".
Line 1: TITLE: <one short complete sentence, at most 10 words, no colon-subtitle>
The TITLE is ACTIVE VOICE and names WHO does WHAT to WHOM — never passive ("was \
blocked", "is excluded"), never agentless hedges ("faces barriers", "comes under \
pressure") when the actor is known.
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

THIS IS A REWRITE, NOT A TRANSLATION. An Arabic reader must never sense an English \
sentence underneath. Write it as the Arabic press writes — the register of الجزيرة نت \
and عرب 48 and وكالة معاً: natural Modern Standard Arabic news prose, verbal sentence \
openings, Arabic connectors (فيما، إذ، في حين، غير أنّ) instead of calqued بينما/حيث \
chains, Arabic quotation marks «», correct Palestinian proper nouns and place names \
(القدس، الضفة الغربية، قطاع غزة، الاحتلال), and Arabic conventions for numbers and \
dates (تموز/يوليو). Every fact, figure, attribution and denial must survive exactly — \
add nothing, drop nothing, soften nothing.

THE HEADLINE IS WRITTEN FRESH, IN ARABIC, FOR ARABS — never translated from the \
English one. Compose it the way Arabic front pages do. The live patterns:
- verbal sentence: «البنوك الإسرائيلية تقطع خدماتها عن الضفة في تصعيد مالي جديد»
- the two-dot pivot: «بعد حصار مصرفي متصاعد.. الفلسطينيون يلجؤون إلى العملات المشفرة»
- colon attribution: «تقرير حقوقي: الاحتلال يعزل الاقتصاد الفلسطيني عن النظام المالي الدولي»
- the direct question: «هل يتحول البيتكوين إلى شريان اقتصادي للفلسطينيين المحاصرين؟»
Choose the pattern that fits the story. Never mirror the English headline's syntax, \
never chain clauses with و the way English chains with "and", and never write a \
copular headline (X هو Y) where a verbal one is possible. The headline is ALWAYS \
المبني للمعلوم and names the actor explicitly.

OUTPUT FORMAT — follow exactly
Begin your reply with TITLE: — no preamble of any kind.
Line 1: TITLE: <the Arabic headline — one short complete sentence, at most 9 words>
Line 2: DEK: <one Arabic sentence, at most 30 words>
Then a blank line, then the body in plain paragraphs separated by blank lines, no \
markdown. Then a blank line, then a final block beginning SOURCES: with the same \
source list, outlet names left in their original script."""

ILLUSTRATION_SYSTEM = """You are the graphics desk of Times of Palestine. You will \
be given a news report. Produce ONE original SVG illustration for it — the lede image \
readers see first. Output ONLY the SVG markup, nothing else: no prose, no markdown fences.

HOUSE STYLE — match the existing graphics exactly:
- 1600x900 viewBox; dark gradient background (#111214 to #1d1e21); a 22px red \
(#8a1f2d) bar and 8px green (#286344) bar down the left edge
- palette: red #8a1f2d/#C8102E, green #286344/#59a97d, gold #c7a86b, ivory #f2eee8, \
muted #aaa9a5; font stacks: "Libre Franklin",Arial for Latin, Cairo,Arial for Arabic, \
"Source Serif 4",Georgia for display
- SUBJECT-SPECIFIC: draw the thing the story is about — a device, a document, a \
building, a map shape, a flow between actors, a chart of the report's own numbers. \
Simple bold shapes, generous spacing; never clip art clutter.
- bilingual: a short English label/title AND its Arabic counterpart on the canvas
- accessibility: include <title> and <desc> tags
- DATA HONESTY: any number, date or name on the canvas must appear in the report. \
No decorative fake data.
- TECHNICAL LIMITS (hard): pure static SVG only — no <script>, no event handlers, \
no external references of any kind (no <image>, no href to any URL, no \
<foreignObject>), no CSS imports; under 40KB."""

_SVG_FORBIDDEN = ("<script", "onload=", "onerror=", "onclick=", "javascript:",
                  "<image", "<foreignObject", "href=\"http", "href='http",
                  "@import", "url(http")


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _pick_topic(topics, state):
    """Next unwritten bitcoin topic; once all are written, the least recently written."""
    beat_topics = [t for t in topics if t.get("cat") in BEAT_CATEGORIES]
    if not beat_topics:
        return None
    done = state.get("done", {})
    for t in beat_topics:
        if t["id"] not in done:
            return t
    return min(beat_topics, key=lambda t: done.get(t["id"], ""))


def _parse(text):
    """Split the desk's output into title, dek, body and sources."""
    text = text.strip()
    # Strip OpenAI citation markers (【4†source】 style) from web search results
    text = re.sub(r"【[^】]*】", "", text).strip()
    # If model adds a preamble before TITLE:, skip to the first TITLE:
    cut = text.find("TITLE:")
    if cut > 0:
        text = text[cut:]
    m_title = re.search(r"^TITLE:\s*(.+)$", text, re.M)
    m_dek = re.search(r"^DEK:\s*(.+)$", text, re.M)
    m_src = re.search(r"^SOURCES:\s*(.*)$", text, re.M | re.S)
    if not m_title:
        return None, "missing TITLE line"
    if not m_dek:
        return None, "missing DEK line"
    if not m_src:
        return None, "missing SOURCES block"
    body = text[m_dek.end():m_src.start()].strip()
    sources = [s.strip(" -–—•\t") for s in m_src.group(1).strip().splitlines() if s.strip()]
    body = re.sub(r"\*\*|__|^#+\s*", "", body, flags=re.M).strip()
    if len(body.split()) < MIN_WORDS:
        return None, f"body too short ({len(body.split())} words < {MIN_WORDS})"
    if len(sources) < MIN_SOURCES:
        return None, f"not enough sources ({len(sources)} < {MIN_SOURCES})"
    return ({
        "title": m_title.group(1).strip().strip('"'),
        "dek": m_dek.group(1).strip().strip('"'),
        "body": body,
        "sources": sources,
    }, None)


def _call_with_search(client, system, user_prompt, max_tokens=16000):
    """Research pass: OpenAI Responses API with web search."""
    response = client.responses.create(
        model=MODEL,
        instructions=system,
        input=user_prompt,
        tools=[{"type": "web_search_preview"}],
        max_output_tokens=max_tokens,
    )
    return response.output_text.strip()


def _call_chat(client, system, user_prompt, max_tokens=16000):
    """Non-search pass (Arabic rewrite, illustration): Chat Completions API."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _clean_svg(text):
    """Return validated SVG markup or None. Never publish active content."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.S).strip()
    if not text.startswith("<svg") or not text.rstrip().endswith("</svg>"):
        return None
    if len(text) > 60000:
        return None
    low = text.lower()
    if any(marker in low for marker in _SVG_FORBIDDEN):
        return None
    try:
        import xml.etree.ElementTree as _ET
        _ET.fromstring(text)
    except Exception:
        return None
    return text


def _make_illustration(client, parsed_en, topic, now):
    """Draw the lede SVG. Fail-open: returns None on any problem."""
    try:
        report = f"TITLE: {parsed_en['title']}\n\n{parsed_en['body'][:6000]}"
        raw = _call_chat(client, ILLUSTRATION_SYSTEM, report, max_tokens=12000)
        svg = _clean_svg(raw)
        if not svg:
            print("bitcoin-desk: illustration pass produced unusable SVG — using category cover")
            return None
        name = f"times-of-palestine-bitcoin-dispatch-{now.strftime('%Y-%m-%d')}-{topic['id']}.svg"
        media = ORIGINALS / "media"
        media.mkdir(exist_ok=True)
        (media / name).write_text(svg, encoding="utf-8")
        return f"/media/{name}"
    except Exception as e:
        print(f"bitcoin-desk: illustration pass failed ({type(e).__name__}) — using category cover")
        return None


def _file_content(topic, parsed, now):
    body = parsed["body"]
    head = (f"title: {parsed['title']}\n"
            f"category: {topic['cat']}\n"
            f"date: {now.isoformat()}\n"
            f"maxAgeHours: 720\n")
    if parsed.get("image"):
        head += f"image: {parsed['image']}\n"
    return head + "---\n" + body + "\n"


def _write_pair(topic, parsed_en, parsed_ar, now):
    """Stage both editions atomically before exposing to the live originals glob."""
    ORIGINALS.mkdir(exist_ok=True)
    date_str = now.strftime("%Y-%m-%d")
    slug = f"bitcoin-dispatch-{date_str}-{topic['id']}"
    destinations = {
        lang: ORIGINALS / f"{slug}.{lang}.txt"
        for lang in ("en", "ar")
    }
    existing = [path.name for path in destinations.values() if path.exists()]
    if existing:
        raise FileExistsError(
            f"refusing to overwrite published dispatch: {', '.join(existing)}")
    staged = []
    try:
        for lang, parsed in (("en", parsed_en), ("ar", parsed_ar)):
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=ORIGINALS, delete=False
            ) as handle:
                handle.write(_file_content(topic, parsed, now))
                staged.append((Path(handle.name), destinations[lang]))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)
    return slug


def _hours_since_last_dispatch(state, now):
    last = state.get("last_filed")
    if not last:
        return float("inf")
    try:
        last_dt = datetime.fromisoformat(last)
        return (now - last_dt).total_seconds() / 3600
    except Exception:
        return float("inf")


def _save_state(state, now, topic_id=None, error=None):
    try:
        ORIGINALS.mkdir(exist_ok=True)
        state["last_attempt"] = now.isoformat()
        if topic_id:
            state["last_filed"] = now.isoformat()
            state.setdefault("done", {})[topic_id] = now.isoformat()
        if error:
            state["error"] = error
        else:
            state.pop("error", None)
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _run():
    now = datetime.now(timezone.utc)
    state = _load(STATE_FILE, {})

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "bitcoin-desk: no OPENAI_API_KEY — skipped"

    hours_since = _hours_since_last_dispatch(state, now)
    if hours_since < MIN_HOURS_BETWEEN_DISPATCHES:
        return (f"bitcoin-desk: last dispatch was {hours_since:.1f}h ago "
                f"(minimum {MIN_HOURS_BETWEEN_DISPATCHES}h) — skipped")

    topics = (_load(TOPICS_FILE, {}) or {}).get("topics") or []
    topic = _pick_topic(topics, state)
    if not topic:
        return "bitcoin-desk: no bitcoin topics in topics.json — skipped"

    import openai
    client = openai.OpenAI(api_key=re.sub(r"\s+", "", api_key))

    brief = (f"Report this story for publication today.\n\n"
             f"WORKING TITLE: {topic['en']}\n\n"
             f"THE REPORTING QUESTION: {topic['q']}\n\n"
             f"Research it now using web search, then write the report.")

    try:
        english = _call_with_search(client, DESK_SYSTEM, brief)
    except Exception as e:
        err = f"research pass failed ({type(e).__name__}: {e})"
        _save_state(state, now, error=err)
        return f"bitcoin-desk: {err} — nothing published"

    if english.strip().upper().startswith("INSUFFICIENT"):
        _save_state(state, now, topic_id=topic["id"])
        return (f"bitcoin-desk: '{topic['id']}' — desk found the record too thin; "
                "nothing published")

    parsed_en, parse_error = _parse(english)
    if not parsed_en:
        err = f"English parse failed ({parse_error})"
        _save_state(state, now, error=err)
        return (f"bitcoin-desk: '{topic['id']}' — output failed sourcing checks; "
                f"nothing published. [{err}] "
                f"[{len(english)} chars, "
                f"has TITLE={'TITLE:' in english} DEK={'DEK:' in english} "
                f"SOURCES={'SOURCES:' in english}] "
                f"opens: {english[:160]!r}")

    try:
        arabic = _call_chat(client, ARABIC_SYSTEM, english)
    except Exception as e:
        err = f"Arabic pass failed ({type(e).__name__}: {e})"
        _save_state(state, now, error=err)
        return f"bitcoin-desk: '{topic['id']}' — {err}; nothing published"

    parsed_ar, ar_error = _parse(arabic)
    if not parsed_ar:
        err = f"Arabic parse failed ({ar_error})"
        _save_state(state, now, error=err)
        return (f"bitcoin-desk: '{topic['id']}' — English OK but Arabic failed; "
                f"nothing published. [{err}]")

    lede = _make_illustration(client, parsed_en, topic, now)
    if lede:
        parsed_en["image"] = lede
        parsed_ar["image"] = lede

    slug = _write_pair(topic, parsed_en, parsed_ar, now)
    _save_state(state, now, topic_id=topic["id"])
    return (f"bitcoin-desk: filed '{slug}' — "
            f"{len(parsed_en['body'].split())} words EN, "
            f"{len(parsed_ar['body'].split())} words AR, "
            f"{len(parsed_en['sources'])} sources")


def run():
    """Run the desk without letting any failure stop the news build."""
    try:
        return _run()
    except Exception as error:
        now = datetime.now(timezone.utc)
        state = _load(STATE_FILE, {})
        _save_state(state, now, error=f"stage failed ({type(error).__name__}: {error})")
        return (f"bitcoin-desk: stage failed ({type(error).__name__}: {error}) "
                "— news build continues")


if __name__ == "__main__":
    print(run())
