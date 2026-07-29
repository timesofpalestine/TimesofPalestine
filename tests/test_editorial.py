import unittest
from datetime import datetime, timedelta, timezone

from editorial import apply_review_gate, classify_risk, cluster_duplicates


def story(source, title, link, dek="", lang="en", source_type="rss", original=False):
    return {
        "title": title,
        "dek": dek,
        "link": link,
        "source_url": link.rsplit("/", 1)[0],
        "source": source,
        "source_id": source.lower(),
        "source_type": source_type,
        "date": datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
        "modified": None,
        "lang": lang,
        "cat": "news",
        "original": original,
        "corrections": [],
    }


class EditorialTests(unittest.TestCase):
    def test_normalized_duplicates_preserve_related_publishers(self):
        left = story(
            "A", "Palestinian artists open a community exhibition",
            "https://a.test/story", "A summary")
        right = story(
            "B", "PALESTINIAN ARTISTS OPEN A COMMUNITY EXHIBITION!",
            "https://b.test/report", "Another summary")
        clustered, removed = cluster_duplicates([left, right])
        self.assertEqual(removed, 1)
        self.assertEqual(len(clustered[0]["corroborating_sources"]), 2)

    def test_risk_rules_cover_english_and_arabic_sensitive_claims(self):
        casualty = story(
            "A", "Five people killed in Gaza strike", "https://a.test/1")
        accusation = story(
            "B", "اتهامات فساد تطال مسؤولاً أمنياً", "https://b.test/2", lang="ar")
        telegram = story(
            "C", "Palestine update", "https://t.me/c/1", source_type="telegram")
        self.assertIn("casualty_claim", classify_risk(casualty))
        self.assertIn("accusation_or_serious_allegation", classify_risk(accusation))
        self.assertIn("citizen_or_social_source", classify_risk(telegram))
        self.assertIn(
            "casualty_claim",
            classify_risk(story(
                "D", "Five Palestinians died in Gaza overnight", "https://d.test/3")),
        )
        self.assertIn(
            "casualty_claim",
            classify_risk(story(
                "E", "وفاة خمسة فلسطينيين في غزة الليلة", "https://e.test/4", lang="ar")),
        )
        self.assertIn(
            "casualty_claim",
            classify_risk(story(
                "F", "Five Palestinians slain in Gaza", "https://f.test/5")),
        )
        self.assertIn(
            "casualty_claim",
            classify_risk(story(
                "G", "استشهاد خمسة فلسطينيين في غزة", "https://g.test/6", lang="ar")),
        )
        self.assertIn(
            "casualty_claim",
            classify_risk(story(
                "H", "مصرع خمسة فلسطينيين في غزة", "https://h.test/7", lang="ar")),
        )
        self.assertIn(
            "named_security_or_military_subject",
            classify_risk(story(
                "I", "الجيش يعلن تعيين إيال زامير رئيساً جديداً للأركان",
                "https://i.test/8", lang="ar")),
        )

    def test_contradictory_reports_are_not_clustered_as_corroboration(self):
        ordered = story(
            "A", "Residents ordered to evacuate Rafah district", "https://a.test/1")
        denied = story(
            "B", "Residents not ordered to evacuate Rafah district", "https://b.test/2")
        clustered, removed = cluster_duplicates([ordered, denied])
        self.assertEqual(removed, 0)
        self.assertEqual(len(clustered), 2)

    def test_exact_approval_is_invalidated_by_content_change(self):
        item = story(
            "A", "Five people killed in Gaza strike", "https://a.test/1",
            "The source reports five deaths.")
        _, held = apply_review_gate([item], {})
        fingerprint = held[0]["review_fingerprint"]
        approved, held = apply_review_gate(
            [item], {fingerprint: {"reviewer": "Editor", "at": "2026-07-29T13:00:00Z"}})
        self.assertEqual(len(approved), 1)
        item["dek"] = "The source now reports six deaths."
        approved, held = apply_review_gate(
            [item], {fingerprint: {"reviewer": "Editor", "at": "2026-07-29T13:00:00Z"}})
        self.assertEqual(len(approved), 0)
        self.assertEqual(len(held), 1)

    def test_all_repository_originals_require_review(self):
        item = story(
            "Times of Palestine", "A local analysis", "original:analysis",
            "Original body", original=True)
        self.assertIn("repository_original", classify_risk(item))


if __name__ == "__main__":
    unittest.main()
