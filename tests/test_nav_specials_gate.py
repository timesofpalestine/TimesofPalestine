"""Interior nav must never link a special whose story page did not render.

The 2026-08-15 sweep found the offline build failing link-check (#272):
`ORIGINALS_LOADED` is a parse-time signal, so an original the pipeline later
drops — or an archive re-render skipped offline — left nav links to pages
that never shipped. `STORY_PAGES_RENDERED` is the render-time gate; once main
populates it for a language, the nav trusts only that."""
import unittest

import build


class NavSpecialsGateTest(unittest.TestCase):
    def setUp(self):
        self._loaded = dict(build.ORIGINALS_LOADED)
        self._rendered = dict(build.STORY_PAGES_RENDERED)

    def tearDown(self):
        build.ORIGINALS_LOADED.clear()
        build.ORIGINALS_LOADED.update(self._loaded)
        build.STORY_PAGES_RENDERED.clear()
        build.STORY_PAGES_RENDERED.update(self._rendered)

    def _gated_special(self):
        for sp in build.SPECIALS:
            if sp.get("requires_original"):
                return sp
        self.fail("no requires_original special defined")

    def test_loaded_but_unrendered_special_is_not_linked(self):
        sp = self._gated_special()
        build.ORIGINALS_LOADED["en"] = {sp["requires_original"]}
        build.STORY_PAGES_RENDERED["en"] = set()  # page did not ship
        nav = build.interior_nav_html("en")
        self.assertNotIn(sp["href"]["en"], nav)

    def test_rendered_special_is_linked(self):
        sp = self._gated_special()
        build.ORIGINALS_LOADED["en"] = {sp["requires_original"]}
        build.STORY_PAGES_RENDERED["en"] = {sp["href"]["en"]}
        nav = build.interior_nav_html("en")
        self.assertIn(sp["href"]["en"], nav)


if __name__ == "__main__":
    unittest.main()
