"""Amed Khan and the foundation that buys Gaza's food and medicine.

Owner request, 2026-09-27: highlight the work and feature it prominently,
and include the articles he has published in the Los Angeles Times and
elsewhere. The feature therefore has to hold two things at once. It is a
CELEBRATION under the features order of 2026-08-05 — the achievement is the
story — and every number in it is somebody's attributed claim, mostly his
own, so each one is pinned here to the outlet and date it came from.

The prominence is a SPECIALS card gated on `requires_original`, which means
it retires with the story instead of squatting the row, and which must not
displace the Dima Barakat campaign pin from the lead.
"""
import re
import unittest
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parents[1]
SLUG = "amed-khan-foundation-gaza-2026"
COVER = "times-of-palestine-amed-khan-gaza-2026-lede.svg"
CHART = "times-of-palestine-amed-khan-promise-gap-2026.svg"


def _original(lang):
    return (ROOT / "originals" / f"{SLUG}.{lang}.txt").read_text(encoding="utf-8")


def _header(lang):
    out = {}
    for line in _original(lang).split("\n---\n", 1)[0].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip()
    return out


def _body(lang):
    return _original(lang).split("\n---\n", 1)[1]


class ContractTests(unittest.TestCase):
    def test_both_editions_exist_and_share_their_headers(self):
        en, ar = _header("en"), _header("ar")
        self.assertEqual(en["category"], "humans")
        self.assertEqual(ar["category"], "humans")
        self.assertEqual(en["date"], ar["date"])
        self.assertTrue(en["image"].endswith(COVER))
        self.assertEqual(en["image"], ar["image"])

    def test_headlines_are_active_and_within_the_cap(self):
        for lang in ("en", "ar"):
            title = _header(lang)["title"]
            self.assertLessEqual(len(title.split()), build.TITLE_MAX_WORDS, lang)
            self.assertEqual([], build.passive_title_warnings(title, lang), lang)

    def test_the_editions_stay_in_parity(self):
        counts = {}
        for lang in ("en", "ar"):
            body = _body(lang)
            counts[lang] = (len(re.findall(r"^## ", body, re.M)),
                            len(re.findall(r"^!\[", body, re.M)))
        self.assertEqual(counts["en"], counts["ar"])
        self.assertEqual(counts["en"], (6, 1))

    def test_no_paragraph_runs_past_the_pacing_limit(self):
        for lang in ("en", "ar"):
            for para in (p.strip() for p in _body(lang).split("\n\n")):
                if not para or para[0] in "#!>":
                    continue
                self.assertLessEqual(len(para.split()), build.MAX_PARA_WORDS,
                                     f"{lang}: {para[:60]}")


class RecordTests(unittest.TestCase):
    def test_his_published_writing_is_listed_with_outlet_and_date(self):
        # The owner asked for this explicitly: he publishes under his own
        # name, and the pieces are part of the work.
        en = _body("en")
        for outlet in ("Los Angeles Times", "The Intercept", "The Nation",
                       "Responsible Statecraft"):
            self.assertIn(outlet, en, outlet)
        for date in ("5 March 2026", "23 March 2024", "16 August 2024"):
            self.assertIn(date, en, date)
        ar = _body("ar")
        for outlet in ("لوس أنجلوس تايمز", "ذي إنترسبت", "ذا نيشن",
                       "ريسبونسبل ستيتكرافت"):
            self.assertIn(outlet, ar, outlet)

    def test_the_hind_rajab_thread_is_carried_with_its_source(self):
        en = _body("en")
        self.assertIn("Wissam Hamada", en)
        self.assertIn("Variety", en)
        self.assertIn("four hours", en)
        self.assertIn("Elpida Home", en)
        ar = _body("ar")
        self.assertIn("وسام حمادة", ar)
        self.assertIn("فارايتي", ar)
        self.assertIn("أربع ساعات", ar)

    def test_every_gap_figure_names_who_gave_it(self):
        en = _body("en")
        self.assertIn("Service95", en)
        self.assertIn("Global Dispatches", en)
        # the truck count Israel disputes is labelled as Israel's own claim
        self.assertIn("Israel claiming about 450", en)
        self.assertIn("113", en)

    def test_his_characterisations_stay_his(self):
        # "Ethnic cleansing" appears as the title of his essay, never as the
        # paper's own voice; the copy says so in the same breath.
        en = _body("en")
        self.assertIn("Ethnic Cleansing", en)
        self.assertIn("These are his arguments", en)

    def test_no_sources_section_or_briefing_memo_furniture(self):
        for lang in ("en", "ar"):
            body = _body(lang).lower()
            for banned in ("## sources", "key takeaways", "bottom line",
                           "## المصادر", "أبرز النقاط"):
                self.assertNotIn(banned, body, f"{lang}/{banned}")


class ProminenceTests(unittest.TestCase):
    def _card(self):
        for card in build.SPECIALS:
            if card.get("requires_original") == SLUG:
                return card
        self.fail("no SPECIALS card for the Amed Khan feature")

    def test_the_card_is_pinned_and_self_retiring(self):
        card = self._card()
        self.assertEqual(card["href"], build._original_story_href(SLUG))
        for key in ("kicker", "title", "dek", "cta", "img_alt", "ticker", "nav"):
            self.assertIn("en", card[key], key)
            self.assertIn("ar", card[key], key)
        self.assertTrue(card["img"].endswith(COVER))

    def test_the_campaign_pin_still_leads_the_row(self):
        slugs = [c.get("requires_original") for c in build.SPECIALS]
        self.assertEqual(slugs[0], "dima-barakat-file-2026")
        self.assertIn(SLUG, slugs)
        self.assertLess(slugs.index(SLUG), slugs.index("palestine-top100-2026"))


class ArtTests(unittest.TestCase):
    def _svgs(self):
        names = [COVER, CHART, CHART.replace(".svg", "-ar.svg")]
        return [(n, ROOT / "originals" / "media" / n) for n in names]

    def test_every_graphic_ships_and_none_overflows(self):
        for name, path in self._svgs():
            self.assertTrue(path.exists(), name)
            self.assertEqual([], build.svg_text_overflows(str(path)), name)

    def test_arabic_runs_carrying_digits_declare_rtl(self):
        # Without direction="rtl" the runs around a number lay out left to
        # right and the line reaches the reader scrambled.
        for name, path in self._svgs():
            for node in build.RTL_MIXED_TEXT_RX.finditer(path.read_text(encoding="utf-8")):
                self.assertIn('direction="rtl"', node.group(1),
                              f"{name}: {node.group(2)[:50]}")

    def test_each_edition_embeds_its_own_language_chart(self):
        self.assertIn(CHART, _body("en"))
        self.assertIn(CHART.replace(".svg", "-ar.svg"), _body("ar"))

    def test_the_cover_is_an_illustration_not_a_chart(self):
        # Covers are pictures; the figures board belongs in the body.
        art = (ROOT / "originals" / "media" / COVER).read_text(encoding="utf-8")
        self.assertIn("FOUR HOURS", art)
        self.assertNotIn("PLEDGED, AND DELIVERED", art)


if __name__ == "__main__":
    unittest.main()
