"""Every section carries its own beat (owner order 2026-09-06).

After the Health & Healing audit the owner ordered every section checked:
"make sure that every section actually carries articles and items that
are related to that section". These cases are the real headlines that
leaked, with the section each now lands in; a new leak gets a new case
here, never a wider rule somewhere else.
"""
import json
import os
import unittest

os.environ.setdefault("TOP_OFFLINE", "1")

import build


def wire(title, dek="", lang="en"):
    return {"title": title, "dek": dek, "link": "https://example.com/s",
            "categories": [], "lang": lang}


class EconomyTests(unittest.TestCase):
    def test_economy_is_the_economy(self):
        self.assertEqual(build.categorize(wire(
            "Foreign currency rates stabilize against Israeli shekel today",
            "Foreign exchange rates held steady against the shekel on Friday.")), "economy")
        self.assertEqual(build.categorize(wire(
            "المالية تصرف رواتب الموظفين بنسبة 50% اليوم الأحد",
            "أعلنت وزارة المالية صرف الرواتب.", "ar")), "economy")

    def test_demolitions_and_humanitarian_copy_are_not_economy(self):
        self.assertNotEqual(build.categorize(wire(
            "Israeli forces demolish 1,059 Palestinian structures since year's start",
            "The demolished facilities include homes and economic structures.")), "economy")
        # «معبراً» ("expressing") once matched «معبر» (crossing).
        self.assertNotEqual(build.categorize(wire(
            "أبو عبيدة الناطق العسكري لكتائب القسام عبر عقدين",
            "شكّل ظهور الناطق زعيماً ناطقاً ومعبراً عن الخطاب الإعلامي.", "ar")), "economy")
        self.assertNotEqual(build.categorize(wire(
            "عائلة العرابيد تطالب بالكشف عن مصير ابنها المختطف",
            "طالبت العائلة المؤسسات الحقوقية والإنسانية بالتحرك العاجل.", "ar")), "economy")


class ArtsTests(unittest.TestCase):
    def test_world_central_kitchen_and_heritage_petroleum_are_not_culture(self):
        self.assertNotEqual(build.categorize(wire(
            "Germany demands Israel prosecute officials over Gaza kitchen workers' deaths",
            "The World Central Kitchen convoy was hit by three strikes.")), "arts")
        self.assertNotEqual(build.categorize(wire(
            "الغارديان: إسرائيل استهدفت قافلة المطبخ العالمي بتكتيك عسكري منهجي",
            "قال تحقيق إن استهداف قافلة المطبخ المركزي العالمي كان منهجياً.", "ar")), "arts")
        self.assertNotEqual(build.categorize(wire(
            "UAE and Swiss firms emerge as top crude suppliers to Israel",
            "Vitol and Heritage Petroleum FZCO have emerged as major suppliers.")), "arts")
        self.assertNotEqual(build.categorize(wire(
            "قوات الاحتلال تقتحم دوار السينما في جنين", "", "ar")), "arts")

    def test_the_arts_still_route(self):
        self.assertEqual(build.categorize(wire(
            "Palestinian artist Sliman Mansour dies at 79",
            "One of the leading figures in contemporary Palestinian art.")), "arts")
        self.assertEqual(build.categorize(wire(
            "وزارة الثقافة تختار فيلماً غزياً لتمثيل فلسطين بالأوسكار", "", "ar")), "arts")


class DiasporaTests(unittest.TestCase):
    def test_the_foreign_ministry_is_not_the_diaspora(self):
        self.assertNotEqual(build.categorize(wire(
            "الخارجية تطلع بعثات دبلوماسية على انتهاكات إسرائيل في قلنديا",
            "نظمت وزارة الخارجية والمغتربين الفلسطينية زيارة ميدانية.", "ar")), "diaspora")
        self.assertNotEqual(build.categorize(wire(
            "عائلة العرابيد تحمّل الاحتلال مسؤولية سلامة الضابط المختطف",
            "عقبت عائلة العرابيد في الوطن والشتات على الجريمة.", "ar")), "diaspora")

    def test_the_diaspora_still_routes(self):
        self.assertEqual(build.categorize(wire(
            "أجيال الشتات تحافظ على الهوية الفلسطينية رغم البعد الجغرافي", "", "ar")), "diaspora")
        self.assertEqual(build.categorize(wire(
            "Palestinian-American documents settler siege on West Bank home")), "diaspora")


class AccountabilityTests(unittest.TestCase):
    def test_rhetoric_and_spoiled_food_are_not_corruption(self):
        self.assertNotEqual(build.categorize(wire(
            "Turkey condemns Israeli allegations against Erdogan as cowardly propaganda",
            "The ministry called them reflections of cowardly and corrupt propaganda.")),
            "accountability")
        self.assertNotEqual(build.categorize(wire(
            "مباحث رفح تضبط 327 كغم مواد غذائية فاسدة",
            "ضبطت المباحث مواد ظهرت عليها علامات الفساد.", "ar")), "accountability")
        self.assertNotEqual(build.categorize(wire(
            "Hezbollah says negotiations shield Israeli occupation from accountability")),
            "accountability")

    def test_corruption_and_its_institutions_route(self):
        self.assertEqual(build.categorize(wire(
            "أمان يطالب بإلغاء شرط السلامة الأمنية للحقوق العامة",
            "طالب الائتلاف من أجل النزاهة والمساءلة الحكومة بإلغاء الشرط.", "ar")),
            "accountability")
        self.assertEqual(build.categorize(wire(
            "Anti-corruption commission charges former minister with embezzlement")),
            "accountability")


class ArabSupportTests(unittest.TestCase):
    def test_unrwa_name_and_a_bank_called_santander_are_not_arab_support(self):
        self.assertNotEqual(build.categorize(wire(
            "مصر تدين استيلاء إسرائيل على مركز قلنديا المهني",
            "أدانت مصر استيلاء الاحتلال على معهد قلنديا التابع لوكالة الأمم المتحدة "
            "لإغاثة وتشغيل اللاجئين الفلسطينيين.", "ar")), "arabaid")
        self.assertNotEqual(build.categorize(wire(
            "متضامنون يحتجون على استثمارات مصرف سانتاندير في شركات أسلحة",
            "نظّم متضامنون مع فلسطين احتجاجًا حاشدًا.", "ar")), "arabaid")
        self.assertNotEqual(build.categorize(wire(
            "UNRWA halts emergency cash aid to six Palestinian refugee camps in Lebanon",
            "The agency excluded six camps from emergency cash assistance.")), "arabaid")
        self.assertNotEqual(build.categorize(wire(
            "منصات رقمية تشهد تضامناً مع ضحايا حرائق الجزائر", "", "ar")), "arabaid")

    def test_arab_support_still_routes(self):
        self.assertEqual(build.categorize(wire(
            "الكويت تمول إعادة إعمار مدرسة فلسطينية بسوريا بـ 2.5 مليون دولار",
            "وقّع الصندوق الكويتي اتفاقية منحة مع الأونروا.", "ar")), "arabaid")
        self.assertEqual(build.categorize(wire(
            "Egypt receives 25 patients evacuated from Gaza",
            "Patients and family members were evacuated to Egypt.")), "arabaid")


class SportsTests(unittest.TestCase):
    def test_elected_councils_raids_and_executions_are_not_sport(self):
        # «المنتخبين» (the elected) is not «المنتخب» (the national team).
        self.assertNotEqual(build.categorize(wire(
            "عباس يستقبل رئيس وأعضاء بلدية طوباس المنتخبين", "", "ar")), "sports")
        self.assertEqual(build.categorize(wire(
            "قوات الاحتلال تقتحم محيط ملعب البلدية غرب نابلس", "", "ar")), "westbank")
        # «تصفيات جسدية» (executions) is not «تصفيات آسيا» (the qualifiers).
        self.assertNotEqual(build.categorize(wire(
            "هآرتس تكشف إدارة الاحتلال لميليشيات بغزة لتهجير المدنيين",
            "نفذت الميليشيات تصفيات جسدية بحق مدنيين.", "ar")), "sports")

    def test_outlet_boilerplate_does_not_make_real_madrid_palestinian(self):
        it = wire("ريال مدريد يواجه ملقا في الجولة الثالثة للدوري الإسباني",
                  "متابعة/ فلسطين أون لاين: يستضيف ريال مدريد نظيره ملقا في تمام "
                  "الساعة السادسة بتوقيت فلسطين.", "ar")
        self.assertEqual(build.categorize(it), "sports")
        self.assertFalse(build.sports_is_palestinian(it))
        home = wire("الفدائي يلعب ثلاث مباريات ودية في الصين",
                    "يشارك المنتخب الوطني الفلسطيني في دورة ودية.", "ar")
        self.assertEqual(build.categorize(home), "sports")
        self.assertTrue(build.sports_is_palestinian(home))


class Pal48Tests(unittest.TestCase):
    def test_arraba_near_jenin_is_the_west_bank(self):
        self.assertEqual(build.categorize(wire(
            "Israeli forces uproot dozens of olive trees near Jenin",
            "Along the road connecting the towns of Arraba and Ya'bad, southwest of Jenin.")),
            "westbank")

    def test_the_beat_still_routes(self):
        self.assertEqual(build.categorize(wire(
            "Higher Follow-Up Committee calls a general strike in Umm al-Fahm")), "pal48")


class HerStoryTests(unittest.TestCase):
    def test_tallies_that_list_women_are_not_her_story(self):
        self.assertEqual(build.categorize(wire(
            "مركز فلسطين يوثّق 500 اعتقال في أغسطس بينهم قاصرون ونساء",
            "واصلت سلطات الاحتلال سياسة المداهمات والاعتقال.", "ar")), "prisoners")
        self.assertNotEqual(build.categorize(wire(
            "Resistance arrests three alleged collaborators during Gaza kidnapping plot",
            "A source said three collaborators, including a woman, were detained.")), "women")
        # «مطالبة» (demanded) is not «طالبة» (a student).
        self.assertNotEqual(build.categorize(wire(
            "بريطانيا مطالبة بمواجهة مشروع الاستيطان إي 1",
            "يدعو المقال بريطانيا إلى التحرك ضد عنف المستوطنين.", "ar")), "women")

    def test_she_is_the_subject(self):
        self.assertEqual(build.categorize(wire(
            "طبيبة فلسطينية تُصاب بنوبة قلبية أثناء اعتقالها",
            "أصيبت الطبيبة بنوبة قلبية أثناء اعتقال قوة إسرائيلية لها.", "ar")), "women")
        self.assertEqual(build.categorize(wire(
            "الاحتلال يفرج عن الأسيرة آية فقهاء بعد ستة أشهر اعتقال", "", "ar")), "women")


class PrisonersTests(unittest.TestCase):
    def test_field_arrests_foreign_detainees_and_courts_abroad_are_not_the_file(self):
        self.assertNotEqual(build.categorize(wire(
            "Israeli forces arrest youth in central Tulkarem",
            "The detainees were taken to an unknown destination.")), "prisoners")
        self.assertNotEqual(build.categorize(wire(
            "Israel releases five Lebanese detainees from southern Lebanon")), "prisoners")
        self.assertNotEqual(build.categorize(wire(
            "متظاهرون في برلين يطالبون بوقف تصدير الأسلحة لإسرائيل",
            "طالب المتظاهرون بالإفراج عن الأسرى.", "ar")), "prisoners")
        self.assertNotEqual(build.categorize(wire(
            "San Francisco court jails seven pro-Palestine protesters for 30 days")),
            "prisoners")

    def test_the_file_still_routes(self):
        self.assertEqual(build.categorize(wire(
            "Israel issues administrative detention orders for 45 Palestinians")), "prisoners")
        self.assertEqual(build.categorize(wire(
            "الاحتلال يفرج عن الأسير مالك القواسمة من الخليل", "", "ar")), "prisoners")
        self.assertEqual(build.categorize(wire(
            "نجوم هوليوود يطالبون الاحتلال بالإفراج عن البرغوثي",
            "وقّع فنانون رسالة مفتوحة.", "ar")), "prisoners")


class ArchiveRefileTests(unittest.TestCase):
    def rec(self, **kw):
        base = {"pid": "abc", "title": "t", "dek": "", "cat": "health", "link": "",
                "source_id": "shehab-en", "original": False}
        base.update(kw)
        return base

    def test_a_strike_filed_under_health_moves_to_gaza(self):
        r = self.rec(title="Israeli airstrike kills three-year-old and another in central Gaza",
                     dek="Two people were killed in a strike on a tent.")
        self.assertEqual(build.refile_archived([r]), 1)
        self.assertEqual(r["cat"], "gaza")

    def test_a_story_its_section_still_claims_stays(self):
        r = self.rec(title="Gaza hospital exhausts cancer drug supplies")
        self.assertEqual(build.refile_archived([r]), 0)
        self.assertEqual(r["cat"], "health")

    def test_originals_pinned_feeds_and_unclaimed_stories_never_move(self):
        keep = [
            self.rec(title="Israeli airstrike kills two in Gaza", original=True),
            self.rec(title="Israeli airstrike kills two in Gaza", source_id="gnews-health"),
            self.rec(title="A quiet day", cat="economy"),  # no rule claims it → stays
            self.rec(title="Israeli airstrike kills two", cat="israelipress"),
        ]
        self.assertEqual(build.refile_archived(keep), 0)
        self.assertEqual([r["cat"] for r in keep],
                         ["health", "health", "economy", "israelipress"])


class FieldReportsTests(unittest.TestCase):
    def test_telegram_news_networks_are_wires_not_field_dispatches(self):
        feeds = json.load(open("feeds.json", encoding="utf-8"))
        by_id = {f["id"]: f for f in feeds["ar"]}
        for fid in ("tg-qudsn", "tg-qastal", "tg-palinfo", "tg-arabi21"):
            self.assertTrue(by_id[fid].get("wire"), fid)


if __name__ == "__main__":
    unittest.main()
