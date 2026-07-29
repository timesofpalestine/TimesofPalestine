import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from publishing import (
    PublishingError, canonicalize_url, is_http_url, is_public_http_url,
    load_media_manifest, media_rights_for,
    parse_timestamp, revision_fingerprint, safe_urlopen, validate_corrections,
    validate_feed_config,
)


class PublishingTests(unittest.TestCase):
    def test_feed_config_requires_attribution_site(self):
        feeds = {
            "en": [{"id": "x", "name": "X", "url": "https://x.test/rss"}],
            "ar": [{"id": "y", "name": "Y", "url": "https://y.test/rss",
                    "site": "https://y.test"}],
        }
        with self.assertRaises(PublishingError):
            validate_feed_config(feeds)

    def test_naive_timestamp_requires_declared_timezone_and_becomes_utc(self):
        self.assertIsNone(parse_timestamp("29/07/2026 - 15:00"))
        parsed = parse_timestamp("29/07/2026 - 15:00", "Asia/Gaza")
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

    def test_canonical_url_removes_fragment_and_tracking(self):
        self.assertEqual(
            canonicalize_url("https://EXAMPLE.com/a/?utm_source=x&id=2#part"),
            "https://example.com/a?id=2",
        )

    def test_malformed_mixed_script_hostname_is_rejected(self):
        self.assertFalse(is_http_url("http://www.arab48.comفلسطينيات/story"))

    def test_private_and_metadata_destinations_are_rejected(self):
        self.assertFalse(is_public_http_url("http://127.0.0.1:8080/private"))
        self.assertFalse(is_public_http_url("http://169.254.169.254/latest/meta-data"))
        self.assertFalse(is_public_http_url("http://localhost:3000"))

    def test_safe_urlopen_pins_the_validated_address(self):
        response = mock.MagicMock()
        response.status = 200
        with mock.patch(
            "publishing._public_addresses", return_value=["93.184.216.34"]
        ) as resolve, mock.patch(
            "publishing._open_pinned", return_value=response
        ) as open_pinned:
            self.assertIs(
                safe_urlopen("https://example.com/feed.xml"), response)
        resolve.assert_called_once_with("https://example.com/feed.xml")
        self.assertEqual(open_pinned.call_args.args[1], "93.184.216.34")

    def test_media_manifest_requires_complete_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.json"
            path.write_text(
                '{"version":1,"assets":[{"asset":"x.png","rightsBasis":"owned",'
                '"credit":"Desk","source":"Desk"}]}',
                encoding="utf-8",
            )
            manifest = load_media_manifest(path)
            self.assertEqual(media_rights_for("x.png", manifest).credit, "Desk")
            self.assertIsNone(media_rights_for("https://remote.test/x.png", manifest))

    def test_correction_changes_exact_version_fingerprint(self):
        story = {
            "title": "Palestine story",
            "dek": "A complete summary.",
            "link": "https://example.com/story",
            "source": "Example",
            "source_url": "https://example.com",
            "date": datetime(2026, 7, 29, tzinfo=timezone.utc),
            "modified": None,
            "corrections": [],
            "lang": "en",
        }
        first = revision_fingerprint(story)
        story["image"] = "/media/approved.svg"
        story["media"] = {"credit": "Times of Palestine", "rightsBasis": "owned"}
        self.assertNotEqual(first, revision_fingerprint(story))
        first = revision_fingerprint(story)
        story["media_evidence"] = [{"asset": "approved.svg", "sha256": "abc"}]
        self.assertNotEqual(first, revision_fingerprint(story))
        first = revision_fingerprint(story)
        story["corrections"] = [{
            "at": "2026-07-29T12:00:00Z", "type": "correction", "note": "Fixed a date."
        }]
        self.assertNotEqual(first, revision_fingerprint(story))

    def test_corrections_require_bilingual_note_for_requested_language(self):
        with self.assertRaises(PublishingError):
            validate_corrections(
                [{"at": "2026-07-29T12:00:00Z", "type": "update", "ar": "تحديث"}],
                "story", "en",
            )


if __name__ == "__main__":
    unittest.main()
