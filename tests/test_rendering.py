import os
import json
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

    def test_tablet_navigation_uses_one_scrollable_row(self):
        self.assertIn(
            "@media(max-width:960px){nav.sections .wrap{"
            "flex-wrap:nowrap;overflow-x:auto",
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
