"""Wire-fetch resilience: transient HTTP failures retry, mangled XML parses.

Site sweep 2026-08-19: one production run saw eight outlets 403 (Cloudflare
and Substack rejecting the runner IP), one 429, and the Amnesty AR feed die
on 'not well-formed (invalid token)'. fetch_bytes now retries once on
transient codes, and parse_xml's lenient pass escapes bare '<' in text.
"""
import unittest
import urllib.error
from unittest import mock

import build


def _http_error(code):
    return urllib.error.HTTPError("https://feeds.example/rss", code, "x", {}, None)


class FetchRetryTests(unittest.TestCase):
    def test_transient_403_retries_once_then_succeeds(self):
        body = mock.MagicMock()
        body.__enter__.return_value.read.return_value = b"<rss/>"
        body.__enter__.return_value.headers = {}
        with mock.patch.object(build, "safe_urlopen",
                               side_effect=[_http_error(403), body]) as opener, \
             mock.patch.object(build.time, "sleep"):
            self.assertEqual(build.fetch_bytes("https://feeds.example/rss"), b"<rss/>")
            self.assertEqual(opener.call_count, 2)

    def test_second_failure_still_raises_for_feed_health(self):
        with mock.patch.object(build, "safe_urlopen",
                               side_effect=[_http_error(429), _http_error(429)]), \
             mock.patch.object(build.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                build.fetch_bytes("https://feeds.example/rss")

    def test_hard_404_does_not_retry(self):
        with mock.patch.object(build, "safe_urlopen",
                               side_effect=[_http_error(404)]) as opener:
            with self.assertRaises(urllib.error.HTTPError):
                build.fetch_bytes("https://feeds.example/rss")
            self.assertEqual(opener.call_count, 1)


class LenientXmlTests(unittest.TestCase):
    def test_bare_angle_bracket_in_text_parses(self):
        raw = ("<?xml version=\"1.0\"?><rss><channel><item>"
               "<title>aid trucks < 20 a day</title>"
               "</item></channel></rss>").encode("utf-8")
        root = build.parse_xml(raw)
        self.assertIn("< 20 a day", "".join(root.itertext()))

    def test_wellformed_feed_unaffected(self):
        raw = b"<?xml version=\"1.0\"?><rss><channel><title>ok</title></channel></rss>"
        self.assertEqual(build.parse_xml(raw).tag, "rss")


if __name__ == "__main__":
    unittest.main()
