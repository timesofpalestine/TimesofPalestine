"""The Almadhoun screening file and its front-page pin (owner request 2026-09-14).

The owner sent Hani Almadhoun's own account of being flagged at every stage of
a 4 July family flight and asked for a full, professional write-up featured
prominently. What is pinned here is the DISCIPLINE, because that is what makes
the piece hold up: his account is labelled as his account and explicitly not
independently verified; the mechanism is explained from named institutional
sources (the oversight board, the two appellate lines, the July ruling) rather
than asserted; the context that would be easy to turn into an accusation —
his employer, the UNRWA designation question — carries the counterweight that
no agency has connected any of it to his screening and that he has never been
charged. The pin is prominent and self-retiring, behind the campaign card.
"""
import json
import re
import unittest
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parents[1]
SLUG = "hani-almadhoun-airport-screening-2026"
COVER = "times-of-palestine-almadhoun-screening-2026.svg"


def _original(lang):
    return (ROOT / "originals" / f"{SLUG}.{lang}.txt").read_text(encoding="utf-8")


def _header(lang):
    out = {}
    for line in _original(lang).split("\n---\n", 1)[0].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip()
    return out


class FileTests(unittest.TestCase):
    def test_both_editions_exist_and_file_to_the_diaspora_beat(self):
        for lang in ("en", "ar"):
            self.assertTrue((ROOT / "originals" / f"{SLUG}.{lang}.txt").is_file(), lang)
            self.assertEqual(_header(lang)["category"], "diaspora", lang)

    def test_headlines_obey_the_house_rules(self):
        for lang in ("en", "ar"):
            title = _header(lang)["title"]
            self.assertLessEqual(len(title.split()), build.TITLE_MAX_WORDS, lang)
            self.assertEqual(build.passive_title_warnings(title, lang), [], lang)

    def test_the_arabic_edition_gets_its_own_explainer(self):
        self.assertIn("times-of-palestine-watchlist-redress-2026.svg", _original("en"))
        self.assertIn("times-of-palestine-watchlist-redress-2026-ar.svg", _original("ar"))

    def test_every_graphic_exists_and_fits_its_canvas(self):
        media = ROOT / "originals" / "media"
        for lang in ("en", "ar"):
            for name in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", _original(lang)):
                self.assertTrue((media / name).is_file(), name)
        for name in (COVER, "times-of-palestine-watchlist-redress-2026.svg",
                     "times-of-palestine-watchlist-redress-2026-ar.svg"):
            self.assertEqual(
                build.svg_text_overflows((media / name).read_text(encoding="utf-8")),
                [], name)


class DisciplineTests(unittest.TestCase):
    """An accountability file, not a campaign."""

    def test_his_account_is_labelled_as_his_account(self):
        self.assertIn("has not independently verified", _original("en"))
        self.assertIn("لم تتحقق", _original("ar"))

    def test_the_context_carries_its_counterweight(self):
        # The UNRWA funding and designation context is the easiest thing in
        # this story to turn into an accusation. It never runs without the
        # sentence saying no agency has connected it to his screening.
        en = _original("en")
        self.assertIn("foreign terrorist organisation", en)
        self.assertIn("never been charged", en)
        self.assertIn("no agency has said his screening", en)
        ar = _original("ar")
        self.assertIn("منظمة إرهابية أجنبية", ar)
        self.assertIn("لم تُوجَّه إلى المدهون تهمة", ar)
        self.assertIn("ولم تقل أي جهة", ar)

    def test_the_mechanism_is_sourced_to_named_institutions(self):
        for lang, markers in (
                ("en", ("Privacy and Civil Liberties Oversight Board", "January 2025",
                        "Latif v. Holder", "Elhady v. Kable", "Nachmanoff",
                        "Council on American-Islamic Relations", "Quiet Skies")),
                ("ar", ("مجلس الرقابة على الخصوصية والحريات المدنية", "لطيف ضد هولدر",
                        "الهادي ضد كيبل", "ناكمانوف", "مجلس العلاقات الأميركية الإسلامية",
                        "السماء الهادئة"))):
            text = _original(lang)
            for marker in markers:
                self.assertIn(marker, text, f"{marker} missing from {lang}")

    def test_the_july_ruling_carries_what_it_did_not_decide(self):
        # It found a Fourth Amendment violation and declined to find First
        # Amendment retaliation. Reporting only the first half would overstate.
        self.assertIn("declined to find", _original("en"))
        self.assertIn("ورفضت المحكمة", _original("ar"))

    def test_the_agencies_are_given_their_answer_and_a_standing_update(self):
        self.assertIn("will be added to this report", _original("en"))
        self.assertIn("يُضاف إلى هذا التقرير", _original("ar"))


class PinTests(unittest.TestCase):
    def _card(self):
        for s in build.SPECIALS:
            if s.get("requires_original") == SLUG:
                return s
        self.fail(f"no SPECIALS card for {SLUG}")

    def test_the_file_is_pinned_to_the_front_page_row(self):
        card = self._card()
        self.assertEqual(card["href"], build._original_story_href(SLUG))
        for lang in ("en", "ar"):
            for field in ("kicker", "title", "dek", "cta", "img_alt", "ticker", "nav"):
                self.assertTrue(card[field][lang].strip(), f"{field}/{lang}")

    def test_it_sits_behind_the_campaign_pin(self):
        self.assertEqual(build.SPECIALS[0].get("requires_original"),
                         "dima-barakat-file-2026")
        self.assertEqual(build.SPECIALS[1].get("requires_original"), SLUG)

    def test_the_pin_retires_with_the_story(self):
        for lang in ("en", "ar"):
            self.assertNotIn("maxagehours", _header(lang))
            self.assertNotIn("standing", _header(lang))
        self.assertNotIn(SLUG, build.PINNED_ORIGINAL_SLUGS)
        self.assertNotIn(self._card(), build.available_specials("en", items=[]))
        self.assertIn(self._card(),
                      build.available_specials("en", [{"link": f"original:{SLUG}.en"}]))

    def test_the_card_art_ships(self):
        self.assertEqual(self._card()["img"], f"/media/{COVER}")
        self.assertTrue((ROOT / "originals" / "media" / COVER).is_file())


class ArabicNameTests(unittest.TestCase):
    def _lexicon(self):
        return json.loads((ROOT / "editorial" / "arabic-names.json")
                          .read_text(encoding="utf-8"))["names"]

    def test_the_names_are_recorded_with_their_sources(self):
        for arabic in ("هاني المدهون", "أسامة أبو ارشيد", "مايكل ناكمانوف"):
            entry = next((n for n in self._lexicon() if n["ar"] == arabic), None)
            self.assertIsNotNone(entry, f"{arabic} missing from the lexicon")
            self.assertIn("aljazeera.net", entry["verified"], arabic)

    def test_the_arabic_edition_uses_the_verified_spellings(self):
        text = _original("ar")
        for arabic in ("هاني المدهون", "أسامة أبو ارشيد", "مايكل ناكمانوف"):
            self.assertIn(arabic, text)


if __name__ == "__main__":
    unittest.main()
