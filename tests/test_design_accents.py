"""Section accents, split hero, thumb tiles, running-files strip
(owner-approved design pass 2026-09-01; patterns recorded in
editorial/design-system.md §2–3)."""
import json
import re
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build


class AccentSystemTests(unittest.TestCase):
    def test_accented_cats_are_real_sections(self):
        for cat in build.SECTION_ACCENTS:
            self.assertIn(cat, build.STR["en"]["sections"], cat)
            self.assertIn(cat, build.STR["ar"]["sections"], cat)

    def test_accent_values_are_hex_pairs(self):
        for cat, pair in build.SECTION_ACCENTS.items():
            self.assertEqual(len(pair), 2, cat)
            for v in pair:
                self.assertRegex(v, r"^#[0-9a-f]{6}$", cat)

    def test_generated_css_attached_to_both_sheets(self):
        self.assertIn("--sa-gaza:#8a1f2d", build.CSS)
        self.assertIn(".sa-gaza{--sa:var(--sa-gaza)}", build.CSS)
        self.assertIn(".tile.sa-gaza{background:#8a1f2d}", build.CSS)
        self.assertIn(".sa-gaza{--sa:#e0808c}", build._DARK_RULES)
        self.assertIn("[class*=sa-]", build._DARK_RULES)

    def test_unaccented_section_falls_back(self):
        self.assertEqual(build.accent_class("sports"), "")
        self.assertIn("var(--sa,var(--green-deep))", build.CSS)

    def test_palette_documented_in_design_system(self):
        doc = (ROOT / "editorial" / "design-system.md").read_text(
            encoding="utf-8")
        for cat, (lv, dv) in build.SECTION_ACCENTS.items():
            self.assertIn(lv, doc, f"{cat} light value undocumented")
            self.assertIn(dv, doc, f"{cat} dark value undocumented")


class ThumbTileTests(unittest.TestCase):
    def test_house_svg_detection(self):
        self.assertTrue(build._is_house_svg("/media/times-of-palestine-x.svg"))
        self.assertFalse(build._is_house_svg("https://example.org/p.jpg"))
        self.assertFalse(build._is_house_svg("/media/photo.jpg"))
        self.assertFalse(build._is_house_svg(None))

    def test_tile_carries_accent_and_initial(self):
        it = {"cat": "gaza", "image": "/media/times-of-palestine-x.svg",
              "title": "T", "pid": "abc123", "link": "x"}
        html = build.thumb_tile(it, "en", "story/", "lt-thumb")
        self.assertIn("sa-gaza", html)
        self.assertIn("<span>G</span>", html)
        html_ar = build.thumb_tile(it, "ar", "story/", "sub-thumb")
        self.assertIn("<span>غ</span>", html_ar)

    def test_rail_and_sub_items_swap_svg_thumbs_for_tiles(self):
        it = {"cat": "gaza", "image": "/media/times-of-palestine-x.svg",
              "title": "T", "pid": "abc123", "link": "x",
              "date": datetime.now(timezone.utc), "original": False,
              "source": "S", "source_id": "s", "lang": "en"}
        self.assertIn('class="lt-thumb tile sa-gaza"',
                      build.latest_item(it, "en", ""))
        self.assertIn('class="sub-thumb tile sa-gaza"',
                      build.sub_item(it, "en", ""))

    def test_photo_thumbs_stay_photos(self):
        it = {"cat": "gaza", "image": "https://example.org/p_640.jpg",
              "title": "T", "pid": "abc123", "link": "x",
              "date": datetime.now(timezone.utc), "original": False,
              "source": "S", "source_id": "s", "lang": "en"}
        self.assertIn("<img", build.latest_item(it, "en", ""))
        self.assertNotIn("tile", build.latest_item(it, "en", ""))


class SplitHeroTests(unittest.TestCase):
    def test_split_css_and_dead_graphic_treatment(self):
        self.assertIn(".hero-imgwrap.split", build.CSS)
        self.assertIn(".hs-panel", build.CSS)
        # the dim-and-scrim treatment is retired — nothing may re-add it
        self.assertNotIn(".hero-imgwrap.graphic>a>img{filter", build.CSS)
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertNotIn('_hero_graphic = (" graphic"', src)
        self.assertIn('hero-imgwrap split', src)


class RunningFilesStripTests(unittest.TestCase):
    def test_day_counter_math(self):
        today = date(2026, 9, 1)
        self.assertEqual(
            build.file_day_label({"since": "2026-08-18"}, "en", today),
            "DAY 15")
        self.assertEqual(
            build.file_day_label({"since": "2026-08-11"}, "ar", today),
            "اليوم 22")
        self.assertEqual(
            build.file_day_label({"until": "2026-10-27"}, "en", today),
            "56 DAYS")

    def test_bad_or_missing_dates_fail_open(self):
        today = date(2026, 9, 1)
        self.assertEqual(build.file_day_label({}, "en", today), "")
        self.assertEqual(
            build.file_day_label({"since": "not-a-date"}, "en", today), "")
        # a future `since` or passed `until` renders no counter, not nonsense
        self.assertEqual(
            build.file_day_label({"since": "2027-01-01"}, "en", today), "")
        self.assertEqual(
            build.file_day_label({"until": "2026-08-01"}, "en", today), "")

    def test_strip_renders_only_shipped_hubs(self):
        built_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        saved = dict(build.TOPIC_HUBS_LIVE)
        try:
            build.TOPIC_HUBS_LIVE.clear()
            self.assertEqual(build.files_strip_html("en", built_at), "")
            tf = {"slug": "qusra", "since": "2026-08-11",
                  "en": {"name": "The Qusra File", "dek": ""},
                  "ar": {"name": "ملف قصرة", "dek": ""}}
            build.TOPIC_HUBS_LIVE["en"] = [(tf, [{}, {}])]
            html = build.files_strip_html("en", built_at)
            self.assertIn("RUNNING FILES", html)
            self.assertIn("topic-qusra.html", html)
            self.assertIn("DAY 22", html)
        finally:
            build.TOPIC_HUBS_LIVE.clear()
            build.TOPIC_HUBS_LIVE.update(saved)

    def test_repo_topic_files_dates_parse(self):
        d = json.loads((ROOT / "editorial" / "topic-files.json").read_text(
            encoding="utf-8"))
        dated = 0
        for f in d["files"]:
            for k in ("since", "until"):
                if k in f:
                    datetime.fromisoformat(f[k])
                    dated += 1
        self.assertGreaterEqual(dated, 3, "strip counters need dated files")

    def test_strip_css_present(self):
        self.assertIn(".files-strip", build.CSS)
        self.assertIn(".fs-chip", build.CSS)


if __name__ == "__main__":
    unittest.main()
