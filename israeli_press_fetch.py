#!/usr/bin/env python3
"""Hebrew-first wire for the Israeli press desk (owner directive 2026-08-07).

Pulls the Hebrew (and English) RSS feeds of the Israeli press listed in
editorial/israeli-press-feeds.json and prints a digest — outlet, headline,
link, timestamp, summary — in the source language, so the desk translates
and composes in-house instead of working from third-party bulletin
translations. Owner-supplied bulletins remain a cross-check only.

Stdlib only. Fail-open everywhere: a dead feed warns and is skipped; the
script always exits 0 and never sits in the build path.

Usage:
    python3 israeli_press_fetch.py                 # digest to stdout (markdown)
    python3 israeli_press_fetch.py --hours 36      # freshness window (default 36)
    python3 israeli_press_fetch.py --limit 15      # max items per feed (default 20)
    python3 israeli_press_fetch.py --json out.json # machine-readable copy
    python3 israeli_press_fetch.py --feeds FILE    # alternate feed list (tests)
"""
import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 TimesofPalestine-desk/1.0")
FEEDS_FILE = Path(__file__).parent / "editorial" / "israeli-press-feeds.json"


def strip_html(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_when(text):
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def first_text(node, *paths):
    for p in paths:
        el = node.find(p)
        if el is not None:
            val = el.text or el.get("href")
            if val and val.strip():
                return val.strip()
    return ""


def parse_feed(raw):
    """RSS 2.0 or Atom → list of {title, link, when, summary} dicts."""
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):  # RSS
        items.append({
            "title": strip_html(first_text(it, "title")),
            "link": first_text(it, "link", "guid"),
            "when": parse_when(first_text(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date")),
            "summary": strip_html(first_text(it, "description")),
        })
    if not items:  # Atom
        for it in root.iter("{http://www.w3.org/2005/Atom}entry"):
            items.append({
                "title": strip_html(first_text(it, "{http://www.w3.org/2005/Atom}title")),
                "link": first_text(it, "{http://www.w3.org/2005/Atom}link"),
                "when": parse_when(first_text(it, "{http://www.w3.org/2005/Atom}updated",
                                              "{http://www.w3.org/2005/Atom}published")),
                "summary": strip_html(first_text(it, "{http://www.w3.org/2005/Atom}summary",
                                                 "{http://www.w3.org/2005/Atom}content")),
            })
    return [i for i in items if i["title"]]


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=36.0)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--feeds", metavar="FILE", default=str(FEEDS_FILE))
    args = ap.parse_args()

    try:
        cfg = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"israeli-press wire: cannot read feed list ({e})", file=sys.stderr)
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    digest, dead = [], []
    for feed in cfg.get("feeds", []):
        outlet, url = feed.get("outlet", "?"), feed.get("url", "")
        try:
            items = parse_feed(fetch(url))
        except Exception as e:  # noqa: BLE001 — any feed failure is survivable
            dead.append(f"{outlet}: {type(e).__name__}: {e}")
            continue
        fresh = [i for i in items if i["when"] is None or i["when"] >= cutoff][: args.limit]
        if fresh:
            digest.append({"outlet": outlet, "lang": feed.get("lang", "he"), "items": fresh})

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"# Israeli press wire — {now} (window: last {args.hours:g}h)\n")
    if not digest:
        print("No feeds reachable from this network. Run from CI (open egress) or "
              "fall back to WebSearch per the skill.\n")
    for block in digest:
        print(f"## {block['outlet']} [{block['lang']}]")
        for i in block["items"]:
            when = i["when"].strftime("%H:%M") if i["when"] else "--:--"
            print(f"- {when} · {i['title']}")
            if i["summary"] and i["summary"] != i["title"]:
                print(f"  {i['summary'][:300]}")
            print(f"  {i['link']}")
        print()
    for d in dead:
        print(f"⚠ feed unreachable — {d}", file=sys.stderr)

    if args.json:
        serializable = [
            {**b, "items": [{**i, "when": i["when"].isoformat() if i["when"] else None}
                            for i in b["items"]]}
            for b in digest
        ]
        Path(args.json).write_text(json.dumps(serializable, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
