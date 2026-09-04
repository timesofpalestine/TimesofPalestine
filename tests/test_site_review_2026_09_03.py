"""Site review 2026-09-03 — the fixes it shipped stay fixed.

1. Card, row and hero images: the width/height attributes are CLS hints
   only; CSS keeps height:auto so aspect-ratio:16/9 governs (a fixed 360px
   attribute rendered near-square cards and letterboxed covers).
2. Phones stack the solo section row — its side-by-side art overflowed a
   390px viewport (the only horizontal scroll on the site).
3. Pinned originals (standing pages, SPECIALS-required reports, the election
   tracker) never fall off the originals cap: at exactly 200 live originals
   the newest-first cap silently dropped the TOP 100 and the scholarship map
   and, with them, their front-page cards, nav links and ticker entries.
4. The front page always has a lead: an 18-hour quiet stretch left the hero
   slot empty. The last-resort fallback takes the freshest hard-news story
   with art, features and standing pages still excluded.
"""
import os
import re
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TOP_OFFLINE", "1")

import build  # noqa: E402


def _item(**kw):
    base = {
        "title": "Israeli forces raid a Nablus village and detain four residents",
        "dek": "A sourced summary of the raid on the village.",
        "link": "https://example.com/story",
        "source_url": "https://example.com",
        "source": "Example News",
        "source_id": "example",
        "source_type": "rss",
        "date": datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        "modified": None,
        "image": "/media/photo.jpg",
        "media": None,
        "categories": [],
        "lang": "en",
        "original": False,
        "partner": False,
        "cat": "westbank",
        "score": 10,
        "pid": "1234567890",
        "corrections": [],
        "corroborating_sources": [],
    }
    base.update(kw)
    return base


class CardGeometryTest(unittest.TestCase):
    def test_card_row_and_hero_images_keep_height_auto(self):
        for selector in (".card img{", ".rowcard img,.rowcard .ph{", ".hero-imgwrap>a>img{"):
            rule = build.CSS.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("aspect-ratio:16/9", rule, selector)
            self.assertIn("height:auto", rule, selector)

    def test_solo_row_stacks_on_phones(self):
        phone = build.CSS.split("@media(max-width:560px){", 1)[1]
        self.assertIn(".rowcard.solo{flex-direction:column", phone)
        self.assertIn(".rowcard.solo img,.rowcard.solo .ph{width:100%}", phone)


class PinnedOriginalsTest(unittest.TestCase):
    def test_standing_and_specials_originals_are_pinned(self):
        standing = _item(source_id="top-original", original=True, standing=True,
                         link="original:some-guide.en")
        self.assertTrue(build.pinned_original(standing, "en"))
        slug = next(s["requires_original"] for s in build.SPECIALS
                    if s.get("requires_original"))
        special = _item(source_id="top-original", original=True,
                        link=f"original:{slug}.en")
        self.assertTrue(build.pinned_original(special, "en"))
        self.assertFalse(build.pinned_original(special, "ar"))  # other edition's file
        tracker = _item(source_id="top-original", original=True,
                        link="original:israel-election-2026-tracker.ar", lang="ar")
        self.assertTrue(build.pinned_original(tracker, "ar"))

    def test_ordinary_items_are_not_pinned(self):
        self.assertFalse(build.pinned_original(_item(), "en"))
        plain = _item(source_id="top-original", original=True,
                      link="original:ordinary-report.en")
        self.assertFalse(build.pinned_original(plain, "en"))


class HeroFallbackTest(unittest.TestCase):
    def test_quiet_day_still_renders_a_lead(self):
        built_at = datetime(2026, 9, 3, 15, tzinfo=timezone.utc)
        old_news = _item(
            title="Israeli forces raid a Nablus village and detain four residents",
            date=built_at - timedelta(hours=40), pid="old0000001", score=30)
        feature = _item(
            title="A Ramallah painter carries her city's colours to a Berlin gallery",
            date=built_at - timedelta(hours=30), cat="arts", pid="art0000001",
            score=99, link="https://example.com/painter")
        standing = _item(
            title="Times of Palestine maps the world's scholarships for Palestinian students",
            date=built_at - timedelta(hours=20), cat="social", pid="std0000001",
            score=120, standing=True, link="https://example.com/guide")
        homepage = build.render_page("en", [old_news, feature, standing], built_at)
        self.assertIn('class="hero-imgwrap', homepage)
        overlay = homepage.split("hero-overlay", 1)[1][:500]
        self.assertIn("Nablus", overlay)
        self.assertNotIn("painter", overlay)
        self.assertNotIn("scholarships", overlay)

    def test_fresh_news_still_leads_over_the_fallback(self):
        built_at = datetime(2026, 9, 3, 15, tzinfo=timezone.utc)
        fresh = _item(title="Israeli forces raid Jenin camp before dawn on Thursday",
                      date=built_at - timedelta(hours=2), pid="new0000001", score=5)
        old = _item(title="Israeli forces raid a Nablus village and detain four residents",
                    date=built_at - timedelta(hours=40), pid="old0000001", score=80,
                    link="https://example.com/old")
        homepage = build.render_page("en", [fresh, old], built_at)
        overlay = homepage.split("hero-overlay", 1)[1][:500]
        self.assertIn("Jenin", overlay)


class ReaderCopyTest(unittest.TestCase):
    def test_field_reports_note_makes_no_human_approval_claim(self):
        src = Path(build.__file__).read_text(encoding="utf-8")
        self.assertNotIn("human editor approves", src)
        self.assertNotIn("موافقة محرر بشري", src)

    def test_one_arabic_opengraph_locale(self):
        src = Path(build.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ar_PS", src)
        self.assertGreaterEqual(len(re.findall(r"ar_AR", src)), 3)



class LeadAndListTest(unittest.TestCase):
    """Design pass 2026-09-04: flagship sections lead-and-list, press desks
    keep grids, the rest alternate; only four-story blocks qualify."""

    def test_flagships_always_lead_and_press_never(self):
        self.assertTrue(build.lead_list_section("gaza", 5, 4))
        self.assertTrue(build.lead_list_section("prisoners", 1, 4))
        self.assertFalse(build.lead_list_section("israelipress", 0, 4))
        self.assertFalse(build.lead_list_section("uspress", 2, 4))
        self.assertFalse(build.lead_list_section("gaza", 0, 3))  # needs four

    def test_other_sections_alternate(self):
        self.assertTrue(build.lead_list_section("women", 4, 4))
        self.assertFalse(build.lead_list_section("women", 5, 4))

    def test_front_renders_lead_grid_with_dek(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       dek=f"Sourced summary of raid {i}.", pid=f"wb0000000{i}",
                       link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(13)]
        homepage = build.render_page("en", items, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="grid lead"', block)
        self.assertIn('class="dek"', block)
        self.assertIn("Sourced summary of raid", block)

    def test_list_fills_the_lead_height(self):
        """Owner report 2026-09-04: three rows beside a 620px lead left
        ~300px of dead white. Up to six rows now ride the list, the grid
        shares the lead's height across them, and a short list prints deks."""
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       dek=f"Sourced summary of raid {i}.", pid=f"wb0000000{i}",
                       link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(17)]
        homepage = build.render_page("en", items, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="grid lead" style="--rows:6"', block)
        self.assertEqual(block.count('<article class="card">'), 7)
        self.assertEqual(block.count('class="dek"'), 1)  # six rows: headlines only
        short = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       dek=f"Sourced summary of raid {i}.", pid=f"wb0000000{i}",
                       link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(13)]
        homepage = build.render_page("en", short, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn('style="--rows:3"', block)
        self.assertEqual(block.count('class="dek"'), 4)  # lead + three rows with deks
        self.assertIn("grid-template-rows:repeat(var(--rows,3),minmax(0,1fr))", build.CSS)
        phone = build.CSS.split("@media(max-width:560px){", 1)[1]
        self.assertIn(".grid.lead{grid-template-rows:none}", phone)

    def test_css_carries_lead_and_phone_rows_and_print(self):
        self.assertIn(".grid.lead{grid-template-columns:", build.CSS)
        phone = build.CSS.split("@media(max-width:560px){", 1)[1]
        self.assertIn(".grid .card:not(:first-child){display:grid", phone)
        self.assertIn("@media print{", build.CSS)


class FrontWindowTest(unittest.TestCase):
    """Owner order 2026-09-04: "some stories show they are from 16 days
    ago — I want a fresh day of news on the front page." A section slot
    is a story from the last three days; a quiet section may reach back a
    week to keep two stories; nothing older takes a slot."""

    def _wb(self, i, hours, built_at):
        return _item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                     dek=f"Sourced summary of raid {i}.", pid=f"wb0000{i:04d}",
                     link=f"https://example.com/wb{i}",
                     date=built_at - timedelta(hours=hours))

    def test_old_stories_never_take_a_front_slot(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        # hero + 8 subs consume nine of the fresh ones; the rest form the block
        fresh = [self._wb(i, 2 + i, built_at) for i in range(12)]
        old = [self._wb(90 + i, 24 * 16 + i, built_at) for i in range(4)]  # 16 days
        homepage = build.render_page("en", fresh + old, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn("village number 11", block)
        self.assertNotIn("village number 9", block.replace("village number 9 ", "x"))  # no 90-93
        for i in range(90, 94):
            self.assertNotIn(f"village number {i} ", block)

    def test_quiet_section_reaches_back_six_days_but_no_further(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        gaza = [_item(title=f"Israeli strikes hit Gaza City block number {i} overnight",
                      cat="gaza", pid=f"gz0000{i:04d}", link=f"https://example.com/gz{i}",
                      date=built_at - timedelta(hours=1 + i)) for i in range(10)]
        wb = [self._wb(1, 100, built_at),            # four days old
              self._wb(2, 150, built_at),            # six days old
              self._wb(3, 24 * 20, built_at)]        # twenty days old
        homepage = build.render_page("en", gaza + wb, built_at)
        block = homepage.split('id="westbank"', 1)[1].split("</section>", 1)[0]
        self.assertIn("village number 1 ", block)
        self.assertIn("village number 2 ", block)
        self.assertNotIn("village number 3 ", block)

    def test_window_constants(self):
        self.assertEqual(build.FRONT_WINDOW_H, 72)
        self.assertEqual(build.FRONT_WINDOW_MAX_H, 150)


class WireCopyHygieneTest(unittest.TestCase):
    """Front render 2026-09-04: headlines carried full stops and Arabic
    deks ended on a cut-off word — both fixed at the source."""

    def test_dek_never_ends_in_a_fragment(self):
        cut = "أعلنت الوزارة الرقم الجديد للشهداء في القطاع. وقال الباح"
        self.assertEqual(build.clean_dek(cut), "أعلنت الوزارة الرقم الجديد للشهداء في القطاع.")
        whole = "The ministry announced the new figure for the Strip."
        self.assertEqual(build.clean_dek(whole), whole)
        single = "The ministry announced the new figure for the Strip and the min"
        self.assertTrue(build.clean_dek(single).endswith("…"))
        self.assertEqual(build.clean_dek("Is the crossing open?"), "Is the crossing open?")

    def test_card_legend_sits_inside_the_desktop_crop(self):
        svg = (Path(build.__file__).parent / "originals" / "media"
               / "times-of-palestine-israel-votes-card.svg").read_text(encoding="utf-8")
        ys = [float(y) for y in re.findall(r'<text[^>]* y="([\d.]+)"', svg)]
        self.assertTrue(ys and max(ys) <= 320, ys)  # 16:6 crop shows y 25–325
        self.assertFalse(build.svg_text_overflows(svg))


class LivingStoryPageTest(unittest.TestCase):
    """Owner order 2026-09-04: a story page must not be a dull column. The
    layers are automatic and drawn only from the copy and the live ledger."""

    TEXT = ("Two months before Israel votes, the Maariv analysis puts the Zionist "
            "opposition at 59 seats, two short of a governing majority. Turnout in "
            "Arab towns reached 53% in the last election, the pollster said on 28 "
            "August 2026. The list won 10 seats in 2022. “The community is deciding "
            "whether it is worth voting at all, and that decision decides the next "
            "government,” one organiser told the paper. It was 09:30 when polls opened.")

    def test_figures_are_quantities_not_dates(self):
        figs = build.story_figures(self.TEXT, "en")
        self.assertEqual([f[0] for f in figs], ["53%", "59", "10"])
        self.assertTrue(all("28" not in f[0] and "2026" not in f[0] for f in figs))

    def test_markdown_furniture_never_reaches_a_tile(self):
        text = ("## The count\n\n> More than 140 Arab citizens were killed by mid-year, "
                "the **Abraham Initiatives** said.\n\n- Last year ended with 250 killed.")
        figs = build.story_figures(text, "en")
        self.assertEqual([f[0] for f in figs], ["250", "140"])
        self.assertTrue(all(not sent.startswith(">") and "**" not in sent for _, sent in figs))

    def test_arabic_figures_and_percent(self):
        text = ("أعلنت الوزارة أن 92 في المئة من المدارس تحتاج إلى إعادة بناء. "
                "وتوقفت 12 مستشفى عن العمل منذ تشرين الأول/أكتوبر 2023. "
                "وأحصت الأونروا 637000 طفل خارج المدرسة.")
        figs = build.story_figures(text, "ar")
        self.assertEqual(figs[0][0], "92 في المئة")
        self.assertIn("637000", [f[0] for f in figs])
        self.assertNotIn("2023", [f[0] for f in figs])

    def test_pull_quote_is_verbatim_and_sized(self):
        q = build.story_pull_quote(self.TEXT, "en")
        self.assertIn("decides the next government", q)
        self.assertEqual(build.story_pull_quote("He said “no”. Then “yes, twice”.", "en"), "")

    def test_story_page_carries_rail_figures_and_plate(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        paras = " ".join(f"Sentence number {i} of the report continues the account of the raid." for i in range(3))
        brief = "\n\n".join([self.TEXT] + [paras] * 7)
        story = _item(title="Palestinian citizens of Israel raise their turnout and unsettle both blocs",
                      cat="pal48", brief=brief, image="/media/times-of-palestine-cover-pal48.svg",
                      pid="pal4800001", link="https://example.com/turnout")
        related = [_item(title=f"Nazareth council counts killing number {i} this year", cat="pal48",
                         pid=f"pal48000{i}", link=f"https://example.com/n{i}",
                         date=built_at - timedelta(hours=i + 1)) for i in range(2, 12)]
        html = build.render_story(story, "en", related, related, built_at)
        self.assertIn('class="story-rail"', html)
        self.assertIn("More from Palestinians in Israel", html)
        self.assertIn('class="story-figs"', html)
        self.assertIn('class="pull lifted"', html)
        self.assertIn("cover-pal48-hero.svg", html)
        self.assertIn('<article class="story sa-pal48">', html)
        # the rail's four section stories do not repeat in Keep Reading
        keep = html.split('class="keep"', 1)[1].split('class="wrap latest"', 1)[0]
        self.assertNotIn("killing number 2 ", keep)
        self.assertIn("killing number 6 ", keep)

    def test_originals_and_short_briefs_are_left_alone(self):
        paras = '<p class="summary">one</p><p class="summary">two</p><p class="summary">three</p>'
        self.assertEqual(build.weave_story_visuals(paras, self.TEXT, "en", "gaza"), paras)
        # a body with its own figure gets no tiles; the lifted quote may still ride
        with_fig = paras * 3 + "<figure class=\"lf\"></figure>"
        woven = build.weave_story_visuals(with_fig, self.TEXT, "en", "gaza")
        self.assertNotIn("story-figs", woven)
        self.assertIn("pull lifted", woven)
        # a writer's own pull quote keeps its place; the figures still ride
        with_quote = paras * 3 + "<blockquote class=\"pull\"><p>x</p></blockquote>"
        woven = build.weave_story_visuals(with_quote, self.TEXT, "en", "gaza")
        self.assertIn("story-figs", woven)
        self.assertNotIn("pull lifted", woven)


class RunningFileChipTest(unittest.TestCase):
    def test_story_in_a_live_hub_carries_the_chip(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        story = _item(title="Settlers attack Qusra again as the siege enters its fourth week",
                      pid="qusra00001", link="https://example.com/qusra")
        tf = {"slug": "qusra", "pattern": "qusra", "since": "2026-08-11",
              "en": {"name": "The Qusra File", "dek": "d"},
              "ar": {"name": "ملف قصرة", "dek": "d"}}
        old = dict(build.TOPIC_HUBS_LIVE)
        build.TOPIC_HUBS_LIVE["en"] = [(tf, [story])]
        try:
            html = build.render_story(story, "en", [], [], built_at)
        finally:
            build.TOPIC_HUBS_LIVE.clear(); build.TOPIC_HUBS_LIVE.update(old)
        self.assertIn('class="file-chip" href="../topic-qusra.html"', html)
        self.assertIn("The Qusra File", html)
        self.assertIn("DAY 25", html)

    def test_story_outside_every_file_has_no_chip(self):
        built_at = datetime(2026, 9, 4, 9, tzinfo=timezone.utc)
        old = dict(build.TOPIC_HUBS_LIVE)
        build.TOPIC_HUBS_LIVE["en"] = []
        try:
            html = build.render_story(_item(), "en", [], [], built_at)
        finally:
            build.TOPIC_HUBS_LIVE.clear(); build.TOPIC_HUBS_LIVE.update(old)
        self.assertNotIn("file-chip", html)


class FrontFlowTest(unittest.TestCase):
    """Owner order 2026-09-04: sections and bands in priority order. The
    news of the ground leads, the numbers ledger follows the block it
    counts, power and money come next, then depth and comment, then
    society, culture and sport, then service — never a ledger, a memory
    line or an opinion block between the hero and the first Gaza story."""

    def test_every_section_once_and_bands_between(self):
        keys = [k for k in build.FRONT_FLOW if not k.startswith("@")]
        self.assertEqual(sorted(keys), sorted(set(build.STR["en"]["sections"])))
        self.assertEqual(len(keys), len(set(keys)))
        for lang in ("en", "ar"):
            self.assertEqual(build.SECTION_ORDER[lang], keys)
        self.assertEqual(keys[:4], ["gaza", "westbank", "pal48", "prisoners"])
        self.assertLess(keys.index("politics"), keys.index("health"))
        self.assertLess(keys.index("economy"), keys.index("sports"))
        self.assertLess(keys.index("research"), keys.index("israelipress"))
        self.assertLess(keys.index("uspress"), keys.index("opinion"))
        self.assertEqual(keys[-2:], ["news", "archive"])
        flow = build.FRONT_FLOW
        self.assertLess(flow.index("prisoners"), flow.index("@numbers"))
        self.assertLess(flow.index("@numbers"), flow.index("politics"))
        self.assertLess(flow.index("bitcoin"), flow.index("@onthisday"))

    def test_rendered_front_puts_news_before_opinion_and_memory(self):
        built_at = datetime(2026, 5, 15, 12, tzinfo=timezone.utc)  # a dated day
        items = []  # hero + eight sub-items consume nine before the blocks
        for i in range(13):
            items.append(_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                               pid=f"wb000000{i:02d}", link=f"https://example.com/wb{i}", cat="gaza",
                               date=built_at - timedelta(hours=i + 1)))
        for i in range(2):
            items.append(_item(title=f"Why the Gaza ceasefire talks stall again this week, take {i}",
                               pid=f"op0000000{i}", link=f"https://example.com/op{i}", cat="opinion",
                               date=built_at - timedelta(hours=i + 1)))
        for i in range(2):
            items.append(_item(title=f"Palestinian Authority names a new finance minister in Ramallah {i}",
                               pid=f"po0000000{i}", link=f"https://example.com/po{i}", cat="politics",
                               date=built_at - timedelta(hours=i + 20)))
        page = build.render_page("en", items, built_at)
        main = page.split('<main id="top">', 1)[1]
        gaza = main.index('id="gaza"')
        self.assertLess(main.index('class="franchise"') if 'class="franchise"' in main else 0, gaza)
        self.assertLess(gaza, main.index('id="politics"'))
        self.assertLess(main.index('id="politics"'), main.index('id="opinion"'))
        self.assertLess(main.index('id="opinion"'), main.index('class="otd"'))
        self.assertNotIn('class="otd"', main[:gaza])
        self.assertNotIn('id="opinion"', main[:gaza])


if __name__ == "__main__":
    unittest.main()
