import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import story_archive


def sample_item(pid="abc123def0", lang="en", **overrides):
    item = {
        "pid": pid,
        "lang": lang,
        "title": "Example ministry opens Gaza field hospital for dialysis care",
        "dek": "A short dek.",
        "brief": "The rewritten brief body.\n\nSecond paragraph.",
        "image": "https://example.test/photo.jpg",
        "media": None,
        "link": "https://example.test/story",
        "source": "Example Wire",
        "source_url": "https://example.test",
        "source_id": "example-wire",
        "cat": "health",
        "date": datetime(2026, 8, 9, 10, 30, tzinfo=timezone.utc),
        "modified": None,
        "original": False,
        "corroborating_sources": None,
        "max_age_hours": 72,
        "score": 41.5,
        "extra_runtime_field": "never persisted",
    }
    item.update(overrides)
    return item


class StoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(
            os.environ, {"STORY_ARCHIVE_DIR": self._tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_then_load_round_trips_dates_and_whitelists_fields(self):
        story_archive.save(sample_item())
        loaded = story_archive.load("en")
        self.assertEqual(len(loaded), 1)
        item = loaded[0]
        self.assertEqual(item["pid"], "abc123def0")
        self.assertEqual(item["date"],
                         datetime(2026, 8, 9, 10, 30, tzinfo=timezone.utc))
        # Null optionals load as ABSENT keys so the renderer's
        # .get(field, default) patterns keep their defaults…
        self.assertNotIn("modified", item)
        self.assertNotIn("corroborating_sources", item)
        # …while directly-subscripted fields are always present.
        self.assertEqual(item["image"], "https://example.test/photo.jpg")
        self.assertTrue(item["archived"])
        self.assertNotIn("extra_runtime_field", item)
        # A photoless story still loads with its image key present (None),
        # because the renderer subscripts it["image"] directly.
        story_archive.save(sample_item(pid="ffffffffff", image=None))
        photoless = [i for i in story_archive.load("en")
                     if i["pid"] == "ffffffffff"][0]
        self.assertIsNone(photoless["image"])

    def test_load_excludes_live_and_retracted_pids(self):
        story_archive.save(sample_item(pid="aaaaaaaaaa"))
        story_archive.save(sample_item(pid="bbbbbbbbbb"))
        loaded = story_archive.load("en", exclude={"aaaaaaaaaa"})
        self.assertEqual([i["pid"] for i in loaded], ["bbbbbbbbbb"])

    def test_load_is_scoped_per_language(self):
        story_archive.save(sample_item(pid="aaaaaaaaaa", lang="en"))
        story_archive.save(sample_item(pid="cccccccccc", lang="ar"))
        self.assertEqual([i["pid"] for i in story_archive.load("ar")],
                         ["cccccccccc"])

    def test_corrupt_record_is_skipped_not_fatal(self):
        story_archive.save(sample_item(pid="aaaaaaaaaa"))
        bad = Path(self._tmp.name) / "en" / "dddddddddd.json"
        bad.write_text("{not json", encoding="utf-8")
        incomplete = Path(self._tmp.name) / "en" / "eeeeeeeeee.json"
        incomplete.write_text(json.dumps({"pid": "eeeeeeeeee"}), encoding="utf-8")
        loaded = story_archive.load("en")
        self.assertEqual([i["pid"] for i in loaded], ["aaaaaaaaaa"])

    def test_resave_updates_changed_record(self):
        story_archive.save(sample_item())
        story_archive.save(sample_item(title="Ministry expands the Gaza field hospital it opened"))
        loaded = story_archive.load("en")
        self.assertEqual(len(loaded), 1)
        self.assertIn("expands", loaded[0]["title"])

    def test_newest_first_ordering(self):
        story_archive.save(sample_item(
            pid="aaaaaaaaaa", date=datetime(2026, 8, 1, tzinfo=timezone.utc)))
        story_archive.save(sample_item(
            pid="bbbbbbbbbb", date=datetime(2026, 8, 8, tzinfo=timezone.utc)))
        self.assertEqual([i["pid"] for i in story_archive.load("en")],
                         ["bbbbbbbbbb", "aaaaaaaaaa"])


class StoryArchiveOfflineTests(unittest.TestCase):
    def test_offline_fixture_builds_never_touch_repo_state(self):
        env = {"TOP_OFFLINE": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("STORY_ARCHIVE_DIR", None)
            self.assertIsNone(story_archive.archive_dir())
            story_archive.save(sample_item())  # must be a silent no-op
            self.assertEqual(story_archive.load("en"), [])


if __name__ == "__main__":
    unittest.main()
