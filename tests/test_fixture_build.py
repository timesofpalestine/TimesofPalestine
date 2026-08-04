import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FixtureBuildTests(unittest.TestCase):
    def test_offline_fixture_build_and_validator(self):
        env = os.environ.copy()
        env.update({
            "TOP_FEEDS_FILE": "tests/fixtures/feeds.json",
            "TOP_OFFLINE": "1",
            "TOP_SKIP_ORIGINALS": "1",
            "TOP_ALLOW_RAW_SUMMARIES": "1",
            "TOP_REMOTE_MEDIA": "rights-only",
        })
        subprocess.run(
            [sys.executable, "build.py"], cwd=ROOT, env=env,
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [sys.executable, "validate_build.py", "dist"], cwd=ROOT, env=env,
            check=True, capture_output=True, text=True,
        )
        health = json.loads((ROOT / "dist" / "health.json").read_text(encoding="utf-8"))
        self.assertEqual(health["stories"], {"en": 1, "ar": 1})
        self.assertEqual(health["mediaBlocked"], 1)
        self.assertEqual(health["connectors"]["telegram"], "disabled")
        # Every category cover ships in every build: lede_fallback_attrs points
        # dying remote images at covers from inside onerror attributes, which
        # copy_media cannot see — a missing cover 404s in the reader's browser.
        src_covers = {f.name for f in
                      (ROOT / "originals" / "media").glob("times-of-palestine-cover-*.svg")}
        out_covers = {f.name for f in
                      (ROOT / "dist" / "media").glob("times-of-palestine-cover-*.svg")}
        self.assertTrue(src_covers)
        self.assertEqual(src_covers - out_covers, set())
        # Sanad (owner directive 2026-08-04) is a standing service: the static
        # feature must deploy at /sanad/ with its offline files, its brand art
        # must ship for the specials row, and both front pages must link it.
        self.assertTrue((ROOT / "dist" / "sanad" / "index.html").is_file())
        self.assertTrue((ROOT / "dist" / "sanad" / "sw.js").is_file())
        self.assertTrue((ROOT / "dist" / "sanad" / "manifest.webmanifest").is_file())
        self.assertFalse((ROOT / "dist" / "sanad" / ".static-feature").exists())
        self.assertTrue(
            (ROOT / "dist" / "media" / "times-of-palestine-sanad-2026.svg").is_file())
        for lang in ("en", "ar"):
            front = (ROOT / "dist" / lang / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="/sanad/"', front)


if __name__ == "__main__":
    unittest.main()
