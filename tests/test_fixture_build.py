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


if __name__ == "__main__":
    unittest.main()
