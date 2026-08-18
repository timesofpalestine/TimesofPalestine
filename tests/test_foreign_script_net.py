"""No foreign-script homoglyph publishes inside Arabic copy.

Owner report 2026-08-17: a live title read «بين ترامป ونتنياهو» — THAI
letter ป (U+0E1B) in place of ب. The Arabic quality nets now catch any
Thai/CJK/Cyrillic/Devanagari/Kana/Hangul character and the Persian-only
letters پ/چ/ژ/گ inside Arabic text; the cache scrub then regenerates the
tainted brief."""
import unittest

import build


class ForeignScriptNetTest(unittest.TestCase):
    def test_the_published_homoglyph_title_is_caught(self):
        issues = build.language_quality_issues(
            "التايمز: هجمات مستوطنين قد تعمّق الخلاف بين ترامป ونتنياهو", "ar")
        self.assertTrue(issues)

    def test_persian_peh_variant_is_caught(self):
        self.assertTrue(build.language_quality_issues("زيارة ترامپ", "ar"))

    def test_hard_gate_regex_exists_and_catches_both_live_leaks(self):
        # 2026-08-17 follow-up: the advisory net alone let a SECOND Thai
        # headline publish («تحليل: المفاوضات بين ترامప ونتنياهو») because
        # generation publishes best-effort after one retry and the cache
        # scrub exempted current-style entries. FOREIGN_SCRIPT_RX is the
        # hard gate both paths now share.
        for title in ("التايمز: هجمات مستوطنين قد تعمّق الخلاف بين ترامప ونتنياهو",
                      "تحليل: المفاوضات بين ترامప ونتنياهو أداة مراوغة"):
            self.assertIsNotNone(build.FOREIGN_SCRIPT_RX.search(title))
        self.assertIsNone(build.FOREIGN_SCRIPT_RX.search(
            "الخلاف بين ترامب ونتنياهو يتسع"))

    def test_correct_spelling_and_digits_pass(self):
        for text in ("الخلاف بين ترامب ونتنياهو يتسع",
                     "قالت وزارة الصحة إن 20 جريحاً وصلوا المستشفى.",
                     "نُشر التقرير في 17 آب/أغسطس 2026."):
            self.assertFalse(
                build.language_quality_issues(text, "ar"),
                f"foreign-script net over-matched: {text}")


if __name__ == "__main__":
    unittest.main()
