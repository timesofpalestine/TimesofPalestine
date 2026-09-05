import os
import json
import re
import sys
import tempfile
import time
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import budget_ledger
import build
import distribute
import longform
import originals_gen
import seo_extras
import telegram_publish

# The briefs-desk tests below drive write_brief with fake clients whose
# usage objects carry token counts; the governor would faithfully record
# that fake spend into the COMMITTED ledger (site scan 2026-09-02). Point
# the ledger at a throwaway file for this process.
budget_ledger.LEDGER_FILE = Path(tempfile.mkdtemp(prefix="top-ledger-")) / "_ledger.json"


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
    def setUp(self):
        build.discover_story_image.cache_clear()

    def test_homepage_front_page_surfaces_follow_fresh_items(self):
        built_at = datetime(2026, 7, 29, 15, tzinfo=timezone.utc)
        stale = item()
        stale.update({
            "title": "Older Gaza accountability report keeps a premium slot",
            "link": "https://example.com/stale",
            "date": datetime(2026, 7, 29, 9, tzinfo=timezone.utc),
            "image": "/media/stale.jpg",
            "score": 999,
            "pid": "stale00001",
        })
        records = [stale]
        for idx, minutes, score in (
            (1, 5, 25),
            (2, 15, 24),
            (3, 25, 23),
            (4, 35, 22),
            (5, 45, 21),
            (6, 55, 20),
        ):
            record = item()
            record.update({
                "title": f"Israeli forces raid Gaza district as updates arrive {idx}",
                "link": f"https://example.com/fresh-{idx}",
                "date": built_at - timedelta(minutes=minutes),
                "image": f"/media/fresh-{idx}.jpg",
                "score": score,
                "pid": f"fresh0000{idx}",
            })
            records.append(record)

        homepage = build.render_page("en", records, built_at)

        self.assertLess(
            homepage.index("Israeli forces raid Gaza district as updates arrive 1"),
            homepage.index("Older Gaza accountability report keeps a premium slot"),
        )
        latest = homepage.split('<aside class="latest">', 1)[1].split("</aside>", 1)[0]
        self.assertLess(
            latest.index("Israeli forces raid Gaza district as updates arrive 6"),
            latest.index("Older Gaza accountability report keeps a premium slot"),
        )
        ticker = homepage.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn("Israeli forces raid Gaza district as updates arrive 1", ticker)
        self.assertNotIn("Older Gaza accountability report keeps a premium slot", ticker)

    def test_press_review_never_squats_hero_or_breaking_ticker(self):
        # Owner scan 2026-08-06: israelipress writeups are secondary coverage —
        # they live in their section and the Latest rail, never as the paper's
        # top story or in the breaking ticker, however fresh or high-scoring.
        built_at = datetime(2026, 8, 6, 15, tzinfo=timezone.utc)
        press = item()
        press.update({
            "title": "Israeli think tank calls Hamas election exclusion a strategic defeat",
            "link": "original:israelipress-besa.en",
            "date": built_at - timedelta(minutes=3),
            "image": "/media/times-of-palestine-cover-israelipress.svg",
            "cat": "israelipress",
            "original": True,
            "score": 999,
            "pid": "press00001",
        })
        wire = item()
        wire.update({
            "title": "Israeli forces raid Jenin refugee camp before dawn on Thursday",
            "link": "https://example.com/jenin-raid",
            "date": built_at - timedelta(minutes=20),
            "image": "/media/jenin.jpg",
            "cat": "westbank",
            "score": 25,
            "pid": "wire000001",
        })

        homepage = build.render_page("en", [press, wire], built_at)

        overlay = homepage.split("hero-overlay", 1)[1][:400]
        self.assertIn("Jenin", overlay)
        self.assertNotIn("think tank", overlay)
        ticker = homepage.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn("Jenin", ticker)
        self.assertNotIn("think tank", ticker)

    def test_summary_markdown_renders_safely_across_reader_surfaces(self):
        record = item()
        record.update({
            "cat": "research",
            "dek": (
                "A [corporate filing](https://example.com/filing?half=1&year=2026) "
                "sets the timetable <script>alert('unsafe')</script>."
            ),
            "image": "/media/times-of-palestine-cover-research.svg",
            "original": True,
            "source_id": "top-original",
            "link": "original:research.en",
        })
        homepage = build.render_page(
            "en", [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        story = build.render_story(
            record, "en", [], [record],
            datetime(2026, 7, 29, 15, tzinfo=timezone.utc))

        for rendered in (homepage, story):
            self.assertIn(
                '<a href="https://example.com/filing?half=1&amp;year=2026"',
                rendered,
            )
            self.assertIn("&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;", rendered)
            self.assertNotIn("[corporate filing](", rendered)
            self.assertNotIn("<script>alert('unsafe')</script>", rendered)
        self.assertIn(
            'content="A corporate filing sets the timetable '
            '&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;."',
            story,
        )

    def test_longform_table_stays_inside_scrollable_wrapper(self):
        rendered = longform.body_html(
            "| Area | Partner | Period | Result |\n"
            "| --- | --- | --- | --- |\n"
            "| Health | Palestine | 2026–2028 | Training underway |"
        )
        self.assertIn('<div class="tablewrap"><table class="lf">', rendered)
        self.assertIn(".story .tablewrap{overflow-x:auto", longform.CSS)

    def test_navigation_bar_wraps_and_drops_open_grouped_panels(self):
        # Grouped nav (owner order 2026-08-05): one wrapping line-tab bar,
        # with dropdown panels that are solid black and open via the
        # .nav-group.open state (hover/focus covered separately by CSS).
        self.assertIn(
            "nav.sections .wrap{display:flex;flex-wrap:wrap;", build.CSS)
        self.assertIn("nav.sections .nav-drop{display:none;", build.CSS)
        self.assertIn(
            "nav.sections .nav-group.open .nav-drop{display:block}", build.CSS)
        # Phones: an OPEN panel is position:fixed under the bar — iOS Safari
        # clips absolutely-positioned panels inside the composited scroll row
        # (owner report 2026-08-06), and fixed boxes escape by construction.
        self.assertIn(
            "nav.sections .nav-group.open .nav-drop{position:fixed;"
            "inset-inline:0;top:var(--navdrop-top,0px)}", build.CSS)
        homepage = build.render_page(
            "en", [item()], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn("--navdrop-top", homepage)   # toggle JS measures the bar
        self.assertNotIn("-webkit-overflow-scrolling", build.CSS)

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
        self.assertIn('datetime="2026-07-29T12:00:00Z"', html)
        self.assertIn("Published", html)

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
        self.assertIn("Updated", html)

    def test_story_pages_add_breadcrumbs_and_toc_for_long_originals(self):
        record = item()
        record.update({
            "title": "Palestinian nurses rebuild trauma care across Gaza",
            "original": True,
            "source_id": "top-original",
            "source": "Times of Palestine",
            "link": "original:health-check.en",
            "cat": "health",
            "brief": (
                "## First turn\n\n"
                "Paragraph one.\n\n"
                "## Second turn\n\n"
                "Paragraph two.\n\n"
                "## Third turn\n\n"
                "Paragraph three."
            ),
        })
        html = build.render_story(
            record, "en", [], [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn('class="breadcrumbs"', html)
        self.assertIn('href="../section-health.html"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)
        self.assertIn('class="story-toc"', html)
        self.assertIn('href="#first-turn"', html)
        self.assertIn('id="second-turn"', html)

    def test_rendered_pages_do_not_depend_on_google_fonts(self):
        record = item()
        record.update({
            "cat": "research",
            "original": True,
            "source_id": "top-original",
            "source": "Times of Palestine",
            "link": "original:research-check.en",
        })
        homepage = build.render_page(
            "en", [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        story = build.render_story(
            record, "en", [], [record], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertNotIn("fonts.googleapis.com", homepage)
        self.assertNotIn("fonts.googleapis.com", story)
        self.assertIn("1 story", homepage)

    def test_rss_dates_are_gmt_and_source_is_present(self):
        xml = build.render_rss(
            "en", [item()], datetime(2026, 7, 29, 15, tzinfo=timezone.utc))
        self.assertIn("GMT</pubDate>", xml)
        self.assertIn('<source url="https://example.com">Example News</source>', xml)

    def test_source_hosted_remote_image_retains_source_credit_by_default(self):
        record = item()
        with mock.patch("build.is_public_http_url", return_value=True), \
                mock.patch("build.remote_image_ok", return_value=True):
            build.attach_media(record, "https://images.example.com/photo.jpg")
        self.assertEqual(record["image"], "https://images.example.com/photo.jpg")
        self.assertEqual(record["media"]["credit"], "Example News")

    def test_dead_remote_image_is_dropped_so_category_cover_takes_over(self):
        record = item()
        with mock.patch("build.is_public_http_url", return_value=True), \
                mock.patch("build.remote_image_ok", return_value=False):
            build.attach_media(record, "https://images.example.com/gone.jpg")
        self.assertIsNone(record["image"])
        self.assertIsNone(record["media"])

    def test_remote_lede_gets_reader_side_fallback_attributes(self):
        record = item()
        record["image"] = "https://images.example.com/photo.jpg"
        record["cat"] = "gaza"
        attrs = build.lede_fallback_attrs(record)
        self.assertIn('referrerpolicy="no-referrer"', attrs)
        self.assertIn("times-of-palestine-cover-gaza.svg", attrs)
        self.assertIn("onerror=", attrs)

    def test_local_lede_needs_no_fallback_attributes(self):
        record = item()
        record["image"] = "/media/times-of-palestine-cover-gaza.svg"
        self.assertEqual(build.lede_fallback_attrs(record), "")

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

    def test_discover_story_image_reads_og_image_and_resolves_relative_urls(self):
        class Response:
            url = "https://publisher.test/world/story"
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return (
                    b'<html><head><meta property="og:image" '
                    b'content="/media/hero.jpg"></head></html>'
                )

        with mock.patch("build.safe_urlopen", return_value=Response()), mock.patch(
            "build.is_public_http_url", return_value=True
        ):
            self.assertEqual(
                build.discover_story_image("https://publisher.test/world/story"),
                "https://publisher.test/media/hero.jpg",
            )

    def test_backfill_remote_story_image_uses_discovered_photo(self):
        record = item()
        with mock.patch(
            "build.discover_story_image",
            return_value="https://images.example.com/auto.jpg",
        ), mock.patch("build.is_public_http_url", return_value=True), \
                mock.patch("build.remote_image_ok", return_value=True):
            build.backfill_remote_story_image(record)
        self.assertEqual(record["image"], "https://images.example.com/auto.jpg")
        self.assertEqual(record["media"]["credit"], "Example News")

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
                "complete newsroom brief.\n\nResidents told the publisher that rescue "
                "crews reached the district within the hour and moved the wounded to "
                "the nearest hospital, while municipal teams surveyed the damage and "
                "families waited for word on relatives reported missing overnight."
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
                "includes enough context for readers, and ends with a finished "
                "sentence.\n\nThe cached copy carries the full account of the day's "
                "events as the desk wrote it, names the outlet once inline in the "
                "prose, and keeps every figure and attribution exactly as the "
                "original wire report carried them for the reader."
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

    def test_review_status_is_never_reader_facing(self):
        # Owner decision 2026-07-30: no review labels or chips on any story.
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
        self.assertNotIn("Developing report", html)
        self.assertNotIn("review-chip", html)
        self.assertNotIn("Developing<", html)
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


class SvgTextOverflowTests(unittest.TestCase):
    """Owner report 2026-08-11: a desk graphic's headline ran off the canvas
    mid-word. The estimator guards LATIN runs; the whole shipped library must
    stay clean, and the clamp caps an overflowing run with textLength."""

    def test_estimator_flags_an_overflowing_latin_headline(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">'
               '<text x="90" y="128" font-size="46">'
               'Donors bypass World Bank fund for Gaza and it has received nothing'
               '</text></svg>')
        self.assertTrue(build.svg_text_overflows(svg))
        clamped = build.clamp_svg_text(svg)
        self.assertIn('textLength="1494"', clamped)
        self.assertFalse(build.svg_text_overflows(clamped))

    def test_arabic_runs_are_left_to_editorial_judgment(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">'
               '<text x="1520" y="128" font-size="46">'
               'إسرائيل تمنع مرضى السرطان في غزة من مستشفيات الضفة الغربية'
               '</text></svg>')
        self.assertEqual(build.svg_text_overflows(svg), [])
        self.assertEqual(build.clamp_svg_text(svg), svg)  # never auto-mutated

    def test_shipped_media_library_is_clean(self):
        from pathlib import Path
        media = Path(build.__file__).resolve().parent / "originals" / "media"
        findings = {}
        for p in sorted(media.glob("*.svg")):
            f = build.svg_text_overflows(p.read_text(encoding="utf-8"))
            if f:
                findings[p.name] = f
        self.assertEqual(findings, {})


class MarketWatchTests(unittest.TestCase):
    """Owner directive 2026-08-11: Al-Quds and TA-125 in the strip, fail-open."""

    def test_market_figures_fail_open_and_editorial_fallback(self):
        # Without network the fetches fail silently, and the Al-Quds cell
        # still fills from editorial/markets.json WITH its as-of date —
        # the Ramallah ticker must show (owner order 2026-08-11).
        import gaza_panel
        old = dict(gaza_panel._MARKETS_CACHE)
        gaza_panel._MARKETS_CACHE.clear()
        gaza_panel._MARKETS_CACHE["done"] = False
        try:
            out = gaza_panel.market_figures()  # no network in tests
            self.assertIn("alquds", out)
            self.assertTrue(out["alquds"]["level"] > 0)
            self.assertTrue(out["alquds"].get("asof"))
        finally:
            gaza_panel._MARKETS_CACHE.clear()
            gaza_panel._MARKETS_CACHE.update(old)

    def test_strip_renders_market_cells_when_figures_exist(self):
        import gaza_panel
        old_mk = dict(gaza_panel._MARKETS_CACHE)
        old_rt = dict(gaza_panel._RATES_CACHE)
        gaza_panel._MARKETS_CACHE.clear()
        gaza_panel._MARKETS_CACHE.update(
            {"done": True, "alquds": {"level": 641.3},
             "ta125": {"level": 2104.0, "pct": -0.42}})
        gaza_panel._RATES_CACHE.clear()
        gaza_panel._RATES_CACHE.update(
            {"usd": 3.41, "eur": 3.96, "jod": 4.81, "date": "2026-08-11"})
        try:
            with mock.patch.object(gaza_panel, "live_figures",
                                   return_value=({"killed": 60000}, "", {}, "")), \
                 mock.patch.object(gaza_panel, "prisoner_figures",
                                   return_value=({"pr_total": 9600}, "")):
                html = gaza_panel.strip("en")
                self.assertIn("Al-Quds index", html)
                self.assertIn("TA-125", html)
                self.assertIn("▼0.4%", html)
                self.assertIn("₪3.41", html)
                html_ar = gaza_panel.strip("ar")
                self.assertIn("مؤشر القدس", html_ar)
                self.assertIn("تل أبيب 125", html_ar)
        finally:
            gaza_panel._MARKETS_CACHE.clear(); gaza_panel._MARKETS_CACHE.update(old_mk)
            gaza_panel._RATES_CACHE.clear(); gaza_panel._RATES_CACHE.update(old_rt)


class PrisonersSectionTests(unittest.TestCase):
    """Owner directive 2026-08-11: the أسرى file is a standing section —
    prisoner items route in automatically; female prisoners stay Her Story."""

    def test_prisoner_items_route_to_the_section_in_both_languages(self):
        en = item()
        en.update({"title": "Prisoners' Club says detainees began a hunger strike",
                   "dek": "Administrative detention numbers keep rising.",
                   "categories": []})
        ar = item()
        ar.update({"lang": "ar", "categories": [],
                   "title": "نادي الأسير: الأسرى يبدؤون إضراباً مفتوحاً عن الطعام",
                   "dek": "أعداد الاعتقال الإداري تواصل الارتفاع."})
        self.assertEqual(build.categorize(en), "prisoners")
        self.assertEqual(build.categorize(ar), "prisoners")

    def test_female_prisoner_account_keeps_her_story_routing(self):
        it = item()
        it.update({"lang": "ar", "categories": [],
                   "title": "أسيرة محررة تروي شهادتها عن الاعتقال",
                   "dek": "شهادة من داخل سجن الدامون."})
        self.assertEqual(build.categorize(it), "women")

    def test_prisoners_section_renders_on_the_front(self):
        built_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
        base = item()
        # Front-page window (owner order 2026-09-04): a section slot is a
        # story from the last three days — the fixture dates inside it.
        base.update({"image": "/media/x.svg",
                     "date": built_at - timedelta(hours=5)})
        subjects = [
            "Red Cross visits Palestinian prisoners in Gaza jails",
            "Prisoners' Club counts the detainees taken from Jenin",
            "Administrative detention of Palestinians reaches a record",
            "Freed Palestinian prisoners reach Khan Younis families",
            "Hunger strike spreads through Palestinian prisoners' wings",
            "Israel moves Palestinian detainees out of Ofer prison",
            "Lawyers document prison conditions for Palestinian detainees",
            "Families rally in Nablus for the Palestinian prisoners",
            "Court extends detention of Palestinian journalists again",
            "Doctors warn over sick Palestinian prisoners in Ramla",
            "Children held in Israeli jails reach a new Palestinian record",
            "Prisoner exchange list grows in Gaza ceasefire talks",
        ]
        for lang in ("en", "ar"):
            rows = [dict(base, lang=lang, cat="prisoners", pid=f"pris{n:04d}",
                         title=t, link=f"https://example.com/pris-{n}")
                    for n, t in enumerate(subjects)]
            page = build.render_page(lang, rows, built_at)
            self.assertIn('id="prisoners"', page)


class OnThisDayTests(unittest.TestCase):
    """Owner directive 2026-08-11: a daily memory line on both fronts,
    keyed to the Jerusalem date; silent on days without an entry."""

    def test_band_renders_on_a_dated_day_and_not_otherwise(self):
        it = item()
        it.update({"image": "/media/x.svg"})
        nakba_day = datetime(2026, 5, 15, 12, tzinfo=timezone.utc)
        for lang, needle in (("en", "Nakba"), ("ar", "النكبة")):
            page = build.render_page(lang, [dict(it, lang=lang)], nakba_day)
            self.assertIn('class="otd"', page)
            self.assertIn("1948", page.split('class="otd"', 1)[1][:600])
            self.assertIn(needle, page)
        quiet_day = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        page = build.render_page("en", [it], quiet_day)
        self.assertNotIn('class="otd"', page)


class PressDeskFreshnessTests(unittest.TestCase):
    """Owner order 2026-08-11: the press-review sections front the NEWEST
    items — a daily review showing five-day-old cards reads as dead."""

    def test_topical_sections_list_newest_first_regardless_of_score(self):
        # Every section fronts the day's coverage (owner order 2026-08-11,
        # second round — the press-desk rule extended to the whole paper).
        # 12 economy items: the hero tier consumes the newest nine, the
        # section shows the remainder — still in date order, not score order.
        built_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
        rows = []
        for n in range(12):
            it2 = item()
            it2.update({"cat": "economy", "pid": f"econ{n:04d}", "image": "/media/x.svg",
                        "score": n,  # older items score HIGHER under this order
                        "date": datetime(2026, 8, 11, 11, tzinfo=timezone.utc)
                        - timedelta(hours=n),
                        "title": f"Gaza merchants report market shift number {n} today",
                        "link": f"https://example.com/econ-{n}"})
            rows.append(it2)
        page = build.render_page("en", rows, built_at)
        block = page.split('id="economy"', 1)[1].split("</section>", 1)[0]
        present = sorted((block.index(f"market shift number {n} today"), n)
                         for n in range(12)
                         if f"market shift number {n} today" in block)
        self.assertTrue(present)
        order = [n for _, n in present]
        self.assertEqual(order, sorted(order))  # lower n = newer = first

    def test_press_sections_list_newest_first_regardless_of_score(self):
        built_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
        for cat in ("israelipress", "uspress"):
            old = item()
            old.update({"cat": cat, "pid": f"pf1{cat[:4]}", "score": 99,
                        "image": "/media/x.svg",
                        "date": datetime(2026, 8, 6, 9, tzinfo=timezone.utc),
                        "title": "Haaretz reviews five days of Gaza coverage"})
            new = item()
            new.update({"cat": cat, "pid": f"pf2{cat[:4]}", "score": 1,
                        "image": "/media/x.svg",
                        "date": datetime(2026, 8, 11, 9, tzinfo=timezone.utc),
                        "title": "Maariv leads with the Gaza corridor talks today"})
            page = build.render_page("en", [old, new], built_at)
            block = page.split(f'id="{cat}"', 1)[1].split("</section>", 1)[0]
            self.assertLess(block.index("Maariv leads"), block.index("Haaretz reviews"))


class WrongScriptDekTests(unittest.TestCase):
    """Owner report 2026-08-11: an Arabic feed summary rendered under an
    English hero headline. The scrub reads the text itself — no reliance on
    the feed's needs_translation flag — and swaps in the brief's opening."""

    def test_wrong_script_deks_replaced_from_brief_or_dropped(self):
        en = item()
        en.update({"pid": "dksc00en01",
                   "dek": "نظّمت البطريركية اللاتينية دورة تدريبية لموظفيها",
                   "brief": "The Latin Patriarchate trained its Jerusalem staff "
                            "on ethical decision-making, the church said. " * 6})
        en_no_brief = item()
        en_no_brief.update({"pid": "dksc00en02", "dek": "ملخص عربي بلا موجز"})
        ar = item()
        ar.update({"lang": "ar", "pid": "dksc00ar01",
                   "dek": "An English summary leaking into the Arabic edition",
                   "brief": "نظّمت البطريركية اللاتينية في القدس دورة تدريبية "
                            "لموظفيها حول أخلاقيات القرار، حسب بيان الكنيسة. " * 6})
        ar_ok = item()
        ar_ok.update({"lang": "ar", "pid": "dksc00ar02",
                      "dek": "ملخص عربي سليم يذكر مقاتلات F-35 بالاسم"})
        build.select_publishable_copy([en, en_no_brief], [ar, ar_ok])
        self.assertTrue(en["dek"].startswith("The Latin Patriarchate"))
        self.assertEqual(en_no_brief["dek"], "")
        self.assertIn("البطريركية", ar["dek"])
        self.assertIn("F-35", ar_ok["dek"])  # Latin acronyms in Arabic deks survive


class VideoEmbedTests(unittest.TestCase):
    def test_instagram_reel_embeds_with_rebuilt_src(self):
        html = longform.video_embed(
            "Reel caption",
            "https://www.instagram.com/reel/Dbg318clIQ8/?igsh=MXU3c2pzNzdnZTNmZQ==")
        self.assertIn('src="https://www.instagram.com/reel/Dbg318clIQ8/embed/captioned/"', html)
        self.assertIn('class="embed ig"', html)
        self.assertNotIn("igsh", html)  # tracking params never reach the page

    def test_youtube_telegram_and_mp4_still_embed(self):
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ",
                      longform.video_embed("", "https://youtu.be/dQw4w9WgXcQ"))
        self.assertIn("t.me/example/42?embed=1",
                      longform.video_embed("", "https://t.me/example/42"))
        self.assertIn("<video",
                      longform.video_embed("", "https://cdn.example.com/clip.mp4"))

    def test_self_hosted_mp4_video_is_copied_into_the_build(self):
        # A !video directive pointing at our own /media/ path must ship the
        # file with the build, or the embed 404s on the live site.
        record = item()
        record["brief"] = (
            "A report.\n\n"
            "!video[Inside the school](https://timesofpalestine.com/media/haya-washington-life-school-2026.mp4)"
        )
        with tempfile.TemporaryDirectory() as directory:
            longform.copy_media(directory, [record])
            self.assertTrue(
                (Path(directory) / "media" /
                 "haya-washington-life-school-2026.mp4").is_file())

    def test_non_whitelisted_hosts_do_not_embed(self):
        for url in ("https://vimeo.com/12345",
                    "https://www.instagram.com/stories/user/123/",
                    "https://evil.example.com/reel/abc/"):
            self.assertIsNone(longform.video_embed("", url))


class SportsRelevanceTests(unittest.TestCase):
    def test_regional_club_sports_leaking_through_link_match_is_dropped(self):
        record = item()
        record.update({
            "title": "الزمالك يعزز صفوفه بسبعة لاعبين قبل انطلاق الموسم الجديد",
            "dek": "أعلن النادي المصري تعاقداته الصيفية استعداداً للدوري الجديد.",
            # outlet URL satisfies the general relevance gate — the leak path
            "link": "https://felesteen.news/palestine/589f7b5e9",
        })
        self.assertIsNone(build.finish_item(record, {"id": "felesteen", "name": "صحيفة فلسطين"}))

    def test_palestinian_sports_story_is_kept(self):
        record = item()
        record.update({
            "title": "منتخب فلسطين يفتتح تصفيات كأس العالم بفوز مهم",
            "dek": "الفدائي يواصل مشواره في التصفيات بروح قتالية.",
            "link": "https://example.com/fidai-win",
        })
        out = build.finish_item(record, {"id": "felesteen", "name": "صحيفة فلسطين"})
        self.assertIsNotNone(out)


class ArabSupportSectionTests(unittest.TestCase):
    """The Arab Support division (owner directive 2026-08-02): wire items
    about Arab actors helping Palestinians land in the arabaid section."""

    def test_arab_actor_plus_assistance_categorizes_as_arabaid(self):
        record = item()
        record.update({
            "title": "Jordan dispatches medical aid convoy to Gaza field hospitals",
            "dek": "The army sent ten trucks of medicines to its hospitals in the Strip.",
        })
        self.assertEqual(build.categorize(record), "arabaid")

    def test_arabic_wire_support_story_categorizes_as_arabaid(self):
        record = item()
        record.update({
            "title": "مصر ترسل قافلة مساعدات جديدة إلى قطاع غزة عبر معبر رفح",
            "dek": "شاحنات محملة بالغذاء والدواء دخلت القطاع صباح اليوم.",
        })
        self.assertEqual(build.categorize(record), "arabaid")

    def test_arab_actor_without_assistance_does_not_leak_in(self):
        record = item()
        record.update({
            "title": "Egypt and Israel discuss security arrangements along the border",
            "dek": "Talks in Cairo covered the Philadelphi corridor patrols.",
        })
        self.assertNotEqual(build.categorize(record), "arabaid")


class OriginalRemoteLedeTests(unittest.TestCase):
    """A desk report may carry a remote lede only when the exact URL has a
    media-rights.json entry; verification failures degrade to the fallback
    chain instead of failing the build or publishing a broken frame."""

    URL = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           "Gadi%20Eizenkot,%20November%202020%20(GPOMN1%209040)%20(cropped).jpg?width=640")

    def test_manifest_backed_remote_lede_attaches_when_image_is_live(self):
        record = item()
        record["original"] = True
        with mock.patch.object(build, "remote_image_ok", return_value=True):
            build.attach_media(record, self.URL, local_original=True)
        self.assertEqual(record["image"], self.URL)
        self.assertIn("Wikimedia", record["media"]["credit"])

    def test_dead_remote_lede_leaves_original_photoless_not_broken(self):
        record = item()
        record["original"] = True
        with mock.patch.object(build, "remote_image_ok", return_value=False):
            build.attach_media(record, self.URL, local_original=True)
        self.assertIsNone(record["image"])

    def test_remote_lede_without_rights_entry_still_fails_loudly(self):
        record = item()
        record["original"] = True
        with self.assertRaises(build.PublishingError):
            build.attach_media(
                record, "https://example.com/random-photo.jpg",
                local_original=True)


class _FakeImageResponse:
    """Minimal stand-in for the ranged-GET response remote_image_ok reads."""

    def __init__(self, status=206, ctype="image/jpeg", length="184000"):
        self.status = status
        self.headers = {"Content-Type": ctype, "Content-Range": f"bytes 0-2047/{length}"}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class RemoteImageVerificationTests(unittest.TestCase):
    """Wikimedia answers a burst of portrait checks with 429 for a varying
    subset each run (owner report 2026-08-08). A rate limit is not a dead
    image: a URL that verified on a recent build keeps its photo, while a
    genuinely missing file still demotes to the fallback chain at once."""

    URL = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           "Mahmoud%20Abbas%20May%202018.jpg?width=640")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cache = Path(self._tmp.name) / "remote-image-cache.json"
        patches = [
            mock.patch.object(build, "REMOTE_IMAGE_CACHE", self.cache),
            mock.patch.object(build, "is_public_http_url", return_value=True),
            mock.patch.object(build.time, "sleep"),   # no real backoff in tests
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self._reset_state()
        self.addCleanup(self._reset_state)

    def _reset_state(self):
        build.remote_image_ok.cache_clear()
        build._remote_image_seen = None
        build._remote_image_dirty = False
        build._throttle_next.clear()

    def _warm_cache(self, url=None, age=None):
        # Default age is past the freshness window, so the probe still runs and
        # the memory is exercised as a fallback rather than a short-circuit.
        if age is None:
            age = build.REMOTE_IMAGE_FRESH + 60
        self.cache.write_text(json.dumps(
            {"verified": {url or self.URL: time.time() - age}}), encoding="utf-8")

    @staticmethod
    def _raises(status):
        def opener(request, timeout=8):
            raise urllib.error.HTTPError(
                request.full_url, status, "rate limited", {}, None)
        return opener

    def test_rate_limited_url_keeps_the_photo_verified_on_an_earlier_build(self):
        self._warm_cache()
        with mock.patch.object(build, "safe_urlopen", self._raises(429)):
            self.assertTrue(build.remote_image_ok(self.URL))

    def test_timeout_keeps_the_photo_verified_on_an_earlier_build(self):
        self._warm_cache()

        def opener(request, timeout=8):
            raise TimeoutError("read timed out")

        with mock.patch.object(build, "safe_urlopen", opener):
            self.assertTrue(build.remote_image_ok(self.URL))

    def test_recent_verification_skips_the_network_check_entirely(self):
        # The burst of repeat checks is what earns the 429: a portrait verified
        # minutes ago is not re-fetched by the next ten-minute build.
        self._warm_cache(age=120)

        def opener(request, timeout=8):
            raise AssertionError("a fresh verification must not hit the network")

        with mock.patch.object(build, "safe_urlopen", opener):
            self.assertTrue(build.remote_image_ok(self.URL))

    def test_rate_limited_url_with_no_memory_still_falls_back(self):
        with mock.patch.object(build, "safe_urlopen", self._raises(429)):
            self.assertFalse(build.remote_image_ok(self.URL))

    def test_expired_verification_no_longer_covers_a_rate_limit(self):
        self._warm_cache(age=build.REMOTE_IMAGE_TTL + 60)
        with mock.patch.object(build, "safe_urlopen", self._raises(429)):
            self.assertFalse(build.remote_image_ok(self.URL))

    def test_rate_limited_head_does_not_rescue_a_missing_file(self):
        # The ranged GET is the decisive probe: a 404 there demotes even when
        # HEAD was rate-limited a moment earlier.
        self._warm_cache()
        calls = {"n": 0}

        def opener(request, timeout=8):
            calls["n"] += 1
            raise urllib.error.HTTPError(
                request.full_url, 429 if calls["n"] % 2 else 404, "mixed", {}, None)

        with mock.patch.object(build, "safe_urlopen", opener):
            self.assertFalse(build.remote_image_ok(self.URL))

    def test_missing_file_demotes_at_once_and_forgets_the_verification(self):
        self._warm_cache()
        with mock.patch.object(build, "safe_urlopen", self._raises(404)):
            self.assertFalse(build.remote_image_ok(self.URL))
        build.save_remote_image_cache()
        self.assertEqual(
            json.loads(self.cache.read_text(encoding="utf-8"))["verified"], {})

    def test_live_image_is_remembered_for_the_next_build(self):
        with mock.patch.object(build, "safe_urlopen",
                               lambda request, timeout=8: _FakeImageResponse()):
            self.assertTrue(build.remote_image_ok(self.URL))
        build.save_remote_image_cache()
        self.assertIn(
            self.URL, json.loads(self.cache.read_text(encoding="utf-8"))["verified"])

    def test_rate_limited_check_is_retried_once_before_it_counts(self):
        # HEAD and GET both 429 on the first probe; the retry finds the image,
        # so a cold URL survives a passing rate limit without any memory.
        calls = {"n": 0}

        def opener(request, timeout=8):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "slow down", {}, None)
            return _FakeImageResponse()

        with mock.patch.object(build, "safe_urlopen", opener):
            self.assertTrue(build.remote_image_ok(self.URL))
        self.assertGreater(calls["n"], 2)

    def test_wikimedia_hosts_are_paced_and_given_a_longer_timeout(self):
        self.assertEqual(build.throttle_key(self.URL), "wikimedia.org")
        self.assertEqual(build.throttle_key("https://images.example.com/a.jpg"), "")
        seen = []
        with mock.patch.object(build, "safe_urlopen",
                               lambda request, timeout=8: seen.append(timeout)
                               or _FakeImageResponse()):
            build.remote_image_ok(self.URL)
        self.assertEqual(seen[0], build.THROTTLED_TIMEOUT)


class RunningStoryDedupeTests(unittest.TestCase):
    """Near-identical headlines are one running story: neither an updated
    count nor days between filings may put the same headline on the site
    twice (owner call 2026-08-02, after five same-headline follow-ups ran)."""

    @staticmethod
    def wire(title, hours_after=0, count=0, score=10):
        record = item()
        record.update({
            "title": title,
            "link": f"https://example.com/rolling-{count}",
            "pid": f"rolling{count:03d}",
            "date": datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
            + timedelta(hours=hours_after),
            "score": score,
            "corroborating_sources": [],
        })
        return record

    def test_rolling_count_updates_collapse_to_one_story(self):
        # Five follow-ups over four days: only the tolls differ, and the
        # spacing defeats any fixed dedupe window. Exactly one survives.
        stories = [
            self.wire(f"Israeli strikes on Gaza City kill {n} Palestinians",
                      hours_after=h, count=i, score=10 + i)
            for i, (n, h) in enumerate([(12, 0), (15, 20), (18, 44), (21, 70), (24, 92)])
        ]
        survivors = build.dedupe_events(stories)
        self.assertEqual(len(survivors), 1)

    def test_distinct_incidents_in_different_places_both_run(self):
        pair = [
            self.wire("Israeli forces kill five Palestinians in Jenin raid", count=1),
            self.wire("Israeli forces kill nine Palestinians in Rafah strike",
                      hours_after=2, count=2),
        ]
        self.assertEqual(len(build.dedupe_events(pair)), 2)

    def test_follow_up_chain_matches_absorbed_members_not_just_the_head(self):
        # C paraphrases B but not A; B already folded into A's cluster, so C
        # must match through the absorbed member instead of leaking.
        a = self.wire("Israeli forces kill three Palestinians in Jenin raid",
                      count=1, score=30)
        b = self.wire("Army kills three Palestinians during Jenin attack",
                      hours_after=30, count=2, score=20)
        c = self.wire("Army kills 3 Palestinians during Jenin attack",
                      hours_after=64, count=3, score=10)
        self.assertEqual(len(build.dedupe_events([a, b, c])), 1)

    def test_desk_originals_never_fold_into_each_other(self):
        first, second = self.wire("Gaza aid convoy report", count=1), self.wire(
            "Gaza aid convoy report", hours_after=1, count=2)
        for record in (first, second):
            record.update({"original": True, "source_id": "top-original"})
        self.assertEqual(len(build.dedupe_events([first, second])), 2)

    def test_arabic_rolling_headline_collapses_across_days(self):
        stories = [
            self.wire(f"ارتفاع حصيلة الشهداء في قصف مدينة غزة إلى {n}",
                      hours_after=h, count=i)
            for i, (n, h) in enumerate([(30, 0), (34, 40), (39, 80)])
        ]
        self.assertEqual(len(build.dedupe_events(stories)), 1)


class CardImageDedupeTests(unittest.TestCase):
    """One photo, one story: duplicate remote card images collapse to the
    newest story; the rest step down to their category cover."""

    def _item(self, pid, hours, image, cat="gaza"):
        it = item()
        it.update({
            "pid": pid, "link": f"https://example.com/{pid}",
            "date": datetime(2026, 8, 2, 12, tzinfo=timezone.utc) + timedelta(hours=hours),
            "image": image, "cat": cat,
        })
        return it

    def test_same_url_keeps_photo_only_on_newest(self):
        url = "https://cdn.example.com/frame.jpg"
        older = self._item("older00001", 0, url)
        newer = self._item("newer00001", 2, url)
        with mock.patch.object(build, "_card_image_hash", return_value=None):
            build.dedupe_card_images([older, newer])
        self.assertEqual(newer["image"], url)
        # The fallback alternates the branded gaza cover's A/B(/AR) variants
        # (owner visual sweep 2026-08-11) — any of them is the correct outcome.
        self.assertRegex(older["image"],
                         r"^/media/times-of-palestine-cover-gaza(-b)?(-ar)?\.svg$")
        self.assertEqual(older["media"]["rightsBasis"], "owned")

    def test_same_bytes_under_two_urls_collapse(self):
        older = self._item("older00002", 0, "https://cdn.example.com/a.jpg")
        newer = self._item("newer00002", 2, "https://cdn.example.com/b.jpg")
        with mock.patch.object(build, "_card_image_hash", return_value="samehash"):
            build.dedupe_card_images([older, newer])
        self.assertEqual(newer["image"], "https://cdn.example.com/b.jpg")
        self.assertTrue(older["image"].startswith("/media/times-of-palestine-cover-"))

    def test_distinct_images_and_local_covers_untouched(self):
        a = self._item("distinct001", 0, "https://cdn.example.com/a.jpg")
        b = self._item("distinct002", 1, "https://cdn.example.com/b.jpg")
        c = self._item("localcover1", 2, "/media/times-of-palestine-cover-gaza.svg")
        d = self._item("localcover2", 3, "/media/times-of-palestine-cover-gaza.svg")
        with mock.patch.object(build, "_card_image_hash", side_effect=lambda u: None):
            build.dedupe_card_images([a, b, c, d])
        self.assertEqual(a["image"], "https://cdn.example.com/a.jpg")
        self.assertEqual(b["image"], "https://cdn.example.com/b.jpg")
        self.assertEqual(c["image"], "/media/times-of-palestine-cover-gaza.svg")
        self.assertEqual(d["image"], "/media/times-of-palestine-cover-gaza.svg")


class ListenButtonTests(unittest.TestCase):
    """Every story page carries the listen button and its inline player."""

    def test_story_page_includes_listen_button_and_player(self):
        it = item()
        it.update({"brief": "A first paragraph of the story.\n\nA second paragraph.",
                   "image": "/media/x.svg", "pid": "listen0001"})
        for lang, play in (("en", "Listen"), ("ar", "استمع")):
            it2 = dict(it, lang=lang)
            html = build.render_story(it2, lang, [], [], datetime(2026, 8, 3, tzinfo=timezone.utc))
            self.assertIn('id="listen"', html)
            self.assertIn(play, html)
            self.assertIn("speechSynthesis", html)
            self.assertIn('data-resume', html)


class LiveTVTests(unittest.TestCase):
    """The Arabic edition carries the floating live pill; editions with an
    empty stream id render nothing."""

    def test_arabic_pages_carry_live_pill_english_does_not(self):
        built_at = datetime(2026, 8, 3, tzinfo=timezone.utc)
        it = item()
        it.update({"brief": "فقرة أولى.", "image": "/media/x.svg", "pid": "live000001", "lang": "ar"})
        ar_front = build.render_page("ar", [it], built_at)
        ar_story = build.render_story(it, "ar", [], [], built_at)
        self.assertIn('id="livefab"', ar_front)
        self.assertIn('id="livefab"', ar_story)
        self.assertIn("bNyUyrR0PHo", ar_front)
        self.assertIn("مباشر", ar_front)
        it_en = item(); it_en.update({"image": "/media/x.svg", "pid": "live000002"})
        en_front = build.render_page("en", [it_en], built_at)
        self.assertNotIn('id="livefab"', en_front)


class ImageOverrideTests(unittest.TestCase):
    """The photo desk can kill a specific story's image by pid."""

    def test_override_replaces_wire_image_with_category_cover(self):
        it = item()
        it.update({"pid": "287efd3ca4", "cat": "gaza",
                   "image": "https://cdn.example.com/bad-frame.jpg"})
        other = item()
        other.update({"pid": "untouched1", "cat": "gaza",
                      "image": "https://cdn.example.com/fine.jpg"})
        with mock.patch.object(build, "IMAGE_OVERRIDES",
                               {"287efd3ca4": {"image": "cover"}}):
            build.apply_image_overrides([it, other])
        self.assertEqual(it["image"], "/media/times-of-palestine-cover-gaza.svg")
        self.assertEqual(it["media"]["rightsBasis"], "owned")
        self.assertEqual(other["image"], "https://cdn.example.com/fine.jpg")

    def test_override_accepts_explicit_local_asset(self):
        it = item()
        it.update({"pid": "abcabcabca", "image": "https://cdn.example.com/x.jpg"})
        with mock.patch.object(build, "IMAGE_OVERRIDES",
                               {"abcabcabca": {"image": "/media/times-of-palestine-her-story-2026.svg"}}):
            build.apply_image_overrides([it])
        self.assertEqual(it["image"], "/media/times-of-palestine-her-story-2026.svg")

    def test_local_photo_override_carries_its_own_manifest_credit(self):
        # The Ali Al Thawadi order (2026-08-03): an owner-supplied photo must
        # run with ITS manifest credit, never the replaced wire image's.
        # (The eb18db4ce2 entry has since retired from image-overrides.json —
        # the story now carries the photo in its own image: header — so the
        # behaviour is pinned here with an explicit override mapping.)
        it = item()
        it.update({"pid": "eb18db4ce2",
                   "image": "https://cdn.example.com/wire.jpg",
                   "media": {"credit": "Photo: Some Wire Agency",
                             "rightsBasis": "wire", "source": "wire",
                             "licenseUrl": None}})
        with mock.patch.object(
                build, "IMAGE_OVERRIDES",
                {"eb18db4ce2": {"image": "/media/ali-al-thawadi-un-2026.jpg"}}):
            build.apply_image_overrides([it])
        self.assertEqual(it["image"], "/media/ali-al-thawadi-un-2026.jpg")
        self.assertEqual(it["media"]["credit"], "Photo: Times of Palestine")
        self.assertNotIn("Wire Agency", str(it["media"]))
        self.assertTrue((Path(build.ROOT) / "originals" / "media"
                         / "ali-al-thawadi-un-2026.jpg").is_file())


class StandingFlagTests(unittest.TestCase):
    """Only an explicit standing flag keeps a story out of the hero tier —
    a long archive shelf-life alone must not (owner report 2026-08-03)."""

    def test_long_shelf_life_news_can_lead_but_standing_pages_cannot(self):
        # Hero freshness windows are measured against the REAL clock, so the
        # fixture dates must be relative — fixed dates turned this test into a
        # time bomb that broke main a day later (2026-08-04 outage).
        built_at = datetime.now(timezone.utc)
        fresh_news = item()
        fresh_news.update({
            "title": "Israeli forces raid a Gaza district as the day begins",
            "link": "https://example.com/fresh-long", "pid": "freshlong1",
            "date": built_at - timedelta(minutes=30),
            "image": "/media/x.svg", "score": 50, "cat": "gaza",
            "max_age_hours": 999999})
        guide = item()
        guide.update({
            "title": "Times of Palestine maps scholarships for Palestinian students",
            "link": "https://example.com/guide", "pid": "guidepage1",
            "date": built_at - timedelta(minutes=10),
            "image": "/media/y.svg", "score": 60,
            "max_age_hours": 999999, "standing": True})
        homepage = build.render_page("en", [fresh_news, guide], built_at)
        # SVG-led fixture art renders the split hero (design pass
        # 2026-09-01); photo art keeps the overlay — bound the hero block
        # by structure, not by which skin rendered.
        hero_zone = homepage.split('hero-imgwrap', 1)[1].split('hero-sub', 1)[0]
        self.assertIn("Israeli forces raid a Gaza district", hero_zone)
        self.assertNotIn("maps scholarships", hero_zone)


class LatestRailTests(unittest.TestCase):
    """The Latest is a live wire: fresh entries pulse on the timeline, stories
    with art carry a thumbnail, and the clock script keeps timestamps ticking."""

    def test_rail_marks_fresh_items_and_carries_thumbs_and_clock(self):
        now = datetime.now(timezone.utc)
        fresh = item()
        fresh.update({
            "title": "Israeli forces raid a Gaza district before dawn today",
            "link": "https://example.com/rail-fresh", "pid": "railfresh1",
            "date": now - timedelta(minutes=10), "image": "/media/x.svg"})
        stale = item()
        stale.update({
            "title": "Older cultural festival coverage stays on the record",
            "link": "https://example.com/rail-stale", "pid": "railstale1",
            "date": now - timedelta(days=2), "image": None})
        homepage = build.render_page("en", [fresh, stale], now)
        rail = homepage.split('<aside class="latest">', 1)[1].split("</aside>", 1)[0]
        self.assertEqual(rail.count('<li class="fresh">'), 1)
        self.assertIn("lt-thumb", rail)
        self.assertIn("setInterval(tick,30000)", homepage)

    def test_story_page_carries_the_clock_script(self):
        now = datetime.now(timezone.utc)
        it = item()
        it.update({"brief": "A first paragraph.", "image": "/media/x.svg",
                   "pid": "railclock1"})
        html = build.render_story(it, "en", [], [], now)
        self.assertIn("setInterval(tick,30000)", html)

    def test_clock_never_relativizes_the_absolute_story_stamp(self):
        # The Published/Updated stamp is the page's honest absolute record;
        # the ticking clock must only rewrite relative (.t) timestamps.
        self.assertIn('t.closest(".story-stamp")', build._CLOCK_JS)
        self.assertIn('t.closest(".revisions")', build._CLOCK_JS)


class StaticFeatureTests(unittest.TestCase):
    """Static features ship self-hosted assets only: a Google Fonts link
    leaks every reader's IP to a third party and dies on blocked networks —
    the same rule the main site already enforces on itself."""

    def test_static_features_do_not_depend_on_third_party_fonts(self):
        for feature in Path(build.ROOT).iterdir():
            if not (feature.is_dir() and (feature / ".static-feature").is_file()):
                continue
            for asset in feature.rglob("*"):
                if asset.suffix in (".html", ".css"):
                    text = asset.read_text(encoding="utf-8")
                    self.assertNotIn("fonts.googleapis.com", text, asset)
                    self.assertNotIn("fonts.gstatic.com", text, asset)


class GazaNumbersTests(unittest.TestCase):
    """Gaza by the Numbers leads with the Ministry of Health's live toll and
    ships the poll file + in-place update script (owner directive 2026-08-03)."""

    SUMMARY = {
        "gaza": {"last_update": "2026-08-02",
                 "killed": {"total": 68643, "children": 20125, "women": 12500,
                            "press": 254, "famine": 470},
                 "injured": {"total": 170655},
                 "famine": {"total": 470}},
        "west_bank": {"last_update": "2026-08-03",
                      "killed": {"total": 1093, "children": 220},
                      "injured": {"total": 9970},
                      "settler_attacks": 2470},
        "known_press_killed_in_gaza": {"records": 254},
    }

    PRISONERS = {"asOf": "2026-04-14",
                 "figures": {"pr_total": 9600, "pr_admin": 3532, "pr_gaza": 1251,
                             "pr_women": 86, "pr_children": 350}}

    def setUp(self):
        import gaza_panel
        self.gp = gaza_panel
        self._moh, self._gi = dict(gaza_panel._moh_cache), dict(gaza_panel._gaza_cache)
        self._pr = dict(gaza_panel._pr_cache)
        gaza_panel._moh_cache.clear()
        gaza_panel._gaza_cache.clear()
        gaza_panel._pr_cache.clear()
        gaza_panel._moh_cache["data"] = self.SUMMARY
        gaza_panel._gaza_cache["rows"] = {}
        gaza_panel._pr_cache["data"] = self.PRISONERS
        os.environ.pop("TOP_OFFLINE", None)

    def tearDown(self):
        self.gp._moh_cache.clear(); self.gp._moh_cache.update(self._moh)
        self.gp._gaza_cache.clear(); self.gp._gaza_cache.update(self._gi)
        self.gp._pr_cache.clear(); self.gp._pr_cache.update(self._pr)

    def test_panel_renders_moh_lead_row_with_live_hooks(self):
        html = self.gp.panel("en")
        self.assertIn("Palestine by the Numbers", html)
        self.assertIn('data-gi-key="killed"', html)
        self.assertIn('data-gi-val="68643"', html)
        self.assertIn("68,643", html)
        self.assertIn("Gaza Ministry of Health", html)
        self.assertIn("2026-08-02", html)
        self.assertIn("gaza-numbers.json", html)   # the polling script travels
        self.assertIn("gi-live", html)

    def test_west_bank_row_carries_deaths_and_settler_attacks(self):
        html = self.gp.panel("en")
        self.assertIn("West Bank", html)
        self.assertIn('data-gi-key="wb_killed"', html)
        self.assertIn('data-gi-val="1093"', html)
        self.assertIn('data-gi-key="wb_attacks"', html)
        self.assertIn("Settler attacks", html)
        self.assertIn("UN OCHA", html)
        self.assertIn('data-gi-asof="wb"', html)
        self.assertIn("2026-08-03", html)

    def test_prisoners_row_arranged_by_age_and_gender(self):
        html = self.gp.panel("en")
        self.assertIn("Prisoners in Israeli jails", html)
        self.assertIn('data-gi-key="pr_total"', html)
        self.assertIn("9,600+", html)          # Addameer reports "more than"
        self.assertIn('data-gi-key="pr_women"', html)
        self.assertIn('data-gi-key="pr_children"', html)
        self.assertIn("Administrative detention", html)
        self.assertIn("Addameer", html)
        self.assertIn('data-gi-asof="pr"', html)
        self.assertIn("2026-04-14", html)

    def test_composition_strips_show_shares(self):
        html = self.gp.panel("en")
        self.assertIn("gi-comp", html)
        self.assertIn("Of those killed", html)
        self.assertIn("Held without charge or trial", html)
        # 3,532 + 1,251 of 9,600 — the strip carries both detention segments
        self.assertIn("Children 29%", html)
        self.assertIn("From Gaza, uncharged 13%", html)

    def test_arabic_panel_uses_arabic_digits_and_labels(self):
        html = self.gp.panel("ar")
        self.assertIn("فلسطين بالأرقام", html)
        self.assertIn("٦٨،٦٤٣", html)
        self.assertIn("شهداء", html)
        self.assertIn("وزارة الصحة في غزة", html)
        self.assertIn("الضفة الغربية", html)
        self.assertIn("اعتداءات المستوطنين", html)
        self.assertIn("الأسرى في سجون الاحتلال", html)
        self.assertIn("أسيرات", html)
        self.assertIn("٩،٦٠٠+", html)
        self.assertIn("مؤسسة الضمير", html)

    def test_payload_carries_figures_for_the_poll_file(self):
        data = self.gp.payload()
        self.assertEqual(data["figures"]["killed"], 68643)
        self.assertEqual(data["figures"]["press"], 254)
        self.assertEqual(data["figures"]["wb_killed"], 1093)
        self.assertEqual(data["figures"]["wb_attacks"], 2470)
        self.assertEqual(data["figures"]["pr_total"], 9600)
        self.assertEqual(data["figures"]["pr_women"], 86)
        self.assertEqual(data["asOf"], "2026-08-02")
        self.assertEqual(data["wbAsOf"], "2026-08-03")
        self.assertEqual(data["prAsOf"], "2026-04-14")

    def test_everything_fails_open_without_data(self):
        self.gp._moh_cache["data"] = {}
        self.gp._pr_cache["data"] = {}
        self.assertEqual(self.gp.panel("en"), "")
        self.assertIsNone(self.gp.payload())

    def test_panel_offers_open_data_downloads_in_both_languages(self):
        html = self.gp.panel("en")
        self.assertIn('href="/data/gaza-numbers.json" download', html)
        self.assertIn('href="/data/gaza-numbers.csv" download', html)
        self.assertIn("Open data", html)
        ar = self.gp.panel("ar")
        self.assertIn("حمّل هذا السجل", ar)
        self.assertIn('href="/data/gaza-numbers.csv" download', ar)

    def test_complex_figures_carry_focusable_methodology_tooltips(self):
        html = self.gp.panel("en")
        self.assertIn('class="gi-help" tabindex="0"', html)
        self.assertIn("renewable indefinitely", html)          # pr_admin
        self.assertIn("Unlawful Combatants Law", html)         # pr_gaza
        self.assertIn("malnutrition and dehydration", html)    # famine
        self.assertIn("casualties or property damage", html)   # wb_attacks
        ar = self.gp.panel("ar")
        self.assertIn("المقاتلين غير الشرعيين", ar)
        # the note reaches screen readers via the marker's aria-label
        self.assertIn('aria-label="اعتقال بأمر عسكري إسرائيلي', ar)

    def test_panel_keeps_a_chart_slot_when_daily_series_is_down(self):
        old = self.gp._get_json
        self.gp._get_json = lambda url: (_ for _ in ()).throw(OSError()) if url == self.gp.DAILY_URL else old(url)
        try:
            html = self.gp.panel("en")
        finally:
            self.gp._get_json = old
        self.assertIn('class="toll-chart toll-chart-fallback"', html)
        self.assertIn("Daily series temporarily unavailable", html)
        self.assertIn('aria-label="Gaza deaths, cumulative: 68,643', html)

    def test_panel_keeps_short_loaded_series_on_the_existing_non_render_path(self):
        old = self.gp._get_json
        self.gp._get_json = lambda url: [{"report_date": "2026-08-01", "killed_cum": 10}] if url == self.gp.DAILY_URL else old(url)
        try:
            html = self.gp.panel("en")
        finally:
            self.gp._get_json = old
        self.assertNotIn("Daily series temporarily unavailable", html)
        self.assertNotIn("toll-chart toll-chart-fallback", html)

    def test_csv_export_mirrors_the_payload_with_bilingual_labels(self):
        import csv as _csv
        import io as _io
        data = self.gp.payload()
        rows = list(_csv.reader(_io.StringIO(self.gp.payload_csv(data))))
        self.assertEqual(rows[0][:5],
                         ["region", "key", "indicator_en", "indicator_ar", "value"])
        by_key = {r[1]: r for r in rows[1:]}
        self.assertEqual(by_key["killed"][0], "gaza")
        self.assertEqual(by_key["killed"][4], "68643")
        self.assertEqual(by_key["killed"][5], "2026-08-02")
        self.assertEqual(by_key["wb_attacks"][2], "Settler attacks")
        self.assertEqual(by_key["wb_attacks"][3], "اعتداءات المستوطنين")
        self.assertEqual(by_key["pr_total"][0], "prisoners")
        self.assertIn("Addameer", by_key["pr_total"][6])
        # every published figure has a CSV row — nothing silently dropped
        self.assertEqual(set(by_key), set(data["figures"]))


class _FakeBriefsClient:
    """Plays back canned model replies and records every request."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                text = outer._replies.pop(0)
                block = type("Block", (), {"type": "text", "text": text})()
                return type("Response", (), {"content": [block]})()

        self.messages = _Messages()


class LanguageQualityTests(unittest.TestCase):
    """Machine diction never publishes unchallenged (owner order 2026-08-03,
    after «أسلمت قوات الاحتلال» reached the Arabic front page)."""

    AR_BAD_BODY = (
        "أسلمت قوات الاحتلال جثامين ثلاثة أسرى إلى اللجنة الدولية للصليب الأحمر "
        "عند حاجز بيت حانون شمالي قطاع غزة بعد ظهر الأحد، بحسب وكالة معاً. "
        "وأوضحت الوكالة أن التسليم جرى بحضور طواقم طبية فلسطينية استلمت "
        "الجثامين ونقلتها إلى مجمع الشفاء الطبي غربي مدينة غزة.\n\n"
        "وذكرت الوكالة أن الطواقم باشرت توثيق هويات الأسرى الثلاثة تمهيداً "
        "لتسليم الجثامين إلى ذويهم في وقت لاحق من مساء اليوم نفسه. وأشارت إلى "
        "أن عمليات مماثلة جرت خلال الأسابيع الماضية عبر الحاجز ذاته ضمن "
        "التفاهمات القائمة بين الجانبين برعاية اللجنة الدولية للصليب الأحمر، "
        "فيما ينتظر ذوو أسرى آخرين إشعاراً مماثلاً بشأن أبنائهم.")
    AR_GOOD_BODY = AR_BAD_BODY.replace("أسلمت", "سلّمت")

    def setUp(self):
        # The fixtures must clear the structural gates so the diction tests
        # exercise diction alone.
        assert len(self.AR_BAD_BODY.split()) >= 90
        assert len([p for p in self.AR_BAD_BODY.split("\n\n") if p.strip()]) >= 2

    def test_arabic_wrong_verb_and_fillers_are_flagged(self):
        self.assertTrue(build.language_quality_issues("أسلمت قوات الاحتلال الجثامين", "ar"))
        self.assertTrue(build.language_quality_issues("قامت الطائرات بقصف المخيم", "ar"))
        self.assertTrue(build.language_quality_issues("تم اعتقال ثلاثة شبان", "ar"))
        self.assertTrue(build.language_quality_issues("يذكر أن الوفد وصل أمس", "ar"))
        self.assertFalse(build.language_quality_issues("سلّمت قوات الاحتلال الجثامين", "ar"))
        self.assertFalse(build.language_quality_issues("قصفت الطائرات المخيم فجراً", "ar"))

    def test_english_stock_ai_diction_is_flagged(self):
        self.assertTrue(build.language_quality_issues("The report delves into the crisis.", "en"))
        self.assertTrue(build.language_quality_issues("The strike underscores the risk.", "en"))
        self.assertTrue(build.language_quality_issues("It is worth noting the toll rose.", "en"))
        self.assertFalse(build.language_quality_issues(
            "Israeli forces raided the camp at dawn, residents said.", "en"))

    def test_write_brief_sends_flagged_draft_back_for_one_editor_pass(self):
        title = "HEADLINE: الاحتلال يسلم جثامين ثلاثة أسرى للصليب الأحمر"
        client = _FakeBriefsClient([
            f"{title}\n\n{self.AR_BAD_BODY}",
            f"{title}\n\n{self.AR_GOOD_BODY}",
        ])
        it = item()
        it.update({"lang": "ar", "pid": "diction001"})
        brief = build.write_brief(client, it)
        self.assertIn("سلّمت", brief)
        self.assertNotIn("أسلمت", brief)
        self.assertEqual(len(client.calls), 2)
        # The retry carries the flagged wording back to the desk as editor notes.
        retry_convo = client.calls[1]["messages"]
        self.assertEqual(retry_convo[1]["role"], "assistant")
        self.assertIn("أسلم", retry_convo[2]["content"])

    def test_persistent_diction_publishes_best_effort_never_holds_coverage(self):
        title = "HEADLINE: الاحتلال يسلم جثامين ثلاثة أسرى للصليب الأحمر"
        client = _FakeBriefsClient([
            f"{title}\n\n{self.AR_BAD_BODY}",
            f"{title}\n\n{self.AR_BAD_BODY}",
        ])
        it = item()
        it.update({"lang": "ar", "pid": "diction002"})
        brief = build.write_brief(client, it)
        self.assertIsNotNone(brief)          # charter: gating defaults to publish
        self.assertNotIn("brief_refused", it)
        self.assertEqual(len(client.calls), 2)


class PacingTests(unittest.TestCase):
    """Neither wall-of-text paragraphs nor two-line stub articles publish
    (owner order 2026-08-03)."""

    LONG_SENT = ("Israeli forces raided the northern district before dawn and "
                 "residents described convoys moving through the market road. ")

    def test_reflow_splits_wall_of_text_at_sentence_boundaries(self):
        wall = self.LONG_SENT * 8                      # ~128 words, one block
        flowed = build.reflow_paragraphs(wall)
        paras = flowed.split("\n\n")
        self.assertGreater(len(paras), 1)
        for p in paras:
            self.assertLessEqual(len(p.split()), build.MAX_PARA_WORDS)
        self.assertEqual(flowed.replace("\n\n", " ").split(), wall.split())

    def test_reflow_leaves_well_paced_copy_alone(self):
        text = "One short paragraph here.\n\nAnd a second one after it."
        self.assertEqual(build.reflow_paragraphs(text), text)

    def test_structure_issues_flag_stub_and_single_block(self):
        stub = "Israeli forces raided the camp at dawn. Residents counted twelve vehicles."
        issues = build.structure_issues(stub, "en")
        self.assertTrue(any("too short" in i for i in issues))
        self.assertTrue(any("single-block" in i for i in issues))
        good = (self.LONG_SENT * 3).strip() + "\n\n" + (self.LONG_SENT * 3).strip()
        self.assertEqual(build.structure_issues(good, "en"), [])

    def test_stub_brief_is_withheld_after_failed_expansion(self):
        title = "HEADLINE: Israeli forces raid Jenin camp before dawn today"
        stub = ("Israeli forces raided Jenin refugee camp before dawn, the "
                "Wafa news agency reported. Residents counted twelve military "
                "vehicles entering through the eastern road of the camp.")
        client = _FakeBriefsClient([f"{title}\n\n{stub}", f"{title}\n\n{stub}"])
        it = item()
        it.update({"pid": "pacing0001"})
        self.assertIsNone(build.write_brief(client, it))
        self.assertTrue(it.get("brief_refused"))
        self.assertEqual(len(client.calls), 2)     # the desk got its retry first

    def test_publish_floor_drops_stubs_but_keeps_substantial_briefs(self):
        stub_item = item()
        stub_item["brief"] = "Two short sentences only. Nothing else was reported."
        ok_item = item()
        ok_item.update({"link": "https://example.com/ok", "pid": "pacing0002",
                        "brief": (self.LONG_SENT * 3).strip() + "\n\n"
                                 + (self.LONG_SENT * 2).strip()})
        kept = build.select_publishable_copy([stub_item, ok_item], [])
        self.assertEqual([k["pid"] for k in kept], ["pacing0002"])

    def test_story_page_renders_reflowed_multi_paragraph_body(self):
        it = item()
        it.update({"brief": (self.LONG_SENT * 8).strip(), "pid": "pacing0003",
                   "image": "/media/x.svg"})
        html = build.render_story(it, "en", [], [],
                                  datetime(2026, 8, 3, tzinfo=timezone.utc))
        body = html.split('class="kind"', 1)[1]
        self.assertGreaterEqual(body.count('<p class="summary">'), 2)

    def test_longform_splits_wall_paragraphs_in_originals_too(self):
        # Owner order 2026-08-03: no wall paragraphs anywhere — originals
        # included. Prose blocks split at render; structure blocks untouched.
        wall = (self.LONG_SENT * 8).strip()
        html = longform.body_html(f"## A subhead\n\n{wall}\n\n> A quoted line.")
        self.assertGreaterEqual(html.count('<p class="summary">'), 2)
        self.assertEqual(html.count('<h2 class="sub">'), 1)
        self.assertEqual(html.count('<blockquote class="pull">'), 1)
        text_only = re.sub(r"<[^>]+>", " ", html)
        self.assertEqual(text_only.split()[2:2 + len(wall.split())][:5],
                         wall.split()[:5])   # words preserved, only breaks added

    def test_longform_leaves_short_paragraphs_alone(self):
        html = longform.body_html("A short paragraph that stays whole.")
        self.assertEqual(html.count('<p class="summary">'), 1)


class MobileChromeTests(unittest.TestCase):
    """Outside review 2026-08-03 (Gemini): the ticker's seamless-loop copy is
    decorative and must not reach screen readers or the tab order; the desks
    nav tier folds behind a More toggle on phones."""

    def test_ticker_duplicate_copy_is_hidden_from_assistive_tech(self):
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        it = item()
        it.update({"image": "/media/x.svg", "pid": "chrome0001"})
        homepage = build.render_page("en", [it], built_at)
        track = homepage.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn('aria-hidden="true" tabindex="-1"', track)
        story = build.render_story(dict(it, brief="A body paragraph here."),
                                   "en", [], [it], built_at)
        s_track = story.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn('aria-hidden="true" tabindex="-1"', s_track)

    def test_nav_flat_priority_row_plus_single_all_sections_index(self):
        # Flat-priority nav (owner decision 2026-08-06, replacing the four
        # per-group dropdowns): flagship sections are DIRECT links — Gaza
        # never hides behind a menu — and ONE All-Sections button opens the
        # full index whose columns are the old groups as .mhead headings.
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        it = item()
        it.update({"image": "/media/x.svg"})
        for lang, col_label, all_label in (
                ("en", "News & Regions", "All Sections"),
                ("ar", "الأخبار والمناطق", "كل الأقسام")):
            rows = [dict(it, lang=lang, cat="gaza", pid=f"chrome100{i}",
                         title=f"Gaza artists open community exhibition number {i}",
                         link=f"https://example.com/nav-{i}") for i in range(12)]
            page = build.render_page(lang, rows, built_at)
            nav = page.split('<nav class="sections"', 1)[1].split("</nav>", 1)[0]
            self.assertIn('href="#gaza"', nav)               # flagship = direct link
            self.assertIn('aria-controls="navg-all"', nav)   # exactly one index…
            self.assertNotIn('aria-controls="navg-regions"', nav)  # …no group buttons
            self.assertEqual(nav.count('class="nav-gbtn"'), 1)
            self.assertIn('class="nav-drop mega"', nav)
            # Gold specials strip leads the panel (owner order 2026-08-11):
            # visible on open, never below the fold of the phone scroll.
            mega = nav.split('class="nav-drop mega"', 1)[1]
            self.assertIn('class="mspecials"', mega)
            self.assertLess(mega.index('class="mspecials"'),
                            mega.index('class="mcol"'))
            self.assertIn(f'<p class="mhead">{col_label}</p>', nav)
            self.assertIn(all_label, nav)
            self.assertNotIn('class="nav-more"', nav)
            self.assertNotIn('navtier2', nav)

    def test_interior_pages_carry_the_sections_nav_and_totop(self):
        # UX study (owner order 2026-08-11): a reader landing on a story from
        # a shared link gets the same wayfinding as the front page — the
        # sticky bar links the section archives, the footer indexes every
        # section, and a back-to-top floats after two screens of scroll.
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        it = item()
        it.update({"image": "/media/x.svg", "brief": "A body paragraph here."})
        for lang in ("en", "ar"):
            it2 = dict(it, lang=lang)
            story = build.render_story(it2, lang, [], [it2], built_at)
            self.assertIn('<nav class="sections"', story)
            self.assertIn('href="../section-gaza.html"', story)
            self.assertIn('href="../search.html"', story)
            self.assertIn('class="foot-sections"', story)
            self.assertIn('class="totop"', story)
            section = build.render_section_page(lang, "gaza", [it2], built_at)
            self.assertIn('<nav class="sections"', section)
            self.assertIn('href="section-westbank.html"', section)
            self.assertIn('class="foot-sections"', section)
            self.assertIn('class="totop"', section)
            home = build.render_page(lang, [it2], built_at)
            self.assertIn('class="foot-sections"', home)
            self.assertIn('class="totop"', home)
            search = build.render_search_page(lang, built_at,
                                              cats=["arts", "gaza", "westbank"])
            self.assertIn('<nav class="sections"', search)
            # chips follow the paper's order — Gaza first, never the alphabet
            self.assertLess(search.index("section-gaza.html"),
                            search.index("section-arts.html"))

    def test_us_press_tab_rides_beside_israeli_press_in_priority_row(self):
        # Owner order 2026-08-11: the two press desks are one-tap neighbours
        # on the bar — US Press immediately after Israeli Press, both editions.
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        base = item()
        base.update({"image": "/media/x.svg"})
        titles = {
            "israelipress": "Haaretz reports army knew West Bank outpost plans",
            "uspress": "Washington Post details Gaza aid corridor talks",
        }
        for lang in ("en", "ar"):
            rows = [dict(base, lang=lang, cat=cat, pid=f"pressnav{n}",
                         title=title, link=f"https://example.com/pressnav-{n}")
                    for n, (cat, title) in enumerate(titles.items())]
            page = build.render_page(lang, rows, built_at)
            row = page.split('<nav class="sections"', 1)[1].split("nav-group", 1)[0]
            self.assertRegex(
                row, r'href="#israelipress">[^<]+</a><a href="#uspress"')

    def test_methodology_tooltips_become_bottom_sheets_on_phones(self):
        # Owner report 2026-08-11: edge-cell "?" tooltips rendered partly
        # off-screen on phones — they pin as a fixed bottom sheet instead.
        import gaza_panel
        self.assertIn(
            "@media(max-width:560px){.gi-help .gi-tip{position:fixed",
            gaza_panel.PANEL_CSS)

    def test_text_only_mode_toggle_rides_every_chrome_bar(self):
        """Owner-forwarded review 2026-08-04: a low-data text-only mode for
        readers on unstable connections. The preference applies from <head>
        so hidden lazy images are never fetched."""
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        it = item()
        it.update({"image": "/media/x.svg", "pid": "chrome0003"})
        for lang in ("en", "ar"):
            page = build.render_page(lang, [dict(it, lang=lang)], built_at)
            self.assertIn('id="litetoggle"', page)
            self.assertIn('top-lite', page)          # head script reads the pref
            story = build.render_story(dict(it, lang=lang, brief="A body."),
                                       lang, [], [dict(it, lang=lang)], built_at)
            self.assertIn('id="litetoggle"', story)
        self.assertIn("[data-lite] .hero-imgwrap>a", build.CSS)
        self.assertIn("[data-lite] .embed", build.CSS)
        self.assertIn("[data-lite] .litetoggle", build.CSS)
        # the hero headline must SURVIVE text-only mode — only its image goes
        self.assertIn("[data-lite] .hero-overlay{position:static", build.CSS)


class OutbreakWatchTests(unittest.TestCase):
    """Owner directive 2026-08-04: the newsroom monitors diseases spreading
    in Gaza and the West Bank and posts them to SANAD automatically."""

    def _items(self):
        from datetime import datetime, timezone
        d = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)
        return [
            {"pid": "aaa111", "lang": "en", "date": d,
             "title": "Cholera cases surge in Gaza shelters",
             "dek": "Health ministry reports an outbreak in the north."},
            {"pid": "bbb222", "lang": "ar", "date": d,
             "title": "نفاد محلول رخيص يعطّل نصف أجهزة الغسيل الكلوي",
             "dek": "أزمة مستلزمات في مستشفيات غزة."},
            {"pid": "ccc333", "lang": "en", "date": d,
             "title": "A hepatitis survivor rebuilds her bakery",
             "dek": "A feature about recovery."},  # no spread-context: no alert
            {"pid": "ddd444", "lang": "en", "date": d,
             "title": "Measles cases rise in West Bank refugee camps",
             "dek": "Vaccination coverage fell during the war."},
        ]

    def test_detects_outbreaks_and_supply_failures_not_features(self):
        import outbreak_watch
        evs = outbreak_watch.watch_events(self._items())
        keys = {e["ref"].split("-")[-1] for e in evs}
        self.assertIn("CHOLER", keys)
        self.assertIn("DIALYS", keys)
        self.assertIn("MEASLE", keys)
        self.assertNotIn("HEPATI", keys)          # feature story filtered out
        chol = next(e for e in evs if "CHOLER" in e["ref"])
        self.assertEqual(chol["ty"], "case")
        self.assertEqual(chol["c"]["urgency"], "red")
        self.assertEqual(chol["c"]["zone"], "Gaza City")
        self.assertIn("timesofpalestine.com/en/story/aaa111.html",
                      chol["c"]["findings"])
        self.assertIn("TOP Health Watch", chol["by"]["n"])
        measles = next(e for e in evs if "MEASLE" in e["ref"])
        self.assertEqual(measles["c"]["zone"], "West Bank")

    def test_ids_are_deterministic_and_weekly_deduped(self):
        import outbreak_watch
        a = outbreak_watch.watch_events(self._items())
        b = outbreak_watch.watch_events(self._items() + self._items())
        self.assertEqual([e["id"] for e in a], [e["id"] for e in b])


class AdScreenTests(unittest.TestCase):
    """Advertising is not news: promo items drop before categorization
    (owner takedown 2026-08-05 — a TCN paid life-insurance segment with an
    Israel clickbait headline published as a brief)."""

    def test_paid_partnership_item_is_flagged(self):
        self.assertTrue(build.AD_RX.search(
            "Israel Supported This. Here's Why "
            "paid partnership advertisement for Ethos life insurance — "
            "up to $3 million in coverage in ten minutes"))

    def test_promo_code_and_arabic_markers_flagged(self):
        self.assertTrue(build.AD_RX.search("Subscribe with promo code TUCKER for 20% off"))
        self.assertTrue(build.AD_RX.search("بالشراكة مع الراعي — شراكة مدفوعة مع كود خصم خاص"))

    def test_reporting_about_ads_still_publishes(self):
        for text in (
            "AIPAC's ad spending more than doubled to $67.2M in Democratic primaries",
            "A bill sponsored by Senator Sanders would condition military aid to Israel",
            "Israeli ministry buys sponsored ads targeting European voters, report finds",
            "Gaza health coverage collapses as hospitals lose insurance reimbursements",
        ):
            self.assertFalse(build.AD_RX.search(text), text)


class CrossDeskDedupeTests(unittest.TestCase):
    """One event, one article — across desks. A wire brief and an original
    describe the same event under unlike headlines; the names each headline
    omits appear in the other's dek, and the original survives (owner call
    2026-08-05, after a wire brief on the Dabbour arrest published beside
    the original covering it)."""

    @staticmethod
    def story(title, dek, hours_after=0, n=0, original=False, score=10):
        record = item()
        record.update({
            "title": title, "dek": dek,
            "link": f"https://example.com/cross-{n}",
            "pid": f"cross{n:04d}",
            "date": datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
            + timedelta(hours=hours_after),
            "score": score, "corroborating_sources": [],
        })
        if original:
            record.update({"original": True, "source_id": "top-original"})
        return record

    def test_wire_brief_folds_into_the_original_covering_the_event(self):
        original = self.story(
            "Lebanon arrests envoy who accused Abbas's son of turning security on him",
            "Lebanese authorities arrested Ashraf Dabbour, the Palestinian "
            "Authority's former ambassador in Beirut, at the city's airport "
            "on Monday ahead of extradition on embezzlement charges.",
            original=True, n=1, score=90)
        brief = self.story(
            "Lebanon detains former Palestinian ambassador Ashraf Dabbour for extradition",
            "The former envoy was held at Beirut airport at Ramallah's "
            "request over embezzlement charges back home.",
            hours_after=3, n=2)
        survivors = build.dedupe_events([original, brief])
        self.assertEqual(len(survivors), 1)
        self.assertTrue(survivors[0]["original"])

    def test_arabic_wire_brief_folds_into_the_arabic_original(self):
        original = self.story(
            "لبنان يوقف السفير الذي اتهم نجل عباس بتسليط الأمن عليه",
            "أوقفت السلطات اللبنانية أشرف دبّور، سفير السلطة الفلسطينية "
            "السابق في بيروت، في مطار المدينة تمهيداً لتسليمه على ذمة تهم اختلاس.",
            original=True, n=3, score=90)
        brief = self.story(
            "لبنان يوقف السفير الفلسطيني السابق أشرف دبور تمهيداً لتسليمه بتهم اختلاس",
            "أوقف القضاء اللبناني السفير السابق في مطار بيروت بطلب من رام الله.",
            hours_after=5, n=4)
        survivors = build.dedupe_events([original, brief])
        self.assertEqual(len(survivors), 1)
        self.assertTrue(survivors[0]["original"])

    def test_disjoint_headlines_on_one_meeting_fold_by_coverage(self):
        # The Amman case (owner call 2026-08-05): two desks composed fully
        # different headlines for one gathering, and title-level nets missed
        # them. The title+dek coverage net must fold them to one story.
        first = self.story(
            "Arab officials demand action on Jerusalem tensions",
            "Foreign ministers from Jordan, Egypt and the Arab League met in "
            "Amman on Tuesday to demand international action over escalating "
            "tensions at Al-Aqsa Mosque in occupied Jerusalem.",
            n=7, score=40)
        second = self.story(
            "Arab ministers meet in Amman to discuss occupied Jerusalem",
            "Arab foreign ministers gathered in the Jordanian capital Amman "
            "to discuss rising tensions in occupied Jerusalem and Israeli "
            "restrictions at Al-Aqsa Mosque.",
            hours_after=1, n=8, score=30)
        survivors = build.dedupe_events([first, second])
        self.assertEqual(len(survivors), 1)

    def test_arabic_disjoint_headlines_on_one_meeting_fold_by_coverage(self):
        first = self.story(
            "وزراء عرب يطالبون بتحرك دولي إزاء التوتر في القدس",
            "اجتمع وزراء خارجية الأردن ومصر والجامعة العربية في عمّان "
            "للمطالبة بتحرك دولي إزاء التصعيد في المسجد الأقصى بالقدس المحتلة.",
            n=9, score=40)
        second = self.story(
            "اجتماع عربي في عمّان يبحث الأوضاع في القدس المحتلة",
            "عقد وزراء الخارجية العرب اجتماعاً في العاصمة الأردنية عمّان "
            "لبحث التوتر المتصاعد في القدس المحتلة والاعتداءات على المسجد الأقصى.",
            hours_after=1, n=10, score=30)
        survivors = build.dedupe_events([first, second])
        self.assertEqual(len(survivors), 1)

    def test_two_different_jerusalem_stories_both_run(self):
        # Same city, same day, different events: a diplomatic meeting and a
        # court decision must not fold into each other.
        meeting = self.story(
            "Arab ministers meet in Amman to discuss occupied Jerusalem",
            "Arab foreign ministers gathered in the Jordanian capital Amman "
            "to discuss rising tensions in occupied Jerusalem and Israeli "
            "restrictions at Al-Aqsa Mosque.",
            n=11, score=40)
        court = self.story(
            "Israeli court approves settler takeover of Silwan homes",
            "An Israeli court in Jerusalem ruled that twelve Palestinian "
            "families in Silwan can be evicted from their homes in favor of "
            "a settler organization.",
            hours_after=2, n=12, score=30)
        self.assertEqual(len(build.dedupe_events([meeting, court])), 2)

    def test_state_and_leader_headlines_on_one_decision_fold(self):
        # Owner report 2026-08-09: "Netanyahu rejects Trump peace plan…" and
        # "Israel rejects Trump's 15-point Gaza plan" ran as adjacent cards.
        # The leader is the state's voice, and the shorter headline sits
        # inside the longer one — one decision, one card.
        first = self.story(
            "Netanyahu rejects Trump peace plan, vows no Gaza withdrawal "
            "or Palestinian state", "", n=13, score=40)
        second = self.story(
            "Israel rejects Trump's 15-point Gaza plan", "",
            hours_after=1, n=14, score=30)
        survivors = build.dedupe_events([first, second])
        self.assertEqual(len(survivors), 1)

    def test_arabic_state_and_leader_headlines_on_one_decision_fold(self):
        first = self.story(
            "نتنياهو يرفض خطة ترامب ويتعهد بمواصلة حرب غزة", "",
            n=17, score=40)
        second = self.story(
            "إسرائيل ترفض خطة ترامب لوقف حرب غزة", "",
            hours_after=1, n=18, score=30)
        survivors = build.dedupe_events([first, second])
        self.assertEqual(len(survivors), 1)

    def test_rewritten_headlines_on_one_announcement_fold_by_brief(self):
        # Owner report 2026-08-09: two rewrites of one JDECO announcement ran
        # side by side in The Latest. Their house headlines share only
        # "Jerusalem", and the translated item's dek was blanked — the brief
        # bodies are what tell the same story, so the coverage net reads them.
        first = self.story(
            "Jerusalem Electric prepares grid for winter storms", "",
            n=15, score=40)
        first["brief"] = (
            "The Jerusalem District Electricity Company said its crews are "
            "preparing the grid for winter storms, with scheduled power cuts "
            "across parts of Ramallah and Al-Bireh through the afternoon "
            "while maintenance teams reinforce lines.")
        second = self.story(
            "Jerusalem electricity company schedules power cuts through "
            "afternoon", "", hours_after=1, n=16, score=30)
        second["brief"] = (
            "The Jerusalem District Electricity Company announced scheduled "
            "power cuts through the afternoon across parts of Ramallah and "
            "Al-Bireh as maintenance crews reinforce the grid ahead of "
            "winter storms.")
        survivors = build.dedupe_events([first, second])
        self.assertEqual(len(survivors), 1)

    def test_unrelated_netanyahu_and_israel_stories_both_run(self):
        # The metonymy fold must not glue every Netanyahu item to every
        # Israel item: different subjects share only the actor token.
        trial = self.story(
            "Netanyahu appears in court for corruption trial hearing", "",
            n=19, score=40)
        settlements = self.story(
            "Israel approves thousands of new settlement units in the "
            "West Bank", "", hours_after=2, n=20, score=30)
        self.assertEqual(len(build.dedupe_events([trial, settlements])), 2)

    def test_different_stories_about_the_same_person_both_run(self):
        congress = self.story(
            "Fatah's eighth congress elevates Barghouti, Faraj and the president's son",
            "Marwan Barghouti topped the vote from prison and Yasser Abbas "
            "entered the Central Committee eighth of eighteen.",
            original=True, n=5, score=90)
        arrest = self.story(
            "Lebanon detains former Palestinian ambassador Ashraf Dabbour for extradition",
            "The former envoy was held at Beirut airport at Ramallah's "
            "request over embezzlement charges back home.",
            hours_after=6, n=6)
        self.assertEqual(len(build.dedupe_events([congress, arrest])), 2)


class FrontPageDisciplineTests(unittest.TestCase):
    """Owner audit 2026-08-07: features never lead, the ticker is hard news
    only, and no single desk floods the Latest rail."""

    def _item(self, **kw):
        it = item()
        it.update({"image": "/media/x.jpg", "pid": kw.get("pid", "p%08d" % (abs(hash(kw.get("title", "x"))) % 10**8))})
        it.update(kw)
        return it

    def test_arts_feature_never_takes_the_hero(self):
        built_at = datetime(2026, 8, 7, 15, tzinfo=timezone.utc)
        feature = self._item(
            title="A Palestinian musician rebuilds Gaza's oldest song archive",
            cat="arts", original=True, score=999,
            date=built_at - timedelta(minutes=5), pid="artfeat001")
        wire = self._item(
            title="Israeli forces raid Nablus in Palestine overnight on Friday",
            cat="westbank", score=20,
            date=built_at - timedelta(minutes=40), pid="wirenb0001")
        homepage = build.render_page("en", [feature, wire], built_at)
        overlay = homepage.split("hero-overlay", 1)[1][:400]
        self.assertIn("Nablus", overlay)
        self.assertNotIn("song archive", overlay)

    def test_routine_utility_notice_never_takes_the_hero(self):
        # Owner report 2026-08-09: a JDECO power-cut schedule led the paper
        # purely because it was the newest wire item.
        built_at = datetime(2026, 8, 9, 15, tzinfo=timezone.utc)
        notice = self._item(
            title="Jerusalem electricity company schedules power cuts through afternoon",
            cat="westbank", score=40,
            date=built_at - timedelta(minutes=5), pid="jdeco00001")
        wire = self._item(
            title="Israeli forces raid Nablus in Palestine overnight on Friday",
            cat="westbank", score=20,
            date=built_at - timedelta(hours=3), pid="wirenb0002")
        homepage = build.render_page("en", [notice, wire], built_at)
        overlay = homepage.split("hero-overlay", 1)[1][:400]
        self.assertIn("Nablus", overlay)
        self.assertNotIn("power cuts", overlay)
        # The notice stays off the top block entirely — the sub grid too.
        top_block = homepage.split('<aside class="latest">', 1)[0]
        self.assertNotIn("power cuts", top_block.split("hero-overlay", 1)[1])

    def test_hero_rotates_among_comparable_top_stories_across_builds(self):
        # Owner report 2026-08-09: the same lead sat on top for hours while
        # the site rebuilt every 10 minutes. Among fresh stories of comparable
        # weight the lead advances with the build clock — and stays
        # deterministic for a given build moment.
        base = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)
        a = self._item(
            title="Israeli airstrike kills twelve Palestinians in Gaza City homes",
            cat="gaza", score=80,
            date=base - timedelta(hours=2), pid="rotgaza001")
        b = self._item(
            title="Israeli forces raid Nablus in Palestine overnight on Friday",
            cat="westbank", score=70,
            date=base - timedelta(hours=3), pid="rotwb00001")
        leads = set()
        for n in range(3):
            page = build.render_page("en", [a, b], base + timedelta(minutes=10 * n))
            overlay = page.split("hero-overlay", 1)[1][:400]
            leads.add("airstrike" if "airstrike" in overlay else "Nablus")
        self.assertEqual(leads, {"airstrike", "Nablus"})
        first = build.render_page("en", [a, b], base)
        again = build.render_page("en", [a, b], base)
        self.assertEqual(first.split("hero-overlay", 1)[1][:400],
                         again.split("hero-overlay", 1)[1][:400])

    def test_minor_story_never_rotates_into_the_lead(self):
        # Rotation is among comparable stories only: an item under half the
        # leader's score must not take the top slot on any build.
        base = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)
        major = self._item(
            title="Israeli airstrike kills twelve Palestinians in Gaza City homes",
            cat="gaza", score=80,
            date=base - timedelta(hours=2), pid="rotmaj0001")
        minor = self._item(
            title="Ramallah municipality opens Palestine flower show for the season",
            cat="westbank", score=15,
            date=base - timedelta(minutes=10), pid="rotmin0001")
        for n in range(4):
            page = build.render_page("en", [major, minor], base + timedelta(minutes=10 * n))
            overlay = page.split("hero-overlay", 1)[1][:400]
            self.assertIn("airstrike", overlay)
            self.assertNotIn("flower show", overlay)

    def test_hero_prefers_strongest_story_in_freshest_window(self):
        # Within the freshest window the hero ranks by editorial score —
        # importance leads, not simply the last item off the wire.
        built_at = datetime(2026, 8, 9, 15, tzinfo=timezone.utc)
        minor = self._item(
            title="Ramallah municipality opens Palestine flower show for the season",
            cat="westbank", score=15,
            date=built_at - timedelta(minutes=10), pid="minorx0001")
        major = self._item(
            title="Israeli airstrike kills twelve Palestinians in Gaza City homes",
            cat="gaza", score=80,
            date=built_at - timedelta(hours=4), pid="majorx0001")
        homepage = build.render_page("en", [minor, major], built_at)
        overlay = homepage.split("hero-overlay", 1)[1][:400]
        self.assertIn("airstrike", overlay)
        self.assertNotIn("flower show", overlay)

    def test_ticker_is_hard_news_only(self):
        built_at = datetime(2026, 8, 7, 15, tzinfo=timezone.utc)
        feature = self._item(
            title="A Palestinian musician rebuilds Gaza's oldest song archive",
            cat="arts", date=built_at - timedelta(minutes=5), pid="tickart001")
        wire = self._item(
            title="Israeli forces raid Nablus in Palestine overnight on Friday",
            cat="westbank", date=built_at - timedelta(minutes=40), pid="ticknb0001")
        homepage = build.render_page("en", [feature, wire], built_at)
        ticker = homepage.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn("Nablus", ticker)
        self.assertNotIn("song archive", ticker)

    def test_latest_rail_caps_a_single_section(self):
        built_at = datetime(2026, 8, 7, 15, tzinfo=timezone.utc)
        flood = [self._item(
            title=f"Israeli daily says the Palestine file shifts again number {n}",
            cat="israelipress", original=True,
            link=f"original:ip{n}.en",
            date=built_at - timedelta(minutes=3 + n), pid=f"ipflood{n:03d}")
            for n in range(8)]
        others = [self._item(
            title=f"Gaza hospitals in Palestine report new shortage figures {n}",
            cat="health",
            date=built_at - timedelta(minutes=90 + n), pid=f"hlthx{n:04d}")
            for n in range(4)]
        homepage = build.render_page("en", flood + others, built_at)
        rail = homepage.split('<aside class="latest">', 1)[1].split("</aside>", 1)[0]
        self.assertLessEqual(rail.count("Israeli daily says"), 4)
        self.assertIn("Gaza hospitals", rail)


class AIDedupeJudgeTests(unittest.TestCase):
    """Owner order 2026-08-09: paraphrase-level duplicates (one event, almost
    no shared words) are settled by the newsroom model, not another lexical
    net. The judge is conservative, cached, and fail-open."""

    def _jdeco_pair(self):
        base = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
        a = item()
        a.update({
            "title": "Jerusalem electricity company cuts power across West Bank areas",
            "dek": "The company announced planned outages from 9 a.m. to 2 p.m. "
                   "across Bethlehem governorate, the Ma'an wire reported.",
            "cat": "westbank", "lang": "en", "score": 30, "pid": "jdecocuts1",
            "date": base, "link": "https://example.com/a"})
        b = item()
        b.update({
            "title": "Jerusalem Electricity readies grid for winter with maintenance push",
            "dek": "The utility is washing and reinforcing its electrical networks "
                   "ahead of winter storms, the Ma'an wire reported.",
            "cat": "westbank", "lang": "en", "score": 20, "pid": "jdecomaint",
            "date": base - timedelta(hours=2), "link": "https://example.com/b"})
        return a, b

    def _run(self, en, ar, client, cache_dir):
        with mock.patch.object(build, "BRIEFS_CACHE", Path(cache_dir) / "briefs-cache.json"):
            return build.adjudicate_duplicates(en, ar, client)

    def test_judge_folds_a_paraphrase_duplicate_and_caches_the_verdict(self):
        a, b = self._jdeco_pair()
        client = _FakeBriefsClient(["DUPLICATE"])
        with tempfile.TemporaryDirectory() as td:
            en, ar, dropped = self._run([a, b], [], client, td)
            cache = json.loads((Path(td) / "briefs-cache.json").read_text())
        self.assertEqual(dropped, 1)
        self.assertEqual([i["pid"] for i in en], ["jdecocuts1"])  # higher score survives
        self.assertEqual(len(client.calls), 1)
        key = build._judge_pair_key("en", "jdecocuts1", "jdecomaint")
        self.assertTrue(cache[key]["same"])

    def test_separate_verdict_keeps_both_stories(self):
        a, b = self._jdeco_pair()
        client = _FakeBriefsClient(["SEPARATE"])
        with tempfile.TemporaryDirectory() as td:
            en, ar, dropped = self._run([a, b], [], client, td)
        self.assertEqual(dropped, 0)
        self.assertEqual(len(en), 2)

    def test_no_client_is_fail_open(self):
        a, b = self._jdeco_pair()
        with tempfile.TemporaryDirectory() as td:
            en, ar, dropped = self._run([a, b], [], None, td)
        self.assertEqual(dropped, 0)
        self.assertEqual(len(en), 2)

    def test_cached_verdict_never_asks_the_model_again(self):
        a, b = self._jdeco_pair()
        client = _FakeBriefsClient([])  # any call would raise IndexError
        key = build._judge_pair_key("en", "jdecocuts1", "jdecomaint")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "briefs-cache.json").write_text(
                json.dumps({key: {"same": True, "ts": 0}}))
            en, ar, dropped = self._run([a, b], [], client, td)
        self.assertEqual(dropped, 1)
        self.assertEqual(len(client.calls), 0)

    def test_standard_is_the_readers_and_versioned(self):
        # Owner report 2026-09-02: five relays of Dr Abu Safiya's account of
        # being beaten ran the same afternoon because v1 called every relay
        # "a separate announcement" and defaulted to SEPARATE when unsure.
        self.assertIn("reading the same news twice", build.DEDUPE_JUDGE_SYSTEM)
        self.assertIn("whichever outlet, agency, rights group, lawyer",
                      build.DEDUPE_JUDGE_SYSTEM)
        self.assertNotIn("When uncertain, answer SEPARATE", build.DEDUPE_JUDGE_SYSTEM)
        key = build._judge_pair_key("ar", "b", "a")
        self.assertTrue(key.startswith(f"dupe:{build.DEDUPE_JUDGE_VERSION}:ar:a:b"))
        self.assertNotEqual(build.DEDUPE_JUDGE_VERSION, "v1",
                            "a changed standard must re-ask the old verdicts")

    def test_judged_loser_with_a_permalink_is_flagged_in_the_archive(self):
        import story_archive
        a, b = self._jdeco_pair()
        client = _FakeBriefsClient(["DUPLICATE"])
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"STORY_ARCHIVE_DIR": td}):
            story_archive.save(a)  # both published before the verdict —
            story_archive.save(b)  # the Abu Safiya case; score decides
            en, ar, dropped = self._run([a, b], [], client, td)
            loser = json.loads((Path(td) / "en" / "jdecomaint.json").read_text(
                encoding="utf-8"))
            winner = json.loads((Path(td) / "en" / "jdecocuts1.json").read_text(
                encoding="utf-8"))
            self.assertEqual(loser["dup_of"], "jdecocuts1")
            self.assertIsNone(winner.get("dup_of"))
            loaded = {r["pid"]: r for r in story_archive.load("en")}
            self.assertEqual(loaded["jdecomaint"]["dup_of"], "jdecocuts1")
            self.assertNotIn("dup_of", loaded["jdecocuts1"])
        self.assertEqual(dropped, 1)
        self.assertEqual([i["pid"] for i in en], ["jdecocuts1"])

    def test_judged_loser_without_a_permalink_gains_none(self):
        a, b = self._jdeco_pair()
        client = _FakeBriefsClient(["DUPLICATE"])
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"STORY_ARCHIVE_DIR": td}):
            self._run([a, b], [], client, td)
            self.assertFalse((Path(td) / "en").exists())

    def test_rare_shared_name_outranks_stock_words_in_the_queue(self):
        # Owner report 2026-09-02: ranking by shared-token COUNT buried the
        # Abu Safiya doubles under thousands of pairs sharing only stock words.
        stock = {"israel", "gaza", "forces", "occupation", "strike"}
        sets = [stock | {f"x{i}"} for i in range(30)]          # 30 stock stories
        sets += [stock | {"abu", "safiya", "beating"}, {"abu", "safiya", "lawyer"}]
        weight = build._pair_token_weights(sets)
        stock_pair = build.pair_suspicion(stock, weight)                 # 5 shared
        name_pair = build.pair_suspicion({"abu", "safiya"}, weight)      # 2 shared
        self.assertGreater(name_pair, stock_pair)

    def test_stock_word_pairs_in_a_live_pool_get_no_verdict(self):
        # In a real-sized pool, pairs that share only the stock words of the
        # beat never spend a verdict; the pair sharing a rare name does.
        base = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        ar = []
        for n in range(build.MIN_POOL_FOR_SUSPICION_FLOOR + 5):
            it = item()
            it.update({"title": f"قوات الاحتلال تقتحم بلدة {'ب' * (n + 2)} شمال الضفة",
                       "dek": "اقتحمت قوات الاحتلال الإسرائيلي البلدة فجراً بحسب مصادر محلية",
                       "cat": "westbank", "lang": "ar", "score": 30 - n * 0.1,
                       "pid": f"arstock{n:03d}", "date": base})
            ar.append(it)
        a, b = item(), item()
        a.update({"title": "أبو صفية يكشف اعتداءات مستمرة عليه في السجن",
                  "dek": "كشف الطبيب حسام أبو صفية عن تعرضه لاعتداءات داخل السجن بحسب محاميه",
                  "cat": "prisoners", "lang": "ar", "score": 40, "pid": "arabusafa",
                  "date": base})
        b.update({"title": "الأورومتوسطي يوثّق تعرض أبو صفية للضرب في سجون الاحتلال",
                  "dek": "قال المرصد الأورومتوسطي إن الطبيب حسام أبو صفية يتعرض للضرب في السجن",
                  "cat": "prisoners", "lang": "ar", "score": 30, "pid": "arabusafb",
                  "date": base})
        client = _FakeBriefsClient(["DUPLICATE"])  # a second call would raise
        with tempfile.TemporaryDirectory() as td:
            en_out, ar_out, dropped = self._run([], ar + [a, b], client, td)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(dropped, 1)
        self.assertNotIn("arabusafb", [i["pid"] for i in ar_out])
        self.assertGreater(build.suspicion_floor(450), 15)
        self.assertEqual(build.suspicion_floor(2), 0.0)

    def test_each_language_has_its_own_verdict_budget(self):
        # A shared budget was spent on English first; Arabic never got a call.
        base = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        en = []
        for n in range(12):  # 66 pairs exhaust the 40-verdict budget; pool < floor size
            it = item()  # distinct by a word, not a digit (digits trip the count veto)
            it.update({"title": f"Israeli forces raid a village near Ramallah {'x' * (n + 2)}",
                       "dek": "Soldiers entered the village at dawn, residents said.",
                       "cat": "westbank", "lang": "en", "score": 30 - n * 0.1,
                       "pid": f"enpair{n:04d}", "date": base})
            en.append(it)
        a, b = item(), item()
        a.update({"title": "أبو صفية يكشف اعتداءات مستمرة عليه في السجن",
                  "dek": "كشف الطبيب حسام أبو صفية عن تعرضه لاعتداءات داخل السجن",
                  "cat": "prisoners", "lang": "ar", "score": 40, "pid": "arabusafa",
                  "date": base})
        b.update({"title": "الأورومتوسطي يوثّق تعرض أبو صفية للضرب في سجون الاحتلال",
                  "dek": "قال المرصد الأورومتوسطي إن الطبيب حسام أبو صفية يتعرض للضرب",
                  "cat": "prisoners", "lang": "ar", "score": 30, "pid": "arabusafb",
                  "date": base})
        answers = ["SEPARATE"] * build.MAX_DEDUPE_VERDICTS_PER_RUN + ["DUPLICATE"]
        client = _FakeBriefsClient(answers)
        with tempfile.TemporaryDirectory() as td:
            en_out, ar_out, dropped = self._run(en, [a, b], client, td)
        self.assertEqual(dropped, 1, "the Arabic pair still got its verdict")
        self.assertEqual([i["pid"] for i in ar_out], ["arabusafa"])

    def test_contradicting_places_are_never_even_asked_about(self):
        base = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
        a, b = item(), item()
        a.update({"title": "Israeli forces raid Jenin refugee camp at dawn injuring residents",
                  "dek": "", "cat": "westbank", "lang": "en", "score": 30,
                  "pid": "jeninraid1", "date": base})
        b.update({"title": "Israeli forces raid Nablus old city at dawn injuring residents",
                  "dek": "", "cat": "westbank", "lang": "en", "score": 20,
                  "pid": "nablusraid", "date": base})
        client = _FakeBriefsClient([])  # any call would raise IndexError
        with tempfile.TemporaryDirectory() as td:
            en, ar, dropped = self._run([a, b], [], client, td)
        self.assertEqual(dropped, 0)
        self.assertEqual(len(en), 2)
        self.assertEqual(len(client.calls), 0)


class ReaderGrowthHooksTests(unittest.TestCase):
    """Newsletter band + analytics tag (owner order 2026-08-10): both are OFF
    without their repo variables, and go live everywhere when set."""

    def setUp(self):
        self._nl, self._gc = build.NEWSLETTER_URL, build.GOATCOUNTER_CODE

    def tearDown(self):
        build.NEWSLETTER_URL, build.GOATCOUNTER_CODE = self._nl, self._gc

    def test_everything_off_without_the_variables(self):
        build.NEWSLETTER_URL, build.GOATCOUNTER_CODE = "", ""
        self.assertEqual(build.newsletter_band("en"), "")
        self.assertEqual(build.analytics_tag(), "")
        built_at = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
        homepage = build.render_page("en", [item()], built_at)
        self.assertNotIn("newsband", homepage)
        self.assertNotIn("goatcounter", homepage)

    def test_buttondown_url_renders_the_real_inline_form(self):
        build.NEWSLETTER_URL = "https://buttondown.com/timesofpalestine"
        for lang, cta in (("en", "Subscribe"), ("ar", "اشترك")):
            band = build.newsletter_band(lang)
            self.assertIn(
                'action="https://buttondown.com/api/emails/embed-subscribe/'
                'timesofpalestine"', band)
            self.assertIn('type="email"', band)
            self.assertIn(cta, band)
        self.assertIn("newsband", build.render_story(
            item(), "en", [], [], datetime(2026, 8, 10, tzinfo=timezone.utc)))

    def test_other_provider_url_falls_back_to_a_link(self):
        build.NEWSLETTER_URL = "https://example-letters.com/subscribe"
        band = build.newsletter_band("en")
        self.assertNotIn("<form", band)
        self.assertIn('class="nb-link"', band)
        self.assertIn("https://example-letters.com/subscribe", band)

    def test_analytics_tag_rides_every_template(self):
        build.GOATCOUNTER_CODE = "timesofpalestine"
        tag = 'data-goatcounter="https://timesofpalestine.goatcounter.com/count"'
        built_at = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
        self.assertIn(tag, build.render_page("en", [item()], built_at))
        self.assertIn(tag, build.render_story(item(), "en", [], [], built_at))
        self.assertIn(tag, build.render_section_page("en", "arts", [item()], built_at))
        self.assertIn(tag, build.render_search_page("en", built_at))
        self.assertIn(tag, seo_extras.render_about("en", built_at))


class RefusalScreenTest(unittest.TestCase):
    """The refusal screen catches model refusals, not ordinary Arabic prose.

    Regression: «يتعذر» ("cannot be done") is an everyday Arabic verb. Matched
    bare, it silently withheld the Arabic edition of a published report while
    the English one ran (daily editor 2026-08-13). Both directions are asserted
    so nobody restores the loose form.
    """

    def test_arabic_refusals_are_still_caught(self):
        for refusal in [
            "يتعذر عليّ إنتاج خبر من هذه المادة",
            "يتعذّر تقديم ملخص كامل",
            "يتعذر إعداد المادة المطلوبة",
            "لا أستطيع كتابة الخبر",
            "I cannot produce a brief from this material",
        ]:
            self.assertTrue(
                build.REFUSAL_RX.search(refusal), f"missed refusal: {refusal}")

    def test_ordinary_arabic_prose_publishes(self):
        for prose in [
            "أما حيث يتعذر إجراء انتخابات مباشرة، فتُشكَّل هيئة ناخبة",
            "يتعذر على المرضى الوصول إلى المستشفى بسبب الحواجز",
            "يتعذّر إصلاح شبكة الكهرباء قبل رفع الحصار",
        ]:
            self.assertIsNone(
                build.REFUSAL_RX.search(prose), f"false refusal hit: {prose}")


class FeedEntityTests(unittest.TestCase):
    """Wire feeds publish the HTML entity set inside otherwise valid XML.

    XML defines only five named entities. Before this, `parse_xml`'s
    bare-ampersand repair rewrote `&rsquo;` to `&amp;rsquo;`, so the feed
    parsed but the literal string "&rsquo;" reached headlines and card decks
    (daily editor 2026-08-16, found while checking why the `amnesty-ar` feed
    fails in CI). Entities now resolve to real characters; the ampersand
    repair and the XML-defined names must keep working beside it.
    """

    def _title(self, raw):
        return build.parse_xml(raw).find(".//title").text

    def _feed(self, title):
        return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0">'
                "<channel><item><title>" + title
                + "</title></item></channel></rss>").encode()

    def test_html_entities_become_characters(self):
        # &nbsp; is U+00A0, &rsquo; is U+2019 — real characters, not literals.
        self.assertEqual(self._title(self._feed("A&nbsp;B&rsquo;s")),
                         "A\u00a0B\u2019s")

    def test_xml_named_entities_survive(self):
        self.assertEqual(self._title(self._feed("Fish &amp; Chips &lt;x&gt;")),
                         "Fish & Chips <x>")

    def test_bare_ampersand_still_repaired(self):
        self.assertEqual(self._title(self._feed("Fish & Chips")),
                         "Fish & Chips")

    def test_unknown_entity_is_dropped_not_guessed(self):
        self.assertEqual(self._title(self._feed("X&bogus;Y")), "XY")

    def test_arabic_feed_text_is_preserved(self):
        self.assertEqual(
            self._title(self._feed("\u0642\u0635\u0631\u0629&nbsp;\u062a\u062d\u062a \u0627\u0644\u062d\u0635\u0627\u0631")),
            "\u0642\u0635\u0631\u0629\u00a0\u062a\u062d\u062a \u0627\u0644\u062d\u0635\u0627\u0631")
