"""Palestinian Minds — the weekly scholar franchise (owner directive 2026-09-19).

"Make it a habit to feature a researcher or a professor of Palestinian origin
and highlight his work, in both languages."

The habit is the point, so what is pinned here is the machinery that makes it
recur — the charter section, the queue, the editor's Wednesday cadence — and
the two rules that keep the franchise honest when it runs unattended: the WORK
has to be explained and sourced to a journal and a year, and nothing about a
person's origin or politics goes beyond the record. A profile that lists
prizes is the failure mode this franchise is built to avoid.
"""
import re
import unittest
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "editorial" / "palestinian-minds-queue.md"
LAUNCH = "palestinian-minds-abu-rabia-2026"
COVER = "times-of-palestine-palestinian-minds.svg"


def _original(lang):
    return (ROOT / "originals" / f"{LAUNCH}.{lang}.txt").read_text(encoding="utf-8")


def _header(lang):
    out = {}
    for line in _original(lang).split("\n---\n", 1)[0].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip()
    return out


class FranchiseTests(unittest.TestCase):
    def test_both_charters_carry_the_directive_and_stay_identical(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("Palestinian Minds", text, name)
            block = text.split("## Palestinian Minds", 1)[1].split("\n## ", 1)[0]
            self.assertIn("WEDNESDAY", block, name)
            self.assertIn("palestinian-minds-queue.md", block, name)
            self.assertIn("The work is the story", block, name)
            self.assertIn("Nothing beyond the record", block, name)
        self.assertEqual((ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
                         (ROOT / "AGENTS.md").read_text(encoding="utf-8"))

    def test_the_editor_is_told_the_weekly_cadence(self):
        wf = (ROOT / ".github" / "workflows" / "daily-editor.yml").read_text(encoding="utf-8")
        self.assertIn("Palestinian Minds", wf)
        self.assertIn("WEDNESDAY", wf)
        self.assertIn("palestinian-minds-queue.md", wf)

    def test_the_queue_exists_and_holds_a_real_rotation(self):
        text = QUEUE.read_text(encoding="utf-8")
        self.assertIn("## Published", text)
        self.assertIn("## Up next", text)
        upcoming = text.split("## Up next", 1)[1]
        entries = re.findall(r"^\s*\d+\.\s+\*\*", upcoming, re.M)
        self.assertGreaterEqual(len(entries), 5,
                                "the queue must stay deep enough to run weekly")

    def test_the_queue_carries_the_discipline_rules(self):
        text = QUEUE.read_text(encoding="utf-8")
        for rule in ("The work is the story", "never insinuated",
                     "Nothing beyond the record"):
            self.assertIn(rule, text, rule)


class LaunchFeatureTests(unittest.TestCase):
    def test_both_editions_exist_under_the_right_category(self):
        for lang in ("en", "ar"):
            self.assertTrue((ROOT / "originals" / f"{LAUNCH}.{lang}.txt").is_file(), lang)
            self.assertEqual(_header(lang)["category"], "humans", lang)

    def test_headlines_obey_the_house_rules(self):
        for lang in ("en", "ar"):
            title = _header(lang)["title"]
            self.assertLessEqual(len(title.split()), build.TITLE_MAX_WORDS, lang)
            self.assertEqual(build.passive_title_warnings(title, lang), [], lang)

    def test_the_work_is_named_to_its_journal_and_year(self):
        # The franchise's core rule. Each edition must carry real citations,
        # not a list of honours.
        for lang, markers in (
                ("en", ("Bilingual Research Journal", "Reading and Writing",
                        "Journal of Learning Disabilities", "Dyslexia",
                        "Race Ethnicity and Education")),
                ("ar", ("مجلة البحوث ثنائية اللغة", "مجلة القراءة والكتابة",
                        "مجلة صعوبات التعلم", "ديسلكسيا"))):
            text = _original(lang)
            for marker in markers:
                self.assertIn(marker, text, f"{marker} missing from {lang}")
            years = set(re.findall(r"\b(19|20)\d{2}\b", text))
            self.assertTrue(years, f"{lang} carries no years")

    def test_the_central_idea_is_explained_not_just_named(self):
        en = _original("en")
        self.assertIn("Cognitive Retroactive Transfer", en)
        self.assertIn("the other way", en)
        ar = _original("ar")
        self.assertIn("النقل الفكري التراجعي", ar)
        self.assertIn("الاتجاه المعاكس", ar)

    def test_metrics_are_attributed_and_dated(self):
        self.assertIn("at the time of writing", _original("en"))
        self.assertIn("عند كتابة هذا التقرير", _original("ar"))

    def test_the_arabic_edition_gets_its_own_graphic(self):
        self.assertIn("times-of-palestine-abu-rabia-transfer-2026.svg", _original("en"))
        self.assertIn("times-of-palestine-abu-rabia-transfer-2026-ar.svg", _original("ar"))

    def test_every_graphic_exists_and_fits_its_canvas(self):
        media = ROOT / "originals" / "media"
        for lang in ("en", "ar"):
            for name in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", _original(lang)):
                self.assertTrue((media / name).is_file(), name)
        for name in (COVER, "times-of-palestine-abu-rabia-transfer-2026.svg",
                     "times-of-palestine-abu-rabia-transfer-2026-ar.svg"):
            self.assertEqual(
                build.svg_text_overflows((media / name).read_text(encoding="utf-8")),
                [], name)

    def test_the_franchise_cover_is_reusable_art(self):
        # It carries the franchise, not the subject, so every future entry
        # can lead with it until a portrait is cleared.
        for lang in ("en", "ar"):
            self.assertEqual(_header(lang)["image"], f"/media/{COVER}", lang)
        art = (ROOT / "originals" / "media" / COVER).read_text(encoding="utf-8")
        self.assertNotIn("Abu-Rabia", art)
        self.assertIn("PALESTINIAN MINDS", art)
        self.assertIn("عقول فلسطينية", art)


if __name__ == "__main__":
    unittest.main()
