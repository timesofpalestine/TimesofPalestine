"""Desk meta-commentary must never publish as an article body.

Owner takedown 2026-08-16: six Arabic briefs ran bodies that narrated the
source material itself — «المادة المرسلة تتضمن عنواناً فقط دون نص خبري…» —
because the refusal screen lacked the Arabic desk-voice phrasings. Each
retracted body's lead phrasing must trip REFUSAL_RX forever, and ordinary
news prose must keep passing."""
import unittest

import build


META_BODIES = [
    # the six retracted bodies' opening phrasings, verbatim
    "المادة المرسلة تتضمن عنواناً فقط دون نص خبري أو تفاصيل تدعمه.",
    "لم تتضمّن المادة المرسلة من قناة «القسطل» على تيليغرام تفاصيل محددة",
    "المادة المرسلة تقتصر على عنوان واحد دون تفاصيل تفسيرية",
    "المادة المرسلة من حساب القسطل عبر تيليغرام تشير إلى اعتداءات",
    "المادة المرسلة عبارة عن مقدمة نصية افتتاحية لا تتضمن خبراً محدداً قابلاً للنشر كموجز صحفي.",
    "المادة المرسلة تحتوي على عنوان إشاري فحسب، من دون نص توضيحي",
    "لا تتوفر في المصدر بيانات عن التفاصيل الزمنية",
    "النشر الكامل للموجز يستلزم معلومات إضافية حول أطراف القضية",
]

REAL_PROSE = [
    "قالت وزارة الصحة إن المستشفى استقبل عشرين جريحاً منذ الفجر.",
    "أفاد شهود بأن القوات اقتحمت البلدة قبل منتصف الليل واعتقلت ثلاثة شبان.",
    "وأوضح المتحدث أن التفاصيل الكاملة ستعلن في مؤتمر صحفي غداً.",
    # 2026-08-18: bare «عنوان واحد» over-matched and cost the Yasmin Abu
    # Hassan feature its whole Arabic edition — this exact sentence stays legal.
    "ولخّص موقع «مدار الساعة» الأردني القوس كله في عنوان واحد: من طبخة كوسا باللبن إلى كتاب.",
    "واختصرت الصحيفة الحدث بعنوان واحد على صدر صفحتها الأولى.",
]


class ArabicMetaRefusalTest(unittest.TestCase):
    def test_every_retracted_meta_phrasing_trips_the_screen(self):
        for body in META_BODIES:
            self.assertIsNotNone(
                build.REFUSAL_RX.search(body),
                f"refusal screen missed desk meta-voice: {body[:60]}")

    def test_ordinary_news_prose_still_passes(self):
        for body in REAL_PROSE:
            self.assertIsNone(
                build.REFUSAL_RX.search(body),
                f"refusal screen over-matched real prose: {body[:60]}")

    def test_the_six_takedowns_stay_retracted(self):
        for pid in ("53ab09a3cc", "0b27c584e6", "bb71af3551",
                    "cdbc2183ca", "8e66be8ab8", "cb2e25be5e"):
            self.assertIn(pid, build.RETRACTED_PIDS)


if __name__ == "__main__":
    unittest.main()
