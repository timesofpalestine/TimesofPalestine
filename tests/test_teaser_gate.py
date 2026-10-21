"""A teaser is not a story (owner order 2026-10-15).

Zeteo's feed summary for its CBS piece only advertised the news ("explained
exactly why Netanyahu was removed… You also won't believe what she said about
the Palestinian death toll"). The briefs desk padded it into two paragraphs
that told the reader nothing and ended on the desk's own aside: "the specific
details of her comments were not elaborated in the summary provided". The
owner's verdict: never again. These cases pin the three nets that stop it —
the teaser skip before any model call, the NO_STORY sentinel, and the refusal
screen for copy that narrates the text the desk was handed — and the ordinary
news prose those nets must never catch.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("TOP_OFFLINE", "1")

import build

ZETEO_DEK = ("CBS News foreign editor Shayndi Raice explained exactly why "
             "Netanyahu was removed from an Oct. 7 script. You also won’t "
             "believe what she said about the Palestinian death toll in Gaza.")
LEAKED_BRIEF = ("Raice also addressed the Palestinian death toll in Gaza during "
                "the exchange, though the specific details of her comments were "
                "not elaborated in the summary provided.")


class TeaserSkipTests(unittest.TestCase):
    def test_zeteo_teaser_is_caught(self):
        self.assertTrue(build.is_teaser(
            "CBS foreign editor explains Netanyahu removal", ZETEO_DEK))

    def test_teaser_never_reaches_the_model(self):
        class Boom:
            @property
            def messages(self):
                raise AssertionError("a teaser must not buy a model call")
        item = {"pid": "25f8e7035e", "lang": "en", "source": "Zeteo",
                "title": "CBS foreign editor explains Netanyahu removal",
                "dek": ZETEO_DEK}
        self.assertIsNone(build.write_brief(Boom(), item))
        self.assertTrue(item["brief_refused"])

    def test_news_deks_are_not_teasers(self):
        for dek in (
            "Investigators are trying to find out how the fire started in the camp.",
            "The minister did not elaborate on the timing of the transfer.",
            "Police explained the closure as a security measure, residents said.",
            "اكتشف المزارعون كيف أتلف المستوطنون أشجار الزيتون صباح الأحد.",
        ):
            self.assertFalse(build.is_teaser("", dek), dek)


class SentinelTests(unittest.TestCase):
    def test_no_story_reply_publishes_nothing(self):
        reply = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="NO_STORY")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                  cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0))
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: reply))
        item = {"pid": "x", "lang": "en", "source": "Outlet",
                "title": "Minister says talks will resume", "dek": "A short item."}
        self.assertIsNone(build.write_brief(client, item))
        self.assertTrue(item["brief_refused"])

    def test_short_retry_note_offers_the_sentinel(self):
        short = [i for i in build.structure_issues("Too short.", "en")
                 if build._ISSUE_SHORT_RX.search(i)]
        self.assertIn("NO_STORY", build._diction_retry_note(short, "en"))
        short_ar = [i for i in build.structure_issues("قصير جداً.", "ar")
                    if build._ISSUE_SHORT_RX.search(i)]
        self.assertIn("NO_STORY", build._diction_retry_note(short_ar, "ar"))

    def test_prompts_name_the_sentinel(self):
        for lang in ("en", "ar"):
            self.assertIn("NO_STORY", build.BRIEF_SYSTEM[lang])


class RefusalScreenTests(unittest.TestCase):
    def test_leaked_aside_is_refused(self):
        self.assertTrue(build.REFUSAL_RX.search(LEAKED_BRIEF))
        for meta in (
            "Further details were not specified in the excerpt provided.",
            "The provided summary does not name the officials.",
            "لم تُذكر التفاصيل في الملخص المتاح.",
            "NO_STORY",
        ):
            self.assertTrue(build.REFUSAL_RX.search(meta), meta)

    def test_news_prose_passes(self):
        for prose in (
            "According to a summary provided to reporters, the cabinet approved the plan.",
            "The army did not elaborate on the circumstances of the arrest.",
            "The court issued a summary judgment on Tuesday.",
            "He did not specify how many prisoners would be released.",
        ):
            self.assertIsNone(build.REFUSAL_RX.search(prose), prose)


if __name__ == "__main__":
    unittest.main()
