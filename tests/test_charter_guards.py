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
        self.assertIn("git pull --rebase", self.text)
        persist = self.text.split("Persist generated investigations", 1)[1]
        persist = persist.split("- name:", 1)[0]
        self.assertNotIn("continue-on-error", persist)

    def test_rearm_pause_switch_is_a_variable(self):
        for name in ("rearm.yml", "heartbeat.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8")
            self.assertIn("vars.SELF_REARM", text, name)


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
