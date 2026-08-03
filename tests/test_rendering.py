import os
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_navigation_uses_one_scrollable_row_at_every_width(self):
        # The section nav is a single horizontally scrollable row of text
        # tabs at all viewport widths — never wrapped, never clipped.
        self.assertIn(
            "nav.sections .wrap{display:flex;flex-wrap:nowrap;"
            "gap:.15rem;padding-block:.15rem;overflow-x:auto",
            build.CSS,
        )

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
        self.assertIn('href="../#health"', html)
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
        self.assertEqual(older["image"], "/media/times-of-palestine-cover-gaza.svg")
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
        it = item()
        it.update({"pid": "eb18db4ce2",
                   "image": "https://cdn.example.com/wire.jpg",
                   "media": {"credit": "Photo: Some Wire Agency",
                             "rightsBasis": "wire", "source": "wire",
                             "licenseUrl": None}})
        build.apply_image_overrides([it])   # real editorial/image-overrides.json
        self.assertEqual(it["image"], "/media/ali-al-thawadi-un-2026.jpg")
        self.assertEqual(it["media"]["credit"], "Photo: Times of Palestine")
        self.assertNotIn("Wire Agency", str(it["media"]))
        self.assertTrue((Path(build.ROOT) / "originals" / "media"
                         / "ali-al-thawadi-un-2026.jpg").is_file())


class StandingFlagTests(unittest.TestCase):
    """Only an explicit standing flag keeps a story out of the hero tier —
    a long archive shelf-life alone must not (owner report 2026-08-03)."""

    def test_long_shelf_life_news_can_lead_but_standing_pages_cannot(self):
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        fresh_news = item()
        fresh_news.update({
            "title": "Israeli forces raid a Gaza district as the day begins",
            "link": "https://example.com/fresh-long", "pid": "freshlong1",
            "date": built_at - timedelta(minutes=30),
            "image": "/media/x.svg", "score": 50,
            "max_age_hours": 999999})
        guide = item()
        guide.update({
            "title": "Times of Palestine maps scholarships for Palestinian students",
            "link": "https://example.com/guide", "pid": "guidepage1",
            "date": built_at - timedelta(minutes=10),
            "image": "/media/y.svg", "score": 60,
            "max_age_hours": 999999, "standing": True})
        homepage = build.render_page("en", [fresh_news, guide], built_at)
        overlay = homepage.split('hero-overlay', 1)[1][:400]
        self.assertIn("Israeli forces raid a Gaza district", overlay)
        self.assertNotIn("maps scholarships", overlay)


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

    def test_nav_carries_the_mobile_more_toggle(self):
        built_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        it = item()
        it.update({"image": "/media/x.svg", "pid": "chrome0002"})
        for lang, label in (("en", "More"), ("ar", "المزيد")):
            page = build.render_page(lang, [dict(it, lang=lang)], built_at)
            self.assertIn('class="nav-more"', page)
            self.assertIn('aria-controls="navtier2"', page)
            self.assertIn(label, page)
