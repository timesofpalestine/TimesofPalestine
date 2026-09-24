"""The govmap layer: Israel published northern Gaza's ruins, then blurred them.

Two claims arrived on the same day from sources that did not agree. Nathan
Ruser said at 10:44 UTC that govmap had REMOVED the imagery; the Times of
Israel's military correspondent reported at 18:11 Jerusalem time that the
site had PARTIALLY RE-BLURRED it and that the photography was still loaded.
Both are in the copy, each attributed and timed, because a story about an
official record being withdrawn cannot itself be loose about who said what.
That, and the govmap and army statements, is what these tests hold.

The SVG rule pinned at the bottom is the one that broke here in preview:
`direction="rtl"` on an SVG <text> INVERTS text-anchor, so a "start"-anchored
Arabic run walks off the left edge of the canvas and an "end"-anchored one
walks off the right. Arabic text nodes are skipped by svg_text_overflows, so
nothing but a screenshot catches it. Leave the attribute off and let the
bidi algorithm place the run.
"""
import re
import unittest
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parents[1]
SLUG = "govmap-northern-gaza-imagery-2026-09-24"
COVER = "times-of-palestine-govmap-imagery-2026-09-24-lede.svg"
CHART = "times-of-palestine-imagery-resolution-2026-09-24.svg"


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
        self.assertEqual(en["category"], "gaza")
        self.assertEqual(ar["category"], "gaza")
        self.assertEqual(en["date"], ar["date"])
        self.assertEqual(en["image"], ar["image"])
        self.assertTrue(en["image"].endswith(COVER))

    def test_headlines_are_active_and_within_the_cap(self):
        for lang in ("en", "ar"):
            title = _header(lang)["title"]
            self.assertLessEqual(len(title.split()), build.TITLE_MAX_WORDS, lang)
            self.assertFalse(title.endswith("..."), lang)
            self.assertEqual([], build.passive_title_warnings(title, lang), lang)

    def test_the_editions_stay_in_parity(self):
        counts = {}
        for lang in ("en", "ar"):
            body = _body(lang)
            counts[lang] = (
                len(re.findall(r"^## ", body, re.M)),
                len(re.findall(r"^!\[", body, re.M)),
            )
        self.assertEqual(counts["en"], counts["ar"])
        self.assertEqual(counts["en"], (5, 1))

    def test_no_paragraph_runs_past_the_pacing_limit(self):
        for lang in ("en", "ar"):
            for para in (p.strip() for p in _body(lang).split("\n\n")):
                if not para or para[0] in "#!>":
                    continue
                self.assertLessEqual(len(para.split()), build.MAX_PARA_WORDS,
                                     f"{lang}: {para[:60]}")


class AttributionTests(unittest.TestCase):
    def test_both_accounts_of_what_happened_to_the_layer_are_carried(self):
        # Ruser said removed; the Times of Israel reported partially re-blurred
        # hours later. Dropping either one would make the copy take a side.
        en = _body("en")
        self.assertIn("removed this imagery from its map platform", en)
        self.assertIn("partially re-blurred", en)
        self.assertIn("Emanuel Fabian", en)
        ar = _body("ar")
        self.assertIn("أزال هذه الصور من منصته", ar)
        self.assertIn("أعاد حجبًا جزئيًا", ar)
        self.assertIn("إيمانويل فابيان", ar)

    def test_the_analyst_is_named_with_his_institution_and_his_numbers(self):
        for lang, analyst, institute in (
            ("en", "Nathan Ruser", "Australian Strategic Policy Institute"),
            ("ar", "ناثان روزر", "معهد السياسة الإستراتيجية الأسترالي"),
        ):
            body = _body(lang)
            self.assertIn(analyst, body, lang)
            self.assertIn(institute, body, lang)
            self.assertIn("2.5", body, lang)
            self.assertIn("13", body, lang)

    def test_govmap_and_the_army_answer_in_their_own_words(self):
        en = _body("en")
        self.assertIn("in accordance with relevant guidelines and approvals", en)
        self.assertIn("examine it with the authorized authorities", en)
        self.assertIn("looking into the imagery", en)
        ar = _body("ar")
        self.assertIn("وفق التعليمات والموافقات ذات الصلة", ar)
        self.assertIn("سيفحص الأمر مع الجهات المخوّلة", ar)

    def test_the_resolution_claim_carries_the_law_that_makes_it_matter(self):
        self.assertIn("Kyl-Bingaman", _body("en"))
        self.assertIn("40 centimetres", _body("en"))
        self.assertIn("كايل-بينغمان", _body("ar"))
        self.assertIn("40 سنتيمترًا", _body("ar"))

    def test_the_destruction_counts_are_attributed_and_dated(self):
        en = _body("en")
        self.assertIn("UNOSAT", en)
        self.assertIn("11 October 2025", en)
        self.assertIn("Al Jazeera", en)
        ar = _body("ar")
        self.assertIn("يونوسات", ar)
        self.assertIn("11 أكتوبر/تشرين الأول 2025", ar)
        self.assertIn("الجزيرة نت", ar)

    def test_no_sources_section_and_no_briefing_memo_furniture(self):
        for lang in ("en", "ar"):
            body = _body(lang).lower()
            for banned in ("## sources", "## bibliography", "key takeaways",
                           "bottom line", "## المصادر", "أبرز النقاط"):
                self.assertNotIn(banned, body, f"{lang}/{banned}")


class ArtTests(unittest.TestCase):
    def _svgs(self):
        names = [COVER, CHART, CHART.replace(".svg", "-ar.svg")]
        return [(n, ROOT / "originals" / "media" / n) for n in names]

    def test_every_graphic_ships_and_none_overflows(self):
        for name, path in self._svgs():
            self.assertTrue(path.exists(), name)
            self.assertEqual([], build.svg_text_overflows(str(path)), name)

    def test_no_svg_text_sets_direction_rtl(self):
        # It inverts text-anchor and walks Arabic runs off the canvas, and the
        # overflow checker skips Arabic nodes, so only a screenshot sees it.
        for name, path in self._svgs():
            self.assertNotIn('direction="rtl"', path.read_text(encoding="utf-8"), name)

    def test_each_edition_embeds_its_own_language_chart(self):
        self.assertIn(CHART, _body("en"))
        self.assertIn(CHART.replace(".svg", "-ar.svg"), _body("ar"))

    def test_the_cover_says_the_tiles_are_a_schematic(self):
        art = (ROOT / "originals" / "media" / COVER).read_text(encoding="utf-8")
        self.assertIn("Schematic, not the imagery itself", art)


if __name__ == "__main__":
    unittest.main()
