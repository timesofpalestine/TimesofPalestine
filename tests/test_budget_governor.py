"""Budget governor (owner order 2026-09-01: never go over budget again).

August's spend-cap freeze took the whole paper down for six days. The
governor paces the discretionary desks against a monthly budget and stops
everything at a hard ceiling BELOW the provider cap, so the wire always
keeps last-resort headroom. These tests pin the money math, the pacing
rules, the wire's protected status, and the wiring into the desks and
workflows — no agent removes a gate to make a desk run.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import budget_ledger


def _iso(day, hour=12):
    return datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc)


class TempPaths:
    """Point the module at throwaway config/ledger files."""

    def __init__(self, budget=100.0, allocations=None, hard_stop=0.92):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        self.config = base / "budget.json"
        self.ledger = base / "_ledger.json"
        self.config.write_text(json.dumps({
            "monthly_budget_usd": budget,
            "hard_stop_fraction": hard_stop,
            "allocations": allocations or {
                "briefs": 0.12, "investigations": 0.22, "editor": 0.30,
                "washington": 0.24, "maintenance": 0.04},
        }), encoding="utf-8")

    def __enter__(self):
        self._saved = (budget_ledger.CONFIG_FILE, budget_ledger.LEDGER_FILE)
        budget_ledger.CONFIG_FILE = self.config
        budget_ledger.LEDGER_FILE = self.ledger
        return self

    def __exit__(self, *exc):
        budget_ledger.CONFIG_FILE, budget_ledger.LEDGER_FILE = self._saved
        self.dir.cleanup()


class PricingTests(unittest.TestCase):
    def test_haiku_estimate_matches_list_price(self):
        usage = {"input_tokens": 1_000_000, "output_tokens": 200_000,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        self.assertAlmostEqual(
            budget_ledger.estimate_usd("claude-haiku-4-5", usage),
            1.00 + 0.2 * 5.00, places=6)

    def test_unknown_model_uses_most_expensive_rates(self):
        usage = {"input_tokens": 1_000_000, "output_tokens": 0}
        self.assertAlmostEqual(
            budget_ledger.estimate_usd("claude-mystery-9", usage),
            budget_ledger.PRICES["claude-opus-5"]["in"], places=6)

    def test_web_searches_are_billed(self):
        self.assertAlmostEqual(
            budget_ledger.estimate_usd("claude-opus-5", {}, web_searches=100),
            1.00, places=6)

    def test_usage_object_attributes_supported(self):
        class Usage:
            input_tokens = 1_000_000
            output_tokens = 0
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0
        self.assertGreater(
            budget_ledger.estimate_usd("claude-haiku-4-5", Usage()), 0)


class PacingTests(unittest.TestCase):
    def test_desk_under_pace_allowed_over_pace_blocked(self):
        with TempPaths(budget=100.0):
            now = _iso(15)  # roughly mid-month
            allowed, _ = budget_ledger.pace_allows("editor", now=now)
            self.assertTrue(allowed)
            # editor allocation 0.30 × $100 × ~0.48 elapsed ≈ $14.5 paced
            budget_ledger.record("editor", usd=20.0, now=now)
            allowed, reason = budget_ledger.pace_allows("editor", now=now)
            self.assertFalse(allowed)
            self.assertIn("purse empty", reason)

    def test_briefs_protected_until_hard_ceiling(self):
        with TempPaths(budget=100.0, hard_stop=0.92):
            now = _iso(2)
            budget_ledger.record("briefs", usd=80.0, now=now)  # ×1.1 = 88
            allowed, _ = budget_ledger.pace_allows("briefs", now=now)
            self.assertTrue(allowed, "the wire is never paced under the ceiling")
            budget_ledger.record("editor", usd=10.0, now=now)  # total 99 ≥ 92
            allowed, reason = budget_ledger.pace_allows("briefs", now=now)
            self.assertFalse(allowed)
            self.assertIn("hard ceiling", reason)

    def test_ceiling_blocks_every_desk(self):
        with TempPaths(budget=100.0):
            now = _iso(28)
            budget_ledger.record("washington", usd=90.0, now=now)  # ×1.1 = 99
            for desk in budget_ledger.DESKS:
                allowed, _ = budget_ledger.pace_allows(desk, now=now)
                self.assertFalse(allowed, desk)

    def test_safety_factor_applied(self):
        with TempPaths():
            now = _iso(10)
            budget_ledger.record("editor", usd=10.0, now=now)
            ledger = budget_ledger.load_ledger(now)
            self.assertAlmostEqual(ledger["desks"]["editor"], 11.0, places=4)


class LedgerRobustnessTests(unittest.TestCase):
    def test_corrupt_ledger_fails_open_to_empty(self):
        with TempPaths():
            budget_ledger.LEDGER_FILE.write_text("{not json", encoding="utf-8")
            ledger = budget_ledger.load_ledger(_iso(5))
            self.assertEqual(ledger["desks"], {})

    def test_month_rollover_resets_the_count(self):
        with TempPaths():
            budget_ledger.record("editor", usd=50.0,
                                 now=datetime(2026, 8, 30, tzinfo=timezone.utc))
            ledger = budget_ledger.load_ledger(_iso(1))
            self.assertEqual(ledger["desks"], {}, "last month's spend expires")

    def test_broken_config_falls_back_to_floor_not_unlimited(self):
        with TempPaths():
            budget_ledger.CONFIG_FILE.write_text("nope", encoding="utf-8")
            cfg = budget_ledger.load_config()
            self.assertEqual(cfg["budget"], 150.0)

    def test_check_cli_exit_codes(self):
        with TempPaths(budget=100.0):
            self.assertEqual(budget_ledger.main(["--check", "editor"]), 0)
            budget_ledger.record("editor", usd=95.0, now=_iso(2))
            self.assertEqual(budget_ledger.main(["--check", "editor"]), 3)


class LedgerNeverWipesTests(unittest.TestCase):
    """Site scan 2026-09-02: the ledger lost every desk's month-to-date three
    times in its first day. The briefs desk records from a 4-thread pool;
    a reader that caught a half-written file "failed open" to an empty
    ledger and saved it over the month. These pin the cure: locked,
    atomic records; no overwrite of an unreadable ledger; and a three-way
    merge for the persist step's rebase conflicts."""

    def test_concurrent_records_lose_nothing(self):
        import threading
        with TempPaths():
            now = _iso(3)
            budget_ledger.record("investigations", usd=10.0, now=now)
            errors = []

            def worker():
                for _ in range(40):
                    budget_ledger.record("briefs", usd=0.01, now=now)

            def reader():
                # A reader must never see a partial file.
                for _ in range(200):
                    try:
                        json.loads(budget_ledger.LEDGER_FILE.read_text(
                            encoding="utf-8"))
                    except Exception as exc:
                        errors.append(repr(exc))

            threads = [threading.Thread(target=worker) for _ in range(8)]
            threads.append(threading.Thread(target=reader))
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            ledger = budget_ledger.load_ledger(now)
            self.assertEqual(errors, [], "a reader saw a half-written ledger")
            self.assertAlmostEqual(ledger["desks"]["briefs"],
                                   8 * 40 * 0.01 * 1.1, places=4)
            self.assertAlmostEqual(ledger["desks"]["investigations"], 11.0,
                                   places=4, msg="another desk's entry was wiped")

    def test_unreadable_ledger_is_never_overwritten_by_a_record(self):
        with TempPaths():
            budget_ledger.LEDGER_FILE.write_text("{half-written", encoding="utf-8")
            budget_ledger._READ_RETRY_DELAY = 0.0
            try:
                recorded = budget_ledger.record("briefs", usd=1.0, now=_iso(3))
            finally:
                budget_ledger._READ_RETRY_DELAY = 0.05
            self.assertEqual(recorded, 0.0)
            self.assertEqual(budget_ledger.LEDGER_FILE.read_text(encoding="utf-8"),
                             "{half-written", "the corrupt file stays for repair")

    def test_record_leaves_no_temp_files(self):
        with TempPaths():
            budget_ledger.record("editor", usd=1.0, now=_iso(3))
            leftovers = [p.name for p in budget_ledger.LEDGER_FILE.parent.iterdir()
                         if p.name.endswith(".tmp")]
            self.assertEqual(leftovers, [])

    def test_month_rollover_still_starts_fresh(self):
        with TempPaths():
            budget_ledger.record("editor", usd=50.0,
                                 now=datetime(2026, 8, 30, tzinfo=timezone.utc))
            budget_ledger.record("editor", usd=1.0, now=_iso(1))
            ledger = budget_ledger.load_ledger(_iso(1))
            self.assertAlmostEqual(ledger["desks"]["editor"], 1.1, places=4)

    def test_three_way_merge_adds_this_runs_delta_to_upstream(self):
        base = {"month": "2026-09", "desks": {"briefs": 1.0, "investigations": 2.0}}
        upstream = {"month": "2026-09", "desks": {"briefs": 1.3, "washington": 14.2}}
        ours = {"month": "2026-09", "desks": {"briefs": 1.2, "investigations": 3.5}}
        merged = budget_ledger.merge_ledgers(base, upstream, ours)
        self.assertAlmostEqual(merged["desks"]["briefs"], 1.5, places=6)
        self.assertAlmostEqual(merged["desks"]["investigations"], 3.5, places=6)
        self.assertAlmostEqual(merged["desks"]["washington"], 14.2, places=6)

    def test_three_way_merge_newer_month_wins(self):
        upstream = {"month": "2026-09", "desks": {"briefs": 40.0}}
        ours = {"month": "2026-10", "desks": {"briefs": 0.2}}
        self.assertEqual(budget_ledger.merge_ledgers(upstream, upstream, ours)["month"],
                         "2026-10")
        self.assertEqual(budget_ledger.merge_ledgers(None, upstream, None), upstream)

    def test_resolve_conflict_inside_a_real_rebase(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                   "HOME": d, "PATH": __import__("os").environ.get("PATH", "")}

            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, env=env,
                                      capture_output=True, text=True)

            git("init", "-q", "-b", "main")
            (repo / "originals").mkdir()
            ledger = repo / "originals" / "_ledger.json"

            def commit(desks, msg):
                ledger.write_text(json.dumps(
                    {"month": "2026-09", "desks": desks, "updated": None},
                    indent=1) + "\n", encoding="utf-8")
                git("add", "-A")
                git("commit", "-q", "-m", msg)

            commit({"briefs": 1.0, "investigations": 2.0}, "base")
            git("checkout", "-q", "-b", "run")
            commit({"briefs": 1.2, "investigations": 2.0}, "our run")
            git("checkout", "-q", "main")
            commit({"briefs": 1.1, "investigations": 2.0, "washington": 9.0}, "other run")
            git("checkout", "-q", "run")
            rebase = git("rebase", "main")
            self.assertNotEqual(rebase.returncode, 0, "the fixture must conflict")
            saved = (budget_ledger.ROOT, budget_ledger.LEDGER_FILE)
            budget_ledger.ROOT, budget_ledger.LEDGER_FILE = repo, ledger
            try:
                self.assertEqual(budget_ledger.resolve_conflict(), 0)
                merged = json.loads(ledger.read_text(encoding="utf-8"))
            finally:
                budget_ledger.ROOT, budget_ledger.LEDGER_FILE = saved
                git("rebase", "--abort")
            self.assertAlmostEqual(merged["desks"]["briefs"], 1.3, places=6)
            self.assertAlmostEqual(merged["desks"]["investigations"], 2.0, places=6)
            self.assertAlmostEqual(merged["desks"]["washington"], 9.0, places=6)

    def test_build_persist_step_merges_the_ledger(self):
        wf = (ROOT / ".github" / "workflows" / "build.yml").read_text(
            encoding="utf-8")
        self.assertIn("budget_ledger.py --resolve-conflict", wf)


class PurseTests(unittest.TestCase):
    """The purse (owner question 2026-09-02): silos became weights over what
    the wire leaves, each desk saves up in a purse, and the editor runs in
    editions the purse can pay for. These pin the pool math, the tier
    choice, the learned prices and the forecast's honesty."""

    TIERS = {"editor": {
        "full": {"model": "claude-opus-5", "max_turns": 300, "usd": 18,
                 "days": ["mon", "thu"]},
        "light": {"model": "claude-sonnet-5", "max_turns": 90, "usd": 4}}}

    def _cfg(self, tp, tiers=None):
        cfg = json.loads(tp.config.read_text(encoding="utf-8"))
        cfg["tiers"] = tiers or self.TIERS
        tp.config.write_text(json.dumps(cfg), encoding="utf-8")

    def test_wire_projection_reserves_the_wire_first(self):
        with TempPaths(budget=100.0) as tp:
            now = _iso(10)  # ~32% of September elapsed
            budget_ledger.record("briefs", usd=9.0, now=now)  # ×1.1 = 9.9
            cfg = budget_ledger.load_config()
            ledger = budget_ledger.load_ledger(now)
            wire = budget_ledger.wire_projection(cfg, ledger, now)
            self.assertAlmostEqual(
                wire, 9.9 / budget_ledger._elapsed_fraction(now), places=4)
            caps, pool = budget_ledger.desk_caps(cfg, ledger, now)
            self.assertAlmostEqual(pool, 92.0 - wire, places=6)
            # weights: editor .30 of the .80 non-wire total
            self.assertAlmostEqual(caps["editor"], pool * 0.30 / 0.80, places=6)

    def test_pool_empties_when_the_wire_eats_the_budget(self):
        with TempPaths(budget=100.0):
            now = _iso(10)
            budget_ledger.record("briefs", usd=40.0, now=now)  # projects ~146
            allowed, reason = budget_ledger.pace_allows("editor", now=now)
            self.assertFalse(allowed)
            self.assertIn("pool $0.00", reason)

    def test_light_edition_when_the_full_purse_is_short(self):
        with TempPaths(budget=300.0) as tp:
            self._cfg(tp)
            now = datetime(2026, 9, 8, 6, 30, tzinfo=timezone.utc)  # a Tuesday
            name, spec, reason = budget_ledger.choose_tier("editor", now=now)
            self.assertEqual(name, "light", reason)
            self.assertEqual(spec["model"], "claude-sonnet-5")

    def test_full_edition_only_on_its_days_and_when_saved_up(self):
        with TempPaths(budget=600.0) as tp:
            self._cfg(tp)
            tuesday = datetime(2026, 9, 15, 6, 30, tzinfo=timezone.utc)
            name, _, _ = budget_ledger.choose_tier("editor", now=tuesday)
            self.assertEqual(name, "light", "full is a Monday/Thursday edition")
            monday = datetime(2026, 9, 14, 6, 30, tzinfo=timezone.utc)
            name, spec, _ = budget_ledger.choose_tier("editor", now=monday)
            self.assertEqual(name, "full")
            self.assertEqual(spec["max_turns"], 300)

    def test_skip_when_no_purse_can_pay(self):
        with TempPaths(budget=100.0) as tp:
            self._cfg(tp)
            now = _iso(2)
            budget_ledger.record("editor", usd=30.0, now=now)
            name, _, reason = budget_ledger.choose_tier("editor", now=now)
            self.assertIsNone(name)
            self.assertIn("cannot pay any edition", reason)

    def test_tier_price_is_learned_from_recorded_runs(self):
        with TempPaths(budget=300.0) as tp:
            self._cfg(tp)
            now = _iso(3)
            for usd in (2.0, 3.0, 2.5):
                budget_ledger.record("editor", usd=usd, now=now, tier="light")
            cfg = budget_ledger.load_config()
            ledger = budget_ledger.load_ledger(now)
            prices = budget_ledger.tier_prices(cfg, ledger, "editor")
            self.assertAlmostEqual(prices["light"], 2.5 * 1.1, places=4)
            self.assertEqual(prices["full"], 18.0, "no runs yet → configured price")
            self.assertEqual(len(ledger["runs"]["editor"]), 3)

    def test_untracked_spend_charges_the_full_edition_not_the_light(self):
        with TempPaths(budget=300.0) as tp:
            self._cfg(tp)
            now = _iso(5)
            budget_ledger.record("editor", usd=40.0, now=now)  # no tier: restored history
            cfg = budget_ledger.load_config()
            ledger = budget_ledger.load_ledger(now)
            balances = budget_ledger.tier_balances(cfg, ledger, "editor", now)
            self.assertLess(balances["full"], 0)
            self.assertGreater(balances["light"], 0)

    def test_simulation_and_forecast_are_honest(self):
        with TempPaths(budget=150.0) as tp:
            self._cfg(tp)
            now = _iso(2)
            budget_ledger.record("briefs", usd=7.0, now=now)  # a wire-sized wire
            cfg = budget_ledger.load_config()
            ledger = budget_ledger.load_ledger(now)
            counts, cap = budget_ledger.simulate_month(cfg, ledger, "editor", now)
            self.assertEqual(sum(counts.values()), 0, "the wire leaves nothing")
            normal, cap400 = budget_ledger.simulate_month(
                cfg, ledger, "editor", now, budget=400, fresh=True)
            self.assertGreater(normal["light"], 5)
            self.assertGreaterEqual(normal["full"], 1)
            text = budget_ledger.forecast(now=now)
            self.assertIn("discretionary pool", text)
            self.assertIn("$400:", text)
            self.assertIn("editor", text)

    def test_tags_and_runs_survive_the_three_way_merge(self):
        base = {"month": "2026-09", "desks": {"briefs": 1.0}, "tags": {"briefs:judge": 0.4},
                "runs": {}}
        upstream = {"month": "2026-09", "desks": {"briefs": 1.2}, "tags": {"briefs:judge": 0.5},
                    "runs": {"editor": [{"ts": "a", "usd": 3.0, "tier": "light"}]}}
        ours = {"month": "2026-09", "desks": {"briefs": 1.3}, "tags": {"briefs:judge": 0.7},
                "runs": {"editor": [{"ts": "b", "usd": 18.0, "tier": "full"}]}}
        merged = budget_ledger.merge_ledgers(base, upstream, ours)
        self.assertAlmostEqual(merged["tags"]["briefs:judge"], 0.8, places=6)
        self.assertEqual(len(merged["runs"]["editor"]), 2)

    def test_tier_cli_emits_workflow_outputs(self):
        with TempPaths(budget=600.0) as tp:
            self._cfg(tp)
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = budget_ledger.main(["--tier", "editor"])
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("run=yes", out)
            self.assertRegex(out, r"tier=(full|light)")
            self.assertIn("model=claude-", out)
            self.assertIn("max_turns=", out)

    def test_editor_workflow_is_tier_driven(self):
        text = (ROOT / ".github" / "workflows" / "daily-editor.yml").read_text(
            encoding="utf-8")
        self.assertIn("budget_ledger.py --tier editor", text)
        self.assertIn("steps.budget.outputs.model", text)
        self.assertIn("steps.budget.outputs.max_turns", text)
        self.assertIn("TODAY'S EDITION TIER", text)
        self.assertIn('--tier "${{ steps.budget.outputs.tier', text)

    def test_wire_calls_are_tagged(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('tag="judge"', src)
        self.assertIn('tag="rewrite"', src)

    def test_repo_tiers_are_sane(self):
        cfg = json.loads((ROOT / "editorial" / "budget.json").read_text(
            encoding="utf-8"))
        editor = cfg["tiers"]["editor"]
        self.assertEqual(list(editor), ["full", "light"], "highest tier first")
        for spec in editor.values():
            self.assertIn(spec["model"], budget_ledger.PRICES)
            self.assertGreater(spec["usd"], 0)
            self.assertGreater(spec["max_turns"], 0)


class WiringTests(unittest.TestCase):
    """The gates stay wired into the desks and workflows."""

    def test_repo_budget_config_is_sane(self):
        cfg = json.loads((ROOT / "editorial" / "budget.json").read_text(
            encoding="utf-8"))
        self.assertGreater(cfg["monthly_budget_usd"], 0)
        self.assertLessEqual(cfg["hard_stop_fraction"], 1.0)
        self.assertLessEqual(sum(cfg["allocations"].values()), 1.0,
                             "allocations must leave the reserve intact")
        for desk in budget_ledger.DESKS:
            self.assertIn(desk, cfg["allocations"])

    def test_workflows_gate_and_record(self):
        for wf, desk, gate in (("daily-editor.yml", "editor", "--tier"),
                               ("washington-brief.yml", "washington", "--check"),
                               ("weekly-maintenance.yml", "maintenance", "--check")):
            text = (ROOT / ".github" / "workflows" / wf).read_text(
                encoding="utf-8")
            self.assertIn(f"budget_ledger.py {gate} {desk}", text, wf)
            self.assertIn(f"--record-usd {desk}", text, wf)
            # Site scan 2026-09-02: the Claude action strips git credentials
            # on exit and the editor's record pushes all failed auth — the
            # record step re-authenticates with the workflow token itself.
            record = text.split("Record API spend in the ledger", 1)[1]
            self.assertIn("x-access-token:${GH_TOKEN}@github.com", record, wf)
            self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", record, wf)

    def test_investigations_desk_carries_the_pace_gate(self):
        src = (ROOT / "originals_gen.py").read_text(encoding="utf-8")
        self.assertIn('pace_allows("investigations")', src)

    def test_briefs_desk_records_spend(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count('budget_ledger.record("briefs"'), 2,
                                "brief writer AND duplicate judge both record")

    def test_ledger_rides_the_persist_commit(self):
        # originals/_ledger.json must be inside the persist step's `git add
        # originals/` path and must not be gitignored.
        # (the module attribute may be redirected to a temp file by other
        # test modules in this process — pin the shipped default instead)
        src = (ROOT / "budget_ledger.py").read_text(encoding="utf-8")
        self.assertIn('LEDGER_FILE = ROOT / "originals" / "_ledger.json"', src)
        wf = (ROOT / ".github" / "workflows" / "build.yml").read_text(
            encoding="utf-8")
        self.assertIn("git add originals/ story-archive/", wf)
        # …while the lock and temp files beside it never do.
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("originals/._ledger.json.lock", ignore)
        self.assertIn("originals/._ledger.json.*.tmp", ignore)


if __name__ == "__main__":
    unittest.main()
