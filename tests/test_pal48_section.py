"""Palestinians in Israel — the pal48 section is wired end to end.

Owner directive 2026-08-21: daily coverage of the two million Palestinian
citizens of Israel as a first-class section. These tests pin the wiring —
category registered everywhere, routing net catching the beat's signals
without stealing other sections' leads, and the supply lines present.
"""
import json
import unittest

import build
import section_freshness


class WiringTests(unittest.TestCase):
    def test_category_registered_everywhere(self):
        self.assertIn("pal48", build.ORIGINAL_CATEGORIES)
        self.assertIn("pal48", section_freshness.SECTIONS)
        self.assertIn("pal48", build.FOCUS_SECTIONS)
        self.assertIn(("pal48", build.PAL48_RX),
                      [(k, r) for k, r in build.CATEGORY_RULES if k == "pal48"])

    def test_section_named_in_both_editions(self):
        for lang in ("en", "ar"):
            self.assertIn("pal48", build.STR[lang]["sections"])

    def test_daily_freshness_target(self):
        # No override → the default 24h target: daily coverage, owner order.
        self.assertNotIn("pal48", section_freshness.STALE_OVERRIDES)

    def test_supply_lines_exist(self):
        feeds = json.load(open("feeds.json", encoding="utf-8"))
        pinned = [e for lst in feeds.values() for e in lst
                  if e.get("category") == "pal48"]
        self.assertGreaterEqual(len(pinned), 2, "pal48 radar feeds missing")
        topics = json.load(open("topics.json", encoding="utf-8"))
        items = topics["topics"] if isinstance(topics, dict) else topics
        self.assertTrue(any(t.get("cat") == "pal48" for t in items),
                        "no pal48 keeper topics queued")


class RoutingTests(unittest.TestCase):
    def test_beat_signals_route_in(self):
        for title in (
                "Police solve few killings as Arab citizens of Israel bury another victim",
                "Israel demolishes homes in unrecognized villages of the Naqab Bedouin",
                "Higher Follow-Up Committee calls a general strike in Umm al-Fahm",
                "مسيرة في سخنين ضد الجريمة في المجتمع العربي",
                "لجنة المتابعة العليا تعلن الإضراب في أراضي الـ48",
                "فلسطينيو الداخل يحيون ذكرى هبة القدس والأقصى"):
            with self.subTest(title=title):
                self.assertIsNotNone(build.PAL48_RX.search(title), title)

    def test_other_sections_keep_their_leads(self):
        # Gaza, Ramallah (al-Tira!), and plain West Bank items stay out.
        for title in (
                "Israeli strikes kill five at Gaza's port",
                "الاحتلال يعتقل طبيبة من حي الطيرة في رام الله",
                "Settlers raid Qusra for the twelfth day"):
            with self.subTest(title=title):
                self.assertIsNone(build.PAL48_RX.search(title), title)


if __name__ == "__main__":
    unittest.main()
