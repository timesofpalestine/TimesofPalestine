"""The x-fetch link resolver: ID parsing and log formatting, offline.

The workflow's whole value is that the session can trust what the job log
prints — so the ID extraction and the delimited output format are pinned.
"""
import io
import unittest
from unittest import mock

import x_fetch


class IdParsingTests(unittest.TestCase):
    def test_full_url_with_params(self):
        rc = self._run(["https://x.com/amnestyusa/status/2090016023441252513?s=46"])
        self.assertIn("=== X POST 2090016023441252513 ===", rc)

    def test_bare_id_and_dedupe(self):
        rc = self._run(["2090016023441252513 2090016023441252513"])
        self.assertEqual(rc.count("=== X POST"), 1)

    def test_no_id_fails_loudly(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(x_fetch.main(["not a link"]), 1)

    def _run(self, argv):
        out = io.StringIO()
        with mock.patch.object(x_fetch, "fetch",
                               return_value={"author": "A (@a)", "date": "d",
                                             "text": "t", "photos": [],
                                             "videos": [], "quoted": "",
                                             "via": "test"}), \
             mock.patch("sys.stdout", new=out):
            x_fetch.main(argv)
        return out.getvalue()


class OutputTests(unittest.TestCase):
    def test_error_posts_are_reported_not_fatal(self):
        out = io.StringIO()
        with mock.patch.object(x_fetch, "fetch",
                               return_value={"error": "HTTP 404"}), \
             mock.patch("sys.stdout", new=out):
            rc = x_fetch.main(["1234567890123456789"])
        self.assertEqual(rc, 1)
        self.assertIn("ERROR: could not fetch", out.getvalue())


if __name__ == "__main__":
    unittest.main()
