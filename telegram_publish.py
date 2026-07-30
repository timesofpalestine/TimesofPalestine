"""Deliver the deployed Times of Palestine outbox to Telegram exactly once.

The site build writes telegram-outbox.json. GitHub Actions runs this publisher
only after GitHub Pages reports a successful deployment, so every shared URL is
already live. Successful delivery keys are written to telegram-delivery.json
immediately and carried between runs by the Actions cache.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTBOX_PATH = ROOT / "telegram-outbox.json"
LEDGER_PATH = ROOT / "telegram-delivery.json"
LEGACY_CACHE_PATH = ROOT / "briefs-cache.json"
EXPECTED_CHANNEL = "@timesofpalestin"
SEND_INTERVAL_SECONDS = 3
STORY_URL_RX = re.compile(
    r"https?://(?:www\.)?timesofpalestine\.com/(en|ar)/story/"
    r"([0-9a-f]{10})\.html"
)


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_ledger(ledger):
    temporary = LEDGER_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(LEDGER_PATH)


def migrate_legacy_markers(ledger, outbox, legacy):
    deliveries = ledger.setdefault("deliveries", {})
    migrated = 0
    for entry in outbox.get("entries", []):
        for part in entry.get("parts", []):
            key = part.get("delivery_key", "")
            legacy_key = part.get("legacy_key", "")
            if key and key not in deliveries and legacy_key in legacy:
                deliveries[key] = {
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "migrated_from": "briefs-cache.json",
                }
                migrated += 1
    return migrated


def delivery_keys_from_telegram_html(page):
    return {
        f"story:{lang}:{pid}"
        for lang, pid in STORY_URL_RX.findall(page or "")
    }


def scrape_recent_delivery_keys():
    request = urllib.request.Request(
        f"https://t.me/s/{EXPECTED_CHANNEL.lstrip('@')}",
        headers={"User-Agent": "Mozilla/5.0 TimesOfPalestine/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return delivery_keys_from_telegram_html(
            response.read().decode("utf-8", "replace"))


def recover_public_channel_markers(ledger, outbox, recent_keys):
    deliveries = ledger.setdefault("deliveries", {})
    recovered = 0
    valid_keys = {
        part.get("delivery_key")
        for entry in outbox.get("entries", [])
        for part in entry.get("parts", [])
    }
    for key in recent_keys & valid_keys:
        if key and key not in deliveries:
            deliveries[key] = {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "recovered_from": "public Telegram history",
            }
            recovered += 1
    return recovered


def pending_parts(entry, deliveries):
    return [
        part for part in entry.get("parts", [])
        if part.get("delivery_key") not in deliveries
    ]


def suppress_duplicate_events(parts, deliveries, now=None):
    """Never send the same news twice under a different story ID.

    The site's event dedupe can switch which variant of a story wins between
    builds (a partner-wire copy arriving after an agency copy was already
    delivered), which mints a new pid for an event the channel has already
    seen. Compare each pending headline against titles delivered in the last
    36 hours (same language); matches are marked delivered without sending.
    """
    from event_dedupe import event_tokens, same_event
    now = now or datetime.now(timezone.utc)
    recent = []
    for key, record in deliveries.items():
        title, lang = record.get("title"), record.get("lang")
        if not title or not lang:
            continue  # entries from before titles were recorded
        try:
            sent = datetime.fromisoformat(record.get("sent_at", ""))
        except ValueError:
            continue
        if (now - sent).total_seconds() <= 36 * 3600:
            recent.append((lang, event_tokens(title), key))
    fresh, suppressed = [], 0
    for part in parts:
        toks = event_tokens(part.get("title", ""))
        story_key = ":".join(part.get("delivery_key", "").split(":")[:3])
        match = next((key for lang, ktoks, key in recent
                      if lang == part.get("lang")
                      and ":".join(key.split(":")[:3]) != story_key
                      and same_event(toks, ktoks)), None)
        if match:
            deliveries[part["delivery_key"]] = {
                "sent_at": now.isoformat(),
                "suppressed_duplicate_of": match,
                "title": part.get("title", ""),
                "lang": part.get("lang", ""),
            }
            suppressed += 1
        else:
            fresh.append(part)
    return fresh, suppressed


def format_message(parts):
    return "\n\n".join(
        f"{part['title']}\n{part['url']}" for part in parts)


def wait_until_live(urls, attempts=4):
    for attempt in range(attempts):
        unavailable = []
        for url in urls:
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "TimesOfPalestine-Telegram/1.0",
                        "Range": "bytes=0-0",
                    },
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    if response.status not in (200, 206):
                        unavailable.append(url)
            except (OSError, urllib.error.URLError):
                unavailable.append(url)
        if not unavailable:
            return True
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    return False


def send_message(token, channel, message, attempts=4):
    body = urllib.parse.urlencode({"chat_id": channel, "text": message}).encode()
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage", data=body)
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("ok"):
                    return payload.get("result", {}).get("message_id")
        except urllib.error.HTTPError as error:
            delay = 2 ** attempt
            try:
                payload = json.loads(error.read().decode("utf-8"))
                delay = max(
                    delay,
                    int(payload.get("parameters", {}).get("retry_after", 0)),
                )
            except (AttributeError, TypeError, ValueError):
                pass
            if attempt + 1 < attempts:
                time.sleep(delay)
                continue
        except (OSError, ValueError):
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
        break
    return None


def main():
    token = "".join(os.environ.get("TELEGRAM_BOT_TOKEN", "").split())
    if not token:
        print("Telegram: disabled (TELEGRAM_BOT_TOKEN is not configured)")
        return 0
    try:
        outbox = load_json(OUTBOX_PATH, {})
        ledger = load_json(LEDGER_PATH, {"version": 1, "deliveries": {}})
        legacy = load_json(LEGACY_CACHE_PATH, {})
    except (OSError, ValueError) as error:
        print(
            f"Telegram: delivery state is unreadable ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1
    if outbox.get("version") != 1 or not isinstance(outbox.get("entries"), list):
        print("Telegram: valid telegram-outbox.json is missing", file=sys.stderr)
        return 1
    channel = outbox.get("channel")
    if channel != EXPECTED_CHANNEL:
        print(
            "Telegram: outbox channel does not match the approved channel",
            file=sys.stderr,
        )
        return 1

    if ledger.get("version") != 1 or not isinstance(ledger.get("deliveries"), dict):
        print("Telegram: delivery ledger is invalid", file=sys.stderr)
        return 1
    if not isinstance(legacy, dict):
        print("Telegram: legacy delivery state is invalid", file=sys.stderr)
        return 1
    migrated = migrate_legacy_markers(ledger, outbox, legacy)
    try:
        recovered = recover_public_channel_markers(
            ledger, outbox, scrape_recent_delivery_keys())
    except (OSError, UnicodeError, ValueError):
        recovered = 0
    if migrated or recovered:
        save_ledger(ledger)

    delivered, suppressed_total, failures = 0, 0, []
    for entry in outbox["entries"]:
        parts = pending_parts(entry, ledger["deliveries"])
        if not parts:
            continue
        parts, suppressed = suppress_duplicate_events(parts, ledger["deliveries"])
        if suppressed:
            suppressed_total += suppressed
            save_ledger(ledger)
        if not parts:
            continue
        if not wait_until_live([part["url"] for part in parts]):
            failures.append(f"{entry.get('group_key', 'unknown')}: URL not live")
            continue
        message_id = send_message(token, channel, format_message(parts))
        if message_id is None:
            failures.append(
                f"{entry.get('group_key', 'unknown')}: Telegram send failed")
            continue
        sent_at = datetime.now(timezone.utc).isoformat()
        for part in parts:
            ledger["deliveries"][part["delivery_key"]] = {
                "sent_at": sent_at,
                "message_id": message_id,
                "url": part["url"],
                "title": part.get("title", ""),
                "lang": part.get("lang", ""),
            }
        save_ledger(ledger)
        delivered += 1
        time.sleep(SEND_INTERVAL_SECONDS)

    pending = sum(
        len(pending_parts(entry, ledger["deliveries"]))
        for entry in outbox["entries"]
    )
    print(
        f"Telegram: delivered {delivered} group(s), migrated {migrated}, "
        f"recovered {recovered}, suppressed {suppressed_total} duplicate(s), "
        f"{pending} pending to {channel}"
    )
    if failures:
        for failure in failures:
            print(f"  → {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
