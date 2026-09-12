"""Site review 2026-09-12 — the fixes it shipped stay fixed.

1. The refusal screen no longer eats ordinary third-person prose: "leaving
   bakeries unable to produce what is needed" cost the Gaza night-workers
   report its English edition. Only the refusal shape (opening the copy or
   a sentence, or first person) trips the net.
2. Card, row and original deks cut at a sentence end that fits instead of
   trailing off mid-phrase; figure-tile captions keep whole clauses.
3. CSS: infographic art keeps its edges in the split hero; the lead card's
   art grows to fill the list's height; the featured report's photo fills
   the body's height instead of inflating the row; the backbar's controls
   are readable on black in light mode.
4. Two-story sections run as two rows, not two 600px cards.
5. The vote card and the running-files strip count the same calendar days.
6. Section routing: a reporter called Rasha is not a rash, agriculture is
   not culture, and a Gaza school named Kafr Qasim stays in Gaza.
"""
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        "date": datetime(2026, 9, 12, 12, tzinfo=timezone.utc),
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


def wire(title, dek="", lang="en"):
    return {"title": title, "dek": dek, "link": "https://example.com/s",
            "categories": [], "lang": lang}


class RefusalNetTests(unittest.TestCase):
    def test_third_person_prose_is_not_a_refusal(self):
        prose = ("A shortage of flour and fuel, the outlet reported, was caused by "
                 "Israeli restrictions on imports, leaving bakeries unable to produce "
                 "what is needed. A boy in the queue said he expected to leave without bread.")
        self.assertIsNone(build.REFUSAL_RX.search(prose))

    def test_refusal_shapes_still_trip(self):
        for text in ("Unable to produce a brief from this material.",
                     "The wire item is thin. Unable to write a complete brief.",
                     "I am unable to produce a rewrite of this story.",
                     "We're unable to summarize this post."):
            self.assertIsNotNone(build.REFUSAL_RX.search(text), text)


class DekTruncationTests(unittest.TestCase):
    def test_dek_cuts_at_a_sentence_end(self):
        text = ("The World Health Organization put the number at 12,913, including "
                "6,186 children, the spokesperson said on 11 August. He said evacuations "
                "were running three to four times a week, in remarks carried by the agency.")
        cut = build.truncate_dek(text, 160)
        self.assertTrue(cut.endswith("11 August."), cut)
        self.assertNotIn("…", cut)

    def test_dek_falls_back_to_a_word_cut_without_a_sentence_end(self):
        text = "word " * 80
        cut = build.truncate_dek(text.strip(), 100)
        self.assertTrue(cut.endswith("…"))
        self.assertLessEqual(len(cut), 101)

    def test_short_dek_is_untouched(self):
        self.assertEqual(build.truncate_dek("Short.", 100), "Short.")

    def test_arabic_dek_cuts_at_the_arabic_full_stop(self):
        text = "قدّرت المنظمة العدد بنحو 12 ألفاً. وقال المتحدث إن عمليات الإجلاء تجري ثلاث مرات أسبوعياً في تصريحات نقلتها الوكالة؟ ثم أضاف"
        cut = build.truncate_dek(text, 60)
        self.assertTrue(cut.endswith("ألفاً."), cut)

    def test_figure_caption_keeps_whole_clauses(self):
        sent = ("The army said in April 2026 that the field hospitals had treated more than "
                "700,000 patients and performed over 26,000 surgeries; a year earlier the "
                "figure given was 524,248 patients, according to the same release.")
        cut = build.truncate_clause(sent, 150)
        self.assertTrue(cut.endswith("26,000 surgeries…"), cut)


class CssTests(unittest.TestCase):
    def test_split_hero_keeps_infographic_edges(self):
        self.assertIn('.hero-imgwrap.split .hs-art img[src$=".svg"]{object-fit:contain', build.CSS)

    def test_lead_art_fills_the_list_height(self):
        self.assertIn(".grid.lead .card:first-child>a:first-child{position:relative;flex:1 1 auto", build.CSS)
        self.assertIn(".grid.lead .card:first-child>a:first-child img,", build.CSS)

    def test_featured_report_art_fills_the_body_height(self):
        self.assertIn(".research-feat>a{position:relative;display:block;min-height:240px}", build.CSS)
        self.assertIn(".research-feat img{position:absolute;inset:0;width:100%;height:100%", build.CSS)
        self.assertIn("[data-lite] .research-feat>a,", build.CSS)

    def test_backbar_controls_are_readable_on_black(self):
        self.assertIn(".backbar .themetoggle,.backbar .litetoggle{color:#f2eee8}", build.CSS)


class ChromeContrastTests(unittest.TestCase):
    """Colour and target sizes measured in the browser on 2026-09-12."""

    def test_rail_letter_tiles_carry_the_tile_skin(self):
        # The story rail's initial tiles were page-ink on a mid-dark section
        # accent (2.0-3.0:1) and not centred: .rr-thumb.tile was missing from
        # the base tile rule.
        self.assertIn(".lt-thumb.tile,.sub-thumb.tile,.rr-thumb.tile{display:flex;", build.CSS)

    def test_touch_pointers_get_house_tap_targets_at_any_width(self):
        block = build.CSS.split("@media(hover:none){\n", 1)[1].split("\n}", 1)[0]
        self.assertIn("min-height:44px", block)
        self.assertIn(".breadcrumbs a", block)

    def test_vote_card_keeps_an_ink_ground_under_its_gradient(self):
        self.assertIn(".fr-card.vote{position:relative;isolation:isolate;background:#0d121a linear-gradient", build.CSS)

    def test_dark_mode_byline_and_cta_button(self):
        dark = build.CSS.split("@media(prefers-color-scheme:dark){", 1)[1]
        self.assertIn(".story .byline{color:#3fd07c}", dark)
        self.assertIn(".story .cta a{color:#fff}", dark)

    def test_story_rail_labels_are_headings(self):
        built_at = datetime(2026, 9, 12, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       pid=f"wb0000000{i}", link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(6)]
        rail = build.story_rail_html(items[0], "en", items[1:3], items[3:], built_at)
        self.assertIn('<h2 class="rail-kick"', rail)
        self.assertNotIn('<p class="rail-kick"', rail)


class CanonicalHostTests(unittest.TestCase):
    def test_root_redirect_names_the_site_host(self):
        self.assertIn(f'<link rel="canonical" href="{build.BASE_URL}/en/">', build.REDIRECT_HTML)
        self.assertNotIn("https://timesofpalestine.com/", build.REDIRECT_HTML)
        for tag in ("en", "ar", "x-default"):
            self.assertIn(f'hreflang="{tag}"', build.REDIRECT_HTML)


class ServiceWorkerTests(unittest.TestCase):
    def test_shell_never_precaches_the_removed_pages(self):
        sw = (Path(__file__).resolve().parents[1] / "sw.js").read_text(encoding="utf-8")
        shell = sw.split("const SHELL = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("status.html", shell)
        self.assertNotIn("corrections.html", shell)
        self.assertIn("/en/search.html", shell)


class OpinionBandTests(unittest.TestCase):
    def test_two_comment_pieces_fill_the_row(self):
        built_at = datetime(2026, 9, 12, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       pid=f"wb0000000{i}", link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(8)]
        items += [_item(title=f"Gaza needs a reconstruction plan its people write, number {i}",
                        cat="opinion", pid=f"op0000000{i}", link=f"https://example.com/op{i}",
                        date=built_at - timedelta(hours=i + 2)) for i in range(2)]
        homepage = build.render_page("en", items, built_at)
        self.assertIn('class="op-grid" style="--opcols:2"', homepage)
        self.assertIn("grid-template-columns:repeat(var(--opcols,3),minmax(0,1fr))", build.CSS)


class TwoStoryRowsTests(unittest.TestCase):
    def test_two_story_section_renders_as_rows(self):
        built_at = datetime(2026, 9, 12, 9, tzinfo=timezone.utc)
        items = [_item(title=f"Israeli forces raid village number {i} in the northern West Bank",
                       pid=f"wb0000000{i}", link=f"https://example.com/wb{i}",
                       date=built_at - timedelta(hours=i + 1)) for i in range(12)]
        items += [_item(title=f"Gaza ministry reports hepatitis cases rising in shelter number {i}",
                        dek="Health officials counted the cases.", cat="health", score=5,
                        pid=f"he0000000{i}", link=f"https://example.com/he{i}",
                        date=built_at - timedelta(hours=20 + 10 * i)) for i in range(2)]
        homepage = build.render_page("en", items, built_at)
        block = homepage.split('id="health"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="rowlist"', block)
        self.assertEqual(block.count('<article class="rowcard">'), 2)
        self.assertNotIn('class="grid g2"', block)


class CountdownTests(unittest.TestCase):
    def test_vote_card_and_files_strip_count_the_same_days(self):
        built_at = datetime(2026, 9, 12, 20, 3, tzinfo=timezone.utc)
        tracker = _item(title="The coalition tracker: who leads, who gains, who falls",
                        link="original:israel-election-2026-tracker.en", original=True,
                        source="Times of Palestine", source_id="top-original",
                        cat="politics", pid="trk0000001", date=built_at - timedelta(hours=3))
        items = [tracker] + [_item(pid=f"wb0000000{i}", link=f"https://example.com/wb{i}",
                                   date=built_at - timedelta(hours=i + 1)) for i in range(5)]
        homepage = build.render_page("en", items, built_at)
        m = re.search(r'<span class="days"><b>(\d+)</b><i>DAYS</i>', homepage)
        self.assertIsNotNone(m)
        strip = build.file_day_label({"until": "2026-10-27"}, "en", built_at.date())
        self.assertEqual(f"{m.group(1)} DAYS", strip)
        self.assertEqual(m.group(1), "45")


class RoutingTests(unittest.TestCase):
    def test_a_reporter_called_rasha_is_not_a_rash(self):
        self.assertNotEqual(build.categorize(wire(
            "Gaza garden designer builds beauty amid war's rubble",
            "GAZA CITY, Gaza Strip /PNN - Report by Rasha Ahmad - In Gaza a garden "
            "designer is turning his talent into planted spaces.")), "health")
        self.assertEqual(build.categorize(wire(
            "Scabies and skin rashes spread through Gaza City shelters",
            "Health officials counted the cases.")), "health")

    def test_agriculture_is_not_culture(self):
        self.assertNotEqual(build.categorize(wire(
            "Gaza's chambers of commerce convene over deepening economic crisis",
            "Gaza's chambers of commerce, industry and agriculture held a dialogue "
            "titled 'In Gaza, an Economy Struggles to Survive'.")), "arts")
        self.assertEqual(build.categorize(wire(
            "Foreign currency rates stabilize against Israeli shekel today",
            "Agriculture exporters watched the shekel hold steady on Friday.")), "economy")
        self.assertEqual(build.categorize(wire(
            "Ramallah gallery opens a season of Palestinian culture and film",
            "The programme runs through October.")), "arts")

    def test_a_gaza_school_named_kafr_qasim_stays_in_gaza(self):
        self.assertNotEqual(build.categorize(wire(
            "مشروع غزي يحرز المركز الثاني في مسابقة ابتكار عربية",
            "حصد مشروع «حقيبة غزة الذكية»، التابع لمدرسة كفر قاسم الثانوية في مديرية "
            "التربية والتعليم غرب غزة، المركز الثاني في مسابقة «لنبتكر».", "ar")), "pal48")
        self.assertEqual(build.categorize(wire(
            "الشرطة الإسرائيلية تعتقل ثلاثة شبان في كفر قاسم بعد جريمة إطلاق نار",
            "", "ar")), "pal48")
        self.assertEqual(build.categorize(wire(
            "Follow-Up Committee calls a general strike over the crime wave",
            "Umm al-Fahm and Sakhnin closed their schools.")), "pal48")


if __name__ == "__main__":
    unittest.main()
