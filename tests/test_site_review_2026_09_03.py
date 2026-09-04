"""Site review 2026-09-03 — the fixes it shipped stay fixed.

1. Card, row and hero images: the width/height attributes are CLS hints
   only; CSS keeps height:auto so aspect-ratio:16/9 governs (a fixed 360px
   attribute rendered near-square cards and letterboxed covers).
2. Phones stack the solo section row — its side-by-side art overflowed a
   390px viewport (the only horizontal scroll on the site).
3. Pinned originals (standing pages, SPECIALS-required reports, the election
   tracker) never fall off the originals cap: at exactly 200 live originals
   the newest-first cap silently dropped the TOP 100 and the scholarship map
   and, with them, their front-page cards, nav links and ticker entries.
4. The front page always has a lead: an 18-hour quiet stretch left the hero
   slot empty. The last-resort fallback takes the freshest hard-news story
   with art, features and standing pages still excluded.
"""
import os
import re
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TOP_OFFLINE", "1")

import build  # noqa: E402


def _item(**kw):
    base = {
        "title": "Israeli forces raid a Nablus village and detain four residents",
        "dek": "A sourced summary of the raid on the village.",
        "link": "https://example.com/story",
        "source_url": "https://example.com",
        "source": "Example News",
        "source_id": "example",
        "source_type": "rss",
        "date": datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        "modified": None,
        "image": "/media/photo.jpg",
        "media": None,
        "categories": [],
        "lang": "en",
        "original": False,
        "partner": False,
        "cat": "westbank",
        "score": 10,
        "pid": "1234567890",
        "corrections": [],
        "corroborating_sources": [],
    }
    base.update(kw)
    return base


class CardGeometryTest(unittest.TestCase):
    def test_card_row_and_hero_images_keep_height_auto(self):
        for selector in (".card img{", ".rowcard img,.rowcard .ph{", ".hero-imgwrap>a>img{"):
            rule = build.CSS.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("aspect-ratio:16/9", rule, selector)
            self.assertIn("height:auto", rule, selector)

    def test_solo_row_stacks_on_phones(self):
        phone = build.CSS.split("@media(max-width:560px){", 1)[1]
        self.assertIn(".rowcard.solo{flex-direction:column", phone)
        self.assertIn(".rowcard.solo img,.rowcard.solo .ph{width:100%}", phone)


class PinnedOriginalsTest(unittest.TestCase):
    def test_standing_and_specials_originals_are_pinned(self):
        standing = _item(source_id="top-original", original=True, standing=True,
                         link="original:some-guide.en")
        self.assertTrue(build.pinned_original(standing, "en"))
        slug = next(s["requires_original"] for s in build.SPECIALS
                    if s.get("requires_original"))
        special = _item(source_id="top-original", original=True,
                        link=f"original:{slug}.en")
        self.assertTrue(build.pinned_original(special, "en"))
        self.assertFalse(build.pinned_original(special, "ar"))  # other edition's file
        tracker = _item(source_id="top-original", original=True,
                        link="original:israel-election-2026-tracker.ar", lang="ar")
        self.assertTrue(build.pinned_original(tracker, "ar"))

    def test_ordinary_items_are_not_pinned(self):
        self.assertFalse(build.pinned_original(_item(), "en"))
        plain = _item(source_id="top-original", original=True,
                      link="original:ordinary-report.en")
        self.assertFalse(build.pinned_original(plain, "en"))


class HeroFallbackTest(unittest.TestCase):
    def test_quiet_day_still_renders_a_lead(self):
        built_at = datetime(2026, 9, 3, 15, tzinfo=timezone.utc)
        old_news = _item(
            title="Israeli forces raid a Nablus village and detain four residents",
            date=built_at - timedelta(hours=40), pid="old0000001", score=30)
        feature = _item(
            title="A Ramallah painter carries her city's colours to a Berlin gallery",
            date=built_at - timedelta(hours=30), cat="arts", pid="art0000001",
            score=99, link="https://example.com/painter")
        standing = _item(
            title="Times of Palestine maps the world's scholarships for Palestinian students",
            date=built_at - timedelta(hours=20), cat="social", pid="std0000001",
            score=120, standing=True, link="https://example.com/guide")
        homepage = build.render_page("en", [old_news, feature, standing], built_at)
        self.assertIn('class="hero-imgwrap', homepage)
        overlay = homepage.split("hero-overlay", 1)[1][:500]
        self.assertIn("Nablus", overlay)
        self.assertNotIn("painter", overlay)
        self.assertNotIn("scholarships", overlay)

    def test_fresh_news_still_leads_over_the_fallback(self):
        built_at = datetime(2026, 9, 3, 15, tzinfo=timezone.utc)
        fresh = _item(title="Israeli forces raid Jenin camp before dawn on Thursday",
                      date=built_at - timedelta(hours=2), pid="new0000001", score=5)
        old = _item(title="Israeli forces raid a Nablus village and detain four residents",
                    date=built_at - timedelta(hours=40), pid="old0000001", score=80,
                    link="https://example.com/old")
        homepage = build.render_page("en", [fresh, old], built_at)
        overlay = homepage.split("hero-overlay", 1)[1][:500]
        self.assertIn("Jenin", overlay)


class ReaderCopyTest(unittest.TestCase):
    def test_field_reports_note_makes_no_human_approval_claim(self):
        src = Path(build.__file__).read_text(encoding="utf-8")
        self.assertNotIn("human editor approves", src)
        self.assertNotIn("موافقة محرر بشري", src)

    def test_one_arabic_opengraph_locale(self):
        src = Path(build.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ar_PS", src)
        self.assertGreaterEqual(len(re.findall(r"ar_AR", src)), 3)



class LeadAndListTest(unittest.TestCase):
    """Design pass 2026-09-04: flagship sections lead-and-list, press desks
    keep grids, the rest alternate; only four-story blocks qualify."""

    def test_flagships_always_lead_and_press_never(self):
        self.assertTrue(build.lead_list_section("gaza", 5, 4))
        self.assertTrue(build.lead_list_section("prisoners", 1, 4))
        self.assertFalse(build.lead_list_section("israelipress", 0, 4))
        self.assertFalse(build.lead_list_section("uspress", 2, 4))
        self.assertFalse(build.lead_list_section("gaza", 0, 3))  # needs four

    def test_other_sections_alternate(self):
        self.assertTrue(build.lead_list_section("women", 4, 4))
        self.assertFalse(build.lead_list_section("women", 5, 4))

    def test_front_renders_lead_grid_with_dek(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       dek=f"Sourced summary of raid {i}.", pid=f"wb0000000{i}",
                       link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(13)]
        homepage = build.render_page("en", items, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="grid lead"', block)
        self.assertIn('class="dek"', block)
        self.assertIn("Sourced summary of raid", block)

    def test_css_carries_lead_and_phone_rows_and_print(self):
        self.assertIn(".grid.lead{grid-template-columns:", build.CSS)
        phone = build.CSS.split("@media(max-width:560px){", 1)[1]
        self.assertIn(".grid .card:not(:first-child){display:grid", phone)
        self.assertIn("@media print{", build.CSS)


class RunningFileChipTest(unittest.TestCase):
    def test_story_in_a_live_hub_carries_the_chip(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        story = _item(title="Settlers attack Qusra again as the siege enters its fourth week",
                      pid="qusra00001", link="https://example.com/qusra")
        tf = {"slug": "qusra", "pattern": "qusra", "since": "2026-08-11",
              "en": {"name": "The Qusra File", "dek": "d"},
              "ar": {"name": "ملف قصرة", "dek": "d"}}
        old = dict(build.TOPIC_HUBS_LIVE)
        build.TOPIC_HUBS_LIVE["en"] = [(tf, [story])]
        try:
            html = build.render_story(story, "en", [], [], built_at)
        finally:
            build.TOPIC_HUBS_LIVE.clear(); build.TOPIC_HUBS_LIVE.update(old)
        self.assertIn('class="file-chip" href="../topic-qusra.html"', html)
        self.assertIn("The Qusra File", html)
        self.assertIn("DAY 25", html)

    def test_story_outside_every_file_has_no_chip(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        old = dict(build.TOPIC_HUBS_LIVE)
        build.TOPIC_HUBS_LIVE["en"] = []
        try:
            html = build.render_story(_item(), "en", [], [], built_at)
        finally:
            build.TOPIC_HUBS_LIVE.clear(); build.TOPIC_HUBS_LIVE.update(old)
        self.assertNotIn("file-chip", html)


class FrontFlowTest(unittest.TestCase):
    """Owner order 2026-09-04: sections and bands in priority order. The
    news of the ground leads, the numbers ledger follows the block it
    counts, power and money come next, then depth and comment, then
    society, culture and sport, then service — never a ledger, a memory
    line or an opinion block between the hero and the first Gaza story."""

    def test_every_section_once_and_bands_between(self):
        keys = [k for k in build.FRONT_FLOW if not k.startswith("@")]
        self.assertEqual(sorted(keys), sorted(set(build.STR["en"]["sections"])))
        self.assertEqual(len(keys), len(set(keys)))
        for lang in ("en", "ar"):
            self.assertEqual(build.SECTION_ORDER[lang], keys)
        self.assertEqual(keys[:4], ["gaza", "westbank", "pal48", "prisoners"])
        self.assertLess(keys.index("politics"), keys.index("health"))
        self.assertLess(keys.index("economy"), keys.index("sports"))
        self.assertLess(keys.index("research"), keys.index("israelipress"))
        self.assertLess(keys.index("uspress"), keys.index("opinion"))
        self.assertEqual(keys[-2:], ["news", "archive"])
        flow = build.FRONT_FLOW
        self.assertLess(flow.index("prisoners"), flow.index("@numbers"))
        self.assertLess(flow.index("@numbers"), flow.index("politics"))
        self.assertLess(flow.index("bitcoin"), flow.index("@onthisday"))

    def test_rendered_front_puts_news_before_opinion_and_memory(self):
        built_at = datetime(2026, 5, 15, 12, tzinfo=timezone.utc)  # a dated day
        items = []  # hero + eight sub-items consume nine before the blocks
        for i in range(13):
            items.append(_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                               pid=f"wb000000{i:02d}", link=f"https://example.com/wb{i}", cat="gaza",
                               date=built_at - timedelta(hours=i + 1)))
        for i in range(2):
            items.append(_item(title=f"Why the Gaza ceasefire talks stall again this week, take {i}",
                               pid=f"op0000000{i}", link=f"https://example.com/op{i}", cat="opinion",
                               date=built_at - timedelta(hours=i + 1)))
        for i in range(2):
            items.append(_item(title=f"Palestinian Authority names a new finance minister in Ramallah {i}",
                               pid=f"po0000000{i}", link=f"https://example.com/po{i}", cat="politics",
                               date=built_at - timedelta(hours=i + 20)))
        page = build.render_page("en", items, built_at)
        main = page.split('<main id="top">', 1)[1]
        gaza = main.index('id="gaza"')
        self.assertLess(main.index('class="franchise"') if 'class="franchise"' in main else 0, gaza)
        self.assertLess(gaza, main.index('id="politics"'))
        self.assertLess(main.index('id="politics"'), main.index('id="opinion"'))
        self.assertLess(main.index('id="opinion"'), main.index('class="otd"'))
        self.assertNotIn('class="otd"', main[:gaza])
        self.assertNotIn('id="opinion"', main[:gaza])


if __name__ == "__main__":
    unittest.main()
