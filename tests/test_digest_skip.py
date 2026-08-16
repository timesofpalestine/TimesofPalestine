"""Digest/roundup feed entries never publish as stories (owner report
2026-08-16: a Democracy Now! daily-headlines bundle ran as an Ecuador/CIA
story categorized gaza because Palestine appeared in the bundle's tail).
A feed's skipUrl regex drops such items before the relevance filters."""
import unittest
from datetime import datetime, timezone

import build


def _item(link):
    return {"title": "CIA conducted drone strikes near Ecuador coast",
            "dek": "Bundle of twenty items; Israel and Gaza appear later on.",
            "link": link, "source": "Democracy Now!",
            "source_id": "democracynow", "source_type": "rss",
            "source_url": "https://www.democracynow.org/",
            "date": datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
            "image": None, "media": None,
            "categories": [], "lang": "en"}


class DigestSkipTest(unittest.TestCase):
    FEED = {"id": "democracynow", "name": "Democracy Now!",
            "url": "https://www.democracynow.org/democracynow.rss",
            "filterPalestine": True, "skipUrl": "/headlines"}

    def test_headlines_digest_is_dropped(self):
        it = _item("http://www.democracynow.org/2026/8/14/headlines")
        self.assertIsNone(build.finish_item(it, self.FEED))

    def test_regular_story_link_passes_the_digest_net(self):
        it = _item("https://www.democracynow.org/2026/8/14/gaza_rubble_war_crimes")
        it["title"] = "Israel clears Gaza rubble as rights groups warn of lost evidence"
        out = build.finish_item(it, self.FEED)
        self.assertIsNotNone(out)

    def test_leaked_digest_pids_stay_retracted(self):
        self.assertIn("85db8d3f64", build.RETRACTED_PIDS)
        self.assertIn("b575571cc3", build.RETRACTED_PIDS)


if __name__ == "__main__":
    unittest.main()
