"""Health & Healing response ledger (owner order 2026-09-06): every outbreak
signal the watch raises is matched against the section's own originals, and
an unanswered signal is the desk's next assignment."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import outbreak_watch  # noqa: E402

NOW = datetime(2026, 9, 6, 21, tzinfo=timezone.utc)


def wire(title, dek="", lang="en", days_ago=1):
    from datetime import timedelta
    return {"title": title, "dek": dek, "lang": lang, "pid": "w" + str(abs(hash(title)) % 10**8),
            "date": NOW - timedelta(days=days_ago), "source_id": "example", "cat": "gaza"}


def original(title, body, days_ago=1, cat="health"):
    from datetime import timedelta
    return {"title": title, "dek": "", "body": body, "lang": "en", "pid": "o" + str(abs(hash(title)) % 10**8),
            "date": NOW - timedelta(days=days_ago), "source_id": "top-original", "cat": cat}


class ResponseLedgerTest(unittest.TestCase):
    def test_signal_without_a_health_original_is_unanswered(self):
        items = [wire("Acute watery diarrhoea cases nearly double in Gaza, WHO says",
                      "Water contamination rose to 18 percent.")]
        events = outbreak_watch.watch_events(items, now=NOW)
        self.assertTrue(events, "the watch must raise a diarrhoea signal")
        ledger = outbreak_watch.response_ledger(events, items, now=NOW)
        self.assertEqual(len(ledger["unanswered"]), 1)
        self.assertEqual(ledger["unanswered"][0]["key"], "diarrhoea")
        self.assertIsNone(ledger["signals"][0]["response"])

    def test_health_original_naming_the_disease_answers_the_signal(self):
        items = [wire("Acute watery diarrhoea cases nearly double in Gaza, WHO says",
                      "Water contamination rose to 18 percent."),
                 original("What families can do as diarrhoea spreads before the rains",
                          "Oral rehydration salts, zinc and chlorinated water against acute watery diarrhoea.")]
        events = outbreak_watch.watch_events(items, now=NOW)
        ledger = outbreak_watch.response_ledger(events, items, now=NOW)
        self.assertEqual(ledger["unanswered"], [])
        self.assertEqual(ledger["signals"][0]["response"]["title"],
                         "What families can do as diarrhoea spreads before the rains")

    def test_a_response_outside_the_window_or_section_does_not_count(self):
        items = [wire("Scabies outbreak spreads through Gaza tents, UNRWA says", "Cases rise."),
                 original("Treating scabies in the camps", "permethrin for scabies", days_ago=30),
                 original("Gaza strike: scabies clinic hit", "scabies", cat="gaza")]
        events = outbreak_watch.watch_events(items, now=NOW)
        ledger = outbreak_watch.response_ledger(events, items, now=NOW)
        self.assertEqual(len(ledger["unanswered"]), 1)


if __name__ == "__main__":
    unittest.main()
