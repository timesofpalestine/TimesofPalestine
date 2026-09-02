"""Charter guards: the owner-mandated pieces of the pipeline that prose alone
used to protect (CLAUDE.md rule 1) plus feeds.json consistency rules.

Three different agents edit these files; a passing test suite is the only
protection that survives a well-meaning refactor.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from publishing import PublishingError, validate_feed_config


class WorkflowCharterTest(unittest.TestCase):
    """CLAUDE.md rule 1: the AI-newsroom wiring in build.yml must stay intact."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github" / "workflows" / "build.yml").read_text(
            encoding="utf-8")

    def test_anthropic_install_step_present(self):
        self.assertIn("pip install anthropic", self.text)

    def test_api_key_wired_to_build_step(self):
        self.assertIn("ANTHROPIC_API_KEY", self.text)
        self.assertIn("secrets.ANTHROPIC_API_KEY", self.text)

    def test_investigations_reads_repo_variable_never_hardcoded_off(self):
        self.assertIn("INVESTIGATIONS: ${{ vars.INVESTIGATIONS }}", self.text)
        self.assertNotRegex(
            self.text, re.compile(r"INVESTIGATIONS:\s*['\"]?off", re.I),
            "pause the desk via the INVESTIGATIONS repo variable, "
            "never by hardcoding 'off' in the workflow")

    def test_contents_write_permission_present(self):
        self.assertRegex(self.text, r"permissions:\s*\n\s*contents:\s*write")

    def test_investigations_push_has_rebase_and_retry(self):
        # A silently lost push here loses a finished, deployed investigation.
        persist = self.text.split("Persist generated investigations", 1)[1]
        persist = persist.split("- name:", 1)[0]
        self.assertIn("git rebase --autostash origin/main", persist)
        self.assertIn("for i in 1 2 3", persist)
        self.assertIn("git push origin HEAD:main", persist)
        self.assertNotIn("continue-on-error", persist)

    def test_persist_resolves_conflicts_instead_of_ignoring_them(self):
        # Site scan 2026-09-02: `pull --rebase || true` swallowed conflicts
        # and pushed bare origin/main, silently dropping the run's archive
        # entries and budget ledger. Conflicts are merged or the rebase is
        # aborted and retried — never ignored.
        persist = self.text.split("Persist generated investigations", 1)[1]
        persist = persist.split("- name:", 1)[0]
        self.assertNotIn("pull --rebase", persist)
        self.assertNotRegex(persist, r"rebase --autostash[^\n]*\|\|\s*true")
        self.assertIn("budget_ledger.py --resolve-conflict", persist)
        self.assertIn("git rebase --abort", persist)
        self.assertIn("story-archive/*", persist)

    def test_rearm_pause_switch_is_a_variable(self):
        for name in ("rearm.yml", "heartbeat.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8")
            self.assertIn("vars.SELF_REARM", text, name)


class WeeklyMaintenanceTest(unittest.TestCase):
    """Owner directive 2026-08-31: a standing weekly engineering sweep.

    Ordered after an overflowing SVG pushed straight to main froze 25
    consecutive builds for four hours; the cycle audits workflow-run
    health, the test/build gate, the media library and the archive every
    week. No agent removes the workflow or its schedule.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github" / "workflows" /
                    "weekly-maintenance.yml").read_text(encoding="utf-8")

    def test_workflow_runs_weekly(self):
        self.assertRegex(self.text, r'cron:\s*"[^"]* \* 1"',
                         "the maintenance sweep is weekly (Mondays)")

    def test_core_checks_named_in_prompt(self):
        for marker in ("WORKFLOW-RUN HEALTH", "svg_text_overflows",
                       "STORY-ARCHIVE INTEGRITY", "help:"):
            self.assertIn(marker, self.text)

    def test_no_workflow_pins_node20_actions(self):
        # GitHub force-runs Node-20 actions on Node 24 with warnings since
        # 2026-08; the bumped majors (checkout@v5+, setup-python@v6+,
        # cache@v5+) are the supported runtimes. Don't regress a pin.
        for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = wf.read_text(encoding="utf-8")
            for stale in ("actions/checkout@v4", "actions/setup-python@v5",
                          "actions/cache/restore@v4", "actions/cache/save@v4",
                          "actions/cache@v4"):
                self.assertNotIn(stale, text, f"{wf.name} pins {stale}")


class FeedConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))

    def test_repo_feed_config_is_valid(self):
        validate_feed_config(self.feeds)

    def test_google_news_feeds_declare_gnews_type(self):
        # A gnews search declared as plain RSS attributes every story to
        # Google's redirect URL instead of the outlet that reported it.
        from urllib.parse import urlsplit
        for lang, feeds in self.feeds.items():
            for feed in feeds:
                host = urlsplit(feed.get("url") or "").netloc.lower()
                if host == "news.google.com" or host.endswith(".news.google.com"):
                    self.assertEqual(
                        feed.get("type"), "gnews",
                        f"{lang}:{feed['id']} must declare type 'gnews'")

    def test_validator_rejects_undeclared_google_news_feed(self):
        bad = {
            "en": [{"id": "x", "name": "X", "site": "https://news.google.com",
                    "url": "https://news.google.com/rss/search?q=gaza"}],
            "ar": [{"id": "y", "name": "Y", "site": "https://example.com",
                    "url": "https://example.com/feed"}],
        }
        with self.assertRaises(PublishingError):
            validate_feed_config(bad)

    def test_feed_ids_unique_across_languages(self):
        seen = set()
        for feeds in self.feeds.values():
            for feed in feeds:
                self.assertNotIn(feed["id"], seen)
                seen.add(feed["id"])


if __name__ == "__main__":
    unittest.main()
