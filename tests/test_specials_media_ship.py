"""The SPECIALS band's art always ships with the build.

Production failure 2026-08-19: the Dima Barakat campaign card 404'd its SVG
on both index pages. copy_media only ships story-referenced files, and the
campaign story's remote cover verified live — so its imageFallback SVG (the
same file the band card uses) was never copied. The band renders on every
index page independently of any story, so its /media/ art is a build input
in its own right.
"""
import tempfile
import unittest
from pathlib import Path

import build
import longform


class SpecialsMediaTests(unittest.TestCase):
    def test_every_specials_media_asset_exists_in_the_repo(self):
        for s in build.SPECIALS:
            img = str(s.get("img", ""))
            if img.startswith("/media/"):
                with self.subTest(img=img):
                    self.assertTrue(
                        (Path("originals/media") / Path(img).name).is_file(),
                        f"SPECIALS card art missing from originals/media: {img}")

    def test_copy_media_ships_specials_art_without_any_story(self):
        specials_media = [
            {"image": s["img"]} for s in build.SPECIALS
            if str(s.get("img", "")).startswith("/media/")]
        self.assertTrue(specials_media, "no /media/ specials to exercise")
        with tempfile.TemporaryDirectory() as tmp:
            longform.copy_media(tmp, specials_media)
            for entry in specials_media:
                name = Path(entry["image"]).name
                with self.subTest(name=name):
                    self.assertTrue(
                        (Path(tmp) / "media" / name).is_file(),
                        f"specials art did not ship: {name}")

    def test_build_passes_specials_media_to_copy_media(self):
        # The call-site guard: main() must extend the copy_media story list
        # with the SPECIALS images, or a live remote cover starves the band.
        src = Path("build.py").read_text(encoding="utf-8")
        self.assertIn("_specials_media", src)
        self.assertIn("archived_all + _specials_media", src)


if __name__ == "__main__":
    unittest.main()
