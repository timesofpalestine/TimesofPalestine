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


if __name__ == "__main__":
    unittest.main()
