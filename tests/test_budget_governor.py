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
            self.assertIn("ahead of pace", reason)

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
        for wf, desk in (("daily-editor.yml", "editor"),
                         ("washington-brief.yml", "washington"),
                         ("weekly-maintenance.yml", "maintenance")):
            text = (ROOT / ".github" / "workflows" / wf).read_text(
                encoding="utf-8")
            self.assertIn(f"budget_ledger.py --check {desk}", text, wf)
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
        self.assertTrue(str(budget_ledger.LEDGER_FILE).endswith(
            "originals/_ledger.json"))
        wf = (ROOT / ".github" / "workflows" / "build.yml").read_text(
            encoding="utf-8")
        self.assertIn("git add originals/ story-archive/", wf)
        # …while the lock and temp files beside it never do.
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("originals/._ledger.json.lock", ignore)
        self.assertIn("originals/._ledger.json.*.tmp", ignore)


if __name__ == "__main__":
    unittest.main()
