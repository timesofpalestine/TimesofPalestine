"""Originals first (owner order 2026-09-12).

"We are not producing enough new content. We're just aggregating, and I don't
think that's enough."

The diagnosis was arithmetic. Output ran 16-20 originals a day through August
and collapsed to 1-3 in September, on the day the budget purse ran dry: the
desks that WRITE could not afford to run, so only the wire was left. Measured
over September against `originals/_ledger.json`:

  light edition      11-18 bilingual originals for ~$6   $0.41 a story
  investigations     one deep bilingual report            $2.07 a story
  full edition       ~21 originals for ~$19               $1.76 a story
  no editor run      1.8 originals

So the light edition is the cheapest originals engine by five times, the
weights fund it first, and the full edition runs weekly. These tests keep
that shape, and keep the forecast honest about what the owner's knob buys.
"""
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TOP_OFFLINE", "1")

import budget_ledger  # noqa: E402
import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "editorial" / "budget.json").read_text(encoding="utf-8"))


class AllocationTests(unittest.TestCase):
    def test_the_editor_holds_the_largest_share_of_the_pool(self):
        alloc = CFG["allocations"]
        discretionary = {d: w for d, w in alloc.items()
                         if d != budget_ledger.PROTECTED_DESK}
        top = max(discretionary, key=discretionary.get)
        self.assertEqual(top, "editor",
                         "the cheapest originals engine is funded first")
        self.assertGreaterEqual(discretionary["editor"] / sum(discretionary.values()), 0.5)

    def test_weights_still_leave_the_wire_its_reserve(self):
        self.assertAlmostEqual(sum(CFG["allocations"].values()), 1.0, places=6)

    def test_every_desk_can_still_afford_its_cadence(self):
        # No desk may be zeroed to feed the editor: each keeps a real share.
        for desk, weight in CFG["allocations"].items():
            self.assertGreater(weight, 0.02, desk)

    def test_the_full_edition_runs_weekly(self):
        self.assertEqual(CFG["tiers"]["editor"]["full"]["days"], ["mon"])

    def test_the_light_edition_has_no_day_restriction(self):
        self.assertNotIn("days", CFG["tiers"]["editor"]["light"],
                         "the light edition runs any day the purse allows")


class ForecastTests(unittest.TestCase):
    """The owner turns one knob; the forecast says what it buys in stories."""

    NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)

    def test_an_original_is_priced_from_the_desks_that_write(self):
        ledger = {"month": "2026-09", "desks": {"briefs": 50.0, "editor": 40.0,
                                                "investigations": 20.0}, "runs": {}}
        unit = budget_ledger.cost_per_original(
            budget_ledger.load_config(), ledger, self.NOW)
        self.assertIsNotNone(unit)
        filed = budget_ledger.originals_filed("2026-09")
        # The wire rewrites other people's reporting — it is not an original.
        self.assertAlmostEqual(unit, 60.0 / filed, places=6)

    def test_a_thin_month_prices_nothing(self):
        ledger = {"month": "2026-01", "desks": {"editor": 5.0}, "runs": {}}
        self.assertIsNone(budget_ledger.cost_per_original(
            budget_ledger.load_config(), ledger, self.NOW))

    LEDGER = {"month": "2026-09", "tags": {}, "runs": {},
              "desks": {"briefs": 52.71, "editor": 92.78,
                        "investigations": 26.88, "washington": 27.71}}

    def test_a_bigger_budget_buys_more_originals(self):
        cfg = budget_ledger.load_config()
        small = budget_ledger.originals_forecast(cfg, self.LEDGER, self.NOW, 400)
        large = budget_ledger.originals_forecast(cfg, self.LEDGER, self.NOW, 800)
        self.assertIsNotNone(small)
        self.assertGreater(large[1], small[1])
        self.assertGreater(small[1], 0)

    def test_the_forecast_prints_originals_per_day(self):
        # Hermetic: another suite leaves the ledger path redirected, and the
        # line only prints once a month has originals to price.
        real = budget_ledger.load_ledger
        budget_ledger.load_ledger = lambda *a, **k: dict(self.LEDGER)
        try:
            out = budget_ledger.forecast(self.NOW)
        finally:
            budget_ledger.load_ledger = real
        self.assertIn("originals/day", out)

    def test_originals_are_counted_from_their_dateline(self):
        self.assertGreater(budget_ledger.originals_filed("2026-09"), 0)
        self.assertEqual(budget_ledger.originals_filed("1999-01"), 0)


class IllustrationTierTests(unittest.TestCase):
    """Drawing to a spec is routine work; research is not."""

    def test_the_lede_graphic_runs_on_the_routine_tier(self):
        src = (ROOT / "originals_gen.py").read_text(encoding="utf-8")
        self.assertIn('ILLUSTRATION_MODEL = "claude-sonnet-5"', src)
        self.assertIn('ILLUSTRATION_EFFORT = "low"', src)
        block = src.split("def _make_illustration", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("model=ILLUSTRATION_MODEL", block)
        self.assertIn("effort=ILLUSTRATION_EFFORT", block)

    def test_research_and_arabic_stay_on_the_research_tier(self):
        src = (ROOT / "originals_gen.py").read_text(encoding="utf-8")
        self.assertIn('MODEL = "claude-opus-5"', src)
        for marker in ("DESK_SYSTEM, [{", "ARABIC_SYSTEM, [{"):
            call = src.split(marker, 1)[1][:200]
            self.assertNotIn("model=", call, f"{marker} must use the research tier")
            self.assertNotIn("effort=", call, f"{marker} effort stays at the default")

    def test_the_recorded_spend_names_the_model_that_ran(self):
        src = (ROOT / "originals_gen.py").read_text(encoding="utf-8")
        self.assertIn("budget_ledger.record(desk, model, resp.usage", src)


class ReferenceDataTests(unittest.TestCase):
    """Hand-maintained figures age silently unless the build says so."""

    def test_a_stale_ledger_is_announced(self):
        built_at = datetime(2026, 9, 12, tzinfo=timezone.utc)
        rows = build.reference_data_age(built_at)
        self.assertTrue(rows, "no reference data configured")
        labels = {label for label, *_ in rows}
        self.assertTrue(any("prisoners" in l for l in labels))
        self.assertTrue(any("Al-Quds" in l for l in labels))

    def test_the_stalest_file_sorts_first(self):
        entries = (("editorial/prisoners.json", "asOf", 14, "prisoners"),
                   ("editorial/markets.json", "lastChecked", 4, "markets"))
        rows = build.reference_data_age(
            datetime(2026, 9, 12, tzinfo=timezone.utc), entries)
        overshoot = [age - limit for _l, age, limit, _s in rows]
        self.assertEqual(overshoot, sorted(overshoot, reverse=True))

    def test_an_unreadable_file_never_breaks_the_build(self):
        rows = build.reference_data_age(
            datetime(2026, 9, 12, tzinfo=timezone.utc),
            (("editorial/does-not-exist.json", "asOf", 1, "ghost"),))
        self.assertEqual(rows, [])
        build.check_reference_data(datetime(2026, 9, 12, tzinfo=timezone.utc))

    def test_the_build_runs_the_check(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("check_reference_data(built_at)", src)


class EditorBriefTests(unittest.TestCase):
    def test_the_light_edition_is_told_it_is_the_originals_engine(self):
        wf = (ROOT / ".github" / "workflows" / "daily-editor.yml").read_text(encoding="utf-8")
        self.assertIn("ORIGINALS ENGINE", wf)
        self.assertIn("$0.41", wf)
        self.assertIn("REFERENCE DATA", wf)
        self.assertIn("Never invent a figure", wf)

    def test_both_charters_carry_the_order(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("ORIGINALS FIRST", text, name)
            self.assertIn("Never buy volume with padding", text, name)
        self.assertEqual((ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
                         (ROOT / "AGENTS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
