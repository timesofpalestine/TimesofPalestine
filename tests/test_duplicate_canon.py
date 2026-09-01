"""Duplicate canon (owner sweep 2026-09-01): one incident, one article —
across builds and on the archive layer, not just inside one build.

The audit that ordered this found identical-headline twins in the archive
(worst in Arabic, where prolific Telegram feeds produced same-day doubles):
the lexical nets and the AI judge fold pairs correctly WITHIN a build, but
an unstable cluster-representative choice let equal twins alternate between
builds — archiving both — and the permalink-permanence layer then surfaced
the loser beside the winner in search, the topic hubs and archive-filled
sections. These tests pin the two fixes: a stable, archived-first canon,
and discovery-surface suppression that never touches the permalink pages.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build


def item(pid, title, score=10.0, lang="en", **kw):
    base = {"pid": pid, "title": title, "score": score, "lang": lang,
            "source_id": "wire", "partner": False, "original": False,
            "date": datetime(2026, 9, 1, 12, tzinfo=timezone.utc)}
    base.update(kw)
    return base


class CanonRankTests(unittest.TestCase):
    def test_already_archived_copy_outranks_equal_twin(self):
        a = item("aaaaaaaaaa", "Israeli forces seize tractor in Jordan Valley")
        b = item("bbbbbbbbbb", "Israeli forces seize tractor in Jordan Valley")
        with mock.patch.object(build, "_already_archived",
                               side_effect=lambda i: i["pid"] == "bbbbbbbbbb"):
            ranked = sorted([a, b], key=build._dedupe_rank_key, reverse=True)
        self.assertEqual(ranked[0]["pid"], "bbbbbbbbbb",
                         "the copy readers already hold the link to wins")

    def test_equal_twins_rank_deterministically(self):
        a = item("aaaaaaaaaa", "T")
        b = item("bbbbbbbbbb", "T")
        with mock.patch.object(build, "_already_archived", return_value=False):
            r1 = sorted([a, b], key=build._dedupe_rank_key, reverse=True)
            r2 = sorted([b, a], key=build._dedupe_rank_key, reverse=True)
        self.assertEqual([i["pid"] for i in r1], [i["pid"] for i in r2],
                         "input order must never decide the representative")

    def test_original_still_outranks_archived_wire(self):
        orig = item("aaaaaaaaaa", "T", source_id="top-original", original=True)
        wire = item("bbbbbbbbbb", "T")
        with mock.patch.object(build, "_already_archived",
                               side_effect=lambda i: not i["original"]):
            ranked = sorted([orig, wire], key=build._dedupe_rank_key,
                            reverse=True)
        self.assertTrue(ranked[0]["original"])


class ArchiveSuppressionTests(unittest.TestCase):
    def _now(self):
        return datetime(2026, 9, 1, 12, tzinfo=timezone.utc)

    def test_archived_twin_of_live_story_is_suppressed(self):
        live = [item("live111111", "Israeli forces demolish two buildings in Birzeit")]
        arch = [dict(item("arch111111",
                          "Israeli forces demolish two buildings in Birzeit",
                          date=self._now() - timedelta(hours=10)))]
        n = build.mark_archived_duplicates(live, arch, now=self._now())
        self.assertEqual(n, 1)
        self.assertTrue(arch[0].get("dup_suppressed"))

    def test_rolling_number_update_counts_as_the_same_headline(self):
        live = [item("live111111", "Israeli strikes kill 15 in Gaza City")]
        arch = [dict(item("arch111111", "Israeli strikes kill 12 in Gaza City",
                          date=self._now() - timedelta(hours=30)))]
        self.assertEqual(
            build.mark_archived_duplicates(live, arch, now=self._now()), 1)

    def test_archived_twins_keep_the_oldest_copy(self):
        old = dict(item("arch1aaaaa", "سلطات الاحتلال تبعد شاباً مقدسياً عن الطور 15 يوماً",
                        lang="ar", date=self._now() - timedelta(hours=9)))
        new = dict(item("arch2bbbbb", "سلطات الاحتلال تبعد شاباً مقدسياً عن الطور 15 يوماً",
                        lang="ar", date=self._now() - timedelta(hours=5)))
        n = build.mark_archived_duplicates([], [new, old], now=self._now())
        self.assertEqual(n, 1)
        self.assertTrue(new.get("dup_suppressed"))
        self.assertFalse(old.get("dup_suppressed"))

    def test_distinct_stories_survive(self):
        live = [item("live111111", "Gaza fuel authority receives five trucks of cooking gas")]
        arch = [dict(item("arch111111",
                          "Israel withholds six billion dollars in clearance revenue",
                          date=self._now() - timedelta(hours=20)))]
        self.assertEqual(
            build.mark_archived_duplicates(live, arch, now=self._now()), 0)
        self.assertFalse(arch[0].get("dup_suppressed"))

    def test_exact_repeat_has_no_time_window(self):
        old = dict(item("arch1aaaaa", "Army closes the Container checkpoint",
                        date=self._now() - timedelta(days=40)))
        new = dict(item("arch2bbbbb", "Army closes the Container checkpoint",
                        date=self._now() - timedelta(days=2)))
        n = build.mark_archived_duplicates([], [old, new], now=self._now())
        self.assertEqual(n, 1)
        self.assertTrue(new.get("dup_suppressed"))

    def test_suppression_never_removes_records_from_the_pool(self):
        # Permalink permanence: the flag gates listings only — the caller's
        # pool keeps every record so every page still renders.
        arch = [dict(item("arch1aaaaa", "T", date=self._now())),
                dict(item("arch2bbbbb", "T", date=self._now()))]
        build.mark_archived_duplicates([], arch, now=self._now())
        self.assertEqual(len(arch), 2)


class WiringTests(unittest.TestCase):
    def test_surfaces_filter_suppressed_records(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("mark_archived_duplicates(list(items), _arch_pool)", src)
        self.assertGreaterEqual(src.count('dup_suppressed'), 4,
                                "the setter plus the hub, search and section "
                                "listing gates must all be present")


if __name__ == "__main__":
    unittest.main()
