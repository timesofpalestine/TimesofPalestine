import os
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import build
import distribute
import longform
import originals_gen
import seo_extras
import telegram_publish


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

    def test_source_hosted_remote_image_retains_source_credit_by_default(self):
        record = item()
        with mock.patch("build.is_public_http_url", return_value=True):
            build.attach_media(record, "https://images.example.com/photo.jpg")
        self.assertEqual(record["image"], "https://images.example.com/photo.jpg")
        self.assertEqual(record["media"]["credit"], "Example News")

    def test_non_public_remote_image_is_blocked_in_source_mode(self):
        record = item()
        with mock.patch("build.is_public_http_url", return_value=False):
            build.attach_media(record, "http://127.0.0.1/photo.jpg")
        self.assertIsNone(record["image"])

    def test_rights_only_mode_blocks_unlisted_remote_image(self):
        record = item()
        with mock.patch.dict(
            os.environ, {"TOP_REMOTE_MEDIA": "rights-only"}, clear=True
        ):
            build.attach_media(record, "https://images.example.com/photo.jpg")
        self.assertIsNone(record["image"])

    def test_media_for_held_stories_is_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            longform.copy_media(destination, [])
            self.assertFalse((destination / "media").exists())

    def test_connectors_are_explicitly_disabled_without_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(telegram_publish.main(), 0)
            with tempfile.TemporaryDirectory() as directory:
                self.assertEqual(
                    seo_extras.post_webhook(
                        Path(directory), (("en", []),), "https://example.com"),
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
                self.assertTrue(
                    (Path(directory) / "webhook-delivery.json").is_file())
                self.assertFalse((Path(directory) / "briefs-cache.json").exists())

    def test_distribution_outbox_requires_public_base_url(self):
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / "distribution-outbox.json").write_text(json.dumps({
                "schemaVersion": 1,
                "baseUrl": "http://127.0.0.1/private",
                "items": [],
            }), encoding="utf-8")
            with self.assertRaises(build.PublishingError):
                distribute.load_outbox(dist)

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

    def test_telegram_public_history_does_not_hide_corrected_revision(self):
        outbox = {
            "entries": [{
                "parts": [{
                    "delivery_key": "story:en:abc123def4:2026-07-29T14:00:00Z",
                }],
            }],
        }
        ledger = {"version": 1, "deliveries": {}}
        recovered = telegram_publish.recover_public_channel_markers(
            ledger, outbox, {"story:en:abc123def4"})
        self.assertEqual(recovered, 0)
        self.assertEqual(ledger["deliveries"], {})

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
        self.assertTrue(all(
            source["verified"]
            for source in deduplicated[0]["corroborating_sources"]))

    def test_sensitive_wire_story_keeps_complete_newsroom_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "briefs-cache.json"
            brief = (
                "The report describes the incident using attributed details from the "
                "publisher and provides sufficient context for readers. It clearly "
                "states what is known, avoids unsupported conclusions, and ends as a "
                "complete newsroom brief."
            )
            cache.write_text(json.dumps({
                "en:1234567890": {"brief": brief, "ts": 1},
            }), encoding="utf-8")
            record = item()
            record["title"] = "Five people killed in Gaza strike"
            with mock.patch.object(build, "BRIEFS_CACHE", cache), mock.patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ), mock.patch.dict(sys.modules, {"anthropic": mock.MagicMock()}):
                build.generate_briefs([record])
            self.assertEqual(record["brief"], brief)

    def test_warm_brief_cache_is_used_without_provider_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "briefs-cache.json"
            brief = (
                "This complete cached newsroom brief remains publishable during a "
                "temporary provider outage. It preserves the attributed reporting, "
                "includes enough context for readers, and ends with a finished sentence."
            )
            cache.write_text(json.dumps({
                "en:1234567890": {"brief": brief, "ts": 1},
            }), encoding="utf-8")
            record = item()
            with mock.patch.object(build, "BRIEFS_CACHE", cache), mock.patch.dict(
                os.environ, {}, clear=True
            ):
                status = build.generate_briefs([record])
            self.assertEqual(status, "ok")
            self.assertEqual(record["brief"], brief)

    def test_pending_review_label_is_visible_without_related_reporting_list(self):
        record = item()
        record["review_status"] = "pending"
        record["corroborating_sources"].append({
            "name": "Second News",
            "url": "https://second.example",
            "article": "https://second.example/report",
            "verified": True,
        })
        html = build.render_story(
            record, "en", [], [record],
            datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn("Developing report", html)
        self.assertNotIn("Related reporting", html)
        self.assertIn("https://second.example/report", html)

    def test_markdown_residue_skips_only_the_invalid_original(self):
        with self.assertRaises(build.OriginalSkipError):
            build.validate_original(
                Path("unsafe.en.txt"),
                {"category": "news", "date": "2026-07-29T12:00:00Z"},
                "A sourced paragraph with an unrendered footnote marker [^1].",
                "en",
                datetime(2026, 7, 29, 15, tzinfo=timezone.utc),
                datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
            )

    def test_automated_investigation_uses_immutable_desk_hour_slug(self):
        parsed = {
            "title": "A sourced investigation",
            "dek": "A concise standfirst.",
            "body": "A complete reported body.",
            "sources": ["https://example.com/source"],
        }
        now = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            originals_gen, "ORIGINALS", Path(directory)
        ):
            publication_id = originals_gen._write_pair(
                {"id": "investigation", "cat": "research"},
                parsed, parsed, now)
            self.assertEqual(publication_id, "investigation-2026-07-29-12")
            self.assertTrue(
                (Path(directory) / f"{publication_id}.en.txt").is_file())
            with self.assertRaises(FileExistsError):
                originals_gen._write_pair(
                    {"id": "investigation", "cat": "research"},
                    parsed, parsed, now)


if __name__ == "__main__":
    unittest.main()
