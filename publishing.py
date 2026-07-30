"""Validated publishing records and build health for Times of Palestine."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TypedDict
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
HTTP_SCHEMES = {"http", "https"}
TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref_src",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}
LANGS = {"en", "ar"}
SOURCE_TYPES = {"rss", "gnews", "telegram", "youtube", "original"}


class PublishingError(ValueError):
    """A local publishing-contract violation that must stop the build."""


class Story(TypedDict, total=False):
    title: str
    dek: str
    brief: str
    link: str
    source_url: str
    source: str
    source_id: str
    source_type: str
    date: datetime
    modified: Optional[datetime]
    image: Optional[str]
    media: Optional[Dict[str, str]]
    media_evidence: List[Dict[str, str]]
    categories: List[str]
    lang: str
    original: bool
    partner: bool
    needs_translation: bool
    brief_refused: bool
    cat: str
    max_age_hours: float
    score: float
    pid: str
    risk_reasons: List[str]
    review_fingerprint: str
    review_approved: bool
    review_status: str
    corrections: List[Dict[str, str]]
    corroborating_sources: List[Dict[str, str]]
    vetoed: bool


def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value or "")
        host = parsed.hostname or ""
        parsed.port
    except ValueError:
        return False
    if parsed.scheme.lower() not in HTTP_SCHEMES or not host:
        return False
    if parsed.username or parsed.password or "\\" in value:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if len(ascii_host) > 253:
        return False
    labels = ascii_host.rstrip(".").split(".")
    return all(
        0 < len(label) <= 63
        and not label.startswith("-")
        and not label.endswith("-")
        and re.fullmatch(r"[A-Za-z0-9-]+", label) is not None
        for label in labels
    )


def canonicalize_url(value: str) -> str:
    """Normalize a public URL without changing article identity."""
    if not is_http_url(value):
        return ""
    p = urlsplit(value.strip())
    host = (p.hostname or "").lower()
    if p.port and not ((p.scheme == "http" and p.port == 80)
                       or (p.scheme == "https" and p.port == 443)):
        host = f"{host}:{p.port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if k.lower() not in TRACKING_QUERY_KEYS])
    return urlunsplit(("https" if p.scheme == "https" else "http", host, path, query, ""))


def _public_addresses(value: str) -> List[str]:
    """Resolve once and return only globally routable addresses."""
    if not is_http_url(value):
        raise PublishingError("invalid HTTP(S) destination")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if host.casefold() == "localhost" or host.endswith(".localhost"):
        raise PublishingError("refusing non-public network destination")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(sockaddr[0].split("%", 1)[0])
                for *_prefix, sockaddr in socket.getaddrinfo(
                    host, parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM)
            ]
        except (OSError, ValueError):
            raise PublishingError("destination host did not resolve")
    if not addresses or not all(address.is_global for address in addresses):
        raise PublishingError("refusing non-public network destination")
    return list(dict.fromkeys(str(address) for address in addresses))


def is_public_http_url(value: str) -> bool:
    """Reject destinations that could expose runner-local or cloud metadata services."""
    try:
        _public_addresses(value)
        return True
    except PublishingError:
        return False


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection(
            (self._address, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(
            host, port=port, timeout=timeout,
            context=ssl.create_default_context())
        self._address = address

    def connect(self):
        raw_socket = socket.create_connection(
            (self._address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(
            raw_socket, server_hostname=self.host)


def _open_pinned(request: urllib.request.Request, address: str, timeout: float):
    parsed = urlsplit(request.full_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_type = (
        _PinnedHTTPSConnection if parsed.scheme == "https"
        else _PinnedHTTPConnection)
    connection = connection_type(host, address, port, timeout)
    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    headers = {
        key: value for key, value in request.header_items()
        if key.casefold() != "host"
    }
    headers["Host"] = parsed.netloc
    try:
        connection.request(
            request.get_method(), path, body=request.data, headers=headers)
        response = connection.getresponse()
    except Exception:
        connection.close()
        raise
    response.url = request.full_url
    return response


def safe_urlopen(request, timeout=20, max_redirects=5, allow_redirects=True):
    """Open an untrusted URL after checking its destination and allowed redirects."""
    if isinstance(request, str):
        request = urllib.request.Request(request)
    current = request
    for _hop in range(max_redirects + 1):
        address = _public_addresses(current.full_url)[0]
        response = _open_pinned(current, address, timeout)
        if response.status in {301, 302, 303, 307, 308}:
            if not allow_redirects:
                response.close()
                raise PublishingError("redirects are disabled for this request")
            if current.get_method() not in {"GET", "HEAD"}:
                response.close()
                raise PublishingError("redirects are disabled for non-read requests")
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise PublishingError("redirect lacks Location header")
            next_url = urljoin(current.full_url, location)
            headers = {
                key: value for key, value in current.header_items()
                if key.casefold() not in {
                    "content-length", "content-type", "host", "transfer-encoding",
                }
            }
            current = urllib.request.Request(
                next_url,
                headers=headers,
                method=current.get_method(),
            )
            continue
        if response.status >= 400:
            raise urllib.error.HTTPError(
                current.full_url, response.status, response.reason,
                response.headers, response)
        return response
    raise PublishingError("too many redirects")


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise PublishingError("naive datetime has no declared source timezone")
    return value.astimezone(UTC)


def parse_timestamp(value: str, naive_timezone: Optional[str] = None) -> Optional[datetime]:
    """Parse a source timestamp and return an aware UTC datetime."""
    if not value:
        return None
    text = value.strip()
    parsed: Optional[datetime] = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        pass
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
    if parsed is None:
        match = re.fullmatch(
            r"(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2}):(\d{2})", text)
        if match:
            day, month, year, hour, minute = map(int, match.groups())
            try:
                parsed = datetime(year, month, day, hour, minute)
            except ValueError:
                return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        if not naive_timezone:
            return None
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(naive_timezone))
        except ZoneInfoNotFoundError as exc:
            raise PublishingError(
                f"unknown source timezone {naive_timezone!r}") from exc
    return utc_datetime(parsed)


def utc_iso(value: datetime) -> str:
    return utc_datetime(value).isoformat().replace("+00:00", "Z")


def validate_feed_config(feeds: Dict[str, Any]) -> None:
    """Fail on local feed configuration that cannot produce attributed records."""
    if set(feeds) != LANGS:
        raise PublishingError("feeds.json must contain exactly 'en' and 'ar' arrays")
    seen: Set[str] = set()
    for lang in sorted(LANGS):
        if not isinstance(feeds[lang], list) or not feeds[lang]:
            raise PublishingError(f"feeds.{lang} must be a non-empty array")
        for index, feed in enumerate(feeds[lang]):
            where = f"feeds.{lang}[{index}]"
            if not isinstance(feed, dict):
                raise PublishingError(f"{where} must be an object")
            for key in ("id", "name", "site"):
                if not isinstance(feed.get(key), str) or not feed[key].strip():
                    raise PublishingError(f"{where}.{key} is required")
            if feed["id"] in seen:
                raise PublishingError(f"duplicate feed id {feed['id']!r}")
            seen.add(feed["id"])
            if not is_http_url(feed["site"]):
                raise PublishingError(f"{where}.site must be an HTTP(S) URL")
            source_type = feed.get("type", "rss")
            if source_type not in SOURCE_TYPES - {"original"}:
                raise PublishingError(f"{where}.type {source_type!r} is unsupported")
            required = "channel" if source_type == "telegram" else (
                "query" if source_type == "gnews" else "url")
            if not isinstance(feed.get(required), str) or not feed[required].strip():
                raise PublishingError(f"{where}.{required} is required")
            if required == "url" and not is_http_url(feed["url"]):
                raise PublishingError(f"{where}.url must be an HTTP(S) URL")
            if "timezone" in feed:
                try:
                    ZoneInfo(feed["timezone"])
                except (TypeError, ZoneInfoNotFoundError) as exc:
                    raise PublishingError(
                        f"{where}.timezone is invalid") from exc


def validate_story(story: Story, local: bool = False) -> None:
    """Validate a normalized record before it is allowed into publication."""
    label = story.get("pid") or story.get("source_id") or "story"
    for key in ("title", "source", "source_id", "lang", "cat"):
        if not isinstance(story.get(key), str) or not story[key].strip():
            raise PublishingError(f"{label}: missing {key}")
    if story["lang"] not in LANGS:
        raise PublishingError(f"{label}: unsupported language {story['lang']!r}")
    published = story.get("date")
    if not isinstance(published, datetime) or published.tzinfo is None:
        raise PublishingError(f"{label}: published timestamp must be timezone-aware")
    story["date"] = utc_datetime(published)
    if story.get("modified") is not None:
        story["modified"] = utc_datetime(story["modified"])  # type: ignore[arg-type]
        if story["modified"] < story["date"]:  # type: ignore[operator]
            raise PublishingError(f"{label}: modified timestamp precedes publication")
    if local or story.get("original"):
        if story.get("source_type") != "original":
            raise PublishingError(f"{label}: local original has invalid source type")
    else:
        if not is_http_url(story.get("source_url", "")):
            raise PublishingError(f"{label}: missing source homepage URL")
        if not is_http_url(story.get("link", "")):
            raise PublishingError(f"{label}: missing canonical outbound article URL")
        if story.get("source_type") not in SOURCE_TYPES - {"original"}:
            raise PublishingError(f"{label}: invalid source type")


@dataclass(frozen=True)
class MediaRights:
    asset: str
    rights_basis: str
    credit: str
    source: str
    license_url: str = ""


def load_media_manifest(path: Path) -> Dict[str, MediaRights]:
    if not path.exists():
        raise PublishingError(f"missing media rights manifest: {path.name}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishingError(f"invalid media rights manifest: {exc}") from exc
    if raw.get("version") != 1 or not isinstance(raw.get("assets"), list):
        raise PublishingError("media rights manifest must have version 1 and assets[]")
    result: Dict[str, MediaRights] = {}
    for index, item in enumerate(raw["assets"]):
        if not isinstance(item, dict):
            raise PublishingError(f"media asset {index} must be an object")
        for key in ("asset", "rightsBasis", "credit", "source"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise PublishingError(f"media asset {index} missing {key}")
        asset = item["asset"].strip()
        if asset in result:
            raise PublishingError(f"duplicate media rights entry {asset!r}")
        license_url = item.get("licenseUrl", "")
        if license_url and not is_http_url(license_url):
            raise PublishingError(f"invalid license URL for {asset!r}")
        result[asset] = MediaRights(
            asset=asset,
            rights_basis=item["rightsBasis"].strip(),
            credit=item["credit"].strip(),
            source=item["source"].strip(),
            license_url=license_url,
        )
    return result


def media_rights_for(value: Optional[str],
                     manifest: Dict[str, MediaRights]) -> Optional[MediaRights]:
    if not value:
        return None
    candidates = [value]
    if not is_http_url(value):
        clean = value.lstrip("./")
        candidates.extend([clean, f"originals/media/{Path(clean).name}"])
    for candidate in candidates:
        if candidate in manifest:
            return manifest[candidate]
    return None


def revision_review_data(story: Story) -> Dict[str, Any]:
    """Return the canonical semantic content shown to an approving editor."""
    return {
        "title": story.get("title", "").strip(),
        "summary": (story.get("brief") or story.get("dek") or "").strip(),
        "link": canonicalize_url(story.get("link", "")),
        "source": story.get("source", "").strip(),
        "source_url": canonicalize_url(story.get("source_url", "")),
        "published": utc_iso(story["date"]),
        "modified": utc_iso(story["modified"]) if story.get("modified") else None,
        "corrections": story.get("corrections", []),
        "category": story.get("cat"),
        "origin": {
            "original": bool(story.get("original")),
            "partner": bool(story.get("partner")),
            "source_type": story.get("source_type"),
        },
        "image": story.get("image"),
        "media": story.get("media"),
        "media_evidence": story.get("media_evidence", []),
        "corroborating_sources": story.get("corroborating_sources", []),
        "lang": story.get("lang"),
    }


def revision_fingerprint(story: Story) -> str:
    """Fingerprint the exact semantic content an editor is approving."""
    encoded = json.dumps(
        revision_review_data(story),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class SourceHealth:
    id: str
    name: str
    lang: str
    status: str = "pending"
    fetched: int = 0
    accepted: int = 0
    withheld: int = 0
    error: str = ""


@dataclass
class BuildHealth:
    built_at: datetime
    sources: Dict[str, SourceHealth] = field(default_factory=dict)
    withheld: Dict[str, int] = field(default_factory=dict)
    media_blocked: int = 0
    deduplicated: int = 0
    review_held: int = 0
    review_approved: int = 0
    connectors: Dict[str, str] = field(default_factory=dict)
    checks: Dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def register_source(self, feed: Dict[str, Any], lang: str) -> None:
        with self._lock:
            self.sources[feed["id"]] = SourceHealth(
                id=feed["id"], name=feed["name"], lang=lang)

    def source_result(self, source_id: str, status: str, fetched: int = 0,
                      accepted: int = 0, withheld: int = 0, error: str = "") -> None:
        with self._lock:
            current = self.sources[source_id]
            current.status = status
            current.fetched = fetched
            current.accepted = accepted
            current.withheld = withheld
            current.error = error

    def hold(self, code: str, count: int = 1) -> None:
        with self._lock:
            self.withheld[code] = self.withheld.get(code, 0) + count

    def block_media(self, code: str) -> None:
        with self._lock:
            self.media_blocked += 1
            self.withheld[code] = self.withheld.get(code, 0) + 1

    def public_dict(self, story_counts: Dict[str, int]) -> Dict[str, Any]:
        """Return diagnostics safe to publish from a public repository."""
        with self._lock:
            source_rows = [
                {
                    "id": row.id,
                    "name": row.name,
                    "lang": row.lang,
                    "status": row.status,
                    "fetched": row.fetched,
                    "accepted": row.accepted,
                    "withheld": row.withheld,
                    "errorCode": row.error,
                }
                for row in sorted(self.sources.values(), key=lambda x: (x.lang, x.id))
            ]
            return {
                "schemaVersion": 1,
                "builtAt": utc_iso(self.built_at),
                "status": "degraded" if (
                    any(row.status != "ok" for row in self.sources.values())
                    or self.withheld
                    or any(v not in {"ok", "disabled"} for v in self.checks.values())
                    or any(v not in {"ok", "disabled", "post_deploy"}
                           for v in self.connectors.values())
                ) else "ok",
                "stories": story_counts,
                "sources": source_rows,
                "withheld": dict(sorted(self.withheld.items())),
                "mediaBlocked": self.media_blocked,
                "deduplicated": self.deduplicated,
                "reviewHeld": self.review_held,
                "reviewApproved": self.review_approved,
                "connectors": dict(sorted(self.connectors.items())),
                "checks": dict(sorted(self.checks.items())),
            }


def validate_corrections(raw: Any, identity: str, lang: str) -> List[Dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PublishingError(f"corrections for {identity!r} must be an array")
    output: List[Dict[str, str]] = []
    previous: Optional[datetime] = None
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise PublishingError(f"correction {identity}[{index}] must be an object")
        at = parse_timestamp(entry.get("at", ""))
        note = entry.get(lang)
        kind = entry.get("type", "update")
        if not at or not isinstance(note, str) or not note.strip():
            raise PublishingError(
                f"correction {identity}[{index}] needs UTC at and {lang} note")
        if kind not in {"update", "correction"}:
            raise PublishingError(f"correction {identity}[{index}] has invalid type")
        if previous and at < previous:
            raise PublishingError(f"corrections for {identity!r} are not chronological")
        previous = at
        output.append({"at": utc_iso(at), "type": kind, "note": note.strip()})
    return output


def load_editorial_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishingError(f"invalid {path.name}: {exc}") from exc
