#!/usr/bin/env python3
"""Validate generated publishing surfaces without network access."""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.remote_images = []
        self.jsonld = []
        self.meta_refresh = False
        self._jsonld = False
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"a", "link"} and values.get("href"):
            self.links.append(values["href"])
        if tag in {"img", "script"} and values.get("src"):
            src = values["src"]
            self.links.append(src)
            if tag == "img" and urlsplit(src).scheme in {"http", "https"}:
                self.remote_images.append(src)
        if tag == "meta" and values.get("http-equiv", "").lower() == "refresh":
            self.meta_refresh = True
        if tag == "script" and values.get("type") == "application/ld+json":
            self._jsonld = True
            self._buffer = []

    def handle_data(self, data):
        if self._jsonld:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._jsonld:
            self.jsonld.append("".join(self._buffer))
            self._jsonld = False


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"timestamp is not UTC: {value}")
    return parsed


def internal_path(root, page, target):
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https", "mailto", "tel"} or target.startswith("//"):
        return None
    if parsed.scheme == "data" or not parsed.path:
        return None
    base = "https://timesofpalestine.com/" + page.relative_to(root).as_posix()
    resolved = urlsplit(urljoin(base, target))
    if resolved.netloc != "timesofpalestine.com":
        return None
    relative = unquote(resolved.path.lstrip("/"))
    candidate = root / relative
    if resolved.path.endswith("/"):
        candidate /= "index.html"
    return candidate


def validate(root):
    errors = []
    required = [
        "index.html", "en/index.html", "ar/index.html", "en/rss.xml", "ar/rss.xml",
        "en/feed.json", "ar/feed.json", "sitemap.xml", "news-sitemap.xml",
        "health.json", "review-queue.json", "distribution-outbox.json",
        "manifest.json", "sw.js",
        "assets/site.css", "en/status.html", "ar/status.html",
    ]
    for name in required:
        if not (root / name).is_file():
            errors.append(f"missing required output {name}")

    for path in root.rglob("*.html"):
        parser = DocumentParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root)}: unreadable HTML ({exc})")
            continue
        if parser.meta_refresh and path.name != "index.html":
            errors.append(f"{path.relative_to(root)}: unconditional meta refresh")
        if parser.remote_images:
            errors.append(
                f"{path.relative_to(root)}: remote image hotlink(s): "
                + ", ".join(parser.remote_images[:3]))
        for target in parser.links:
            candidate = internal_path(root, path, target)
            if candidate is not None and not candidate.exists():
                errors.append(
                    f"{path.relative_to(root)}: broken internal target {target}")
        for raw in parser.jsonld:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.relative_to(root)}: invalid JSON-LD ({exc})")
                continue
            if record.get("@type") == "NewsArticle":
                try:
                    utc(record["datePublished"])
                    if record.get("dateModified"):
                        utc(record["dateModified"])
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"{path.relative_to(root)}: {exc}")
                author = record.get("author", {})
                if author.get("name") not in {
                    "Times of Palestine", "تايمز أوف فلسطين"
                } and not record.get("isBasedOn"):
                    errors.append(
                        f"{path.relative_to(root)}: aggregated JSON-LD lacks isBasedOn")

    for name in ("en/rss.xml", "ar/rss.xml", "sitemap.xml", "news-sitemap.xml"):
        path = root / name
        if not path.exists():
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            errors.append(f"{name}: malformed XML ({exc})")
            continue
        if name.endswith("rss.xml"):
            for node in tree.findall(".//pubDate") + tree.findall(".//lastBuildDate"):
                try:
                    date = parsedate_to_datetime(node.text)
                    if not date or date.utcoffset() != timezone.utc.utcoffset(date):
                        raise ValueError(node.text)
                except (TypeError, ValueError):
                    errors.append(f"{name}: non-UTC RSS date {node.text!r}")
        if name == "news-sitemap.xml":
            ns = {"news": "http://www.google.com/schemas/sitemap-news/0.9"}
            for node in tree.findall(".//news:publication_date", ns):
                try:
                    utc(node.text)
                except (TypeError, ValueError) as exc:
                    errors.append(f"{name}: {exc}")

    for name in ("data.json", "health.json", "review-queue.json",
                 "distribution-outbox.json", "en/feed.json", "ar/feed.json"):
        path = root / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: invalid JSON ({exc})")
            continue
        if name == "health.json":
            try:
                utc(payload["builtAt"])
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"{name}: {exc}")
        elif name == "review-queue.json":
            allowed = {"fingerprint", "reasonCodes", "language"}
            for item in payload.get("items", []):
                extra = set(item) - allowed
                if extra:
                    errors.append(
                        f"{name}: sensitive review fields are public: {sorted(extra)}")
        elif name == "distribution-outbox.json":
            allowed = {
                "pid", "lang", "title", "date", "modified", "source",
                "source_url", "original", "link",
            }
            for item in payload.get("items", []):
                extra = set(item) - allowed
                if extra:
                    errors.append(f"{name}: unexpected fields {sorted(extra)}")
                try:
                    utc(item["date"])
                    if item.get("modified"):
                        utc(item["modified"])
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"{name}: {exc}")
        elif name.endswith("feed.json"):
            for item in payload.get("items", []):
                try:
                    utc(item["date_published"])
                    if item.get("date_modified"):
                        utc(item["date_modified"])
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"{name}: {exc}")
    outbox_path = root / "distribution-outbox.json"
    if outbox_path.exists():
        outbox = json.loads(outbox_path.read_text(encoding="utf-8"))
        outbox_ids = {(item["lang"], item["pid"]) for item in outbox.get("items", [])}
        feed_ids = set()
        for lang in ("en", "ar"):
            feed_path = root / lang / "feed.json"
            if feed_path.exists():
                feed = json.loads(feed_path.read_text(encoding="utf-8"))
                for item in feed.get("items", []):
                    feed_ids.add((lang, Path(urlsplit(item["id"]).path).stem))
        if outbox_ids != feed_ids:
            errors.append("distribution outbox does not match eligible JSON Feed stories")
    return errors


def summary(root):
    health = root / "health.json"
    if not health.exists():
        print("## Publishing health\n\nNo health report was generated.")
        return 0
    payload = json.loads(health.read_text(encoding="utf-8"))
    print("## Publishing health")
    print()
    print(f"- Status: **{payload.get('status', 'unknown')}**")
    print(f"- Built: `{payload.get('builtAt', 'unknown')}`")
    print(
        f"- Published: EN {payload.get('stories', {}).get('en', 0)}, "
        f"AR {payload.get('stories', {}).get('ar', 0)}")
    print(f"- Held for review: {payload.get('reviewHeld', 0)}")
    print(f"- Rights-blocked images: {payload.get('mediaBlocked', 0)}")
    failed = [row["id"] for row in payload.get("sources", [])
              if row.get("status") != "ok"]
    print(f"- Degraded feeds: {len(failed)}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.summary:
        return summary(args.dist)
    if not args.dist.is_dir():
        print(f"validate: missing directory {args.dist}", file=sys.stderr)
        return 2
    errors = validate(args.dist)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Generated publishing surfaces are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
