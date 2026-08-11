"""The Hebrew-first wire must parse both feed dialects and never crash the sweep."""
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import israeli_press_fetch as wire  # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>חדשות</title>
<item>
 <title><![CDATA[הקבינט יתכנס הערב לדיון על מתווה עזה]]></title>
 <link>https://example.co.il/article/1</link>
 <pubDate>Fri, 07 Aug 2026 06:10:00 +0300</pubDate>
 <description><![CDATA[<p>דיון על <b>המתווה</b> בן 15 הנקודות.</p>]]></description>
</item>
<item>
 <title>כותרת ישנה מאוד</title>
 <link>https://example.co.il/article/2</link>
 <pubDate>Mon, 01 Jan 2024 00:00:00 +0200</pubDate>
 <description>ארכיון</description>
</item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>English wire</title>
<entry>
 <title>Cabinet convenes on Gaza roadmap</title>
 <link href="https://example.com/a/1"/>
 <updated>2026-08-07T05:00:00Z</updated>
 <summary>The fifteen-point plan discussion.</summary>
</entry>
</feed>"""


class ParseTests(unittest.TestCase):
    def test_rss_hebrew_items_parse_with_clean_text(self):
        items = wire.parse_feed(RSS.encode("utf-8"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "הקבינט יתכנס הערב לדיון על מתווה עזה")
        self.assertNotIn("<", items[0]["summary"])
        self.assertEqual(items[0]["when"].tzinfo, timezone.utc)

    def test_atom_items_parse(self):
        items = wire.parse_feed(ATOM.encode("utf-8"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://example.com/a/1")
        self.assertEqual(items[0]["when"],
                         datetime(2026, 8, 7, 5, 0, tzinfo=timezone.utc))

    def test_html_entities_in_xml_do_not_kill_the_feed(self):
        """Think-tank feeds ship WordPress entities XML rejects — parse anyway."""
        raw = ('<?xml version="1.0"?><rss version="2.0"><channel><item>'
               '<title>Gaza&nbsp;file &amp; the &rsquo;deal&rsquo;</title>'
               '<link>https://example.org/1</link>'
               '<pubDate>Mon, 10 Aug 2026 10:00:00 +0000</pubDate>'
               '<description>Brookings &mdash; analysis</description>'
               '</item></channel></rss>').encode("utf-8")
        items = wire.parse_feed(raw)
        self.assertEqual(len(items), 1)
        self.assertIn("&", items[0]["title"])
        self.assertNotIn("&amp;", items[0]["title"])
        self.assertNotIn("&nbsp;", items[0]["title"])
        self.assertIn("—", items[0]["summary"])

    def test_malformed_feed_raises_and_is_survivable(self):
        with self.assertRaises(Exception):
            wire.parse_feed(b"this is not xml")

    def test_cli_exits_zero_even_with_unreachable_feeds(self, ):
        feeds = {"feeds": [{"outlet": "Dead", "lang": "he",
                            "url": "http://127.0.0.1:1/none.xml"}]}
        tmp = Path(__file__).parent / "fixtures" / "_press_feeds_tmp.json"
        tmp.write_text(json.dumps(feeds), encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(Path(wire.__file__)), "--feeds", str(tmp)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Israeli press wire", proc.stdout)
        finally:
            tmp.unlink(missing_ok=True)


class FeedManifestTests(unittest.TestCase):
    """The shipped source list is editorial config — keep it well formed."""

    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "editorial" / "israeli-press-feeds.json"
        self.feeds = json.loads(path.read_text(encoding="utf-8"))["feeds"]

    def test_every_feed_has_outlet_lang_and_https_url(self):
        for feed in self.feeds:
            self.assertTrue(feed.get("outlet"), feed)
            self.assertIn(feed.get("lang"), {"he", "en"}, feed)
            self.assertTrue(feed.get("url", "").startswith("https://"), feed)

    def test_outlet_labels_and_urls_are_unique(self):
        labels = [f["outlet"] for f in self.feeds]
        urls = [f["url"] for f in self.feeds]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(urls), len(set(urls)))

    def test_hebrew_sources_lead_the_list(self):
        """Owner order 2026-08-07: the desk reads Hebrew first."""
        langs = [f["lang"] for f in self.feeds]
        self.assertEqual(langs[0], "he")
        self.assertGreater(langs.count("he"), langs.count("en"))
        self.assertNotIn("he", langs[langs.index("en"):])


if __name__ == "__main__":
    unittest.main()
