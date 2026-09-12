"""Model policy — the cheapest model that can do the job (owner order 2026-09-12).

The owner's order: the story rewriting runs on a cheaper Claude model to save
money and credits, and Fable 5.1 is only for work that needs extensive
research. These tests keep the tiers where the charter puts them, so no future
change quietly moves the wire — 900-odd model calls a day — onto a bigger
model, or pins Fable on a schedule.

Tiers (list price per million tokens):
  wire rewriting + duplicate judge   claude-haiku-4-5   $1 / $5
  routine cycles                     claude-sonnet-5    $2 / $10
  research + full editorial mandate  claude-opus-5      $5 / $25
  extensive research, by hand only   claude-fable-5-1   $10 / $50
"""
import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("TOP_OFFLINE", "1")

import budget_ledger  # noqa: E402
import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

CHEAPEST = "claude-haiku-4-5"
ROUTINE = "claude-sonnet-5"
RESEARCH = "claude-opus-5"
BY_HAND_ONLY = "claude-fable-5-1"


def _price(model):
    return budget_ledger.PRICES[model]


class TierTests(unittest.TestCase):
    def test_the_wire_runs_on_the_cheapest_model_priced(self):
        self.assertEqual(build.BRIEFS_MODEL, CHEAPEST)
        cheapest = min(budget_ledger.PRICES, key=lambda m: budget_ledger.PRICES[m]["in"])
        self.assertEqual(build.BRIEFS_MODEL, cheapest,
                         "the rewriting desk must sit on the cheapest priced model")

    def test_the_duplicate_judge_rides_the_wire_model(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        judge = src.split("def _duplicate_verdict", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("claude-", judge,
                         "the judge must not pin its own model — it uses BRIEFS_MODEL")
        self.assertIn("BRIEFS_MODEL", judge)

    def test_research_desk_stays_on_the_research_tier(self):
        src = (ROOT / "originals_gen.py").read_text(encoding="utf-8")
        self.assertIn(f'MODEL = "{RESEARCH}"', src)

    def test_tiers_are_ordered_cheapest_to_dearest(self):
        rows = [_price(m)["in"] for m in (CHEAPEST, ROUTINE, RESEARCH, BY_HAND_ONLY)]
        self.assertEqual(rows, sorted(rows))
        self.assertEqual(rows, [1.00, 2.00, 5.00, 10.00], "list prices drifted")


class LedgerPriceTests(unittest.TestCase):
    def test_sonnet_5_is_priced_at_its_own_rate(self):
        # Until 2026-09-12 this row carried Sonnet 4.6's $3/$15, so every
        # light edition was costed 50% high and paced harder than the money
        # required.
        self.assertEqual(_price(ROUTINE)["in"], 2.00)
        self.assertEqual(_price(ROUTINE)["out"], 10.00)

    def test_cache_rates_are_a_tenth_of_input(self):
        for model, row in budget_ledger.PRICES.items():
            if model == BY_HAND_ONLY:
                continue  # Fable's cache read is a published exception
            self.assertAlmostEqual(row["cache_read"], row["in"] / 10, places=4,
                                   msg=f"{model} cache_read")

    def test_unknown_models_cost_the_most_expensive_row(self):
        row = budget_ledger._price_row("claude-something-unreleased")
        dearest = max(budget_ledger.PRICES.values(), key=lambda r: r["in"])
        self.assertEqual(row, dearest,
                         "an unpriced model must over-count, never under-count")


class LearnedPriceTests(unittest.TestCase):
    """A learned price belongs to a model, not to a tier name."""

    CFG = {"tiers": {"editor": {
        "full": {"model": "claude-opus-5", "usd": 18, "max_turns": 300},
        "light": {"model": ROUTINE, "usd": 6, "max_turns": 200}}}}

    def test_runs_on_the_current_model_set_the_price(self):
        ledger = {"runs": {"editor": [
            {"usd": 20.0, "tier": "full", "model": "claude-opus-5"},
            {"usd": 22.0, "tier": "full", "model": "claude-opus-5"}]}}
        prices = budget_ledger.tier_prices(self.CFG, ledger, "editor")
        self.assertAlmostEqual(prices["full"], 21.0)

    def test_a_model_switch_falls_back_to_the_seed(self):
        # The editor's purse reached -$57.75 in September because the full
        # edition's $18.51 estimate — learned from two Opus runs — kept
        # authorising runs after the edition moved to a model priced at twice
        # the tokens. The yardstick must expire with the model.
        ledger = {"runs": {"editor": [
            {"usd": 35.0, "tier": "full", "model": BY_HAND_ONLY},
            {"usd": 37.0, "tier": "full", "model": BY_HAND_ONLY}]}}
        prices = budget_ledger.tier_prices(self.CFG, ledger, "editor")
        self.assertEqual(prices["full"], 18.0, "another model's runs must not price this one")

    def test_legacy_records_without_a_model_are_not_counted(self):
        ledger = {"runs": {"editor": [
            {"usd": 30.0, "tier": "full"}, {"usd": 32.0, "tier": "full"}]}}
        prices = budget_ledger.tier_prices(self.CFG, ledger, "editor")
        self.assertEqual(prices["full"], 18.0)

    def test_a_recorded_run_carries_its_model(self):
        src = (ROOT / "budget_ledger.py").read_text(encoding="utf-8")
        block = src.split('runs = ledger.setdefault("runs"', 1)[1][:600]
        self.assertIn('entry["model"] = model', block)

    def test_the_light_seed_matches_what_light_runs_cost(self):
        # Dropping the model-less history must not change today's pacing:
        # the recorded Sonnet runs ran 2.21, 6.02 and 5.82.
        cfg = json.loads((ROOT / "editorial" / "budget.json").read_text(encoding="utf-8"))
        self.assertLessEqual(cfg["tiers"]["editor"]["light"]["usd"], 7)


class ScheduleTests(unittest.TestCase):
    def test_no_scheduled_workflow_pins_fable(self):
        for wf in sorted(WORKFLOWS.glob("*.yml")):
            text = wf.read_text(encoding="utf-8")
            self.assertNotIn(BY_HAND_ONLY, text,
                             f"{wf.name} pins Fable 5.1 — owner-dispatched work only")

    def test_no_tier_pins_fable(self):
        cfg = json.loads((ROOT / "editorial" / "budget.json").read_text(encoding="utf-8"))
        for desk, tiers in cfg.get("tiers", {}).items():
            for name, spec in tiers.items():
                self.assertNotEqual(spec["model"], BY_HAND_ONLY,
                                    f"{desk}/{name} pins Fable 5.1")

    def test_editor_editions_sit_on_their_tiers(self):
        cfg = json.loads((ROOT / "editorial" / "budget.json").read_text(encoding="utf-8"))
        editor = cfg["tiers"]["editor"]
        self.assertEqual(editor["full"]["model"], RESEARCH)
        self.assertEqual(editor["light"]["model"], ROUTINE)

    def test_the_routine_sweep_runs_on_the_routine_tier(self):
        text = (WORKFLOWS / "weekly-maintenance.yml").read_text(encoding="utf-8")
        self.assertIn(f"--model {ROUTINE}", text)

    def test_research_franchises_stay_on_the_research_tier(self):
        for name in ("washington-brief.yml", "diaspora-dispatch.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn(f"--model {RESEARCH}", text, name)


class RetryEconomyTests(unittest.TestCase):
    """The editor pass rescues copy; it never chases a word count."""

    def test_short_copy_is_flagged_at_the_publish_floor(self):
        floor = build.MIN_BRIEF_WORDS
        just_over = " ".join(["word"] * (floor + 5)) + ".\n\nSecond paragraph here."
        self.assertEqual(build.structure_issues(just_over, "en"), [],
                         "copy above the floor must not buy a second model call")
        under = " ".join(["word"] * (floor - 5)) + ".\n\nSecond paragraph here."
        self.assertTrue(any("publish floor" in i for i in build.structure_issues(under, "en")))

    def test_a_median_length_brief_costs_one_call(self):
        # Measured 2026-09-12: the median published brief runs 76 words and
        # 81% land between 60 and 89. Under the old 90-word gate every one of
        # them bought a rewrite that came back the same length.
        median = (" ".join(["word"] * 40) + ".\n\n" + " ".join(["word"] * 36) + ".")
        self.assertEqual(len(median.split()), 76)  # the measured median
        self.assertEqual(build.structure_issues(median, "en"), [])

    def test_real_defects_still_buy_the_retry(self):
        one_block = " ".join(["word"] * 120) + "."
        issues = build.structure_issues(one_block, "en")
        self.assertTrue(any("single-block" in i for i in issues))
        wall = " ".join(["word"] * 100) + ".\n\n" + " ".join(["word"] * 90) + "."
        self.assertTrue(any("runs past" in i for i in build.structure_issues(wall, "en")))

    def test_both_editions_ask_for_the_same_length(self):
        self.assertIn("90-150", build.BRIEF_SYSTEM["en"])
        self.assertIn("90-150", build.BRIEF_SYSTEM["ar"])
        for lang in ("en", "ar"):
            self.assertNotIn("100-170", build.BRIEF_SYSTEM[lang])

    def test_caching_the_wire_prompt_would_be_a_no_op(self):
        # Haiku 4.5 will not cache a prefix under 4,096 tokens; the briefs
        # system prompt is far shorter, so a cache_control marker here would
        # silently do nothing. Recorded so nobody "optimizes" it and wonders
        # why cache_read_input_tokens stays at zero.
        for lang in ("en", "ar"):
            self.assertLess(len(build.BRIEF_SYSTEM[lang]) / 3.6, 4096)
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        desk = src.split("def write_brief", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("cache_control", desk)


class CharterTests(unittest.TestCase):
    def test_both_charters_carry_the_policy(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("MODEL POLICY", text, name)
            self.assertIn(CHEAPEST, text, name)
            block = text.split("MODEL POLICY", 1)[1].split("\n\n1", 1)[0]
            self.assertIn("reserved for extensive research", block, name)

    def test_the_two_charters_stay_identical(self):
        self.assertEqual((ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
                         (ROOT / "AGENTS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
