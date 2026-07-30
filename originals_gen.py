#!/usr/bin/env python3
"""Automated investigations desk: one researched EN/AR report per desk hour.

The normal build invokes this desk before loading originals. A sourced bilingual
report is written directly to `originals/` and can publish in the same build.

Three rules make this safe enough to publish unattended:

  1. NOTHING IS PUBLISHED THAT ISN'T SOURCED. The desk must cite named,
     published sources it actually retrieved. If the research does not support a
     report, it returns INSUFFICIENT and nothing is written. Silence beats
     invention on a news site.
  2. THE ISSUE, NEVER THE INDIVIDUAL. No topic is avoided for being
     uncomfortable, but the subject is always a system, a policy or a pattern —
     never a person's guilt. The desk may not assemble an accusation.
  3. FAIL OPEN. A desk failure is logged but never stops the news build.

Cost: roughly one Opus research pass plus a shorter Arabic pass per report.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).parent
TOPICS_FILE = ROOT / "topics.json"
ORIGINALS = ROOT / "originals"
DRAFTS = ROOT / ".editorial-drafts"
STATE_FILE = ORIGINALS / "_state.json"

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
- briefing-memo apparatus: no "What is unresolved", "Unanswered questions", "Key \
takeaways", "Conclusion", "Bottom line" or similar sections, and never a list of \
questions — what is unknown is reported in prose sentences ("It remains unclear \
which camp the order names"), the way a newspaper writes it
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
    """Split the desk's output into title, dek, body and sources."""
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
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text, getattr(resp, "stop_reason", None)


def _save_state(state, now, hour, error=None):
    try:
        ORIGINALS.mkdir(exist_ok=True)
        state["last_hour"] = hour
        state["last_attempt"] = now.isoformat()
        if error:
            state["error"] = error
        else:
            state.pop("error", None)
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _file_content(topic, parsed, now):
    # Sources are a reporting gate, not page furniture: the parser still requires
    # MIN_SOURCES before anything publishes, but a news article carries its
    # attribution inline ("according to OCHA figures"), never as a bibliography.
    body = parsed["body"]
    head = (f"title: {parsed['title']}\n"
            f"category: {topic['cat']}\n"
            f"date: {now.isoformat()}\n"
            f"maxAgeHours: 720\n")
    return head + "---\n" + body + "\n"


def _write_pair(topic, parsed_en, parsed_ar, now):
    """Stage both editions before exposing either one to the live originals glob."""
    ORIGINALS.mkdir(exist_ok=True)
    publication_id = f"{topic['id']}-{now.strftime('%Y-%m-%d-%H')}"
    destinations = {
        lang: ORIGINALS / f"{publication_id}.{lang}.txt"
        for lang in ("en", "ar")
    }
    existing = [path.name for path in destinations.values() if path.exists()]
    if existing:
        raise FileExistsError(
            f"refusing to overwrite published investigation: {', '.join(existing)}")
    staged = []
    try:
        for lang, parsed in (("en", parsed_en), ("ar", parsed_ar)):
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=ORIGINALS, delete=False
            ) as handle:
                handle.write(_file_content(topic, parsed, now))
                staged.append((
                    Path(handle.name),
                    destinations[lang],
                ))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)
    return publication_id


# The desk files at most one report per desk hour. Three desk hours a day keeps
# research costs around $5/day instead of ~$40/day hourly; 05/12/19 UTC spreads
# publication across the Palestine morning, evening, and US-afternoon news cycles.
DESK_HOURS = (5, 12, 19)

def _run():
    """Write one report if this desk hour has not had one. Returns a status string."""
    now = datetime.now(timezone.utc)
    hour = now.strftime("%Y-%m-%dT%H")
    state = _load(STATE_FILE, {})

    if os.environ.get("INVESTIGATIONS", "").lower() in ("off", "0", "false"):
        return "investigations: paused by INVESTIGATIONS env"
    if now.hour not in DESK_HOURS:
        return f"investigations: outside desk hours {DESK_HOURS} — next at {min((h for h in DESK_HOURS if h > now.hour), default=DESK_HOURS[0]):02d}:00 UTC"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _save_state(state, now, hour, "no API key")
        return "investigations: no API key — skipped"

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
    english, english_stop_reason, last_err = None, None, None
    for tool in SEARCH_TOOLS:
        try:
            english, english_stop_reason = _call(client, DESK_SYSTEM, [{"role": "user", "content": brief}], tools=[tool])
            break
        except Exception as e:
            last_err = e
            if "tool" not in str(e).lower():   # a real failure, not a rejected tool name
                raise
    if english is None:
        # Never write from memory alone: unresearched is unpublishable.
        err = f"web search unavailable ({type(last_err).__name__}: {last_err})"
        _save_state(state, now, hour, err)
        return f"investigations: {err} — nothing published"

    if english.strip().upper().startswith("INSUFFICIENT"):
        state.setdefault("done", {})[topic["id"]] = now.isoformat()
        _save_state(state, now, hour, None)
        return f"investigations: '{topic['id']}' — desk found the record too thin; nothing published"

    parsed_en, parse_error = _parse(english)
    if not parsed_en:
        err = f"English parse failed ({parse_error}); stop_reason={english_stop_reason!r}"
        _save_state(state, now, hour, err)  # bound retry: try again next hour, not next build
        return (f"investigations: '{topic['id']}' — output failed the sourcing checks; nothing published. "
                f"[{err}] "
                f"[{len(english)} chars, {len(english.split())} words, "
                f"has TITLE={'TITLE:' in english} DEK={'DEK:' in english} SOURCES={'SOURCES:' in english}] "
                f"opens: {english[:160]!r}")

    arabic, arabic_stop_reason = _call(client, ARABIC_SYSTEM, [{"role": "user", "content": english}])
    parsed_ar, ar_error = _parse(arabic)
    if not parsed_ar:
        err = f"Arabic parse failed ({ar_error}); stop_reason={arabic_stop_reason!r}"
        _save_state(state, now, hour, err)
        return (f"investigations: '{topic['id']}' — English filed but Arabic failed; nothing published. "
                f"[{err}] "
                f"[{len(arabic)} chars, has SOURCES={'SOURCES:' in arabic}]")

    import longform
    for lang, parsed in (("en", parsed_en), ("ar", parsed_ar)):
        residue = longform.rendered_residue_warnings(
            longform.body_html(parsed["body"]))
        if residue:
            raise ValueError(
                f"{lang} report contains unsafe rendered markup: "
                f"{'; '.join(residue)}")
    publication_id = _write_pair(topic, parsed_en, parsed_ar, now)

    state.setdefault("done", {})[topic["id"]] = now.isoformat()
    _save_state(state, now, hour, None)
    return (f"investigations: filed '{publication_id}' — "
            f"{len(parsed_en['body'].split())} words EN, "
            f"{len(parsed_ar['body'].split())} words AR, {len(parsed_en['sources'])} sources")


def run():
    """Run the desk without allowing a model or network failure to stop the news."""
    try:
        return _run()
    except Exception as error:
        now = datetime.now(timezone.utc)
        hour = now.strftime("%Y-%m-%dT%H")
        state = _load(STATE_FILE, {})
        _save_state(
            state, now, hour,
            f"stage failed ({type(error).__name__}: {error})")
        return (
            f"investigations: stage failed ({type(error).__name__}: {error}) "
            "— news build continues")


if __name__ == "__main__":
    print(run())
