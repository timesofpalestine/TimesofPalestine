#!/usr/bin/env python3
"""Editor-run investigation draft generator: one researched EN/AR draft.

This command is deliberately outside the deploy workflow. Each run checks whether
a draft was already written this UTC hour. If not, it takes the next
topic from topics.json, researches it with live web search, writes the report in
English, renders it in Arabic, and drops both into the gitignored
`.editorial-drafts/` directory. An editor must inspect and promote an exact version
with `python review.py promote <topic-id> --reviewer <name>`.

Three rules make this safe enough to publish unattended:

  1. NOTHING IS PUBLISHED THAT ISN'T SOURCED. The desk must cite named,
     published sources it actually retrieved. If the research does not support a
     report, it returns INSUFFICIENT and nothing is written. Silence beats
     invention on a news site.
  2. THE ISSUE, NEVER THE INDIVIDUAL. No topic is avoided for being
     uncomfortable, but the subject is always a system, a policy or a pattern —
     never a person's guilt. The desk may not assemble an accusation.
  3. DRAFT ONLY. This module cannot place content in the live originals directory.

Cost: roughly one Opus research pass plus a shorter Arabic pass per report.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TOPICS_FILE = ROOT / "topics.json"
ORIGINALS = ROOT / "originals"
DRAFTS = ROOT / ".editorial-drafts"
STATE_FILE = DRAFTS / "_state.json"

MODEL = "claude-opus-5"
# Server-side search. The tool identifier has changed before, and a wrong one is a
# 400 that would leave the desk silently doing nothing, so try the current one
# first and fall back to the older identifier rather than failing shut.
SEARCH_TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 12}]
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
- Where a court, audit body, parliament or rights organisation has published a \
finding, report the finding and say plainly who made it. That is the record speaking. \
Where a response or denial exists, carry it in the same passage; where none is on \
record, say that none is on record.
- Where the record is contested, incomplete or unavailable, say so plainly. A gap \
honestly named is worth more than a gap filled in.
- Never invent a source, a link, a statistic or a quotation.

WHO THE REPORTING IS ABOUT — READ THIS TWICE
Report the issue, never the individual. The subject of every piece is a system, a \
policy, a pattern or an institution: impunity, concentration of ownership, a permit \
regime, a process that stalled, a rule that is not enforced. It is never a person's \
character, and it is never a person's guilt.
- Avoid no topic because it is uncomfortable. Corruption, nepotism, killings that went \
unpunished, who profits — all of it is reportable. Report it structurally: what the \
rules are, whether they were applied, what the published record shows, what is missing.
- Name a person only where the name IS the public record and the story cannot be told \
without it: someone whose case is publicly known, an office-holder acting in their \
official capacity, a party to a published judgment, or someone quoted in their own \
words. Never name relatives, private individuals, or anyone not already central to the \
public record.
- Never assemble an accusation. Do not imply guilt, do not link a person to wrongdoing \
by juxtaposition or insinuation, and do not let a sequence of true sentences add up to \
a charge no source has made.
- Where responsibility has not been established, that is the story: say that it has not \
been established, and report the accountability gap itself. An unanswered question, \
clearly stated, is stronger journalism than a name you cannot stand behind.

WRITING
Straight, unshowy news prose — the register of a serious wire service, not an essay. \
Open with the single most important finding. Then evidence, context, and what remains \
unknown. No first person, no rhetorical questions, no editorialising, no calls to \
action. Sober about atrocity: specific, sourced and exact does more work than \
adjectives. 700-1000 words.

Structure it the way a reader actually reads. Lead with the finding, not the \
background. Keep paragraphs to one to three sentences. Prefer a concrete number to an \
adjective, and a plain word to an institutional one. Put the attribution inside the \
sentence that carries the claim, so a reader never has to look elsewhere to learn who \
says it. Close on what is still unresolved or what happens next — never on a summary \
of what you just wrote.

WHAT NEVER APPEARS IN A PUBLISHED ARTICLE
This is a news website, not a journal or a case file. The article is the reporting and \
nothing else. Never append, and never write, any of the following:
- a sources, references or bibliography list, or footnote markers of any kind such as \
[1] or [^ref] — attribution goes inside the sentence, always
- a methodology note explaining how the reporting was done
- a right-of-reply, comment-sought or no-response notice
- a corrections policy, editor's note or update log
- image credits, licence notes or a visual-rights block
- a label announcing what something is: a caption reads as a sentence, never as \
"Visual caption:", and a summary is never headed "Summary:"
- any sentence about the article itself — "this report makes no finding", "as noted \
above", "this article will examine". Report the subject, never the reporting.
If a fact cannot stand on inline attribution, it is not ready to publish. Cut it \
rather than propping it up with apparatus.

OUTPUT FORMAT — follow exactly
Begin your reply with TITLE: — no preamble, no "I'll research this now".
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
Begin your reply with TITLE: — no preamble of any kind.
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
    # The model sometimes opens with a courtesy line ("I'll research this now.") and
    # occasionally runs it straight into TITLE: with no line break, which defeats the
    # ^-anchored match below. Anchor on the first TITLE: instead of throwing away an
    # otherwise complete, sourced report over a stray preamble.
    cut = text.find("TITLE:")
    if cut > 0:
        text = text[cut:]
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


def _call(client, system, messages, tools=None, max_tokens=32000):
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=messages, thinking={"type": "adaptive"})
    if tools:
        kwargs["tools"] = tools
    # Must stream. A research pass with adaptive thinking and a large max_tokens can
    # exceed the SDK's 10-minute non-streaming ceiling, and the SDK refuses the call
    # outright rather than letting it run — which is why the desk filed nothing at all.
    with client.messages.stream(**kwargs) as stream:
        resp = stream.get_final_message()
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _write_file(topic, parsed, lang, now):
    """Emit a gitignored draft that the live builder cannot discover."""
    # Sources are a reporting gate, not page furniture: the parser still requires
    # MIN_SOURCES before anything publishes, but a news article carries its
    # attribution inline ("according to OCHA figures"), never as a bibliography.
    body = parsed["body"]
    head = (f"title: {parsed['title']}\n"
            f"category: {topic['cat']}\n"
            f"date: {now.isoformat()}\n"
            f"origin: investigation\n"
            f"review: required\n"
            f"maxAgeHours: 720\n")
    (DRAFTS / f"{topic['id']}.{lang}.txt").write_text(
        head + "---\n" + body + "\n", encoding="utf-8")


def _run():
    """Write one report if this hour has not had one. Returns a status string."""
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
    DRAFTS.mkdir(exist_ok=True)

    brief = (f"Report this story for publication today.\n\n"
             f"WORKING TITLE: {topic['en']}\n\n"
             f"THE REPORTING QUESTION: {topic['q']}\n\n"
             f"Research it now, then write the report.")
    english, last_err = None, None
    for tool in SEARCH_TOOLS:
        try:
            english = _call(client, DESK_SYSTEM, [{"role": "user", "content": brief}], tools=[tool])
            break
        except Exception as e:
            last_err = e
            if "tool" not in str(e).lower():   # a real failure, not a rejected tool name
                raise
    if english is None:
        # Never write from memory alone: unresearched is unpublishable.
        return f"investigations: web search unavailable ({type(last_err).__name__}: {last_err}) — nothing published"

    if english.strip().upper().startswith("INSUFFICIENT"):
        state.setdefault("done", {})[topic["id"]] = now.isoformat()
        state["last_hour"] = hour
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        return f"investigations: '{topic['id']}' — desk found the record too thin; nothing published"

    parsed_en = _parse(english)
    if not parsed_en:
        state["last_hour"] = hour   # bound the retry: try again next hour, not next build
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        return (f"investigations: '{topic['id']}' — output failed the sourcing checks; nothing published. "
                f"[{len(english)} chars, {len(english.split())} words, "
                f"has TITLE={'TITLE:' in english} DEK={'DEK:' in english} SOURCES={'SOURCES:' in english}] "
                f"opens: {english[:160]!r}")

    arabic = _call(client, ARABIC_SYSTEM, [{"role": "user", "content": english}])
    parsed_ar = _parse(arabic)
    if not parsed_ar:
        state["last_hour"] = hour
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        return (f"investigations: '{topic['id']}' — English filed but Arabic failed; nothing published. "
                f"[{len(arabic)} chars, has SOURCES={'SOURCES:' in arabic}]")

    _write_file(topic, parsed_en, "en", now)
    _write_file(topic, parsed_ar, "ar", now)

    state.setdefault("done", {})[topic["id"]] = now.isoformat()
    state["last_hour"] = hour
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return (f"investigations: filed '{topic['id']}' — {len(parsed_en['body'].split())} words EN, "
            f"{len(parsed_ar['body'].split())} words AR, {len(parsed_en['sources'])} sources")


def _record_failure(msg):
    """Leave a trace on disk so a silent desk is visible without reading Actions logs.

    Also stamps last_hour, which bounds the retry: without it a hard failure repeats
    on every build (~every 25 minutes) instead of once an hour. Never raises.
    """
    try:
        now = datetime.now(timezone.utc)
        state = _load(STATE_FILE, {})
        state["last_hour"] = now.strftime("%Y-%m-%dT%H")
        state["last_attempt"] = now.isoformat()
        state["last_status"] = msg
        DRAFTS.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def run():
    """Generate a local draft; failures are explicit because this is editor-run."""
    return _run()


if __name__ == "__main__":
    print(run())
