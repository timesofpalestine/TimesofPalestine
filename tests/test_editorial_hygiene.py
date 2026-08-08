"""The charter's editorial rules, re-checked on the rendered page.

Ingest-time gates protect originals, but they only see the source file. These
tests cover validate_build.check_editorial_hygiene, which reads what actually
shipped — the only thing a reader sees — so a regression, or copy arriving by a
path that skips the ingest gate, cannot publish unnoticed.

The negative cases matter as much as the positives: this check runs over every
story on every build, so a false positive would fail the build on good copy.
"""
import unittest

import validate_build as V


def hygiene(html):
    errors = []
    V.check_editorial_hygiene("en/story/test.html", html, errors)
    return errors


class BannedSectionTests(unittest.TestCase):
    """No sources, methodology or memo-style sections — attribution goes inline."""

    def test_sources_section_is_rejected(self):
        self.assertTrue(hygiene('<h2 class="sub">Sources</h2>'))

    def test_trailing_colon_does_not_evade(self):
        self.assertTrue(hygiene('<h2 class="sub">Sources:</h2>'))

    def test_case_does_not_evade(self):
        self.assertTrue(hygiene('<h2 class="sub">SOURCES</h2>'))

    def test_nested_markup_does_not_evade(self):
        self.assertTrue(hygiene('<h2 class="sub"><strong>Methodology</strong></h2>'))

    def test_arabic_sections_are_rejected(self):
        for head in ("المصادر والوثائق", "المنهجية", "حق الرد", "حقوق المواد البصرية"):
            with self.subTest(head=head):
                self.assertTrue(hygiene(f'<h2 class="sub">{head}</h2>'))

    def test_memo_sections_are_rejected(self):
        for head in ("Key takeaways", "Bottom line", "Unanswered questions",
                     "What remains unanswered", "Conclusion"):
            with self.subTest(head=head):
                self.assertTrue(hygiene(f'<h2 class="sub">{head}</h2>'))

    def test_h3_and_h4_are_covered(self):
        self.assertTrue(hygiene('<h3 class="sub">Right of reply</h3>'))
        self.assertTrue(hygiene('<h4 class="sub">Corrections</h4>'))


class LeakedNoteTests(unittest.TestCase):
    """Internal scaffolding must never reach a reader."""

    def test_pre_publication_instruction_is_caught(self):
        self.assertTrue(hygiene(
            '<p class="summary">Before publication, the newsroom should seek '
            'on-record responses.</p>'))

    def test_draft_state_is_caught(self):
        self.assertTrue(hygiene(
            '<p class="summary">This is an unpublished draft.</p>'))

    def test_placeholders_are_caught(self):
        for note in ("TODO", "[placeholder]", "lorem ipsum"):
            with self.subTest(note=note):
                self.assertTrue(hygiene(f'<p class="summary">{note} fix this.</p>'))

    def test_reader_facing_review_labels_are_caught(self):
        for label in ("developing report", "awaiting review", "pending review"):
            with self.subTest(label=label):
                self.assertTrue(hygiene(f'<p class="summary">This {label} continues.</p>'))


class NoFalsePositiveTests(unittest.TestCase):
    """Good copy must never fail the build."""

    def test_ordinary_subheads_pass(self):
        for head in ("Why this matters", "By the numbers", "What to watch",
                     "لماذا يهم هذا", "بالأرقام"):
            with self.subTest(head=head):
                self.assertEqual(hygiene(f'<h2 class="sub">{head}</h2>'), [])

    def test_sources_as_prose_passes(self):
        # Real sentence from a published desk report: "sources differ on…".
        self.assertEqual(hygiene(
            '<p class="summary">Sources differ on the starting point.</p>'), [])
        self.assertEqual(hygiene(
            '<p class="summary">وتتباين المصادر بشأن نقطة الانطلاق.</p>'), [])

    def test_bottom_line_as_prose_passes(self):
        self.assertEqual(hygiene(
            '<p class="summary">The bottom line is that nobody has answered.</p>'), [])

    def test_attribution_in_prose_passes(self):
        self.assertEqual(hygiene(
            '<p class="summary">The Carter Center found the commission retained '
            'capacity, according to its July assessment.</p>'), [])

    def test_empty_page_passes(self):
        self.assertEqual(hygiene(""), [])


if __name__ == "__main__":
    unittest.main()
