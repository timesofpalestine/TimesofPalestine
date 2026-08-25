"""Share cards never advertise an SVG og:image.

Owner report 2026-08-24: Facebook rejected a story's SVG og:image, scraped
the page instead, and put the NEIGHBORING story's infographic on the share
card. og_image_tags now advertises the build-rasterized .png sibling for
house SVGs, keeps the site banner as the fallback og:image, and passes
raster ledes through untouched.
"""
import re
import unittest

import build


def tags(image):
    it = {"image": image}
    og, card, _url = build.og_image_tags(it)
    return og, card


class OgImageTests(unittest.TestCase):
    def test_svg_lede_advertises_png_sibling_plus_banner(self):
        og, card = tags("/media/times-of-palestine-x-lede.svg")
        self.assertIn("/media/times-of-palestine-x-lede.png", og)
        self.assertIn("og-banner.png", og)
        self.assertNotIn(".svg", og)
        self.assertEqual(card, "summary_large_image")

    def test_raster_lede_passes_through_alone(self):
        og, card = tags("https://example.org/photo_640.jpg")
        self.assertIn("photo_640.jpg", og)
        self.assertNotIn("og-banner", og)
        self.assertEqual(card, "summary_large_image")

    def test_photoless_story_gets_the_banner(self):
        og, card = tags(None)
        self.assertIn("og-banner.png", og)
        self.assertEqual(card, "summary")

    def test_no_rendered_story_page_carries_an_svg_og_image(self):
        # The render sites must use og_image_tags, not raw it["image"].
        src = open("build.py", encoding="utf-8").read()
        self.assertNotIn('og_img_url = (BASE_URL + it["image"])', src)
        self.assertEqual(len(re.findall(r"og_image, _og_card, og_img_url = og_image_tags\(it\)", src)), 2)

    def test_workflow_rasterizes_media_svgs(self):
        wf = open(".github/workflows/build.yml", encoding="utf-8").read()
        self.assertIn("rsvg-convert", wf)
        self.assertIn("dist/media/*.svg", wf)


if __name__ == "__main__":
    unittest.main()
