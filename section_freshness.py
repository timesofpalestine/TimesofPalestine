"""Section-freshness ledger — owner order 2026-08-11.

Every section of the paper, in BOTH editions, updates at least daily
("the page is alive" applies to sections, not only the front). This module
is the newsroom's single measure of that promise:

- `report()` scans the two durable story ledgers — `story-archive/` (every
  published story persists there with cat/lang/date) and `originals/`
  headers — and computes, per language and section, the newest story and
  its age.
- `build.py` writes the report to `dist/section-freshness.json` every build
  and announces stale sections loudly in the log.
- `originals_gen.py` (the investigations desk) reads `stale_sections()` and
  targets its next report at the stalest section that has a queued topic.
- The daily editor cycle treats every stale section as a same-day
  assignment.

Thresholds live here so the owner can tune them in one place. `archive` is
exempt (owner-supplied material only). Everything is fail-open: a broken
ledger disables steering and warnings, never the build. Stdlib only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent

# The site's sections (the publishing contract's category list).
SECTIONS = [
    "gaza", "westbank", "politics", "economy", "accountability", "research",
    "bitcoin", "diaspora", "arts", "sports", "social", "opinion", "news",
    "humans", "health", "archive", "arabaid", "women", "israelipress",
    "uspress", "prisoners", "pal48",
]

DEFAULT_STALE_HOURS = 24
STALE_OVERRIDES = {
    "archive": None,   # owner-supplied scans only — never auto-assigned
    "research": 96,    # long-form research runs on its own clock
    "bitcoin": 72,     # the dispatch desk files every 48h by owner-approved cadence
    "social": 72,      # telegram-sourced surface, follows its channels
}

_HDR_DATE_RX = re.compile(r"^date:\s*(.+)$", re.M)
_HDR_CAT_RX = re.compile(r"^category:\s*(\S+)", re.M)
_ORIGINAL_LANG_RX = re.compile(r"\.(en|ar)\.txt$")


def _parse_dt(value):
    try:
        value = (value or "").strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _iter_stories(root):
    """Yield (lang, cat, datetime) for every story either ledger knows."""
    for lang in ("en", "ar"):
        arch = root / "story-archive" / lang
        if arch.is_dir():
            for f in arch.glob("*.json"):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                dt = _parse_dt(str(d.get("date", "")))
                cat = d.get("cat") or d.get("category")
                if dt and cat:
                    yield lang, cat, dt
    originals = root / "originals"
    if originals.is_dir():
        for f in originals.glob("*.txt"):
            m = _ORIGINAL_LANG_RX.search(f.name)
            if not m:
                continue
            try:
                head = f.read_text(encoding="utf-8")[:2000]
            except Exception:
                continue
            dm, cm = _HDR_DATE_RX.search(head), _HDR_CAT_RX.search(head)
            if not (dm and cm):
                continue
            dt = _parse_dt(dm.group(1))
            if dt:
                yield m.group(1), cm.group(1).strip(), dt


def newest_by_section(root=ROOT):
    """{lang: {section: newest datetime or None}} over both ledgers."""
    newest = {lang: {cat: None for cat in SECTIONS} for lang in ("en", "ar")}
    for lang, cat, dt in _iter_stories(root):
        if cat in newest[lang] and (newest[lang][cat] is None or dt > newest[lang][cat]):
            newest[lang][cat] = dt
    return newest


def threshold(cat):
    return STALE_OVERRIDES.get(cat, DEFAULT_STALE_HOURS)


def report(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    newest = newest_by_section(root)
    out = {"generated": now.isoformat(), "defaultStaleHours": DEFAULT_STALE_HOURS,
           "sections": {}, "stale": []}
    for lang in ("en", "ar"):
        out["sections"][lang] = {}
        for cat in SECTIONS:
            dt = newest[lang][cat]
            age = round((now - dt).total_seconds() / 3600, 1) if dt else None
            limit = threshold(cat)
            stale = bool(limit is not None and (age is None or age > limit))
            out["sections"][lang][cat] = {
                "newest": dt.isoformat() if dt else None,
                "ageHours": age,
                "staleAfterHours": limit,
                "stale": stale,
            }
            if stale:
                out["stale"].append({"lang": lang, "cat": cat,
                                     "ageHours": age, "staleAfterHours": limit})
    # Worst first; a section with no story at all outranks everything.
    out["stale"].sort(key=lambda s: -(s["ageHours"] if s["ageHours"] is not None else 1e9))
    return out


def stale_sections(root=ROOT, now=None):
    """Language-merged staleness for desk steering: [(cat, worst_age_hours)],
    stale sections only, worst first. A section missing in either edition
    counts as infinitely old — both editions are first-class."""
    rep = report(root, now)
    worst = {}
    for s in rep["stale"]:
        age = s["ageHours"] if s["ageHours"] is not None else float("inf")
        worst[s["cat"]] = max(worst.get(s["cat"], 0), age)
    return sorted(worst.items(), key=lambda kv: -kv[1])


def main():
    rep = report()
    print(f"section freshness @ {rep['generated']}")
    for lang in ("en", "ar"):
        for cat in SECTIONS:
            row = rep["sections"][lang][cat]
            mark = "STALE" if row["stale"] else ("exempt" if row["staleAfterHours"] is None else "ok")
            age = "never" if row["ageHours"] is None else f"{row['ageHours']:.0f}h"
            print(f"  {lang}/{cat:<14} newest {age:>6}  target "
                  f"{row['staleAfterHours'] or '—':>3}  {mark}")


if __name__ == "__main__":
    main()
