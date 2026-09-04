#!/usr/bin/env python3
"""Validate generated publishing surfaces without network access."""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from build import BASE_URL, remote_media_mode

BASE_PARTS = urlsplit(BASE_URL)

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
    base = BASE_URL.rstrip("/") + "/" + page.relative_to(root).as_posix()
    resolved = urlsplit(urljoin(base, target))
    if (resolved.scheme, resolved.netloc) != (BASE_PARTS.scheme, BASE_PARTS.netloc):
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
        "assets/site.css",
    ]
    for name in required:
        if not (root / name).is_file():
            errors.append(f"missing required output {name}")

    for path in root.rglob("*.svg"):
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            errors.append(
                f"{path.relative_to(root)}: SVG is not well-formed XML "
                f"and renders as a broken image ({exc})")

    for path in root.rglob("*.html"):
        parser = DocumentParser()
        try:
            html_text = path.read_text(encoding="utf-8")
            parser.feed(html_text)
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root)}: unreadable HTML ({exc})")
            continue
        check_body_starts_clean(path.relative_to(root), html_text, errors)
        if path.parent.name == "story":
            check_editorial_hygiene(path.relative_to(root), html_text, errors)
        # Legitimate redirects: the root language splash, and the bare-pid
        # story stubs that keep every previously shared link resolving now
        # that story filenames carry a headline slug ahead of the pid.
        is_pid_stub = (path.parent.name == "story"
                       and re.fullmatch(r"[0-9a-f]{10}\.html", path.name))
        # The root splash and static-feature landings may redirect; the two
        # edition fronts (en/, ar/) never may — a refresh there is a regression.
        is_splash = (path.name == "index.html"
                     and path.parent.name not in ("en", "ar"))
        if parser.meta_refresh and not is_splash and not is_pid_stub:
            errors.append(f"{path.relative_to(root)}: unconditional meta refresh")
        if parser.remote_images and remote_media_mode() == "rights-only":
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
                    # Filenames are <headline-slug>-<pid>.html; the trailing
                    # pid is the story identity shared with the outbox.
                    stem = Path(urlsplit(item["id"]).path).stem
                    feed_ids.add((lang, stem.rsplit("-", 1)[-1]))
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
    # The Gaza toll curve fails open by design, so its absence is silent in the
    # page itself. Report it here or a dead upstream goes unnoticed for weeks.
    missing = [lang for lang in ("en", "ar")
               if (health.parent / lang / "index.html").exists()
               and 'class="toll-chart"' not in
               (health.parent / lang / "index.html").read_text(encoding="utf-8")]
    print("- Gaza toll curve: "
          + ("rendered in both editions" if not missing
             else f"**MISSING** in {', '.join(missing)} — daily series unreachable?"))
    return 0


# The charter's editorial rules are enforced at ingest, on the source file. This
# re-checks the RENDERED page, which is the only thing a reader ever sees: a rule
# that regresses, or copy arriving by a path that skips the ingest gate, would
# otherwise publish unnoticed. Anchored on subheads and on phrases that can only
# be leaked scaffolding, so ordinary prose ("sources differ", "the bottom line is
# that…") does not trip it.
_BANNED_SUBHEADS = (
    "sources", "source list", "references", "bibliography", "further reading",
    "methodology", "right of reply", "corrections", "visual credits",
    "key takeaways", "bottom line", "unanswered questions", "what is unresolved",
    "what remains unanswered", "conclusion",
    "المصادر", "المصادر والوثائق", "المراجع", "المنهجية", "حق الرد",
    "التصحيحات", "حقوق المواد البصرية", "الخلاصة السريعة", "ما لم يُحسم",
)
_LEAKED_NOTE_RX = re.compile(
    r"verify before publication|before publication,? the newsroom|"
    r"this is an unpublished draft|"
    r"this (?:developing|preliminary) report|"
    r"this (?:story|report|article|brief) (?:is |remains )?"
    r"(?:awaiting|pending|under) review|"
    r"\[placeholder\]|\bTODO\b|\bTK\b|lorem ipsum|"
    r"تحقق قبل النشر|مسودة غير منشورة|"
    r"هذ[اه] (?:التقرير|الموجز|المقال|المادة|القصة) قيد المراجعة", re.I)
# The charter's banned status labels ("developing report", "awaiting review",
# «قيد المراجعة») are only violations when they label THE STORY — the words
# themselves are ordinary journalism about a subject: a library keeps a
# withdrawn book «قيد المراجعة» (production build stopped on exactly that
# sentence, 2026-08-18). Mid-prose uses pass; a bare label paragraph fails.
_STATUS_LABEL_RX = re.compile(
    r"^(?:developing report|awaiting review|pending review|under review|"
    r"قيد المراجعة|بانتظار المراجعة|تقرير قيد الإعداد)\s*[.…:]?$", re.I)


def check_editorial_hygiene(path, html, errors):
    """Charter rules, re-checked on what actually shipped."""
    for raw in re.findall(r'<h[234][^>]*class="sub"[^>]*>(.*?)</h[234]>', html, re.S):
        text = re.sub(r"<[^>]+>", "", raw).strip().rstrip(":：").casefold()
        if text in _BANNED_SUBHEADS:
            errors.append(
                f"{path}: article carries a '{text}' section — attribution belongs "
                f"inline in the prose (charter: no sources/methodology/memo sections)")
    paragraphs = [re.sub(r"<[^>]+>", "", p)
                  for p in re.findall(r'<p class="summary">(.*?)</p>', html, re.S)]
    for text in paragraphs:
        if _STATUS_LABEL_RX.match(text.strip()):
            errors.append(
                f"{path}: reader-facing status label on the story: {text.strip()!r} "
                f"(charter: no 'developing report'/'awaiting review'-style labels)")
    hit = _LEAKED_NOTE_RX.search(" ".join(paragraphs))
    if hit:
        errors.append(f"{path}: internal editorial note reached the page: {hit.group(0)!r}")


def check_body_starts_clean(path, html, errors):
    """Malformed head markup spills visible junk before the first element."""
    import re as _re
    m = _re.search(r"<body>\s*([^<\s][^<]*)", html)
    if m:
        errors.append(f"{path}: stray text at body start: {m.group(1)[:40]!r}")


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
