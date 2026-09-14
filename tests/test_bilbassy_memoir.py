"""The Bilbassy memoir feature and its front-page pin (owner request 2026-09-14).

The owner sent Nadia Bilbassy's own announcement of «من غزة إلى البيت الأبيض»
and asked for it written up and featured prominently. Two things are pinned
here. The FEATURE: both editions first-class, filed under Her Story, with the
bilingual art the Arabic edition has been missing on infographic ledes since
the 7 August audit. The PIN: a SPECIALS card that is prominent but cannot
squat — it hangs off `requires_original`, so it retires with the story's own
shelf life instead of advertising a January book until January. The campaign
pin keeps the first slot it was given on 19 August.
"""
import json
import re
import unittest
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parents[1]
SLUG = "nadia-bilbassy-memoir-2026"
COVER = "times-of-palestine-bilbassy-memoir-2026.svg"


def _original(lang):
    return (ROOT / "originals" / f"{SLUG}.{lang}.txt").read_text(encoding="utf-8")


def _header(lang):
    head = _original(lang).split("\n---\n", 1)[0]
    out = {}
    for line in head.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip()
    return out


def _lexicon():
    return json.loads((ROOT / "editorial" / "arabic-names.json")
                      .read_text(encoding="utf-8"))["names"]


class FeatureTests(unittest.TestCase):
    def test_both_editions_exist(self):
        for lang in ("en", "ar"):
            self.assertTrue((ROOT / "originals" / f"{SLUG}.{lang}.txt").is_file(), lang)

    def test_the_subject_is_the_woman_so_it_files_under_her_story(self):
        for lang in ("en", "ar"):
            self.assertEqual(_header(lang)["category"], "women", lang)

    def test_headlines_obey_the_house_rules(self):
        for lang in ("en", "ar"):
            title = _header(lang)["title"]
            self.assertLessEqual(len(title.split()), build.TITLE_MAX_WORDS, lang)
            self.assertEqual(build.passive_title_warnings(title, lang), [], lang)
            self.assertFalse(title.endswith("…"), lang)

    def test_the_arabic_edition_gets_its_own_artwork(self):
        # Standing complaint from the 7 August audit: Arabic ledes ran
        # English-first infographics. This feature ships the twin.
        self.assertIn("times-of-palestine-bilbassy-route-2026.svg", _original("en"))
        self.assertIn("times-of-palestine-bilbassy-route-2026-ar.svg", _original("ar"))

    def test_every_referenced_graphic_exists_and_fits_its_canvas(self):
        media = ROOT / "originals" / "media"
        for lang in ("en", "ar"):
            for name in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", _original(lang)):
                self.assertTrue((media / name).is_file(), name)
        for name in (COVER, "times-of-palestine-bilbassy-route-2026.svg",
                     "times-of-palestine-bilbassy-route-2026-ar.svg"):
            src = (media / name).read_text(encoding="utf-8")
            self.assertEqual(build.svg_text_overflows(src), [], name)

    def test_the_announcement_is_attributed_not_adopted(self):
        # A social-media announcement is a claim by its author: the copy says
        # who said it, in both editions.
        self.assertIn("she wrote", _original("en"))
        self.assertIn("HarperCollins", _original("en"))
        self.assertIn("وكتبت البلبيسي", _original("ar"))
        self.assertIn("هاربر كولينز", _original("ar"))


class PinTests(unittest.TestCase):
    def _card(self):
        for s in build.SPECIALS:
            if s.get("requires_original") == SLUG:
                return s
        self.fail(f"no SPECIALS card for {SLUG}")

    def test_the_memoir_is_pinned_to_the_front_page_row(self):
        card = self._card()
        self.assertEqual(card["href"], build._original_story_href(SLUG))
        for lang in ("en", "ar"):
            self.assertTrue(card["href"][lang].startswith(f"/{lang}/story/"), lang)
            for field in ("kicker", "title", "dek", "cta", "img_alt", "ticker", "nav"):
                self.assertTrue(card[field][lang].strip(), f"{field}/{lang}")

    def test_the_campaign_pin_still_leads_the_row(self):
        # Owner order 2026-08-19: the Dima Barakat case is the first card.
        self.assertEqual(build.SPECIALS[0].get("requires_original"),
                         "dima-barakat-file-2026")
        self.assertEqual(build.SPECIALS[1].get("requires_original"), SLUG)

    def test_the_pin_retires_with_the_story_and_cannot_squat(self):
        # No `standing:` header and no oversized maxAgeHours: the card is
        # gated on the original, and the original ages out on the house
        # default. A January book must not hold the row until January.
        body = _original("en")
        self.assertNotIn("standing:", body)
        for lang in ("en", "ar"):
            self.assertNotIn("maxAgeHours", _header(lang))
        self.assertNotIn(SLUG, build.PINNED_ORIGINAL_SLUGS)

    def test_the_card_disappears_when_the_story_is_gone(self):
        self.assertNotIn(self._card(), build.available_specials("en", items=[]))
        live = [{"link": f"original:{SLUG}.en"}]
        self.assertIn(self._card(), build.available_specials("en", items=live))

    def test_the_card_art_ships_with_the_build(self):
        self.assertEqual(self._card()["img"], f"/media/{COVER}")
        self.assertTrue((ROOT / "originals" / "media" / COVER).is_file())


class ArabicNameTests(unittest.TestCase):
    def test_her_name_is_recorded_from_her_own_networks_byline(self):
        entry = next((n for n in _lexicon()
                      if n["ar"] == "ناديا البلبيسي"), None)
        self.assertIsNotNone(entry, "Bilbassy missing from the Arabic lexicon")
        self.assertIn("نادية البلبيسي", entry["wrong"])
        self.assertIn("alarabiya.net", entry["verified"])

    def test_the_arabic_edition_uses_the_verified_spelling(self):
        text = _original("ar")
        self.assertIn("ناديا البلبيسي", text)
        self.assertNotIn("نادية البلبيسي", text)


if __name__ == "__main__":
    unittest.main()
