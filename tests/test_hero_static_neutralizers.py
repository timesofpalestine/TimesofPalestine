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

    def test_the_graphic_skin_exists(self):
        # Guard the guard: if the skin is renamed, the variant scan above
        # must still see it — this catches a rename that would silently
        # empty _skin_variants and turn the suite green by vacuity.
        self.assertIn("graphic", self._skin_variants())


if __name__ == "__main__":
    unittest.main()
