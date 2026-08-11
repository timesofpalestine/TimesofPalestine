"""Section-freshness ledger (owner order 2026-08-11): every section, both
editions, updates at least daily. These tests pin the ledger's contract —
what counts as stale, that both ledgers (story-archive and originals) are
read, and that desk steering ranks the worst-starved section first."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import section_freshness as sf

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _write_archive(root, lang, pid, cat, dt):
    d = root / "story-archive" / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps(
        {"pid": pid, "cat": cat, "lang": lang, "date": dt.isoformat()}),
        encoding="utf-8")


def _write_original(root, slug, lang, cat, dt):
    d = root / "originals"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.{lang}.txt").write_text(
        f"title: T\ncategory: {cat}\ndate: {dt.strftime('%Y-%m-%dT%H:%M:%SZ')}\n---\nBody.\n",
        encoding="utf-8")


class SectionFreshnessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_fresh_section_is_not_stale(self):
        _write_archive(self.root, "en", "a1", "gaza", NOW - timedelta(hours=2))
        rep = sf.report(self.root, NOW)
        self.assertFalse(rep["sections"]["en"]["gaza"]["stale"])

    def test_old_and_missing_sections_are_stale(self):
        _write_archive(self.root, "en", "a1", "sports", NOW - timedelta(days=5))
        rep = sf.report(self.root, NOW)
        self.assertTrue(rep["sections"]["en"]["sports"]["stale"])
        # a section with no story at all is stale, not invisible
        self.assertTrue(rep["sections"]["en"]["women"]["stale"])
        self.assertIsNone(rep["sections"]["en"]["women"]["newest"])

    def test_archive_section_is_exempt(self):
        rep = sf.report(self.root, NOW)
        self.assertFalse(rep["sections"]["en"]["archive"]["stale"])
        self.assertIsNone(rep["sections"]["en"]["archive"]["staleAfterHours"])

    def test_originals_ledger_counts(self):
        _write_original(self.root, "story-x", "ar", "women", NOW - timedelta(hours=3))
        rep = sf.report(self.root, NOW)
        self.assertFalse(rep["sections"]["ar"]["women"]["stale"])

    def test_stale_sections_rank_worst_first_and_merge_langs(self):
        _write_archive(self.root, "en", "a1", "sports", NOW - timedelta(hours=30))
        _write_archive(self.root, "ar", "a2", "sports", NOW - timedelta(hours=2))
        order = sf.stale_sections(self.root, NOW)
        cats = [c for c, _ in order]
        # sports is stale (EN edition starved) even though AR is fresh
        self.assertIn("sports", cats)
        # a never-covered section outranks a merely old one
        self.assertLess(cats.index("women"), cats.index("sports"))

    def test_report_stale_list_matches_sections(self):
        rep = sf.report(self.root, NOW)
        for s in rep["stale"]:
            self.assertTrue(rep["sections"][s["lang"]][s["cat"]]["stale"])


if __name__ == "__main__":
    unittest.main()
