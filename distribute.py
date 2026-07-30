#!/usr/bin/env python3
"""Deliver the validated outbox after GitHub Pages deployment succeeds."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import seo_extras
from publishing import (
    BuildHealth, PublishingError, is_public_http_url, parse_timestamp, utc_iso,
)


def load_outbox(dist):
    path = dist / "distribution-outbox.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1 or not isinstance(raw.get("items"), list):
        raise PublishingError("invalid distribution outbox")
    base_url = raw.get("baseUrl")
    if not isinstance(base_url, str) or not is_public_http_url(base_url):
        raise PublishingError("distribution outbox contains invalid baseUrl")
    rows = {"en": [], "ar": []}
    for item in raw["items"]:
        if item.get("lang") not in rows:
            raise PublishingError("outbox contains unsupported language")
        published = parse_timestamp(item.get("date", ""))
        if not published:
            raise PublishingError("outbox contains invalid publication time")
        record = dict(item)
        record["date"] = published
        record["modified"] = (
            parse_timestamp(item["modified"]) if item.get("modified") else None)
        rows[item["lang"]].append(record)
    return base_url.rstrip("/"), (("en", rows["en"]), ("ar", rows["ar"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    try:
        base_url, langs_items = load_outbox(args.dist)
        health = BuildHealth(datetime.now(timezone.utc))
        seo_extras.deliver(args.dist, langs_items, base_url, health)
        report = {
            "schemaVersion": 1,
            "completedAt": utc_iso(datetime.now(timezone.utc)),
            "connectors": health.connectors,
        }
        if args.summary:
            print("## Post-deployment distribution")
            print()
            for name, status in sorted(health.connectors.items()):
                print(f"- {name}: **{status}**")
        else:
            print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, PublishingError) as exc:
        print(f"distribution: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
