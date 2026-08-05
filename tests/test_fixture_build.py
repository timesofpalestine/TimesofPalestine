import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FixtureBuildTests(unittest.TestCase):
    def test_offline_fixture_build_and_validator(self):
        # CI always builds into a fresh workspace; locally, stale dist/
        # leftovers (e.g. an unpublished static feature) would haunt the
        # absence assertions below. Start from scratch like the real deploy.
        import shutil
        shutil.rmtree(ROOT / "dist", ignore_errors=True)
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
        # Sanad is UNPUBLISHED (owner decision 2026-08-04): development
        # continues privately in sanad/ and sanad-app/, but no reader-facing
        # surface may ship until the owner green-lights redeployment.
        self.assertFalse((ROOT / "dist" / "sanad").exists())
        for lang in ("en", "ar"):
            front = (ROOT / "dist" / lang / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('/sanad/', front)
            self.assertNotIn('sanad-band', front)


if __name__ == "__main__":
    unittest.main()
