#!/usr/bin/env python3
"""Persistent story archive — a published link never dies.

The front page is alive (charter): wire items rotate out of their upstream
feeds and off the site within days, and every build wipes dist/<lang>/story/
before re-rendering only what is currently live. But the short share links
(/{lang}/story/<pid>.html) go OUT into the world — the Telegram channel,
WhatsApp shares, search results — and a channel post is forever. Owner order
2026-08-09, after readers hit the 404 page from old Telegram posts: once a
story page has shipped, its permalink keeps resolving on every future build.

Mechanics: while rendering, build.py hands every published story to save(),
which persists exactly the fields the story renderer needs as one small JSON
file per story and language under story-archive/<lang>/<pid>.json. The
workflow's post-deploy persist step commits new files back to the repo (the
same step that persists generated investigations), so the archive survives
the fresh checkout of the next build. Each build then load()s the archived
stories that are no longer live and re-renders their pages — current site
chrome, same URL, same bare-pid share stub.

Archived stories stay out of the front page, the feeds, the sitemaps and
the delivery outboxes: they exist so old links keep resolving, never to
compete with the live news cycle. Retracted pids are excluded by the
caller and never come back through this path.

Offline/fixture builds (TOP_OFFLINE=1) skip the archive entirely unless
STORY_ARCHIVE_DIR points somewhere private, so tests stay hermetic and
never write repository state. Stdlib only (charter rule 6).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Every field the story renderer, the redirect stub, the section-archive
# card and copy_media read from an item. Dates serialize as ISO 8601.
FIELDS = (
    "pid", "lang", "title", "dek", "brief", "image", "media", "link",
    "source", "source_url", "source_id", "cat", "date", "modified",
    "original", "corroborating_sources", "max_age_hours", "score",
)
_DATE_FIELDS = ("date", "modified")


def archive_dir() -> Path | None:
    """The archive location, or None when archiving is disabled."""
    override = os.environ.get("STORY_ARCHIVE_DIR")
    if override:
        return Path(override)
    if os.environ.get("TOP_OFFLINE") == "1":
        return None  # fixture builds must not read or write repo state
    return ROOT / "story-archive"


def save(item: dict) -> None:
    """Persist one published story; quietly a no-op when disabled.

    Re-saves on content change (a correction, a refreshed rewrite) so the
    archived copy always matches the last version that actually shipped.
    """
    base = archive_dir()
    if base is None:
        return
    record = {}
    for field in FIELDS:
        value = item.get(field)
        if isinstance(value, datetime):
            value = value.isoformat()
        record[field] = value
    path = base / item["lang"] / f"{item['pid']}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True)
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == payload:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:  # archiving must never block the news build
        print(f"::warning::story archive: could not save {item['pid']} ({exc})")


def load(lang: str, exclude: set[str] = frozenset()) -> list[dict]:
    """Archived stories for one language, newest first.

    `exclude` carries the currently-live pids (they render from the live
    pipeline) and the retracted pids (takedowns stay down on every route).
    A corrupt file is warned about and skipped — one bad record must never
    stop the newsroom.
    """
    base = archive_dir()
    if base is None or not (base / lang).is_dir():
        return []
    items = []
    for path in sorted((base / lang).glob("*.json")):
        if path.stem in exclude:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            for field in _DATE_FIELDS:
                if record.get(field):
                    record[field] = datetime.fromisoformat(record[field])
            if not (record.get("pid") and record.get("title")
                    and record.get("cat") and record.get("date")):
                raise ValueError("missing pid/title/cat/date")
            # Null-valued optional fields must load as ABSENT keys — the
            # renderer reads them with .get(field, default) and a stored
            # null would shadow the default. Fields the renderer subscripts
            # directly are restored with their natural empty values.
            record = {k: v for k, v in record.items() if v is not None}
            record.setdefault("image", None)
            record.setdefault("dek", "")
            record.setdefault("link", "")
            record.setdefault("source", "")
            record.setdefault("source_url", "")
            record.setdefault("source_id", "")
            record.setdefault("score", 0.0)
            record.setdefault("lang", lang)
            record["archived"] = True
        except (ValueError, OSError) as exc:
            print(f"::warning::story archive: skipping {path.name} ({exc})")
            continue
        items.append(record)
    items.sort(key=lambda r: r["date"], reverse=True)
    return items
