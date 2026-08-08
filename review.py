#!/usr/bin/env python3
"""Local editorial review CLI.

Full pending content is printed only to this terminal. The committed ledger contains
opaque fingerprints and approval metadata, never queued story text or URLs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import build
from editorial import apply_review_gate, cluster_duplicates, load_reviews
from publishing import PublishingError, revision_review_data, utc_iso

ROOT = Path(__file__).parent
LEDGER = ROOT / "editorial" / "reviews.json"


def current_queue():
    build.HEALTH = build.BuildHealth(datetime.now(timezone.utc))
    for lang in ("en", "ar"):
        for feed in build.FEEDS[lang]:
            build.HEALTH.register_source(feed, lang)
    en_items = build.build_lang("en")
    ar_items = build.build_lang("ar")
    build.generate_briefs(en_items + ar_items)
    # Mirror main(): publishability filter, then the final-headline dedupe
    # pass, then the gate — over third-party copy only (desk originals are
    # never held, so listing them as pending was noise).
    candidates = build.select_publishable_copy(en_items, ar_items)
    candidates = (
        build.dedupe_events([i for i in candidates if i["lang"] == "en"])
        + build.dedupe_events([i for i in candidates if i["lang"] == "ar"]))
    third_party = [i for i in candidates if i.get("source_id") != "top-original"]
    _, held = apply_review_gate(third_party, load_reviews(LEDGER))
    return held


def list_pending(args):
    held = current_queue()
    if args.lang:
        held = [item for item in held if item["lang"] == args.lang]
    for item in held:
        print("=" * 78)
        print(f"{item['lang'].upper()}  {item['review_fingerprint']}")
        print(f"Reasons: {', '.join(item['risk_reasons'])}")
        print(json.dumps(
            revision_review_data(item),
            ensure_ascii=False, indent=2, sort_keys=True,
        ))
    print(f"\n{len(held)} pending exact-version review(s).")
    return 0


def write_ledger(raw):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=LEDGER.parent, delete=False
    ) as handle:
        json.dump(raw, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, LEDGER)


def approve(args):
    if not re.fullmatch(r"[0-9a-f]{64}", args.fingerprint):
        raise PublishingError("fingerprint must be 64 lowercase hexadecimal characters")
    raw = json.loads(LEDGER.read_text(encoding="utf-8"))
    raw["approvals"][args.fingerprint] = {
        "reviewer": args.reviewer,
        "at": utc_iso(datetime.now(timezone.utc)),
    }
    if args.expires:
        expiry = datetime.fromisoformat(args.expires.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise PublishingError("--expires must include a UTC offset or Z")
        raw["approvals"][args.fingerprint]["expires"] = utc_iso(expiry)
    write_ledger(raw)
    print(f"Approved exact version {args.fingerprint[:12]} by {args.reviewer}.")
    return 0


def revoke(args):
    raw = json.loads(LEDGER.read_text(encoding="utf-8"))
    removed = raw["approvals"].pop(args.fingerprint, None)
    write_ledger(raw)
    print("Approval revoked." if removed else "Fingerprint was not approved.")
    return 0


def promote(args):
    drafts = ROOT / ".editorial-drafts"
    pairs = {
        lang: drafts / f"{args.topic_id}.{lang}.txt" for lang in ("en", "ar")
    }
    missing = [str(path) for path in pairs.values() if not path.exists()]
    if missing:
        raise PublishingError(f"missing bilingual draft(s): {', '.join(missing)}")
    destinations = {
        lang: ROOT / "originals" / path.name for lang, path in pairs.items()
    }
    existing = [str(path) for path in destinations.values() if path.exists()]
    if existing:
        raise PublishingError(f"live original already exists: {', '.join(existing)}")
    for lang, source in pairs.items():
        shutil.move(str(source), destinations[lang])
    try:
        promoted = []
        for lang in ("en", "ar"):
            records, _removed = cluster_duplicates(build.load_originals(lang))
            promoted.extend(
                item for item in records
                if item["link"] == f"original:{args.topic_id}.{lang}")
        if len(promoted) != 2:
            raise PublishingError("promoted pair did not load as two validated originals")
        apply_review_gate(promoted, {}, mode="label")
        raw = json.loads(LEDGER.read_text(encoding="utf-8"))
        approved_at = utc_iso(datetime.now(timezone.utc))
        for item in promoted:
            raw["approvals"][item["review_fingerprint"]] = {
                "reviewer": args.reviewer,
                "at": approved_at,
            }
        write_ledger(raw)
    except Exception:
        for lang, destination in destinations.items():
            if destination.exists():
                shutil.move(str(destination), pairs[lang])
        raise
    print(
        f"Promoted and approved bilingual investigation {args.topic_id!r} "
        f"by {args.reviewer}.")
    return 0


def parser():
    root = argparse.ArgumentParser(
        description="Review sensitive stories without persisting their content")
    commands = root.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="fetch and print pending stories locally")
    listing.add_argument("--lang", choices=("en", "ar"))
    listing.set_defaults(func=list_pending)
    approval = commands.add_parser("approve", help="approve an exact fingerprint")
    approval.add_argument("fingerprint")
    approval.add_argument("--reviewer", required=True)
    approval.add_argument("--expires", help="optional UTC ISO-8601 expiry")
    approval.set_defaults(func=approve)
    revocation = commands.add_parser("revoke", help="revoke an approval")
    revocation.add_argument("fingerprint")
    revocation.set_defaults(func=revoke)
    promotion = commands.add_parser(
        "promote", help="validate and promote a bilingual investigation draft")
    promotion.add_argument("topic_id")
    promotion.add_argument("--reviewer", required=True)
    promotion.set_defaults(func=promote)
    return root


def main():
    try:
        args = parser().parse_args()
        return args.func(args)
    except (PublishingError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"review: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
