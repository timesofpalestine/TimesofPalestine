"""The desk must never skip a stale section because its queue ran dry.

Regression for 2026-08-16: humans sat 45h stale while its only topic,
written 4 days earlier, hid under the 7-day recycle guard — _pick_topic
fell through to the rotation and the desk filed elsewhere. The fix is a
second pass: a stale section's least-recent topic recycles once 48h have
passed, before the global rotation is ever consulted."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import originals_gen


def _iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


TOPICS = [
    {"id": "humans-only", "cat": "humans"},
    {"id": "politics-fresh", "cat": "politics"},
]


class PickTopicRecycleTest(unittest.TestCase):
    def _pick(self, stale, done):
        with mock.patch("section_freshness.stale_sections", return_value=stale):
            return originals_gen._pick_topic(TOPICS, {"done": done})

    def test_stale_section_recycles_after_48h_before_rotation(self):
        # humans stale, its lone topic written 3 days ago (<7d, >48h):
        # the old guard skipped it; the second pass must return it.
        picked = self._pick([("humans", 45.0)], {"humans-only": _iso(72)})
        self.assertEqual(picked["id"], "humans-only")

    def test_recycle_floor_holds_under_48h(self):
        # Written yesterday: too fresh to recycle — rotation may serve
        # another section instead, but never a same-day repeat.
        picked = self._pick([("humans", 45.0)], {"humans-only": _iso(24)})
        self.assertNotEqual(picked["id"], "humans-only")

    def test_unwritten_topic_still_wins_first(self):
        picked = self._pick(
            [("politics", 30.0)], {"humans-only": _iso(72)})
        self.assertEqual(picked["id"], "politics-fresh")


if __name__ == "__main__":
    unittest.main()
