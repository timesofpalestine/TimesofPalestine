import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import seo_extras
import telegram_publish


def item(lang, pid, title, link, source_id="wire", age_minutes=5):
    return {
        "lang": lang,
        "pid": pid,
        "title": title,
        "link": link,
        "source_id": source_id,
        "date": datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    }


class OutboxTests(unittest.TestCase):
    def test_bilingual_original_is_one_group_with_two_delivery_keys(self):
        en = item(
            "en", "en1", "English title", "original:feature.en", "top-original")
        ar = item(
            "ar", "ar1", "عنوان عربي", "original:feature.ar", "top-original")
        outbox = seo_extras.build_telegram_outbox(
            (("en", [en]), ("ar", [ar])), "https://example.test")

        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["group_key"], "original:feature")
        self.assertEqual(
            [part["delivery_key"] for part in outbox[0]["parts"]],
            ["story:en:en1", "story:ar:ar1"],
        )

    def test_stale_story_is_not_queued(self):
        stale = item(
            "en",
            "old",
            "Old story",
            "https://source.test/old",
            age_minutes=seo_extras.TELEGRAM_MAX_AGE_H * 60 + 1,
        )
        outbox = seo_extras.build_telegram_outbox(
            (("en", [stale]),), "https://example.test")
        self.assertEqual(outbox, [])

    def test_correction_uses_revision_delivery_key(self):
        corrected = item(
            "en", "corrected", "Corrected story", "https://source.test/story")
        corrected["modified"] = datetime.now(timezone.utc)
        outbox = seo_extras.build_telegram_outbox(
            (("en", [corrected]),), "https://example.test")

        part = outbox[0]["parts"][0]
        self.assertTrue(part["delivery_key"].startswith("story:en:corrected:"))
        self.assertEqual(part["legacy_key"], "")


class PublisherTests(unittest.TestCase):
    def test_public_channel_urls_recover_delivery_keys(self):
        page = (
            '<a href="https://timesofpalestine.com/en/story/abc123def4.html">'
            "story</a>"
        )
        self.assertEqual(
            telegram_publish.delivery_keys_from_telegram_html(page),
            {"story:en:abc123def4"},
        )

    def test_legacy_markers_prevent_duplicate_delivery(self):
        outbox = {
            "entries": [{
                "parts": [{
                    "delivery_key": "story:en:abc",
                    "legacy_key": "tg:en:abc",
                }],
            }],
        }
        ledger = {"version": 1, "deliveries": {}}
        migrated = telegram_publish.migrate_legacy_markers(
            ledger, outbox, {"tg:en:abc": {"ts": 1}})
        self.assertEqual(migrated, 1)
        self.assertIn("story:en:abc", ledger["deliveries"])

    def test_success_is_saved_before_next_message(self):
        outbox = {
            "version": 1,
            "channel": telegram_publish.EXPECTED_CHANNEL,
            "entries": [{
                "group_key": "story:en:abc",
                "parts": [{
                    "delivery_key": "story:en:abc",
                    "legacy_key": "tg:en:abc",
                    "title": "A title",
                    "url": "https://example.test/en/story/abc.html",
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outbox_path = root / "telegram-outbox.json"
            ledger_path = root / "telegram-delivery.json"
            legacy_path = root / "briefs-cache.json"
            outbox_path.write_text(json.dumps(outbox), encoding="utf-8")
            with (
                mock.patch.object(telegram_publish, "OUTBOX_PATH", outbox_path),
                mock.patch.object(telegram_publish, "LEDGER_PATH", ledger_path),
                mock.patch.object(
                    telegram_publish, "LEGACY_CACHE_PATH", legacy_path),
                mock.patch.dict(
                    "os.environ", {"TELEGRAM_BOT_TOKEN": "test-token"}),
                mock.patch.object(
                    telegram_publish, "wait_until_live", return_value=True),
                mock.patch.object(
                    telegram_publish, "send_message", return_value=42),
                mock.patch.object(
                    telegram_publish,
                    "scrape_recent_delivery_keys",
                    return_value=set(),
                ),
                mock.patch.object(telegram_publish.time, "sleep"),
            ):
                self.assertEqual(telegram_publish.main(), 0)
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ledger["deliveries"]["story:en:abc"]["message_id"], 42)

    def test_malformed_ledger_recovers_from_public_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outbox_path = root / "telegram-outbox.json"
            ledger_path = root / "telegram-delivery.json"
            legacy_path = root / "briefs-cache.json"
            outbox_path.write_text(json.dumps({
                "version": 1,
                "channel": telegram_publish.EXPECTED_CHANNEL,
                "entries": [{
                    "parts": [{
                        "delivery_key": "story:en:abc123def4",
                        "legacy_key": "",
                    }],
                }],
            }), encoding="utf-8")
            ledger_path.write_text("{not-json", encoding="utf-8")
            with (
                mock.patch.object(telegram_publish, "OUTBOX_PATH", outbox_path),
                mock.patch.object(telegram_publish, "LEDGER_PATH", ledger_path),
                mock.patch.object(
                    telegram_publish, "LEGACY_CACHE_PATH", legacy_path),
                mock.patch.dict(
                    "os.environ", {"TELEGRAM_BOT_TOKEN": "test-token"}),
                mock.patch.object(
                    telegram_publish, "scrape_recent_delivery_keys",
                    return_value={"story:en:abc123def4"}),
            ):
                self.assertEqual(telegram_publish.main(), 0)
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertIn("story:en:abc123def4", ledger["deliveries"])

    def test_url_not_live_exits_zero(self):
        """CDN propagation lag must not paint the build red."""
        outbox = {
            "version": 1,
            "channel": telegram_publish.EXPECTED_CHANNEL,
            "entries": [{
                "group_key": "story:ar:d7d65b319e",
                "parts": [{
                    "delivery_key": "story:ar:d7d65b319e",
                    "legacy_key": "",
                    "title": "عنوان",
                    "url": "https://timesofpalestine.com/ar/story/d7d65b319e.html",
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outbox_path = root / "telegram-outbox.json"
            ledger_path = root / "telegram-delivery.json"
            legacy_path = root / "briefs-cache.json"
            outbox_path.write_text(json.dumps(outbox), encoding="utf-8")
            with (
                mock.patch.object(telegram_publish, "OUTBOX_PATH", outbox_path),
                mock.patch.object(telegram_publish, "LEDGER_PATH", ledger_path),
                mock.patch.object(
                    telegram_publish, "LEGACY_CACHE_PATH", legacy_path),
                mock.patch.dict(
                    "os.environ", {"TELEGRAM_BOT_TOKEN": "test-token"}),
                mock.patch.object(
                    telegram_publish, "wait_until_live", return_value=False),
                mock.patch.object(
                    telegram_publish,
                    "scrape_recent_delivery_keys",
                    return_value=set(),
                ),
            ):
                self.assertEqual(telegram_publish.main(), 0)

    def test_telegram_send_failure_exits_one(self):
        """A Telegram API error is a hard failure and must exit 1."""
        outbox = {
            "version": 1,
            "channel": telegram_publish.EXPECTED_CHANNEL,
            "entries": [{
                "group_key": "story:en:abc",
                "parts": [{
                    "delivery_key": "story:en:abc",
                    "legacy_key": "",
                    "title": "A title",
                    "url": "https://timesofpalestine.com/en/story/abc0000000.html",
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outbox_path = root / "telegram-outbox.json"
            ledger_path = root / "telegram-delivery.json"
            legacy_path = root / "briefs-cache.json"
            outbox_path.write_text(json.dumps(outbox), encoding="utf-8")
            with (
                mock.patch.object(telegram_publish, "OUTBOX_PATH", outbox_path),
                mock.patch.object(telegram_publish, "LEDGER_PATH", ledger_path),
                mock.patch.object(
                    telegram_publish, "LEGACY_CACHE_PATH", legacy_path),
                mock.patch.dict(
                    "os.environ", {"TELEGRAM_BOT_TOKEN": "test-token"}),
                mock.patch.object(
                    telegram_publish, "wait_until_live", return_value=True),
                mock.patch.object(
                    telegram_publish, "send_message", return_value=None),
                mock.patch.object(
                    telegram_publish,
                    "scrape_recent_delivery_keys",
                    return_value=set(),
                ),
            ):
                self.assertEqual(telegram_publish.main(), 1)

    def test_correction_is_not_suppressed_as_duplicate_of_same_story(self):
        now = datetime.now(timezone.utc)
        deliveries = {
            "story:en:abc": {
                "sent_at": (now - timedelta(hours=1)).isoformat(),
                "title": "Three Palestinians killed during Jenin raid",
                "lang": "en",
            },
        }
        correction = {
            "delivery_key": f"story:en:abc:{now.isoformat()}",
            "title": "Three Palestinians killed during Jenin raid",
            "lang": "en",
        }

        fresh, suppressed = telegram_publish.suppress_duplicate_events(
            [correction], deliveries, now=now)

        self.assertEqual(fresh, [correction])
        self.assertEqual(suppressed, 0)

    def test_same_event_under_new_story_id_is_suppressed(self):
        now = datetime.now(timezone.utc)
        deliveries = {
            "story:en:old": {
                "sent_at": (now - timedelta(hours=1)).isoformat(),
                "title": "Israeli forces kill three Palestinians in Jenin raid",
                "lang": "en",
            },
        }
        duplicate = {
            "delivery_key": "story:en:new",
            "title": "Three Palestinians killed by army during Jenin attack",
            "lang": "en",
        }

        fresh, suppressed = telegram_publish.suppress_duplicate_events(
            [duplicate], deliveries, now=now)

        self.assertEqual(fresh, [])
        self.assertEqual(suppressed, 1)
        self.assertEqual(
            deliveries["story:en:new"]["suppressed_duplicate_of"],
            "story:en:old",
        )


if __name__ == "__main__":
    unittest.main()
