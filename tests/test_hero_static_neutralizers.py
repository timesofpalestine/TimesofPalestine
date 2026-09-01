"""Static heroes must neutralize every overlay skin (owner rule 2026-08-12).

On phones and in lite mode the hero headline leaves the image and renders
as a static block below it. Overlay skins are written with higher
specificity than those static rules (`.hero-imgwrap.graphic .hero-overlay`
beats the media query's bare `.hero-overlay`), so a skin that is not
explicitly neutralized bleeds into the static block — the 2026-08-12
regression faded and clipped the mobile headline under the graphic-hero
gradient on both editions.

The rule this test enforces: for every overlay skin defined on
`.hero-imgwrap.<variant> .hero-overlay`, BOTH static contexts (the phone
media block and `[data-lite]`) must carry a same-specificity neutralizer
that resets the background, and dimming filters on the hero image must be
reset alongside it. Adding a new skin without its two neutralizers fails
this test — by design."""
import re
import unittest

import build


class HeroStaticNeutralizerTest(unittest.TestCase):
    def _skin_variants(self):
        """Overlay-skin variant classes defined anywhere in the CSS."""
        return set(re.findall(
            r"\.hero-imgwrap\.([a-z-]+)\s+\.hero-overlay\s*\{background:(?!none)",
            build.CSS))

    def test_every_overlay_skin_is_neutralized_twice(self):
        for variant in self._skin_variants():
            neutralizer = f".hero-imgwrap.{variant} .hero-overlay{{background:none}}"
            self.assertGreaterEqual(
                build.CSS.count(neutralizer), 2,
                f"overlay skin '.{variant}' must be neutralized in BOTH the "
                f"phone media block and [data-lite] — found fewer than two "
                f"'{neutralizer}' rules")

    def test_hero_image_filters_are_reset_in_static_contexts(self):
        for variant in self._skin_variants():
            if f".hero-imgwrap.{variant}>a>img{{filter:" in build.CSS.replace(" ", ""):
                reset = f".hero-imgwrap.{variant}>a>img{{filter:none}}"
                self.assertGreaterEqual(
                    build.CSS.count(reset), 2,
                    f"hero image filter for '.{variant}' must be reset in "
                    f"both static contexts")

    def test_static_hero_image_height_stays_natural(self):
        # 2026-08-16 regression: explicit width/height attributes on the
        # hero <img> (CLS belt) applied literally in the static contexts,
        # which have no CSS height rule — a 675px portrait crop ate the
        # art on phones. Both static contexts must pin height:auto.
        self.assertGreaterEqual(
            build.CSS.count(".hero-imgwrap>a>img{height:auto}"), 2,
            "static hero contexts (phone media block and [data-lite]) must "
            "reset the hero image to height:auto so dimension attributes "
            "never dictate layout there")

    def test_graphic_skin_stays_retired_and_split_hero_stays_static_safe(self):
        # The .graphic dim-and-scrim skin was retired by the split hero
        # (owner-approved design pass 2026-09-01) — house-SVG art now sits
        # BESIDE an ink panel instead of under a dimmed overlay, so there
        # is no overlay skin left to neutralize. Guard the replacement the
        # same way: the split hero must never route through .hero-overlay
        # (that would re-enter the bleed-prone path this file polices), and
        # lite mode must hide its art and flatten its panel.
        self.assertNotIn("graphic", self._skin_variants())
        self.assertNotIn(".hero-imgwrap.split .hero-overlay", build.CSS)
        self.assertIn("[data-lite] .hs-art{display:none!important}", build.CSS)
        self.assertIn("[data-lite] .hs-panel{padding:0;border:0}", build.CSS)


if __name__ == "__main__":
    unittest.main()
