import os
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import build
import longform
import seo_extras


def item():
    return {
        "title": "Palestinian artists open a community exhibition",
        "dek": "A sourced summary of the exhibition.",
        "link": "https://example.com/story",
        "source_url": "https://example.com",
        "source": "Example News",
        "source_id": "example",
        "source_type": "rss",
        "date": datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
        "modified": None,
        "image": None,
        "media": None,
        "categories": [],
        "lang": "en",
        "original": False,
        "partner": False,
        "cat": "arts",
        "score": 10,
        "pid": "1234567890",
        "corrections": [],
        "corroborating_sources": [{
            "name": "Example News", "url": "https://example.com",
            "article": "https://example.com/story",
        }],
    }


class RenderingTests(unittest.TestCase):
    def test_google_news_resolution_returns_publisher_article(self):
        class Response:
            url = "https://publisher.test/palestine-report?utm_source=google"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b""

        with mock.patch("build.safe_urlopen", return_value=Response()):
            self.assertEqual(
                build.resolve_article_url("https://news.google.com/articles/abc"),
                "https://publisher.test/palestine-report",
            )

    def test_story_has_visible_outbound_attribution_and_no_build_modified_date(self):
        record = item()
        html = build.render_story(
            record, "en", [], [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn('href="https://example.com/story"', html)
        self.assertIn("Based on reporting by", html)
        self.assertNotIn('"dateModified"', html)

    def test_correction_controls_date_modified(self):
        record = item()
        record["modified"] = datetime(2026, 7, 29, 14, tzinfo=timezone.utc)
        record["corrections"] = [{
            "at": "2026-07-29T14:00:00Z", "type": "correction", "note": "Fixed the date."
        }]
        html = build.render_story(
            record, "en", [], [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn('"dateModified": "2026-07-29T14:00:00Z"', html)
        self.assertIn("Updates &amp; corrections", html)

    def test_rss_dates_are_gmt_and_source_is_present(self):
        xml = build.render_rss(
            "en", [item()], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn("GMT</pubDate>", xml)
        self.assertIn('<source url="https://example.com">Example News</source>', xml)

    def test_missing_remote_image_rights_uses_fallback(self):
        record = item()
        build.attach_media(record, "https://images.example.com/photo.jpg")
        self.assertIsNone(record["image"])

    def test_media_for_held_stories_is_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            longform.copy_media(destination, [])
            self.assertFalse((destination / "media").exists())

    def test_connectors_are_explicitly_disabled_without_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                seo_extras.post_telegram(None, (("en", []),), "https://example.com"),
                "disabled",
            )

    def test_webhook_rejects_private_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ,
                {"DISTRIBUTION_WEBHOOK_URL": "http://169.254.169.254/hook"},
                clear=True,
            ):
                with self.assertRaises(ValueError):
                    seo_extras.post_webhook(
                        Path(directory), (("en", []), ("ar", [])),
                        "https://timesofpalestine.com")

    def test_webhook_disables_redirects(self):
        record = item()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ,
                {"DISTRIBUTION_WEBHOOK_URL": "https://hooks.example.com/publish"},
                clear=True,
            ), mock.patch(
                "seo_extras.is_public_http_url", return_value=True
            ), mock.patch("seo_extras.safe_urlopen") as opener:
                response = mock.MagicMock()
                response.status = 204
                opener.return_value.__enter__.return_value = response
                seo_extras.post_webhook(
                    Path(directory) / "dist", (("en", [record]), ("ar", [])),
                    "https://timesofpalestine.com")
                self.assertFalse(opener.call_args.kwargs["allow_redirects"])

    def test_corrected_story_is_delivered_as_a_new_revision(self):
        record = item()
        marker = f"webhook:{record['lang']}:{record['pid']}"
        cache = {marker: {"ts": 1}}
        self.assertFalse(
            seo_extras.needs_revision_delivery(cache, marker, record))
        record["modified"] = datetime(2026, 7, 29, 14, tzinfo=timezone.utc)
        self.assertTrue(
            seo_extras.needs_revision_delivery(cache, marker, record))
        cache[marker]["revision"] = seo_extras.delivery_revision(record)
        self.assertFalse(
            seo_extras.needs_revision_delivery(cache, marker, record))

    def test_correction_freshness_uses_modified_time(self):
        record = item()
        record["modified"] = datetime(2026, 8, 5, 14, tzinfo=timezone.utc)
        self.assertEqual(
            seo_extras.delivery_time(record), record["modified"])
        record["modified"] = None
        self.assertEqual(
            seo_extras.delivery_time(record), record["date"])

    def test_brief_stage_preserves_reviewed_original_body(self):
        record = item()
        record.update({
            "brief": "Full editor-authored investigation body.",
            "original": True,
            "source_type": "original",
            "link": "original:investigation.en",
        })
        fake_anthropic = mock.MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ), mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
                    mock.patch.object(
                        build, "BRIEFS_CACHE", Path(directory) / "briefs-cache.json"):
                build.generate_briefs([record])
        self.assertEqual(
            record["brief"], "Full editor-authored investigation body.")

    def test_complete_text_rejects_truncated_copy(self):
        self.assertTrue(build.is_complete_text(
            "A complete sourced summary that ends as a finished sentence.", 40))
        self.assertFalse(build.is_complete_text(
            "A feed summary that stops before completing the report…", 40))

    def test_event_dedupe_preserves_related_source_provenance(self):
        left = item()
        left["title"] = "Israeli forces kill three Palestinians in Jenin raid"
        right = item()
        right.update({
            "title": "Three Palestinians killed by army during Jenin attack",
            "source": "Second News",
            "source_url": "https://second.example",
            "link": "https://second.example/report",
            "pid": "0987654321",
            "corroborating_sources": [{
                "name": "Second News",
                "url": "https://second.example",
                "article": "https://second.example/report",
            }],
        })
        deduplicated = build.dedupe_events([left, right])
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(
            len(deduplicated[0]["corroborating_sources"]), 2)

    def test_sensitive_brief_is_purged_from_persistent_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "briefs-cache.json"
            cache.write_text(json.dumps({
                "en:1234567890": {"brief": "Sensitive generated prose", "ts": 1},
                "other": {"brief": "Safe prose", "ts": 1},
            }), encoding="utf-8")
            with mock.patch.object(build, "BRIEFS_CACHE", cache):
                build.purge_held_briefs([item()])
            remaining = json.loads(cache.read_text(encoding="utf-8"))
            self.assertNotIn("en:1234567890", remaining)
            self.assertIn("other", remaining)


if __name__ == "__main__":
    unittest.main()
