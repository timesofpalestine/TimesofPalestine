#!/usr/bin/env python3
"""
Times of Palestine — static site builder (zero dependencies, Python 3.9+).

Fetches live RSS/Atom feeds from Palestinian & regional outlets, normalizes,
filters for Palestine relevance, categorizes, dedupes, and renders bilingual
(EN/AR) pages into dist/. Designed to run unattended on a schedule
(GitHub Actions) with zero human management.

Design language: Politico's authority (sharp serif headlines, black masthead,
timestamped "Latest" rail) + Axios's clarity (clean cards, whitespace) +
Palestinian flag palette as restrained accents. CSS logical properties make
the Arabic page mirror natively (RTL).
"""
import concurrent.futures
import functools
import gzip
import hashlib
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from zoneinfo import ZoneInfo

from editorial import (
    apply_review_gate, cluster_duplicates, load_reviews,
    review_gate_mode, sanitized_review_queue,
)
from publishing import (
    BuildHealth, PublishingError, canonicalize_url, is_http_url, is_public_http_url,
    load_editorial_json, load_media_manifest, media_rights_for, parse_timestamp,
    safe_urlopen, story_file_name, story_short_path, story_url_path, utc_iso,
    validate_corrections, validate_feed_config, validate_story,
)

ROOT = Path(__file__).parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 TimesOfPalestine/1.0")
GAZA = ZoneInfo("Asia/Gaza")

# Anonymous tip line — the newsroom's Signal account (username TOP.972).
# Link decoded from the official Signal share QR; signal-qr.png in the repo root
# is the matching scannable code, copied into dist/ at build time.
SIGNAL_URL = "https://signal.me/#eu/0_b-q0RDCIq5joH5eX1lR_jVWkiLrah-MdXuqpiCawImwuEDAfdN1Z14HJk-6mRg"
SIGNAL_USERNAME = "@TOP.972"; TELEGRAM_BOT_URL = "https://t.me/TOPnewsdeskbot"; TELEGRAM_BOT_NAME = "@TOPnewsdeskbot"  # tips go to the bot, not the channel. Subscribe-with-Google removed 2026-08-02 (owner: no email pop-up on the site).
TELEGRAM_CHANNEL_URL = "https://t.me/timesofpalestin"  # public delivery channel, for reader follow links
BASE_URL = "https://timesofpalestine.com"

TOP_SOURCE = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}
ARABIC_CHARS_RX = re.compile(r"[؀-ۿ]")


def remote_media_mode():
    mode = os.environ.get("TOP_REMOTE_MEDIA", "source").strip().lower()
    if mode not in {"source", "rights-only"}:
        raise PublishingError("TOP_REMOTE_MEDIA must be 'source' or 'rights-only'")
    return mode

# ---------- TOP Briefs: original newsdesk summaries, written by Claude ----------
# Optional layer: runs only when ANTHROPIC_API_KEY is set (GitHub secret) and the
# `anthropic` package is installed. Every failure falls back to the feed summary —
# the site always publishes. Briefs are cached by story id so nothing is written twice.
BRIEFS_MODEL = "claude-haiku-4-5"
MAX_BRIEFS_PER_RUN = 40          # cost ceiling per build
BRIEFS_CACHE = ROOT / "briefs-cache.json"
# Style generations: wire3 = wire attribution + short headline (2026-07-30);
# wire4 = human-register prompt + diction gate; wire5 = pacing rules — 2-3
# short paragraphs, no stubs, no wall-of-text blocks (owner order 2026-08-03).
# Bumping this queues every cached brief for a progressive restyle.
BRIEF_STYLE = "wire5"

BRIEF_SYSTEM = {
    "en": (
        "You are the newsdesk of Times of Palestine, an independent digital newsroom. "
        "Write an original news brief in English based ONLY on the source material provided: "
        "2-3 short paragraphs separated by blank lines — 2-4 sentences and at most 70 words "
        "per paragraph, 100-170 words total; never a single-block reply and never a "
        "two-sentence stub. Straight news style: lead with the most "
        "important fact, then key details and context. Neutral, precise, professional; no "
        "personal attacks, no editorializing, no first person. "
        "Write like a seasoned wire editor, not a language model: vary sentence rhythm, "
        "prefer concrete verbs and specific facts, and never reach for stock analytic "
        "diction — no 'delve', 'underscore', 'highlights the importance', 'it is worth "
        "noting', 'in a significant development', 'serves as a reminder', 'sheds light "
        "on', 'a testament to'. End on a reported fact, never on a sentence assessing "
        "what the story means. Never invent names, numbers, "
        "quotes, or details that are not in the source material; if the material is only a "
        "headline, still write two short paragraphs (about 90-120 words) unpacking who, what, "
        "where and the immediate context the headline itself carries — without inventing any "
        "fact it does not imply. "
        "Never refuse, and never comment on the material, these instructions, or yourself. "
        "Never say that details, information, or material are missing, unavailable, or not "
        "provided — simply omit what you do not know and let the reader decide. "
        "Attribute wire-style: name the OUTLET given in the material exactly once, inside "
        "the sentence carrying the most important claim — e.g. ', the Ma'an news agency "
        "reported' or 'according to Al Jazeera'. If the OUTLET is given as '(agency wire)', "
        "name no outlet at all. Never mention websites, links, or where to read more. "
        "Begin your reply with a single line 'HEADLINE: <your headline>' — YOUR OWN "
        "headline for the story, never the source's: one short complete sentence, at "
        "most 9 words, no colon-subtitle, no trailing ellipsis, front-page register. "
        "The headline is ACTIVE VOICE and names WHO did WHAT to WHOM — the actor the "
        "reporting identifies is the grammatical subject. Never passive ('was killed', "
        "'is seen'), never agentless hedges ('changes hands', 'comes under fire', "
        "'faces pressure') when the actor is known. "
        "Then a blank line, then the brief text, paragraphs separated by blank lines."
    ),
    "ar": (
        "أنت غرفة أخبار «تايمز أوف فلسطين»، منصة إخبارية رقمية مستقلة. اكتب موجزاً إخبارياً "
        "أصلياً باللغة العربية بالاعتماد حصراً على المواد المصدرية المرفقة: فقرتان إلى ثلاث فقرات "
        "قصيرة يفصل بينها سطر فارغ — من جملتين إلى أربع ولا تتجاوز الفقرة 70 كلمة، "
        "و100-170 كلمة إجمالاً؛ لا ترد أبداً بكتلة نصية واحدة ولا بموجز من جملتين. "
        "أسلوب خبري مباشر: ابدأ بأهم معلومة ثم التفاصيل والسياق. "
        "اكتب عربيةً صحفيةً أصيلة بسجلّ الجزيرة نت وعرب 48: افتتاحات فعلية، وروابط عربية "
        "(فيما، إذ، في حين، غير أنّ) لا ترجمة حرفية لتراكيب إنجليزية، وعلامتا الاقتباس «»، "
        "ويجب ألا يشعر القارئ بجملة إنجليزية تحت النص. "
        "اكتب كمحرر وكالة متمرس لا كنموذج آلي: نوّع إيقاع الجمل، ودقّق في اختيار الأفعال — "
        "فعل التسليم «سلّم/سلّمت» وليس «أسلم» التي تعني اعتنق الإسلام. ممنوع: «قام بـ» "
        "(استعمل الفعل مباشرة: قصف، اعتقل، سلّم)، و«تم/تمت» مع المصدر («تم الاعتقال»)، "
        "وحشو مثل «يُذكر أن» و«تجدر الإشارة» و«الجدير بالذكر». اختم بمعلومة مُبلّغ عنها "
        "لا بجملة تقييم ختامية. "
        "لغة محايدة دقيقة مهنية؛ لا إساءات شخصية ولا إنشاء ولا ضمير متكلم. لا تخترع أسماء أو "
        "أرقاماً أو اقتباسات أو تفاصيل غير واردة في المصدر؛ وإذا كانت المادة مجرد عنوان فاكتب "
        "فقرتين قصيرتين (نحو 90-120 كلمة) تفكّان ما يحمله العنوان — من وماذا وأين وسياقه "
        "المباشر — من دون اختراع أي واقعة لا يدل عليها. لا ترفض أبداً، ولا تعلق على المادة "
        "أو على هذه التعليمات أو على نفسك. انسب الخبر بأسلوب الوكالات: اذكر اسم المصدر الوارد في "
        "المادة مرة واحدة فقط داخل الجملة التي تحمل أهم معلومة — مثل «بحسب وكالة معاً» أو «كما أفادت "
        "الجزيرة». وإذا كان المصدر «(agency wire)» فلا تذكر أي وسيلة إعلامية. لا تذكر أبداً موقعاً إلكترونياً "
        "أو أين يمكن قراءة المزيد. لا تقل أبداً إن التفاصيل أو المعلومات غير متوفرة أو غير واردة — "
        "اكتفِ بما تعرفه واترك للقارئ أن يقرر. ابدأ ردّك بسطر واحد «HEADLINE: <العنوان>» — "
        "عنوانك أنت لا عنوان المصدر: جملة واحدة قصيرة مكتملة، تسع كلمات على الأكثر، بلا نقاط "
        "حذف، بأنماط الصفحات الأولى العربية (جملة فعلية، أو الفاصل «..»، أو النسبة بنقطتين، أو "
        "سؤال مباشر). العنوان بصيغة المبني للمعلوم دائماً ويسمّي الفاعل صراحةً: مَن فعل ماذا وبمَن — "
        "لا مبني للمجهول أبداً («قُتل»، «استُهدف») ولا صياغات تخفي فاعلاً معروفاً؛ إذا حدّد الخبر "
        "الفاعل فاجعله فاعل الجملة. ثم سطر فارغ، ثم نص الموجز والفقرات مفصولة بسطر فارغ."
    ),
}
MAX_AGE_HOURS = 72
PER_SOURCE_CAP = 14

FEEDS_PATH = Path(os.environ.get("TOP_FEEDS_FILE", ROOT / "feeds.json"))
if not FEEDS_PATH.is_absolute():
    FEEDS_PATH = ROOT / FEEDS_PATH
FEEDS = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
# Story ids the owner has ordered removed; blocked no matter which feed or
# radar route resurfaces the underlying link.
RETRACTED_PIDS = {"23ffbc910f", "7b5ecb12e4", "4b6ac6121b", "33a0debafc"}
validate_feed_config(FEEDS)
MEDIA_RIGHTS = load_media_manifest(ROOT / "media-rights.json")
CORRECTIONS = load_editorial_json(
    ROOT / "editorial" / "corrections.json", {"version": 1, "stories": {}})
if CORRECTIONS.get("version") != 1 or not isinstance(CORRECTIONS.get("stories"), dict):
    raise PublishingError("corrections ledger must have version 1 and stories object")
HEALTH = None
ORIGINAL_CATEGORIES = {
    "gaza", "westbank", "politics", "economy", "accountability", "research",
    "bitcoin", "diaspora", "arts", "sports", "social", "opinion", "news", "humans",
    "health", "archive", "arabaid", "women",
}
ORIGINAL_IMG_MD_RX = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
ORIGINAL_BODY_STATS = {}

# ---------- text utilities ----------

TAG_RX = re.compile(r"<[^>]+>")

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", text)
    text = TAG_RX.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

BOILERPLATE_RX = re.compile(
    r"(the post .{0,250}?appeared first on .{0,120}?\.|read more(:| at| on)?\s*$|"
    r"the post .{0,250}$|continue reading.*$|\[…\]|\[\.\.\.\])", re.I)

def clean_dek(text):
    t = BOILERPLATE_RX.sub("", text)
    # HRW-style photo captions: "Click to expand Image <caption> © 2026 X/AP Photo (City) – "
    m = re.search(r"click to expand image.{0,400}?[–—]\s", t, flags=re.I | re.S)
    if m:
        t = t[:m.start()] + t[m.end():]
    t = re.sub(r"click to expand image\s*", "", t, flags=re.I)
    t = re.sub(r"©\s?\d{4}[^.]{0,90}?(photo|images|sipa|afp|reuters|getty|anadolu)\b\.?", "", t, flags=re.I)
    t = re.sub(r"https?://\S+", "", t)                  # bare links
    t = re.sub(r"(?:#[\w؀-ۿ]+\s*){2,}", "", t)  # hashtag runs
    t = re.sub(r"watch more here:?\s*", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .·|-—")
    return t + "." if t else ""

# Arabic outlets often string several stories into one headline separated by "..",
# which renders as five or six lines. Keep at most two sentences and always end on a
# word boundary, so a headline is never chopped mid-word.
SENT_END_RX = re.compile(r"\.{2,}|[.!?؟؛](?=\s|$)")

_ABBREV_RX = re.compile(
    r"(?:\b(?:St|Dr|Mr|Mrs|Ms|Prof|Rev|Sen|Rep|Gen|Col|Lt|Sgt|Jr|Sr|vs|etc|Inc|Ltd|Co|"
    r"U\.S|U\.N|U\.K|E\.U|D\.C|a\.m|p\.m|No|Vol|Fig)\.$)", re.I)

def headline(text, limit=150):
    text = re.sub(r"\s+", " ", text).strip().rstrip("…").strip()
    # A "sentence end" inside a headline must not be an abbreviation dot
    # ("St. Louis", "Dr. Ahmad") and must leave a real headline behind.
    ends = [m.end() for m in SENT_END_RX.finditer(text)
            if m.end() >= 20 and not _ABBREV_RX.search(text[:m.end()])]
    for e in ([ends[1]] if len(ends) > 1 else []) + ([ends[0]] if ends else []):
        if e <= limit:
            text = text[:e]
            break
    if len(text) > limit:
        cut = text[:limit]
        sp = cut.rfind(" ")
        return (cut[:sp] if sp > limit * 0.6 else cut).rstrip(" .،,;؛-—·") + "…"
    return text.strip(" .،,;؛-—·")

def truncate(text, n):
    if len(text) <= n:
        return text
    cut = text[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n - 30 else cut) + "…"

def norm_title(t):
    return re.sub(r"[\W_]+", " ", strip_html(t).lower(), flags=re.UNICODE).strip()


def meta_desc(text, limit=155):
    """Meta/OG description cut at a word boundary — a hard slice ships
    'without cen' to every search snippet and link preview."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    sp = cut.rfind(" ")
    if sp > limit - 40:
        cut = cut[:sp]
    return cut.rstrip(" ,;:·—–-") + "…"

esc = lambda s: html.escape(s or "", quote=True)


def summary_html(text):
    """Render summary inline Markdown through the escape-first long-form parser."""
    return __import__("longform").inline_html(text)


def summary_text(text):
    """Return readable plain text for summary metadata and syndication."""
    return __import__("longform").inline_text(text)


# ---------- relevance & categorization ----------

PALESTINE_RX = re.compile(
    r"palestin|gaza|west bank|jerusalem|bethlehem|ramallah|rafah|khan younis|jenin|nablus|hebron|"
    r"tulkarem|unrwa|al-aqsa|aqsa|intifada|nakba|settler|"
    r"netanyahu|\bicc\b|\bicj\b|\bhague\b|"
    r"فلسطين|الفلسطيني|غزة|غزّة|الضفة|القدس(?! العربي)|رام الله|رفح|خان يونس|جنين|نابلس|الخليل|"
    r"طولكرم|أونروا|الأونروا|الأقصى|الاحتلال|مستوطن|النكبة|"
    r"نتنياهو|الجنائية الدولية|محكمة العدل الدولية|لاهاي", re.I)

# ---- editorial focus topics: these get ranking boosts and dedicated sections ----

# Palestinian Christians — churches, clergy, settler attacks on Christian communities.
# (Bare Arabic "دير" deliberately omitted: Deir al-Balah / Deir Dibwan etc. are place names.)
CHRISTIANS_RX = re.compile(
    r"christian|church|monaster|priest|pastor|patriarch|\bnun\b|parish|holy sepulchre|"
    r"nativity|orthodox|catholic|evangelical|taybeh|holy land|"
    r"مسيحي|المسيحيين|مسيحيو|مسيحيي|كنيسة|كنائس|كنسي|رهبان|راهب|كاهن|بطريرك|بطريركية|"
    r"الأرثوذكس|الكاثوليك|اللاتينية|عيد الميلاد|كنيسة المهد|الطيبة", re.I)

# The Palestinian diaspora — communities, refugees and second generations worldwide.
DIASPORA_RX = re.compile(
    r"diaspora|palestinian[- ](?:american|british|canadian|australian|european)s?|"
    r"palestinians abroad|palestinian expat|refugees? in (?:lebanon|jordan|syria|europe|chile|"
    r"the us|america)|"
    r"الشتات|الجالية الفلسطينية|جاليات|مغترب|فلسطينيو الخارج|فلسطينيي الخارج|"
    r"مخيمات لبنان|مخيمات الأردن|مخيمات سوريا|اللاجئون الفلسطينيون في", re.I)

# Palestinian culture & arts — identity and testimony, from tatreez to cinema.
ARTS_RX = re.compile(
    r"artist|painter|sculpt|exhibit|gallery|mural|filmmaker|documentary|"
    r"\bpoet\b|poetry|novelist|musician|singer|\bdabke\b|embroidery|tatreez|"
    r"heritage|museum|cuisine|cinema|\bfilm\b|culture|"
    r"فنان|فنانة|تشكيلي|معرض|لوحة|جدارية|مخرج(?!ات)|وثائقي|شاعر|شاعرة|روائي|"
    r"موسيقي|مغني|مغنية|دبكة|تطريز|تراث|متحف|مطبخ|سينما|فيلم|ثقافة", re.I); SPORTS_RX = re.compile(r"football|soccer|\bfifa\b|\buefa\b|olympic|paralympic|stadium|league match|world cup|tournament|championship|athlete|footballer|\bcoach\b|national team|كرة القدم|كرة السلة|مباراة|منتخب|نادي رياضي|الدوري|ملعب|أولمبي|فيفا|بطولة|تصفيات|كأس العالم|لاعب|رياضي|رياضة", re.I)

# Real lives — the human stories behind the headlines: profiles, testimony, memory.
REAL_LIVES_RX = re.compile(
    r"story of|life of|survivor|remembers|testimony|his story|her story|"
    r"قصة|حكاية|يروي|تروي|شهادة|ناجٍ|ناجية|شاهد على|صرخة", re.I)

# Corruption, transparency & democratic accountability — wherever it sits, incl. the PA.
ACCOUNTABILITY_RX = re.compile(
    r"corrupt|nepotis|briber|embezzl|cronyis|\bgraft\b|kleptocra|"
    r"فساد|الفساد|محسوبية|رشوة|رشاوى|اختلاس|نزاهة|مساءلة|شفافية|مكافحة الفساد|"
    r"اعتقال سياسي|معتقل سياسي|معتقلي الرأي|تكميم|استبداد", re.I)

ISRAEL_CONTEXT_RX = re.compile(r"israel|settler|idf|zionis|إسرائيل|مستوطن", re.I); ARAB_LEADERS_RX = re.compile(r"(?:king|emir|sultan|crown prince|president|prime minister)\s+\w+.{0,40}(?:palestin|gaza|west bank|jerusalem)|(?:abdullah ii|mohammed bin salman|\bmbs\b|el-?sisi|sheikh tamim|bin zayed|\bmbz\b|salman bin|king abdullah|king mohammed vi|tebboune|saied)|(?:jordan|egypt|saudi|emirat|qatar|kuwait|oman|bahrain|morocc|algeri|tunisia|iraqi|lebanes)\w*\s+(?:king|president|monarch|leader|premier|emir)|(?:الملك|الأمير|الشيخ|الرئيس|ولي العهد|العاهل|السلطان)\s*\S*.{0,40}(?:فلسطين|غزة|الضفة|القدس)|(?:عبدالله الثاني|عبد الله الثاني|محمد بن سلمان|بن زايد|السيسي|تميم بن حمد|محمد السادس|تبون|قيس سعيد)", re.I)

# Advertising is not news (owner takedown 2026-08-05: a Tucker Carlson Network
# feed item that was a paid Ethos life-insurance promotion — clickbait Israel
# headline over ad copy — published as a brief). An item whose own text carries
# unambiguous promo markers is a commercial, whatever its headline says, and is
# dropped before categorization. Markers are kept narrow on purpose: reporting
# ABOUT sponsorship deals or ad campaigns ("a bill sponsored by", "AIPAC ad
# spending") must keep publishing.
AD_RX = re.compile(
    r"paid partnership|sponsored (?:content|post|segment|episode)|promo code|"
    r"use code|discount code|coupon code|\b\d{1,2}% off\b|affiliate link|"
    r"limited.time offer|sign up at|free trial|\$[\d,.]+ ?(?:million|m)? in coverage"
    r"|شراكة مدفوعة|إعلان مموَّ?ل|محتوى مموَّ?ل|كود (?:خصم|الخصم)|رمز الخصم", re.I)

# Site-wide relevance gate: every published story must concern Palestine, the
# occupation, or Israeli politics as they bear on Palestinians. World news from
# Palestinian outlets (earthquakes, sport, foreign politics) never publishes.
RELEVANT_RX = re.compile(
    r"palestin|gaza|west bank|jerusalem|bethlehem|ramallah|rafah|khan younis|jenin|nablus|hebron|"
    r"tulkarem|unrwa|al-aqsa|aqsa|intifada|nakba|settler|israel|\bidf\b|zionis|netanyahu|hamas|"
    r"فلسطين|الفلسطيني|غزة|غزّة|الضفة|القدس(?! العربي)|رام الله|رفح|خان يونس|جنين|نابلس|الخليل|"
    r"طولكرم|أونروا|الأونروا|الأقصى|الاحتلال|مستوطن|النكبة|إسرائيل|نتنياهو|حماس", re.I)

# Bitcoin & financial freedom — adoption in Palestine, the HRF/Gladstein/Dorsey
# freedom-money track: money that cannot be frozen, censored, or occupied.
BITCOIN_RX = re.compile(
    r"bitcoin|\bbtc\b|satoshi|lightning network|\bsats\b|"
    r"بيتكوين|بتكوين|البيتكوين|ساتوشي|شبكة البرق", re.I); BTC_SECTION_RX = re.compile(BITCOIN_RX.pattern + r"|correspondent bank|de-?risk|cash crisis|excess (?:cash|shekel)|shekel (?:surplus|crisis|glut|pile)|cash (?:surplus|glut|pile|transfer limit)|monetary authority|فائض (?:النقد|الشيكل|السيولة)|أزمة (?:النقد|السيولة|الكاش)|البنوك المراسلة|سلطة النقد|bitchat|بيتشات|ecash|إيكاش", re.I)

# For Bitcoin Magazine and the radar queries: keep the freedom/rights/adoption
# stories, drop pure market and product noise.
BTC_FREEDOM_RX = re.compile(
    r"financial freedom|human rights|palestin|gaza|west bank|middle east|"
    r"remittance|censorship|authoritarian|unbanked|self.?custody|circular econom|"
    r"global south|sanction|dictator|freedom money|financial repression|"
    r"فلسطين|غزة|الحرية المالية|حقوق الإنسان|عقوبات|رقابة|تحويلات|الشرق الأوسط", re.I)

FOCUS_BOOST = 30      # score boost for editorial focus topics
RESEARCH_BOOST = 22   # think-tank / OSINT reports: "news before it becomes news"
BREAKING_BOOST = 14   # hard-news urgency: casualties, strikes, raids, ceasefires
IMAGE_BOOST = 8
RECENCY_MAX = 50      # points for a just-published story, linear decay over MAX_AGE_HOURS
HERO_MAX_AGE_H = 18   # the top story must be actual news, not a feature from days ago
HERO_WINDOWS_H = (6, 12, HERO_MAX_AGE_H)  # prefer the freshest qualifying window

# Urgent hard-news markers — these stories are what readers check the site for.
BREAKING_RX = re.compile(
    r"\bkill|dead|death toll|casualt|wound|injur|strike|airstrike|bomb|shell|raid|storm|"
    r"assassinat|ceasefire|truce|escalat|evacuat|massacre|explosion|"
    r"شهيد|شهداء|قتل|مقتل|قصف|غارة|اقتحام|إصاب|جرحى|انفجار|مجزرة|تصعيد|عاجل|إخلاء", re.I)

# Features that should never lead the page, however well they score.
REVIEWISH_RX = re.compile(r"book review|review:|film review|مراجعة كتاب|عرض كتاب", re.I)

def score_item(item):
    hours = (datetime.now(timezone.utc) - item["date"]).total_seconds() / 3600
    # research reports decay over their own longer shelf life, not the 72h news cycle
    horizon = item.get("max_age_hours", MAX_AGE_HOURS)
    s = max(0.0, (horizon - hours) / horizon) * RECENCY_MAX + (FOCUS_BOOST if ARAB_LEADERS_RX.search(f"{item['title']} {item['dek']}") else 0)
    hay = f"{item['title']} {item['dek']}"
    if CHRISTIANS_RX.search(hay):
        s += FOCUS_BOOST
    if ACCOUNTABILITY_RX.search(hay):
        s += FOCUS_BOOST
    if BTC_SECTION_RX.search(hay):
        s += FOCUS_BOOST
    if BREAKING_RX.search(hay):
        s += BREAKING_BOOST
    if item["cat"] == "research":
        s += RESEARCH_BOOST
    if item["image"]:
        s += IMAGE_BOOST
    # Palestinian outlets also carry world news; it never outranks Palestine coverage.
    if not PALESTINE_RX.search(hay) and item["cat"] not in ("research", "bitcoin"):
        s -= 15
    return round(s, 2)

# NOTE: Palestinian Christians deliberately have no section of their own — that
# coverage runs through the general report (with a ranking boost) because it IS
# the story of Palestine and Jerusalem, not a sidebar.
HEALTH_RX = re.compile(
    r"hospital|clinic|medic|health|doctor|nurse|surger|patient|cancer|oncolog|"
    r"prosthetic|amputat|rehabilitat|dialysis|vaccin|polio|epidemi|malnutrit|"
    r"telemedicine|tele-?health|trauma|ptsd|mental health|maternity|maternal|"
    r"مستشفى|مستشفيات|عيادة|صحة|صحية|طبيب|أطباء|تمريض|جراحة|مريض|مرضى|سرطان|"
    r"أطراف صناعية|بتر|تأهيل|غسيل الكلى|تطعيم|لقاح|شلل الأطفال|وباء|سوء التغذية|"
    r"الطب عن بعد|صدمة نفسية|صحة نفسية|ولادة|أمومة", re.I)

# What Arab states and institutions are doing FOR Palestinians — politically,
# economically, in aid, education and culture (owner directive 2026-08-02).
# Both an Arab actor AND an act of support must appear, so ordinary regional
# coverage doesn't leak into the section.
_ARAB_ACTORS = (
    r"egypt|jordan|saudi|\buae\b|emirat|qatar|kuwait|bahrain|\boman\b|morocc|"
    r"algeria|tunisia|iraq|leban|arab league|\bgcc\b|gulf cooperation|"
    r"مصر|المصري|الأردن|السعودية|الإمارات|قطر|الكويت|البحرين|سلطنة عمان|عُمان|"
    r"المغرب|الجزائر|تونس|العراق|لبنان|الجامعة العربية|مجلس التعاون")
_ARAB_SUPPORT = (
    r"\baid\b|convoy|field hospital|reconstruct|rebuild|pledge|grant|scholarship|"
    r"donat|fund|treat|evacuat|(?:aid|medical|humanitarian) corridor|airlift|"
    r"air ?drop|relief|rehabilitat|"
    r"solidarit|twinn|cultural exchange|"
    r"مساعدات|قافلة|قوافل|مستشفى ميداني|إعمار|منحة|منح دراسية|تبرع|تمويل|علاج|"
    r"إجلاء|ممر طبي|إنزال جوي|إغاثة|إسناد|تضامن|كفالة|توأمة")
ARAB_AID_RX = re.compile(
    rf"(?s)^(?=.*(?:{_ARAB_ACTORS}))(?=.*(?:{_ARAB_SUPPORT}))", re.I)

# HER STORY (owner directive 2026-08-03): a story enters the section when a
# woman or girl is its SUBJECT and the reporting is about what she lived —
# violence and survival, detention, motherhood under siege, the work she
# carries. Two-part gate so ordinary war copy that merely mentions women
# stays in its geography section; the section is her account, not a tally.
_WOMEN_SUBJECT = (
    r"wom[ae]n|girls?|mothers?|widows?|daughters?|grandmother|"
    r"female|maternal|midwi(?:fe|ves)|pregnan|"
    r"نساء|امرأة|نسوة|فتاة|فتيات|أمهات|أرملة|أرامل|شقيقة|جدة|"
    r"حامل|حوامل|قابلة|أمومة|سيدة|سيدات")
_WOMEN_CONTEXT = (
    r"violen|assault|rape|harass|abuse|torture|strip[- ]search|"
    r"detain|detention|detainee|prison|interrogat|"
    r"femicide|gender[- ]based|survivor|testimon|widow|"
    r"childbirth|miscarriage|stillbirth|maternity|menstrual|"
    r"breadwinner|female[- ]headed|"
    r"عنف|اعتداء|اغتصاب|تحرش|تعذيب|تفتيش عار|"
    r"اعتقال|معتقلة|معتقلات|أسيرة|أسيرات|"
    r"ناجية|شهادة|إفادة|أرملة|أرامل|ولادة|إجهاض|نفاس|أمومة|معيلة")
# Some terms are already her-story on their own — a female detainee, a
# midwife, femicide — and need no second signal.
_WOMEN_SOLO = (
    r"femicide|gender[- ]based violence|midwi(?:fe|ves)|"
    r"women'?s rights|violence against women|female detainee|"
    r"أسيرة|أسيرات|معتقلة|معتقلات|قابلة قانونية|قابلات|"
    r"العنف ضد النساء|قتل النساء|حقوق المرأة")
WOMEN_RX = re.compile(
    rf"(?s)^(?:(?=.*(?:{_WOMEN_SUBJECT}))(?=.*(?:{_WOMEN_CONTEXT}))|(?=.*(?:{_WOMEN_SOLO})))",
    re.I)

CATEGORY_RULES = [
    ("women", WOMEN_RX),
    ("arabaid", ARAB_AID_RX),
    ("accountability", ACCOUNTABILITY_RX),
    ("health", HEALTH_RX),
    ("bitcoin", BTC_SECTION_RX),
    ("diaspora", DIASPORA_RX),
    ("arts", ARTS_RX), ("sports", SPORTS_RX),
 
    ("gaza", re.compile(
        r"gaza|rafah|khan younis|deir al[- ]balah|beit lahia|jabalia|"
        r"غزة|غزّة|رفح|خان يونس|دير البلح|جباليا|بيت لاهيا", re.I)),
    ("westbank", re.compile(
        r"west bank|jerusalem|jenin|nablus|hebron|ramallah|tulkarem|qalqilya|bethlehem|"
        r"settler|settlement|al-aqsa|aqsa|"
        r"الضفة|القدس|جنين|نابلس|الخليل|رام الله|طولكرم|قلقيلية|بيت لحم|مستوطن|استيطان|الأقصى", re.I)),
    ("politics", re.compile(
        r"\bun\b|united nations|\bicc\b|\bicj\b|ceasefire|truce|negotiat|talks|election|"
        r"congress|white house|\beu\b|resolution|sanction|diplomac|recogni[sz]|statehood|"
        r"hamas|fatah|\bplo\b|palestinian authority|"
        r"الأمم المتحدة|مجلس الأمن|الجنائية الدولية|العدل الدولية|وقف إطلاق النار|هدنة|"
        r"مفاوضات|محادثات|انتخابات|البيت الأبيض|عقوبات|اعتراف|دولة فلسطين|السلطة الفلسطينية|"
        r"حماس|فتح|منظمة التحرير", re.I)),
    ("economy", re.compile(
        r"econom|humanitarian aid|\baid\b|reconstruction|unemploy|trade|funding|donor|"
        r"shekel|bank|crossing|"
        r"اقتصاد|مساعدات|إنساني|إعمار|بطالة|تجارة|تمويل|مانح|معبر|بنك", re.I)),
]

JUNK_TITLE_RX = re.compile(r"#\d+\s*$"); CATEGORY_RX = dict(CATEGORY_RULES)  # section key → its own relevance test

OPINION_URL_RX = re.compile(r"/(opinion|op-ed|analysis|commentary|blog|مقالات)\b", re.I)
OPINION_CAT_RX = re.compile(r"opinion|analysis|commentary|رأي|تحليل|مقال", re.I)

def categorize(item):
    if OPINION_URL_RX.search(item["link"]) or OPINION_CAT_RX.search(" ".join(item["categories"])):
        return "opinion"
    hay = f"{item['title']} {item['dek']}"
    for key, rx in CATEGORY_RULES:
        if rx.search(hay):
            return key
    return "news"
# ---------- fetch & parse ----------

def local(tag):
    return tag.rsplit("}", 1)[-1].lower()

def parse_date(s, naive_timezone=None):
    return parse_timestamp(s, naive_timezone)

IMAGEISH_RX = re.compile(r"image|\.(jpe?g|png|webp|gif|avif)(\?|$)", re.I)

def find_image(el):
    # media:thumbnail is always an image; media:content may be a video (YouTube), so
    # thumbnails win and content must actually look like an image.
    for want in ("thumbnail", "content"):
        for node in el.iter():
            url = node.get("url") or ""
            if (local(node.tag) == want and "mrss" in node.tag.lower() and url.startswith("http")
                    and (want == "thumbnail"
                         or IMAGEISH_RX.search((node.get("type") or "") + (node.get("medium") or "") + url))):
                return url
    for node in el.iter():
        url = node.get("url") or ""
        if local(node.tag) == "enclosure" and url.startswith("http") \
                and IMAGEISH_RX.search((node.get("type") or "") + url):
            return url
    for node in el.iter():
        if local(node.tag) in ("encoded", "description", "content", "summary") and node.text:
            m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', node.text)
            if m:
                return m.group(1)
    return None

def fetch_bytes(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with safe_urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw

def parse_xml(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"^.*?<\?xml", "<?xml", text, count=1, flags=re.S)
        text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        text = re.sub(r'encoding="[^"]+"', 'encoding="utf-8"', text, count=1)
        return ET.fromstring(text.encode("utf-8"))

def item_field(el, names, nested=False):
    for node in el:
        if local(node.tag) in names and node.text and node.text.strip():
            return node.text.strip()
    if nested:  # e.g. YouTube Atom: media:group > media:description
        for node in el.iter():
            if local(node.tag) in names and node.text and node.text.strip():
                return node.text.strip()
    return ""

def item_link(el):
    for node in el:
        if local(node.tag) == "link":
            if node.text and node.text.strip().startswith("http"):
                return node.text.strip()
            href = node.get("href")
            if href and (node.get("rel") in (None, "alternate")):
                return href
    return ""


def item_source(el):
    for node in el:
        if local(node.tag) == "source":
            return (strip_html(node.text or ""), node.get("url") or "")
    return "", ""


CANONICAL_RX = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', re.I)
HTML_TAG_META_RX = re.compile(r"<meta\b[^>]*>", re.I)
HTML_TAG_LINK_RX = re.compile(r"<link\b[^>]*>", re.I)
HTML_ATTR_RX = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\'"])(.*?)\2', re.S)
SOCIAL_IMAGE_KEYS = {
    "og:image", "og:image:url",
    "twitter:image", "twitter:image:src",
    "image",
}


def parse_html_attrs(tag):
    attrs = {}
    for key, _quote, value in HTML_ATTR_RX.findall(tag):
        attrs[key.lower()] = html.unescape(value.strip())
    return attrs


def extract_social_image(page, base_url):
    for tag in HTML_TAG_META_RX.findall(page):
        attrs = parse_html_attrs(tag)
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        candidate = attrs.get("content", "").strip()
        if key in SOCIAL_IMAGE_KEYS and candidate:
            url = urljoin(base_url, candidate)
            if is_http_url(url):
                return url
    for tag in HTML_TAG_LINK_RX.findall(page):
        attrs = parse_html_attrs(tag)
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "").strip()
        if "image_src" in rel and href:
            url = urljoin(base_url, href)
            if is_http_url(url):
                return url
    return None


@functools.lru_cache(maxsize=1024)
def discover_story_image(article_url):
    if not is_http_url(article_url) or not is_public_http_url(article_url):
        return None
    try:
        req = urllib.request.Request(article_url, headers={"User-Agent": UA, "Accept": "text/html, */*"})
        with safe_urlopen(req, timeout=10) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if ctype and "html" not in ctype:
                return None
            page = response.read(280000).decode("utf-8", errors="replace")
            base_url = response.url or article_url
    except (OSError, ValueError):
        return None
    image = extract_social_image(page, base_url)
    if not image:
        return None
    return image.replace("http://", "https://", 1)


@functools.lru_cache(maxsize=2048)
def remote_image_ok(url):
    """A remote lede must actually serve an image before we publish it.

    Dead og:image links, soft-404 HTML pages, hotlink walls and tracking
    pixels all render as a broken photo on the reader's side. A URL that
    fails here is treated as photoless, so the branded category cover takes
    over — never an empty frame.
    """
    if not is_http_url(url) or not is_public_http_url(url):
        return False
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": UA, "Accept": "image/*,*/*;q=0.5"})
        if method == "GET":
            req.add_header("Range", "bytes=0-2047")
        try:
            with safe_urlopen(req, timeout=8) as r:
                if r.status not in (200, 206):
                    if method == "HEAD":
                        continue  # many CDNs reject HEAD; the ranged GET decides
                    return False
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if not ctype and method == "HEAD":
                    continue
                if not (ctype.startswith("image/") or (not ctype and IMAGEISH_RX.search(url))):
                    return False
                # Reject tracking-pixel-sized files when the server states a size.
                total = r.headers.get("Content-Range", "").rpartition("/")[2] \
                    or (r.headers.get("Content-Length") if r.status == 200 else "")
                if total.isdigit() and int(total) < 600:
                    return False
                return True
        except (OSError, ValueError, PublishingError):
            if method == "HEAD":
                continue
            return False
    return False


def resolve_article_url(url):
    """Resolve a Google News item to the publisher article it represents."""
    if not is_http_url(url):
        return ""
    if "news.google.com" not in urlsplit(url).netloc.lower():
        return canonicalize_url(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with safe_urlopen(req, timeout=12) as response:
            final_url = response.url
            page = response.read(250000).decode("utf-8", errors="replace")
        if "news.google.com" not in urlsplit(final_url).netloc.lower():
            return canonicalize_url(final_url)
        canonical = CANONICAL_RX.search(page)
        if canonical and "news.google.com" not in canonical.group(1):
            return canonicalize_url(html.unescape(canonical.group(1)))
        external = re.search(
            r'href=["\'](https?://(?!news\.google|accounts\.google|policies\.google)[^"\']+)',
            page,
            re.I,
        )
        if external:
            return canonicalize_url(html.unescape(external.group(1)))
    except (OSError, ValueError):
        return ""
    return ""


def attach_corrections(item):
    raw = CORRECTIONS["stories"].get(item["pid"], [])
    corrections = validate_corrections(raw, item["pid"], item["lang"])
    item["corrections"] = corrections
    if corrections:
        item["modified"] = parse_date(corrections[-1]["at"])


def attach_media(item, candidate, local_original=False):
    if not candidate:
        item["image"] = None
        item["media"] = None
        return
    if is_http_url(candidate):
        if local_original:
            # A desk report may carry a remote lede (e.g. a Wikimedia Commons
            # portrait) only when the exact URL has a media-rights.json entry.
            # The URL is verified live at build time; a dead or unreachable
            # image degrades to the imageFallback/category-cover chain rather
            # than failing the build or publishing a broken frame.
            rights = media_rights_for(candidate, MEDIA_RIGHTS)
            if rights is None:
                raise PublishingError(
                    f"{item.get('pid', item.get('title', 'original'))}: "
                    "remote original image lacks explicit local rights handling")
            if (
                remote_media_mode() == "source"
                and is_public_http_url(candidate)
                and remote_image_ok(candidate)
            ):
                item["image"] = candidate
                item["media"] = {
                    "credit": rights.credit,
                    "rightsBasis": rights.rights_basis,
                    "source": rights.source,
                    "licenseUrl": rights.license_url,
                }
            else:
                item["image"] = None
                item["media"] = None
            return
        if (
            remote_media_mode() == "source"
            and is_public_http_url(candidate)
        ):
            if not remote_image_ok(candidate):
                item["image"] = None
                item["media"] = None
                if HEALTH:
                    HEALTH.block_media("remote_media_dead")
                return
            item["image"] = candidate
            item["media"] = {
                "credit": item.get("source", ""),
                "rightsBasis": "source-hosted",
                "source": item.get("link") or item.get("source_url", ""),
                "licenseUrl": None,
            }
            return
        item["image"] = None
        item["media"] = None
        if HEALTH:
            HEALTH.block_media(
                "remote_media_not_public"
                if remote_media_mode() == "source"
                else "remote_media_disabled")
        return
    rights = media_rights_for(candidate, MEDIA_RIGHTS)
    if not rights and local_original and __import__("longform").house_asset(candidate):
        item["image"] = candidate
        item["media"] = {"credit": "Graphic: Times of Palestine",
                         "rightsBasis": "owned", "source": "Times of Palestine",
                         "licenseUrl": None}
        return
    if not rights:
        if local_original:
            raise PublishingError(
                f"{item.get('pid', item.get('title', 'original'))}: image lacks rights metadata")
        item["image"] = None
        item["media"] = None
        if HEALTH:
            HEALTH.block_media("media_rights_missing")
        return
    value = candidate
    if not is_http_url(value):
        value = f"/media/{Path(value).name}"
    item["image"] = value
    item["media"] = {
        "credit": rights.credit,
        "source": rights.source,
        "rightsBasis": rights.rights_basis,
        "licenseUrl": rights.license_url,
    }


def backfill_remote_story_image(item):
    if item.get("original") or item.get("image"):
        return
    candidate = discover_story_image(item.get("link") or "")
    if candidate:
        attach_media(item, candidate)


# ── Person-photo fallback ────────────────────────────────────────────────────
# Wire briefs about key political figures often arrive without an og:image
# (paywalled source, Arabic-only outlet, bare text wire). Rather than falling
# all the way back to the generic category cover, we try a known-good portrait
# from Wikimedia Commons under CC or PD licence.
#
# Each entry: (name_regex, image_url, photo_credit, wikimedia_page_url)
# The regex is matched against the article title + dek (case-insensitive).
# Entries are tried top-to-bottom; the first match wins.
# These fire ONLY when both the feed image and og:image backfill have failed.

PERSON_PHOTO_MAP = [
    # Mahmoud Abbas — PA president
    (re.compile(r"mahmoud.{0,4}abbas|أبو مازن|محمود عباس", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Mahmoud_Abbas.jpg/640px-Mahmoud_Abbas.jpg",
     "Mahmoud Abbas — Wikimedia Commons / Palestinian Authority press office",
     "https://commons.wikimedia.org/wiki/File:Mahmoud_Abbas.jpg"),
    # King Mohammed VI of Morocco
    (re.compile(r"king\s+moh(?:a|e)mmed\s+vi|محمد السادس|ملك المغرب|العاهل المغربي|الملك محمد", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Mohammed_VI_of_Morocco.jpg/640px-Mohammed_VI_of_Morocco.jpg",
     "King Mohammed VI — Wikimedia Commons / Moroccan Royal Palace press photo",
     "https://commons.wikimedia.org/wiki/File:Mohammed_VI_of_Morocco.jpg"),
    # King Abdullah II of Jordan
    (re.compile(r"king\s+ab(?:d|d)ullah\s+ii|الملك عبد ?الله الثاني", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/King_Abdullah_II_of_Jordan_%28cropped%29.jpg/640px-King_Abdullah_II_of_Jordan_%28cropped%29.jpg",
     "King Abdullah II — Wikimedia Commons / Jordanian Royal Court press photo",
     "https://commons.wikimedia.org/wiki/File:King_Abdullah_II_of_Jordan_(cropped).jpg"),
    # President El-Sisi of Egypt
    (re.compile(r"\bel-?sisi\b|السيسي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Abdel_Fattah_el-Sisi_in_2021.jpg/640px-Abdel_Fattah_el-Sisi_in_2021.jpg",
     "President el-Sisi — Wikimedia Commons / Egyptian Presidency press photo",
     "https://commons.wikimedia.org/wiki/File:Abdel_Fattah_el-Sisi_in_2021.jpg"),
    # Sheikh Tamim bin Hamad of Qatar
    (re.compile(r"tamim\s+bin\s+hamad|sheikh\s+tamim|تميم بن حمد", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Qatar_Amir_%28cropped%29.jpg/640px-Qatar_Amir_%28cropped%29.jpg",
     "Sheikh Tamim — Wikimedia Commons / Qatari Diwan press photo",
     "https://commons.wikimedia.org/wiki/File:Qatar_Amir_(cropped).jpg"),
    # Crown Prince Mohammed bin Salman
    (re.compile(r"mohammed\s+bin\s+salman|\bmbs\b|محمد بن سلمان|ابن سلمان", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Crown_Prince_of_Saudi_Arabia_Mohammed_Bin_Salman.jpg/640px-Crown_Prince_of_Saudi_Arabia_Mohammed_Bin_Salman.jpg",
     "Crown Prince MBS — Wikimedia Commons / Saudi Royal Court press photo",
     "https://commons.wikimedia.org/wiki/File:Crown_Prince_of_Saudi_Arabia_Mohammed_Bin_Salman.jpg"),
    # Mohammed bin Zayed (UAE president)
    (re.compile(r"mohammed\s+bin\s+zayed|\bmbz\b|محمد بن زايد|ابن زايد", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Mohamed_bin_Zayed.jpg/640px-Mohamed_bin_Zayed.jpg",
     "President MBZ — Wikimedia Commons / UAE Presidential Court press photo",
     "https://commons.wikimedia.org/wiki/File:Mohamed_bin_Zayed.jpg"),
    # Ismail Haniyeh / Hamas leader
    (re.compile(r"haniy(?:eh|a|ye)|هنية|هنيه", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9c/Ismail_Haniyeh.jpg/640px-Ismail_Haniyeh.jpg",
     "Ismail Haniyeh — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Ismail_Haniyeh.jpg"),
    # Yahya Sinwar
    (re.compile(r"sinwar|السنوار", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Yahya_Sinwar.jpg/640px-Yahya_Sinwar.jpg",
     "Yahya Sinwar — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Yahya_Sinwar.jpg"),
    # Benjamin Netanyahu
    (re.compile(r"netanyahu|نتنياهو", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Benjamin_Netanyahu_%282023%29.jpg/640px-Benjamin_Netanyahu_%282023%29.jpg",
     "Benjamin Netanyahu — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Benjamin_Netanyahu_(2023).jpg"),
    # Benny Gantz
    (re.compile(r"benny gantz|غانتس", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Benny_Gantz_March_2019.jpg/640px-Benny_Gantz_March_2019.jpg",
     "Benny Gantz — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Benny_Gantz_March_2019.jpg"),
    # Joe Biden
    (re.compile(r"\bbiden\b|بايدن", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/6/68/Joe_Biden_presidential_portrait.jpg/640px-Joe_Biden_presidential_portrait.jpg",
     "President Biden — White House official portrait, public domain",
     "https://commons.wikimedia.org/wiki/File:Joe_Biden_presidential_portrait.jpg"),
    # Donald Trump
    (re.compile(r"\btrump\b|ترامب", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/56/Donald_Trump_official_portrait.jpg/640px-Donald_Trump_official_portrait.jpg",
     "President Trump — White House official portrait, public domain",
     "https://commons.wikimedia.org/wiki/File:Donald_Trump_official_portrait.jpg"),
    # Antony Blinken / US Secretary of State
    (re.compile(r"\bblinken\b|بلينكن", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1d/Antony_Blinken_official_portrait.jpg/640px-Antony_Blinken_official_portrait.jpg",
     "Secretary Blinken — US State Department official portrait, public domain",
     "https://commons.wikimedia.org/wiki/File:Antony_Blinken_official_portrait.jpg"),
    # António Guterres (UN)
    (re.compile(r"guterres|غوتيريش|غوتيريس", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Ant%C3%B3nio_Guterres_2017.jpg/640px-Ant%C3%B3nio_Guterres_2017.jpg",
     "António Guterres — UN photo, CC BY-NC-ND 2.0",
     "https://commons.wikimedia.org/wiki/File:Ant%C3%B3nio_Guterres_2017.jpg"),
    # ── TOP 100 honorees (editor directive 2026-08-01): wire coverage of the
    # annual list's public figures carries their rights-cleared portrait.
    # Thumb URLs are derived from the Commons filename's md5 hash path;
    # remote_image_ok() verifies each at build time, so a renamed or missing
    # file simply falls through to the next match or the category cover.
    (re.compile(r"marwan\s+barghou?ti|مروان البرغوثي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2c/Marwan_Barghouti.jpg/640px-Marwan_Barghouti.jpg",
     "Marwan Barghouti — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Marwan_Barghouti.jpg"),
    (re.compile(r"mustafa\s+barghou?ti|مصطفى البرغوثي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Mustafa_Barghouti.jpg/640px-Mustafa_Barghouti.jpg",
     "Mustafa Barghouti — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Mustafa_Barghouti.jpg"),
    (re.compile(r"salam\s+fayyad|سلام فياض", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Salam_Fayyad_-_World_Economic_Forum_Annual_Meeting_2011.jpg/640px-Salam_Fayyad_-_World_Economic_Forum_Annual_Meeting_2011.jpg",
     "Salam Fayyad — World Economic Forum photo, CC BY-SA, via Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Salam_Fayyad_-_World_Economic_Forum_Annual_Meeting_2011.jpg"),
    (re.compile(r"\bashrawi\b|عشراوي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Hanan_Ashrawi.jpg/640px-Hanan_Ashrawi.jpg",
     "Hanan Ashrawi — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Hanan_Ashrawi.jpg"),
    (re.compile(r"riyad\s+mansour|رياض منصور", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Riyad_Mansour_%28cropped%29.jpg/640px-Riyad_Mansour_%28cropped%29.jpg",
     "Riyad Mansour — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Riyad_Mansour_(cropped).jpg"),
    (re.compile(r"\btlaib\b|رشيدة طليب", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Rashida_Tlaib%2C_official_portrait%2C_116th_Congress.jpg/640px-Rashida_Tlaib%2C_official_portrait%2C_116th_Congress.jpg",
     "Rep. Rashida Tlaib — US House official portrait, public domain",
     "https://commons.wikimedia.org/wiki/File:Rashida_Tlaib,_official_portrait,_116th_Congress.jpg"),
    (re.compile(r"omar\s+yaghi|عمر ياغي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/9/92/Omar_Yaghi.jpg/640px-Omar_Yaghi.jpg",
     "Omar Yaghi — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Omar_Yaghi.jpg"),
    (re.compile(r"ayman\s+odeh|أيمن عودة", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/Ayman_Odeh.jpg/640px-Ayman_Odeh.jpg",
     "Ayman Odeh — Knesset portrait, via Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Ayman_Odeh.jpg"),
    (re.compile(r"ahmad\s+tibi|أحمد الطيبي", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/Ahmad_Tibi.jpg/640px-Ahmad_Tibi.jpg",
     "Ahmad Tibi — Knesset portrait, via Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Ahmad_Tibi.jpg"),
    (re.compile(r"mansour\s+abbas|منصور عباس", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Mansour_Abbas.jpg/640px-Mansour_Abbas.jpg",
     "Mansour Abbas — Knesset portrait, via Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Mansour_Abbas.jpg"),
    (re.compile(r"abuelaish|أبو العيش", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f8/Izzeldin_Abuelaish.jpg/640px-Izzeldin_Abuelaish.jpg",
     "Izzeldin Abuelaish — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Izzeldin_Abuelaish.jpg"),
    (re.compile(r"abu[\s-]?sittah|غسان أبو ستة", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Ghassan_Abu_Sittah.jpg/640px-Ghassan_Abu_Sittah.jpg",
     "Ghassan Abu-Sittah — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Ghassan_Abu_Sittah.jpg"),
    (re.compile(r"bella\s+hadid|بيلا حديد", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Bella_Hadid_Cannes_2017.jpg/640px-Bella_Hadid_Cannes_2017.jpg",
     "Bella Hadid — Cannes 2017, CC BY-SA, via Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Bella_Hadid_Cannes_2017.jpg"),
    (re.compile(r"mohammed\s+assaf|محمد عساف", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Mohammad_Assaf.jpg/640px-Mohammad_Assaf.jpg",
     "Mohammed Assaf — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Mohammad_Assaf.jpg"),
    (re.compile(r"hussein\s+al[- ]?sheikh|حسين الشيخ", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Hussein_Al_Sheikh.jpg/640px-Hussein_Al_Sheikh.jpg",
     "Hussein al-Sheikh — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Hussein_Al_Sheikh.jpg"),
    (re.compile(r"mohammad\s+mustafa|محمد مصطفى", re.I),
     "https://upload.wikimedia.org/wikipedia/commons/thumb/b/be/Mohammad_Mustafa_2024.jpg/640px-Mohammad_Mustafa_2024.jpg",
     "PM Mohammad Mustafa — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Mohammad_Mustafa_2024.jpg"),
    # ── Israeli election watch (owner directive 2026-08-02) ─────────────────
    # Coalition coverage runs through the 27 October vote; wire briefs about
    # these figures get a face. Special:FilePath survives Commons re-hashing
    # and 404s cleanly, and duplicate regexes act as a fallback chain — a
    # renamed file skips to the next candidate instead of dropping the photo.
    (re.compile(r"ei[sz]enkot|آيزنكوت|أيزنكوت|إيزنكوت", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Gadi%20Eizenkot,%20November%202020%20(GPOMN1%209040)%20(cropped).jpg?width=640",
     "Gadi Eisenkot — Wikimedia Commons / Spokesperson unit, President of Israel",
     "https://commons.wikimedia.org/wiki/File:Gadi_Eizenkot,_November_2020_(GPOMN1_9040)_(cropped).jpg"),
    (re.compile(r"ei[sz]enkot|آيزنكوت|أيزنكوت|إيزنكوت", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Gadi%20Eisenkot.jpg?width=640",
     "Gadi Eisenkot — Wikimedia Commons / Spokesperson unit, President of Israel",
     "https://commons.wikimedia.org/wiki/File:Gadi_Eisenkot.jpg"),
    (re.compile(r"netanyahu|نتنياهو", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Benjamin%20Netanyahu%202018.jpg?width=640",
     "Benjamin Netanyahu — Wikimedia Commons / US State Department (public domain)",
     "https://commons.wikimedia.org/wiki/File:Benjamin_Netanyahu_2018.jpg"),
    (re.compile(r"naftali\s+bennett|نفتالي بينيت|بينيت", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Naftali%20Bennett%202021.jpg?width=640",
     "Naftali Bennett — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Naftali_Bennett_2021.jpg"),
    (re.compile(r"naftali\s+bennett|نفتالي بينيت|بينيت", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Naftali%20Bennett%20(cropped).jpg?width=640",
     "Naftali Bennett — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Naftali_Bennett_(cropped).jpg"),
    (re.compile(r"yair\s+lapid|يائير لبيد|لابيد", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Yair%20Lapid%202022.jpg?width=640",
     "Yair Lapid — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Yair_Lapid_2022.jpg"),
    (re.compile(r"yair\s+lapid|يائير لبيد|لابيد", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Yair%20Lapid%20(cropped).jpg?width=640",
     "Yair Lapid — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Yair_Lapid_(cropped).jpg"),
    (re.compile(r"yair\s+golan|يائير غولان", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Yair%20Golan.jpg?width=640",
     "Yair Golan — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Yair_Golan.jpg"),
    (re.compile(r"li[eb]+erman|ليبرمان", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Avigdor%20Liberman.jpg?width=640",
     "Avigdor Liberman — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Avigdor_Liberman.jpg"),
    (re.compile(r"li[eb]+erman|ليبرمان", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Avigdor%20Lieberman.jpg?width=640",
     "Avigdor Liberman — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Avigdor_Lieberman.jpg"),
    (re.compile(r"ben[- ]?gvir|بن غفير", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Itamar%20Ben-Gvir.jpg?width=640",
     "Itamar Ben Gvir — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Itamar_Ben-Gvir.jpg"),
    (re.compile(r"ben[- ]?gvir|بن غفير", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Itamar%20Ben%20Gvir.jpg?width=640",
     "Itamar Ben Gvir — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Itamar_Ben_Gvir.jpg"),
    (re.compile(r"smotrich|سموتريتش", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Bezalel%20Smotrich.jpg?width=640",
     "Bezalel Smotrich — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Bezalel_Smotrich.jpg"),
    (re.compile(r"aryeh\s+deri|arye\s+deri|أرييه درعي|درعي", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Aryeh%20Deri.jpg?width=640",
     "Aryeh Deri — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Aryeh_Deri.jpg"),
    (re.compile(r"jibril\s+rajoub|جبريل الرجوب|الرجوب", re.I),
     "https://commons.wikimedia.org/wiki/Special:FilePath/Jibril%20Rajoub.jpg?width=640",
     "Jibril Rajoub — Wikimedia Commons",
     "https://commons.wikimedia.org/wiki/File:Jibril_Rajoub.jpg"),
]


def backfill_person_photo(item):
    """Set a portrait photo for wire briefs about key political figures.

    Fires only when all earlier image-resolution steps (feed thumbnail,
    og:image backfill) have left the item photoless.  Matches the article
    title + dek against PERSON_PHOTO_MAP and, on the first match, injects
    the Wikimedia Commons portrait URL with proper CC/PD attribution.

    This gives readers a recognisable face instead of the generic category
    cover for person-centric political news.  Skipped in rights-only mode.
    """
    if item.get("image"):
        return
    if remote_media_mode() != "source":
        return
    hay = f"{item.get('title', '')} {item.get('dek', '')}"
    for rx, img_url, credit, license_url in PERSON_PHOTO_MAP:
        if rx.search(hay):
            if not remote_image_ok(img_url):
                continue  # renamed/moved on Commons — try the next match
            item["image"] = img_url
            item["media"] = {
                "credit": credit,
                "rightsBasis": "wikimedia-cc",
                "source": license_url,
                "licenseUrl": license_url,
            }
            return


def finish_item(item, feed):
    """Apply per-feed relevance filters, then categorize and score. Returns item or None."""
    if JUNK_TITLE_RX.search(item["title"]):
        return None
    if "news.google.com" in feed.get("url", ""):
        # Google News titles end " - Publisher". Credit the real outlet and
        # clean the headline: wire attribution must name who actually reported,
        # never the discovery feed's label.
        title, sep, outlet = item["title"].rpartition(" - ")
        if sep and 2 < len(outlet) <= 60:
            item["title"], item["source"] = title.strip(), outlet.strip()
    # Google News indexes our own site now — never re-aggregate ourselves.
    if item["source"] in ("Times of Palestine", "تايمز أوف فلسطين") \
            or "timesofpalestine." in item["link"]:
        return None
    hay = f"{item['title']} {item['dek']} {item['link']}"
    if AD_RX.search(f"{item['title']} {item['dek']}"):
        print(f"  ⊘ ad/promo dropped: {item.get('source', feed.get('name', '?'))}: {item['title'][:70]}")
        return None
    if feed.get("filterPalestine") and not PALESTINE_RX.search(hay):
        return None
    # For general/foreign outlets and shows (Tucker Carlson, Religion News Service):
    # keep only stories with Palestine or Israel context — not their unrelated coverage.
    if feed.get("filterPalestineChristians"):
        # MENA-wide outlets (DAWN) publish on Yemen, Sudan, Egypt… A story earns a
        # place here only when its HEADLINE concerns Palestine or Israel — a passing
        # mention of Israel deep in a regional piece's summary is not enough.
        if not (PALESTINE_RX.search(item["title"]) or ISRAEL_CONTEXT_RX.search(item["title"])):
            return None
    if feed.get("filterBitcoinFreedom") and not BTC_FREEDOM_RX.search(hay):
        return None
    if feed.get("exclusive"):
        # Historical name retained in feeds.json, but the source is still attributed.
        item["partner"] = True
        if feed.get("translate"):
            item["needs_translation"] = True
        item["cat"] = categorize(item)
    elif feed.get("type") == "telegram":
        item["cat"] = categorize(item) if feed.get("wire") else "social"
    elif feed.get("research"):
        item["cat"] = "research"
    elif feed.get("category"):  # feeds that pre-decide their section
        cat = feed["category"]
        if feed.get("type") == "gnews":  # search results must pass the section's own test
            rx = CATEGORY_RX.get(cat)
            if not (rx and rx.search(f"{item['title']} {item['dek']}")):
                cat = categorize(item)
        item["cat"] = cat
    else:
        item["cat"] = categorize(item)
    # This is a Palestine site. The Bitcoin-freedom track is the only thematic
    # exemption; research feeds are already gated at the feed level.
    if item["cat"] not in ("bitcoin", "research") and not RELEVANT_RX.search(hay):
        return None
    # The Sport section is Palestinian sport. Palestinian wires also carry
    # Egyptian and regional league coverage wholesale, and outlet URLs or
    # boilerplate can satisfy the general gate above — so a sports item earns
    # its place only when the story text itself has Palestine context: the
    # national team, Palestinian players and clubs, the game under occupation
    # (owner call 2026-08-02, after a Zamalek transfer round-up published).
    if item["cat"] == "sports" and not PALESTINE_RX.search(f"{item['title']} {item['dek']}"):
        return None
    item["date"] = min(item["date"], datetime.now(timezone.utc))
    item["max_age_hours"] = feed.get("maxAgeHours", MAX_AGE_HOURS)
    item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]  # stable internal page id
    if item["pid"] in RETRACTED_PIDS:  # owner-ordered takedowns stay down on every route
        return None
    attach_corrections(item)
    validate_story(item)
    item["score"] = score_item(item)
    return item

def gnews_url(feed):
    from urllib.parse import quote
    return (f"https://news.google.com/rss/search?q={quote(feed['query'])}"
            f"&hl={feed.get('hl', 'en-US')}&gl={feed.get('gl', 'US')}&ceid={quote(feed.get('ceid', 'US:en'))}")

def fetch_rss(feed, lang, now, max_age):
    url = gnews_url(feed) if feed.get("type") == "gnews" else feed["url"]
    if feed.get("fixture"):
        fixture = Path(feed["fixture"])
        if not fixture.is_absolute():
            fixture = ROOT / fixture
        root = parse_xml(fixture.read_bytes())
    else:
        root = parse_xml(fetch_bytes(url))
    elements = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    feed["_observed"] = len(elements)
    items = []
    for el in elements:
        title = strip_html(item_field(el, {"title"}))
        source_name = feed["name"]
        source_url = feed["site"]
        if feed.get("type") == "gnews":  # per-item real outlet; strip " - Outlet" title suffix
            outlet, outlet_url = item_source(el)
            if outlet:
                source_name = outlet
                source_url = outlet_url or source_url
                if title.endswith(outlet):
                    title = title[: -len(outlet)].rstrip(" -—–|·")
        if len(title) < 8:
            continue
        published_raw = item_field(el, {"pubdate", "published", "date"})
        updated_raw = item_field(el, {"updated"})
        date = parse_date(
            published_raw or updated_raw,
            feed.get("timezone"),
        )
        if not date or now - date > max_age or date > now + timedelta(hours=2):
            continue
        modified = parse_date(updated_raw, feed.get("timezone")) if updated_raw else None
        if feed.get("type") == "gnews":  # gnews descriptions are just related-link clusters
            dek = ""
        else:
            dek = truncate(clean_dek(strip_html(item_field(el, {"description", "summary", "encoded", "content"},
                                                           nested=feed.get("type") == "youtube"))),
                           420 if feed.get("research") else 260)
        if dek == title:
            dek = ""
        cats = [strip_html(n.text or n.get("term") or "") for n in el if local(n.tag) == "category"]
        raw_link = item_link(el)
        link = resolve_article_url(raw_link) if feed.get("type") == "gnews" \
            else canonicalize_url(raw_link)
        if not link:
            if HEALTH:
                HEALTH.hold("canonical_article_url_missing")
            continue
        candidate_image = (find_image(el) or "").replace("http://", "https://") or None
        item = {
            "title": headline(title), "dek": dek,
            "link": link, "source_url": canonicalize_url(source_url), "date": date,
            "modified": modified,
            "source": source_name, "source_id": feed["id"],
            "source_type": feed.get("type", "rss"),
            "image": None, "media": None,
            "categories": [c for c in cats if c], "lang": lang,
            "original": False, "partner": bool(feed.get("exclusive")),
        }
        try:
            item = finish_item(item, feed)
        except PublishingError:
            if HEALTH:
                HEALTH.hold("remote_story_validation")
            continue
        if item:
            attach_media(item, candidate_image)
            backfill_remote_story_image(item)
            backfill_person_photo(item)
            items.append(item)
    return items

TG_MSG_RX = re.compile(r'class="tgme_widget_message_wrap.*?(?=class="tgme_widget_message_wrap|$)', re.S)
TG_TEXT_RX = re.compile(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
TG_DATE_RX = re.compile(r'<time datetime="([^"]+)"')
TG_LINK_RX = re.compile(r'class="tgme_widget_message_date"[^>]*href="([^"]+)"')
TG_PHOTO_RX = re.compile(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)")
# Channel posts carry emoji and hashtags; neither belongs in a news headline.
EMOJI_RX = re.compile("[\U0001F000-\U0001FAFF\U0001FB00-\U0001FBFF"
                      "☀-➿⬀-⯿←-⇿⌀-⏿️‍]")

# Channel self-promotion ("follow our channel", "subscribe") is not news. It also
# reliably makes the model refuse, so filtering it here saves an API call a build.
PROMO_RX = re.compile(r"قناتنا|منصاتنا|تابعونا|اشتركوا|للاشتراك|رابط القناة|"
                     r"our channel|subscribe to|follow us on", re.I)

def fetch_telegram(feed, lang, now, max_age):
    """Parse a public Telegram channel's t.me/s/<channel> preview page (no API needed)."""
    html_page = fetch_bytes(f"https://t.me/s/{feed['channel']}").decode("utf-8", errors="replace")
    blocks = TG_MSG_RX.findall(html_page)
    feed["_observed"] = len(blocks)
    items = []
    for block in blocks:
        if "service_message" in block:  # "X pinned ..." announcements, not posts
            continue
        m_text, m_date, m_link = TG_TEXT_RX.search(block), TG_DATE_RX.search(block), TG_LINK_RX.search(block)
        if not (m_text and m_date and m_link):
            continue
        raw = strip_html(m_text.group(1))
        m_art = re.search(r"https?://(?!t\.me/)\S+", raw)  # channels often append the article URL
        link = html.unescape(m_art.group(0).rstrip(".,)…")) if m_art else m_link.group(1)
        text = re.sub(r"https?://\S+", "", raw)
        text = EMOJI_RX.sub("", text).replace("#", "")
        text = re.sub(r"\s+", " ", text).strip(" .|-—·")
        text = re.sub(r"^\s*وكالة معا\s*[|:ـ—-]+\s*", "", text); text = re.sub(r"\s*[ـ​-‏﻿]+\s*", "", text)  # strip the agency prefix, then stitch words split by tatweel/zero-width marks (فلسـ ـطين -> فلسطين) to evade keyword filters — otherwise the relevance gate misses the story and the headline publishes mangled
        if len(text) < 25 or PROMO_RX.search(text):
            continue
        date = parse_date(m_date.group(1), feed.get("timezone"))
        if not date or now - date > max_age:
            continue
        m_photo = TG_PHOTO_RX.search(block)
        candidate_image = m_photo.group(1) if m_photo else None
        item = {
            "title": headline(text), "dek": truncate(text, 260) if len(text) > 130 else "",
            "link": canonicalize_url(link), "source_url": canonicalize_url(feed["site"]),
            "date": date, "modified": None,
            "source": feed["name"], "source_id": feed["id"],
            "source_type": "telegram", "image": None, "media": None,
            "categories": [], "lang": lang, "original": False,
            "partner": bool(feed.get("exclusive")),
        }
        try:
            item = finish_item(item, feed)
        except PublishingError:
            if HEALTH:
                HEALTH.hold("remote_story_validation")
            continue
        if item:
            attach_media(item, candidate_image)
            backfill_remote_story_image(item)
            backfill_person_photo(item)
            items.append(item)
    return items
def fetch_feed(feed, lang):
    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=feed.get("maxAgeHours", MAX_AGE_HOURS))
    try:
        if feed.get("type") == "telegram":
            items = fetch_telegram(feed, lang, now, max_age)
        else:
            items = fetch_rss(feed, lang, now, max_age)
        print(f"  ✓ {feed['name']}: {len(items)} items")
        if HEALTH:
            observed = int(feed.get("_observed", len(items)))
            HEALTH.source_result(
                feed["id"], "ok", fetched=observed, accepted=len(items),
                withheld=max(0, observed - len(items)))
        return items
    except Exception as e:
        print(f"  ✗ {feed['name']}: {type(e).__name__}: {e}")
        if HEALTH:
            HEALTH.source_result(feed["id"], "error", error=type(e).__name__)
        return []

# A brief must never talk about itself or its sources' availability. Any output that
# does (a model refusal / meta-commentary) is rejected and scrubbed from the cache.
REFUSAL_RX = re.compile(
    r"cannot (?:produce|write|provide|generate)|insufficient (?:source|material|information)|"
    r"source material|provided material|news brief|full article|complete article|would be required|"
    r"not available in the|available in the (?:provided|source|material)|"
    r"encouraged to visit|visit the .{0,50}website|access to the (?:article|complete|full)|"
    r"i (?:cannot|can.?t|am unable to)|unable to (?:produce|write|provide|generate|create|summari[sz]e)|"
    r"لا (?:أستطيع|يمكنني|نستطيع|يمكن(?:نا)?)\s*(?:إنتاج|كتابة|تقديم|صياغة|إعداد)|يتعذر|"
    r"بناءً? على هذه المادة|لا (?:تتضمن|تحتوي|توجد).{0,20}(?:معلومات|أخبار)|"
    r"المادة المصدرية|المادة المتاحة|المادة المرفقة|هذه التعليمات|"
    r"المقال الكامل|النص الكامل|زيارة موقع|زيارة الموقع", re.I)

# Owner order 2026-08-03, after «أسلمت قوات الاحتلال» reached the Arabic front:
# copy that reads machine-made never publishes unchallenged. These nets are
# deliberately conservative — each pattern is a near-certain marker of
# translationese or stock model diction, so a hit means "rewrite", never a
# judgment call. A flagged draft gets ONE editor retry with the offending
# wordings quoted back; if diction alone still trips after that, the improved
# draft publishes anyway (charter: editorial gating defaults to publish) and
# the residue is logged. Cached pre-gate copy that trips a net is scrubbed at
# load so it regenerates under the new prompt.
_AR_DICTION = [
    (re.compile(r"أسلم(?:ت|وا)?\s+(?:ال)?(?:قوات|جيش|شرطة|سلطات|احتلال|إسرائيل|"
                r"جثامين|جثث|جثة|جثمان|نفسه|نفسها|أنفسهم)"),
     "«أسلم» تعني اعتنق الإسلام — فعل التسليم هو «سلّم/سلّمت»"),
    (re.compile(r"(?:^|[\s،.:«»)(])قام(?:ت|وا)?\s+(?:\S+\s+){0,3}?ب\S"),
     "«قام بـ» ركيكة — استعمل الفعل مباشرة (قصف، اعتقل، سلّم)"),
    (re.compile(r"(?:^|[\s،.:«»)(])تم(?:ت)?\s+\S"),
     "«تم/تمت» مع المصدر ركيكة — استعمل الفعل المبني للمعلوم"),
    (re.compile(r"يُ?ذكر أن|تجدر الإشارة|الجدير بالذكر|ومن الجدير"),
     "حشو صحفي آلي — احذفه وادخل في المعلومة"),
]
_EN_DICTION = [
    (re.compile(r"\bdelv(?:e|es|ed|ing)\b", re.I),
     "'delve' — say plainly what was examined"),
    (re.compile(r"\bunderscor(?:e|es|ed|ing)\b", re.I),
     "'underscore' — state the fact, not its significance"),
    (re.compile(r"\bhighlight(?:s|ed|ing)? the (?:importance|significance|need|challenges)\b", re.I),
     "stock 'highlights the importance' framing"),
    (re.compile(r"\bit (?:is|'s) worth noting\b|\bit should be noted\b", re.I),
     "throat-clearing filler"),
    (re.compile(r"\bin a significant (?:development|move|step|escalation)\b", re.I),
     "stock significance framing"),
    (re.compile(r"\bmarks? a significant\b", re.I),
     "stock significance framing"),
    (re.compile(r"\bserves? as a (?:reminder|testament)\b|\ba testament to\b", re.I),
     "stock assessment closer"),
    (re.compile(r"\bsheds? light on\b", re.I),
     "'sheds light on' — name the finding"),
]


def language_quality_issues(text, lang=None):
    """Wordings that read machine-made rather than newsroom-made.
    lang=None checks both nets (used for the cache scrub, where legacy keys
    carry no language)."""
    nets = []
    if lang in (None, "ar"):
        nets += _AR_DICTION
    if lang in (None, "en"):
        nets += _EN_DICTION
    found = []
    for rx, why in nets:
        m = rx.search(text or "")
        if m:
            found.append(f"{m.group(0).strip()!r}: {why}")
    return found


# A story body must be substantial and end on a finished sentence. Feed summaries
# arrive truncated mid-sentence ("…") and model output can stop short at the token
# ceiling; neither may ever publish as an article.
_TERMINALS = ('.', '!', '?', '"', '”', '»', '؟', ')', "'")
_DANGLING = ("…", "...", ",", "،", ";", "؛", ":", "-", "—", "–")

# Pacing rules (owner order 2026-08-03): neither wall-of-text paragraphs nor
# two-line stub articles publish. A brief must clear MIN_BRIEF_WORDS to run at
# all; anything beyond MAX_PARA_WORDS in one block is reflowed at render time.
MIN_BRIEF_WORDS = 60     # hard publish floor (the desk aims for 100-170)
MAX_PARA_WORDS = 70      # longest acceptable single paragraph
_SENT_SPLIT_RX = re.compile(r"(?<=[.!?؟…])\s+")


def reflow_paragraphs(text):
    """Deterministic pacing guard for wire-brief prose: single newlines count
    as paragraph breaks, and any paragraph beyond MAX_PARA_WORDS is split at
    sentence boundaries into chunks of at most ~55 words. Applied at render
    time so every already-cached brief is fixed without regeneration. Never
    applied to originals (their markdown carries deliberate structure)."""
    out = []
    for para in re.split(r"\n+", (text or "").strip()):
        para = para.strip()
        if not para:
            continue
        if len(para.split()) <= MAX_PARA_WORDS:
            out.append(para)
            continue
        chunk, count = [], 0
        for sent in _SENT_SPLIT_RX.split(para):
            w = len(sent.split())
            if chunk and count + w > 55:
                out.append(" ".join(chunk))
                chunk, count = [], 0
            chunk.append(sent)
            count += w
        if chunk:
            out.append(" ".join(chunk))
    return "\n\n".join(out)


def structure_issues(text, lang):
    """Pacing problems a desk retry can fix: stub-length copy, a single-block
    body, or an oversized paragraph."""
    issues = []
    words = len(text.split())
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if words < 90:
        issues.append(
            f"الموجز قصير جداً ({words} كلمة) — الموجز الصالح للنشر 100-170 كلمة"
            if lang == "ar" else
            f"too short ({words} words) — a publishable brief runs 100-170 words")
    if len(paras) < 2:
        issues.append(
            "النص كتلة واحدة — قسّمه إلى فقرتين أو ثلاث قصيرة يفصل بينها سطر فارغ"
            if lang == "ar" else
            "single-block body — break it into 2-3 short paragraphs separated by blank lines")
    elif any(len(p.split()) > MAX_PARA_WORDS for p in paras):
        issues.append(
            f"فقرة تتجاوز {MAX_PARA_WORDS} كلمة — قسّمها عند حدود الجمل"
            if lang == "ar" else
            f"a paragraph runs past {MAX_PARA_WORDS} words — split it at sentence boundaries")
    return issues

def is_complete_text(s, floor):
    s = (s or "").strip()
    if len(s) < floor:
        return False
    tail = s.rstrip("*_  ")
    if tail.endswith(_DANGLING):
        return False
    return tail.endswith(_TERMINALS)

TITLE_MAX_WORDS = 12   # hard backstop; the desks aim for ≤9-10

# Owner rule 2026-07-30: every title, EN and AR, is active voice and names who
# did what to whom. Undiacritized Arabic passive is ambiguous (قتل reads both
# ways), so the Arabic net only catches explicitly marked or unambiguous forms.
_EN_PASSIVE_TITLE_RX = re.compile(
    r"\b(?:is|are|was|were|be|been|being|get|gets|got)\s+(?:\w+ed|"
    r"born|built|held|hit|hurt|kept|known|left|lost|made|met|paid|put|sent|"
    r"set|shot|shut|sold|struck|torn|thrown|withdrawn|won)\b", re.I)
_EN_AGENTLESS_TITLE_RX = re.compile(
    r"\b(?:changes?\s+hands|comes?\s+under|faces?\s+(?:pressure|scrutiny|"
    r"criticism|questions)|under\s+fire|remains?\s+unclear)\b", re.I)
_AR_PASSIVE_TITLE_RX = re.compile(
    r"(?:^|[\s:،».])(?:قُتل|اغتيل|استُشهد|أُصيب|اعتُقل|أُوقف|استُهدف|صودر|"
    r"صودرت|أُغلق|أُغلقت|هُدم|هُدمت|دُمر|دُمرت|فُرض|فُرضت|مُنع|مُنعت|"
    r"أُطلق|شُيّع|نُقل|أُجبر|أُخلي)(?:$|[\s:،«.])")


def passive_title_warnings(title, lang):
    """Titles must name the actor: no passive voice, no agentless hedges."""
    found = []
    if lang == "en":
        m = _EN_PASSIVE_TITLE_RX.search(title) or _EN_AGENTLESS_TITLE_RX.search(title)
        if m:
            found.append(f"passive/agentless title ({m.group(0)!r}) — name who "
                         "did what to whom")
    else:
        m = _AR_PASSIVE_TITLE_RX.search(title)
        if m:
            found.append(f"عنوان بصيغة المبني للمجهول ({m.group(0).strip()!r}) — "
                         "سمِّ الفاعل: من فعل ماذا وبمن")
    return found


def _diction_retry_note(issues, lang):
    listed = "؛ ".join(issues) if lang == "ar" else "; ".join(issues)
    if lang == "ar":
        return ("ملاحظة المحرر: المسودة سليمة وقائعياً لكنها تستخدم صياغات يمنعها "
                f"دليل الأسلوب: {listed}. أعد كتابة الموجز بالتنسيق نفسه تماماً "
                "(سطر HEADLINE: ثم سطر فارغ ثم النص) مستبدلاً تلك الصياغات بعربية "
                "صحفية طبيعية دقيقة، مع الحفاظ على كل الوقائع والإسناد كما هي.")
    return ("EDITOR: The draft is factually fine but uses wording the house "
            f"forbids: {listed}. Rewrite it in the same exact format (HEADLINE: "
            "line, blank line, body), replacing that phrasing with precise, "
            "natural news prose. Keep every fact and the attribution unchanged.")


def write_brief(client, item):
    material = (f"OUTLET: {item['source']}\n"
                f"SOURCE HEADLINE OR POST TEXT: {item['title']}\n"
                f"FEED SUMMARY: {item['dek'] or '(none)'}")
    system = BRIEF_SYSTEM[item["lang"]]
    if item.get("needs_translation"):  # Arabic wire copy feeding the English edition
        system += " The source material is in Arabic; write the headline and brief in English."
    convo = [{"role": "user", "content": material}]
    text = new_title = None
    for attempt in (0, 1):
        response = client.messages.create(
            model=BRIEFS_MODEL,
            max_tokens=700,
            system=system,
            messages=convo,
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        text, new_title = raw, None
        if text.startswith("HEADLINE:"):
            first, _, rest = text.partition(chr(10))
            new_title = first[len("HEADLINE:"):].strip(" *«»\"")
            text = rest.strip()
        # Owner rule 2026-07-30: no headline longer than one short complete
        # sentence. A missing or bloated headline means the copy is not ready.
        if (not new_title or len(new_title.split()) > TITLE_MAX_WORDS
                or new_title.endswith(("…", "..."))
                or passive_title_warnings(new_title, item["lang"])):
            item["brief_refused"] = True
            return None
        if REFUSAL_RX.search(text) or not is_complete_text(text, 160):
            item["brief_refused"] = True  # nothing to report, or the copy stops short — no stubs
            return None
        # Owner orders 2026-08-03: machine diction and bad pacing (stub-length
        # copy, wall-of-text blocks) get one editor pass. After the retry, a
        # brief still under the hard word floor is withheld — a two-line stub
        # never publishes as an article — while diction or paragraphing
        # residue publishes best-effort (render-time reflow fixes blocks, and
        # style alone never holds coverage).
        issues = (language_quality_issues(f"{new_title}\n{text}", item["lang"])
                  + structure_issues(text, item["lang"]))
        if not issues:
            break
        if attempt == 0:
            convo += [{"role": "assistant", "content": raw},
                      {"role": "user", "content": _diction_retry_note(issues, item["lang"])}]
        else:
            if len(text.split()) < MIN_BRIEF_WORDS:
                item["brief_refused"] = True
                return None
            print(f"  ⚠ brief {item['pid']}: issues persist after editor pass: {issues[:2]}")
    item["title"] = truncate(new_title, 120)
    return text


def generate_briefs(all_items):
    """Attach complete TOP Newsdesk briefs to every aggregated wire item."""
    try:
        cache = json.loads(BRIEFS_CACHE.read_text(encoding="utf-8")) if BRIEFS_CACHE.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Briefs: cache unreadable ({type(exc).__name__}); rebuilding entries.")
        if HEALTH:
            HEALTH.checks["brief_cache"] = "degraded"
        cache = {}
    # Keep connector markers while scrubbing refused or truncated generated copy.
    # Pre-gate entries (style != BRIEF_STYLE) that trip the diction nets or the
    # stub floor are scrubbed too, so «أسلمت قوات»-class copy and two-line
    # articles regenerate immediately under the current prompt instead of
    # republishing until their restyle turn (owner orders 2026-08-03).
    def _entry_ok(key, value):
        if "brief" not in value:
            return True
        brief = value.get("brief", "")
        if REFUSAL_RX.search(brief) or not is_complete_text(brief, 160):
            return False
        if value.get("style") != BRIEF_STYLE:
            if len(brief.split()) < MIN_BRIEF_WORDS:
                return False
            prefix = key.split(":", 1)[0]
            lang = prefix if prefix in ("en", "ar") else None
            if language_quality_issues(f"{value.get('title', '')}\n{brief}", lang):
                return False
        return True

    cache = {key: value for key, value in cache.items() if _entry_ok(key, value)}
    cache_dirty = False
    now_ts = datetime.now(timezone.utc).timestamp()
    for it in all_items:
        if it.get("original"):
            continue
        # Keys are lang-scoped so the same wire story can carry an Arabic brief in /ar/
        # and an English one in /en/; bare-pid entries are legacy single-language cache.
        entry = cache.get(f"{it['lang']}:{it['pid']}") or cache.get(it["pid"])
        if entry:
            it["brief"] = entry["brief"]
            if entry.get("title"):  # translated headline saved alongside the brief
                it["title"] = entry["title"]
            # Pre-BRIEF_STYLE briefs keep publishing (if they clear the hard
            # gates) but are queued for a restyle whenever the run has spare
            # capacity, so the whole cache converges on the current prompt.
            if entry.get("style") != BRIEF_STYLE:
                it["brief_stale"] = True  # regenerate under the current prompt
    todo = [i for i in sorted(
        all_items,
        key=lambda x: (
            x.get("needs_translation", False), x.get("partner", False),
            not x["dek"], x["score"]),
        reverse=True,
    ) if not i.get("original") and "brief" not in i][:MAX_BRIEFS_PER_RUN]
    stale = sorted((i for i in all_items if i.get("brief_stale")),
                   key=lambda x: x["score"], reverse=True)
    if not todo and not stale:
        if cache_dirty:
            save_brief_cache(cache)
        print("\nBriefs: cache warm — nothing new to write.")
        return "ok"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if cache_dirty:
            save_brief_cache(cache)
        print("\nBriefs: ANTHROPIC_API_KEY not set — uncached wire stories will be withheld.")
        # A pending restyle of already-published briefs never degrades the build.
        return "disabled" if todo else "ok"
    try:
        import anthropic
    except ImportError:
        if cache_dirty:
            save_brief_cache(cache)
        print("\nBriefs: `anthropic` package not installed — uncached wire stories will be withheld.")
        return "disabled" if todo else "ok"

    # Remove ALL whitespace (including pasted line-wraps) from the secret — a broken
    # key corrupts the auth header and surfaces as APIConnectionError. The log line
    # prints only length + format validity, never the key (build logs are public).
    if len(todo) < MAX_BRIEFS_PER_RUN:  # spare capacity restyles old briefs
        todo.extend(stale[:MAX_BRIEFS_PER_RUN - len(todo)])
    key = re.sub(r"\s+", "", os.environ["ANTHROPIC_API_KEY"])
    print(f"Briefs: key length {len(key)}, format {'ok' if re.fullmatch(r'sk-ant-[A-Za-z0-9_-]+', key) else 'UNEXPECTED'}")
    client = anthropic.Anthropic(api_key=key)

    def safe(item):
        try:
            return write_brief(client, item)
        except Exception as e:  # isolate one provider failure; incomplete wire copy is withheld
            print(f"  ✗ brief failed ({item['pid']}): {type(e).__name__}")
            return None

    written = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for it, brief in zip(todo, ex.map(safe, todo)):
            if brief:
                it["brief"] = brief
                it.pop("brief_stale", None)
                entry = {"brief": brief, "ts": now_ts, "style": BRIEF_STYLE,
                         "title": it["title"]}  # the desk's own short headline
                cache[f"{it['lang']}:{it['pid']}"] = entry
                written += 1
    cache = {k: v for k, v in cache.items() if now_ts - v.get("ts", now_ts) < 60 * 86400}
    save_brief_cache(cache)
    print(f"\nBriefs: wrote {written} new of {len(todo)} attempted; cache holds {len(cache)}.")
    return "ok" if written == len(todo) else "degraded"


def save_brief_cache(cache):
    try:
        BRIEFS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Briefs: cache write failed ({type(exc).__name__}).")
        if HEALTH:
            HEALTH.checks["brief_cache"] = "degraded"


def select_publishable_copy(en_items, ar_items):
    """Apply the same translation and complete-copy rules in builds and review."""
    en_items = [
        item for item in en_items
        if not (
            item.get("needs_translation")
            and ARABIC_CHARS_RX.search(item["title"])
        )
    ]
    for item in en_items:
        if item.get("needs_translation") and ARABIC_CHARS_RX.search(item["dek"]):
            item["dek"] = ""

    allow_raw = os.environ.get("TOP_ALLOW_RAW_SUMMARIES") == "1"

    def keep(item):
        if item.get("vetoed") or item.get("brief_refused"):
            return False
        if item.get("original"):
            return True
        brief = item.get("brief")
        if brief and not REFUSAL_RX.search(brief):
            # Owner order 2026-08-03: a two-line stub never runs as an article.
            return (is_complete_text(brief, 160)
                    and len(brief.split()) >= MIN_BRIEF_WORDS)
        return allow_raw and is_complete_text(item.get("dek", ""), 60)

    return [item for item in en_items + ar_items if keep(item)]


def dedupe(items):
    seen, out = set(), []
    for it in items:
        kt = norm_title(it["title"])
        kl = re.sub(r"[?#].*$", "", it["link"])
        if kt in seen or kt[:60] in seen or kl in seen:
            continue
        seen.update({kt, kt[:60], kl})
        out.append(it)
    return out

# ---------- event-level dedupe ----------
# Two outlets covering one incident write two different headlines, so title-string
# dedupe misses them. The similarity logic lives in event_dedupe.py, shared with
# telegram_publish.py so the channel never re-receives the same news either.
from event_dedupe import (
    event_tokens, near_identical, same_coverage, same_event, same_story,
)

def dedupe_events(items):
    """One incident, one article. When a cluster forms, our own copy (original,
    then partner wire, then score) is the one that runs. Two rules admit an
    item to a cluster, and both are checked against every member the cluster
    has absorbed — not just its representative — so chains of follow-ups
    collapse instead of leaking every other link:
      1. near-identical headline (same words give or take an updated count):
         one running story, no time window — a daily-repeated headline must
         never publish twice (owner call 2026-08-02, after five same-headline
         follow-ups ran at once);
      2. same_event token similarity, only within 36 hours of a member;
      3. same_story headline-in-dek containment, same 36-hour window — the
         cross-desk net: an original and a wire brief on one event write
         unlike headlines, but the names one headline omits appear in the
         other's dek (owner call 2026-08-05, after a wire brief on the
         Dabbour arrest published beside the original covering it);
      4. same_coverage title+dek similarity, same 36-hour window — the
         diplomatic-meeting net: two desks compose fully disjoint headlines
         for one gathering, but the deks share actors, venue and subject
         (owner call 2026-08-05, after "Arab officials demand action on
         Jerusalem tensions" ran beside "Arab ministers meet in Amman…").
    Originals never fold into each other — the desk curates those."""
    clusters = []  # [representative, [titles], [tokens], [title+dek tokens], [dates]]
    ranked = sorted(items, key=lambda i: (
        i["source_id"] == "top-original", bool(i.get("partner")), i["score"]
    ), reverse=True)
    for it in ranked:
        toks = event_tokens(it["title"])
        ext = event_tokens(f"{it['title']} {(it.get('dek') or '')[:240]}")
        home = None
        for cluster in clusters:
            rep, titles, token_sets, ext_sets, dates = cluster
            if it.get("original") and rep.get("original"):
                continue
            if any(near_identical(it["title"], t) for t in titles) or any(
                abs((it["date"] - d).total_seconds()) <= 36 * 3600
                and (same_event(toks, m) or same_story(toks, x)
                     or same_story(m, ext) or same_coverage(ext, x))
                for m, x, d in zip(token_sets, ext_sets, dates)
            ):
                home = cluster
                break
        if home is None:
            clusters.append([it, [it["title"]], [toks], [ext], [it["date"]]])
            continue
        kept_item, titles, token_sets, ext_sets, dates = home
        titles.append(it["title"]); token_sets.append(toks)
        ext_sets.append(ext); dates.append(it["date"])
        existing = {
            (source.get("name", ""), source.get("url", ""))
            for source in kept_item.get("corroborating_sources", [])
        }
        for source in it.get("corroborating_sources", []):
            key = (source.get("name", ""), source.get("url", ""))
            if key not in existing:
                kept_item.setdefault("corroborating_sources", []).append(source)
                existing.add(key)
        sources = kept_item.get("corroborating_sources", [])
        if len({
            (source.get("name", ""), source.get("url", ""))
            for source in sources
            if source.get("name") and source.get("url")
        }) >= 2:
            for source in sources:
                source["verified"] = True
    survivors = {id(c[0]) for c in clusters}
    dropped = [i for i in items if id(i) not in survivors]
    for d in dropped:
        print(f"  ⊘ duplicate event dropped: {d['source']}: {d['title'][:70]}")
    return [i for i in items if id(i) in survivors]

def diversify(items):
    """Reorder so adjacent cards come from different outlets when possible."""
    pool, out = list(items), []
    while pool:
        pick = next((it for it in pool if not out or it["source_id"] != out[-1]["source_id"]), pool[0])
        pool.remove(pick)
        out.append(pick)
    return out

# ---------- original TOP journalism ----------
# Drop a text file into originals/ (GitHub → Add file) and the next build publishes
# it as a Times of Palestine original — our own byline, no external link-out.
# File name: originals/<slug>.<lang>.txt  (e.g. menaa-workshop.en.txt)
#   title: <headline>
#   category: humans            (any section key; default news)
#   date: 2026-07-28T12:00:00+00:00
#   image: https://...          (optional)
#   maxAgeHours: 336            (optional; how long the story stays on the site)
#   ---
#   Body paragraphs separated by blank lines.

def _original_slug(stem):
    return stem.rsplit(".", 1)[0] if "." in stem else stem


# Newspaper copy, not a briefing memo (owner decision 2026-07-30). A published
# article never carries analyst-deck apparatus: no "what is unresolved /
# unanswered questions / key takeaways / conclusion" sections, and it never
# ends on a list of questions. What is unknown is reported in prose sentences.
MEMO_HEADING_RX = re.compile(
    r"^#{2,4}\s*(what\s+(is|remains)\s+(unresolved|unanswered|unknown|unclear)|"
    r"(open|unanswered|outstanding|remaining)\s+questions?|key\s+takeaways?|takeaways?|"
    r"in\s+summary|summary|conclusions?|bottom\s+line|looking\s+ahead|what('|’)s\s+next|"
    r"ما\s+(الذي\s+)?(لم\s+يُ?حسم|يبقى\s+(مجهولاً|معلقاً|غامضاً))|"
    r"أسئلة\s+(مفتوحة|بلا\s+إجابة|عالقة)|الخلاصة|خلاصة|استنتاجات?|ما\s+التالي)\s*$",
    re.I | re.M)
_QUESTION_ITEM_RX = re.compile(r"^(?:[-*]|\d{1,2}\.)\s+.*[?؟]\**\s*$", re.M)


def memo_style_warnings(body):
    found = []
    m = MEMO_HEADING_RX.search(body)
    if m:
        found.append(f"briefing-memo heading {m.group(0).strip()!r}")
    blocks = [b.strip() for b in body.strip().split("\n\n") if b.strip()]
    for tail in blocks[-2:]:
        q_items = _QUESTION_ITEM_RX.findall(tail)
        if len(q_items) >= 2:
            found.append("article ends on a list of questions — report the "
                         "unknowns as prose sentences")
            break
    return found


class OriginalSkipError(PublishingError):
    """Unsafe original copy is skipped while the rest of the desk publishes."""


def validate_original(path, meta, body, lang, now, date):
    errors = []
    residue_warnings = []
    category = meta.get("category", "")
    if category not in ORIGINAL_CATEGORIES:
        errors.append(f"unknown category '{category}'")
    if date > now:
        errors.append(f"future date '{meta.get('date', '')}'")

    for m in ORIGINAL_IMG_MD_RX.finditer(body):
        src = m.group(2).strip()
        if src.startswith(("http://", "https://", "/")):
            continue
        media_path = ROOT / "originals" / "media" / src.lstrip("./")
        if not media_path.is_file():
            errors.append(f"missing media file '{src}'")

    longform = __import__("longform")
    rendered = longform.body_html(body)
    residue_warnings.extend(longform.rendered_residue_warnings(rendered))
    refusal_match = REFUSAL_RX.search(body)
    if refusal_match:
        residue_warnings.append(
            f"refusal-screen match '{refusal_match.group(0)}' — rephrase the "
            "flagged wording; refusal-pattern text never publishes")
    residue_warnings.extend(memo_style_warnings(body))
    residue_warnings.extend(passive_title_warnings(meta.get("title", ""), lang))
    if len(meta.get("title", "").split()) > TITLE_MAX_WORDS:
        residue_warnings.append(
            f"headline runs {len(meta['title'].split())} words — the rule is one "
            f"short complete sentence (max {TITLE_MAX_WORDS})")

    stats = {
        "subheads": len(re.findall(r'<h[234] class="sub">', rendered)),
        "figures": len(re.findall(r'<figure class="lf">', rendered)),
        "tables": len(re.findall(r'<table class="lf">', rendered)),
        "lists": len(re.findall(r'<(?:ul|ol) class="lf">', rendered)),
    }
    slug = _original_slug(path.stem)
    prev = ORIGINAL_BODY_STATS.get(slug)
    if prev and prev["lang"] != lang:
        parity = [k for k in ("subheads", "figures", "tables") if prev[k] != stats[k]]
        if parity:
            print(f"  ⚠ original parity {slug}: {prev['lang']} vs {lang} mismatch in {', '.join(parity)}")
    ORIGINAL_BODY_STATS[slug] = {"lang": lang, **stats}
    print(f"  → render checks {path.name}: subheads {stats['subheads']} / figures {stats['figures']} / tables {stats['tables']} / lists {stats['lists']}")
    # Machine-diction watch (owner order 2026-08-03): originals publish anyway
    # (gating defaults to publish) but the tell is logged loudly so the daily
    # editor cycle rewrites it — same nets the briefs desk is held to.
    diction = language_quality_issues(f"{meta.get('title', '')}\n{body}", lang)
    if diction:
        print(f"  ⚠ original diction {path.name}: {'; '.join(diction[:2])}")

    if errors:
        raise PublishingError(f"{path.name}: {'; '.join(errors)}")
    if residue_warnings:
        raise OriginalSkipError(
            f"{path.name}: unsafe rendered markup: {'; '.join(residue_warnings)}")


def load_originals(lang):
    if os.environ.get("TOP_SKIP_ORIGINALS") == "1":
        return []
    orig = ROOT / "originals"
    if not orig.is_dir():
        return []
    _orig_cover_cycle = {}
    now = datetime.now(timezone.utc)
    items = []
    for path in sorted(orig.glob(f"*.{lang}.txt")):
        text = path.read_text(encoding="utf-8")
        head, separator, body = text.partition("\n---\n")
        if not separator:
            raise PublishingError(f"{path.name}: missing metadata separator")
        meta = {}
        for line in head.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                meta[key.strip().lower()] = value.strip()
        body = body.strip()
        date = parse_date(meta.get("date", ""))
        if not date:
            raise PublishingError(f"{path.name}: valid UTC date is required")
        modified = parse_date(meta.get("modified", "")) if meta.get("modified") else None
        required = [
            key for key in ("title", "category", "date") if not meta.get(key)
        ]
        if required:
            raise PublishingError(
                f"{path.name}: missing required metadata: {', '.join(required)}")
        try:
            validate_original(path, meta, body, lang, now, date)
        except OriginalSkipError as error:
            print(f"  ⚠ original skipped: {error}")
            continue
        try:
            hours_kept = float(meta.get("maxagehours", 336))
        except ValueError as exc:
            raise PublishingError(f"{path.name}: invalid maxAgeHours") from exc
        if not meta.get("title") or not body:
            raise PublishingError(f"{path.name}: title and body are required")
        if (now - date).total_seconds() / 3600 > hours_kept:
            continue
        item = {
            "title": truncate(meta["title"], 200),
            "dek": truncate(re.sub(r"\s+", " ", body.split("\n\n")[0]), 260),
            "link": f"original:{path.stem}", "source_url": "",
            "date": date, "modified": modified,
            "source": TOP_SOURCE[lang], "source_id": "top-original",
            "source_type": "original", "image": None, "media": None,
            "categories": [], "lang": lang, "original": True, "partner": False,
            "brief": body, "cat": meta.get("category", "news"),
            "max_age_hours": hours_kept,
            # standing: yes → reference page (guide, directory, section
            # charter): stays published but never takes the hero tier.
            "standing": str(meta.get("standing", "")).strip().lower()
                        in ("yes", "true", "1"),
        }
        item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]
        attach_media(item, meta.get("image") or None, local_original=True)
        if not item.get("image") and meta.get("imagefallback"):
            # Second choice when a remote lede fails verification — usually
            # the report's own house infographic, so the story never drops
            # to the generic category cover just because a portrait moved.
            attach_media(item, meta["imagefallback"], local_original=True)
        if not item.get("image"):
            # No lede should ever be the bare flag placeholder: text-only desk
            # reports get the branded category cover (house SVG), alternating
            # A/B variants so adjacent reports never show twin covers.
            _n = _orig_cover_cycle.get(item["cat"], 0)
            _orig_cover_cycle[item["cat"]] = _n + 1
            cover = f"times-of-palestine-cover-{item['cat']}{'-b' if _n % 2 else ''}.svg"
            if not (ROOT / "originals" / "media" / cover).is_file():
                cover = f"times-of-palestine-cover-{item['cat']}.svg"
            if (ROOT / "originals" / "media" / cover).is_file():
                attach_media(item, f"/media/{cover}", local_original=True)
        __import__("longform").validate_media_references(
            body, MEDIA_RIGHTS, path.name)
        item["media_evidence"] = __import__("longform").media_review_evidence(
            body,
            (meta.get("image") or None)
            if not is_http_url(meta.get("image", "")) else None,
        )
        attach_corrections(item)
        validate_story(item, local=True)
        item["score"] = score_item(item) + FOCUS_BOOST
        items.append(item)
        print(f"  ✓ original: {item['title'][:60]}")
    return items

_IMG_HASH_MEMO = {}

def _card_image_hash(url):
    """Content fingerprint for a remote card image (first 512 KB). Fails
    open (None) — a fetch error must never block publication."""
    if url in _IMG_HASH_MEMO:
        return _IMG_HASH_MEMO[url]
    digest = None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "image/*,*/*;q=0.5"})
        with safe_urlopen(req, timeout=4) as r:
            digest = hashlib.sha1(r.read(1 << 19)).hexdigest()
    except Exception:
        pass
    _IMG_HASH_MEMO[url] = digest
    return digest

IMAGE_OVERRIDES = load_editorial_json(
    ROOT / "editorial" / "image-overrides.json", {})


def apply_image_overrides(items):
    """Photo-desk kill switch (owner order 2026-08-03): a story listed in
    editorial/image-overrides.json gets its image replaced no matter what
    the wire supplies — "cover" for the branded category cover, a local
    /media/ path, or a rights-cleared https URL. Keyed by pid, so the order
    holds through every rebuild for the story's lifetime."""
    if not IMAGE_OVERRIDES:
        return
    for it in items:
        ov = IMAGE_OVERRIDES.get(it.get("pid"))
        if not ov:
            continue
        target = (ov.get("image") or "cover").strip()
        if target == "cover":
            cover = f"times-of-palestine-cover-{it['cat']}.svg"
            if not (ROOT / "originals" / "media" / cover).is_file():
                cover = "times-of-palestine-cover-news.svg"
            it["image"] = f"/media/{cover}"
        else:
            it["image"] = target
        if it["image"].startswith("/media/times-of-palestine-"):
            it["media"] = {"credit": "Graphic: Times of Palestine",
                           "rightsBasis": "owned",
                           "source": "Times of Palestine", "licenseUrl": None}
        else:
            # An overriding photo carries ITS OWN manifest credit — never the
            # replaced wire image's. Missing entry → no credit line at all.
            rights = media_rights_for(it["image"], MEDIA_RIGHTS)
            it["media"] = ({"credit": rights.credit,
                            "rightsBasis": rights.rights_basis,
                            "source": rights.source,
                            "licenseUrl": rights.license_url or None}
                           if rights else None)


def dedupe_card_images(items):
    """One photo, one story (owner report 2026-08-02): the same upstream
    photo riding two different stories reads as a broken front. Items whose
    remote images match — same URL, or same bytes re-uploaded under two
    URLs — keep the photo only on the newest story; the others step down to
    their branded category cover. Local house assets are exempt (category
    covers repeat by design), and the content check fails open."""
    remote = [i for i in items if is_http_url(i.get("image") or "")]
    urls = sorted({i["image"] for i in remote})
    if len(urls) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(_card_image_hash, urls))
    seen = set()
    for it in sorted(remote, key=lambda i: (i["date"], i["score"]), reverse=True):
        key = _card_image_hash(it["image"]) or it["image"]
        if key in seen:
            cover = f"times-of-palestine-cover-{it['cat']}.svg"
            if not (ROOT / "originals" / "media" / cover).is_file():
                cover = "times-of-palestine-cover-news.svg"
            it["image"] = f"/media/{cover}"
            it["media"] = {"credit": "Graphic: Times of Palestine",
                           "rightsBasis": "owned",
                           "source": "Times of Palestine", "licenseUrl": None}
        else:
            seen.add(key)

def build_lang(lang):
    print(f"\nFetching {lang.upper()} feeds…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda f: fetch_feed(f, lang), FEEDS[lang]))
    results.append(load_originals(lang))
    items, removed = cluster_duplicates([i for r in results for i in r])
    before_event_dedupe = len(items)
    items = dedupe_events(items)
    removed += before_event_dedupe - len(items)
    if HEALTH:
        HEALTH.deduplicated += removed
    caps = {f["id"]: f.get("cap", PER_SOURCE_CAP) for f in FEEDS[lang]}; caps["top-original"] = 200
    per_source, capped = {}, []
    for it in items:
        per_source[it["source_id"]] = per_source.get(it["source_id"], 0) + 1
        if per_source[it["source_id"]] <= caps.get(it["source_id"], PER_SOURCE_CAP):
            capped.append(it)
    print(f"  → {len(capped)} items after dedupe/cap")
    # Visual-first (owner decision 2026-07-30): no story runs as dead text.
    # Person-photo pass: articles about key political figures get a portrait
    # before we fall back to the generic category cover.
    for it in capped:
        backfill_person_photo(it)
    # Anything still photoless gets its branded category cover — the flag
    # placeholder is a last resort, not a norm. Covers alternate between the
    # A and mirrored B variant per category, so two photoless stories in one
    # section read as a designed pair, not a copy-paste artifact (owner
    # visual audit 2026-08-02).
    cover_cycle = {}
    for it in capped:  # continue the A/B alternation past originals' covers
        if (it.get("image") or "").startswith("/media/times-of-palestine-cover-"):
            cover_cycle[it["cat"]] = cover_cycle.get(it["cat"], 0) + 1
    for it in capped:
        if not it.get("image"):
            n = cover_cycle.get(it["cat"], 0)
            cover_cycle[it["cat"]] = n + 1
            cover = f"times-of-palestine-cover-{it['cat']}{'-b' if n % 2 else ''}.svg"
            if not (ROOT / "originals" / "media" / cover).is_file():
                cover = f"times-of-palestine-cover-{it['cat']}.svg"
            if (ROOT / "originals" / "media" / cover).is_file():
                it["image"] = f"/media/{cover}"
                it["media"] = {"credit": "Graphic: Times of Palestine",
                               "rightsBasis": "owned",
                               "source": "Times of Palestine", "licenseUrl": None}
    apply_image_overrides(capped)
    dedupe_card_images(capped)
    return capped
# ---------- localization ----------

STR = {
    "en": {
        "dir": "ltr", "lang": "en",
        "site_name": "Times of Palestine",
        "masthead_top": "TIMES", "masthead_bottom": "OF PALESTINE",
        "kicker": "Every outlet · Every story · No censorship",
        "view_all": "View all →", "search_nav": "🔍 Search",
        "search_go": "Search",
        "search_title": "Search", "search_prompt": "Search the Times of Palestine archive…",
        "search_none": "No results", "follow_tg": "Telegram channel →",
        "breaking": "BREAKING", "latest": "The Latest",
        "updated": "Updated", "tz": "Jerusalem time",
        "switch_lang": "🌐 العربية", "switch_href": "../ar/",
        "hero_label": "TOP STORY",
        "sections": {"gaza": "Gaza", "westbank": "West Bank & Jerusalem",
                     "humans": "Real Lives", "health": "Health & Healing",
                     "women": "Her Story",
                     "arabaid": "Arab Support",
                     "archive": "From the Archive",
                     "diaspora": "The Diaspora",
                     "arts": "Culture & Arts", "sports": "Sport",
                     "accountability": "Transparency & Accountability",
                     "research": "Research & Investigations",
                     "bitcoin": "Financial Freedom",
                     "politics": "Politics & Diplomacy", "economy": "Economy & Aid",
                     "social": "Field Reports",
                     "opinion": "Opinion & Analysis", "news": "More News"},
        "mission_title": "Editorial Charter",
        "mission": ("Times of Palestine is an independent digital newsroom. We gather and relay "
                    "reporting from across Palestine and around the world — continuously, without "
                    "censorship and without favor. We hold power to account wherever it sits: we "
                    "report on corruption without fear, defend transparency and democratic rights, "
                    "and criticize whoever warrants criticism — through journalism, never personal "
                    "attacks. We answer to no government, party or faction. Our only allegiance is "
                    "to verified truth, and to the people of Palestine and their God-given human "
                    "rights."),
        "attribution": ("Wire reporting is rewritten in-house before publication; every story "
                        "names its source outlet in the text, and publishers retain all rights "
                        "to their work."),
        "footer_lang": "اقرأ بالعربية ←",
        "research_kicker": "FEATURED REPORT",
        "title_suffix": "Independent Palestine News",
        "read_original": "Read the full story at",
        "photo_via": "Photo via",
        "byline": "By TOP Newsdesk",
        "kind_original": "Original Reporting", "kind_brief": "TOP News Brief",
        "kind_curated": "Curated Summary", "based_on": "Based on reporting by",
        "keep_reading": "Keep Reading",
        "toc": "Story guide",
        "back_home": "← All the news",
        "breadcrumbs_home": "Home",
        "section_latest": "Latest",
        "section_fresh": "fresh",
        "story_published": "Published",
        "story_updated": "Updated",
        "summary_note": "Summary curated by Times of Palestine. The full story belongs to its publisher.",
        "special_nav": "Special Report",
        "tips_nav": "Send a Tip",
        "tips_kicker": "SECURE TIP LINE",
        "tips_title": "Know something the public should know?",
        "tips_sub": ("Corruption, abuse of power, a story no one will touch — or your own "
                     "reporting from the field. Send it to our newsroom on Signal. "
                     "Encrypted. Anonymous if you choose."),
        "tips_cta": "Message us on Signal",
        "tips_tg": "Or message us on Telegram", "tips_tg_note": "Telegram is convenient, but Signal is the safer choice for sensitive material.",
        "tips_micro": "No name. No number. Just the truth.",
        "tips_scan": "or scan with your phone",
        "tips_safety": ("For your safety: use Signal on a personal device, and share nothing that "
                        "identifies you unless you choose to."),
    },
    "ar": {
        "dir": "rtl", "lang": "ar",
        "site_name": "تايمز أوف فلسطين",
        "masthead_top": "تايمز", "masthead_bottom": "أوف فلسطين",
        "kicker": "كل المصادر · كل الأخبار · بلا رقابة",
        "view_all": "كل التغطية ←", "search_nav": "🔍 بحث",
        "search_go": "ابحث",
        "search_title": "بحث", "search_prompt": "ابحث في أرشيف تايمز أوف فلسطين…",
        "search_none": "لا نتائج", "follow_tg": "قناتنا على تيليغرام ←",
        "breaking": "عاجل", "latest": "آخر الأخبار",
        "updated": "آخر تحديث", "tz": "بتوقيت القدس",
        "switch_lang": "🌐 English", "switch_href": "../en/",
        "hero_label": "الخبر الأبرز",
        "sections": {"gaza": "غزة", "westbank": "الضفة والقدس",
                     "humans": "حكايات فلسطينية", "health": "الصحة والتعافي",
                     "women": "حكايتها",
                     "arabaid": "الإسناد العربي",
                     "archive": "من الأرشيف",
                     "diaspora": "الشتات الفلسطيني",
                     "arts": "الثقافة والفنون", "sports": "رياضة",
                     "accountability": "شفافية ومساءلة",
                     "research": "أبحاث وتحقيقات",
                     "bitcoin": "الحرية المالية",
                     "politics": "سياسة ودبلوماسية", "economy": "اقتصاد وإغاثة",
                     "social": "من الميدان",
                     "opinion": "رأي وتحليل", "news": "المزيد من الأخبار"},
        "mission_title": "الميثاق التحريري",
        "mission": ("«تايمز أوف فلسطين» غرفة أخبار رقمية مستقلة. نجمع الأخبار وننقلها من داخل فلسطين "
                    "ومن حول العالم — باستمرار، بلا رقابة وبلا محاباة. نحاسب السلطة أينما كانت: "
                    "نكشف الفساد بلا خوف، وندافع عن الشفافية والحقوق الديمقراطية، وننتقد كل من "
                    "يستحق النقد — بالصحافة المهنية لا بالإساءات الشخصية. لا نتبع حكومة ولا حزباً "
                    "ولا فصيلاً. ولاؤنا الوحيد للحقيقة الموثّقة، ولشعب فلسطين وحقوقه الإنسانية التي "
                    "وهبها الله له."),
        "attribution": "تُعاد صياغة أخبار الوكالات داخل غرفة التحرير قبل نشرها؛ ويسمّي كل تقرير مصدره داخل النص، ويحتفظ الناشرون بكامل حقوقهم.",
        "footer_lang": "→ Read in English",
        "research_kicker": "تقرير مميز",
        "title_suffix": "أخبار فلسطين المستقلة",
        "read_original": "اقرأ المادة كاملة في",
        "photo_via": "الصورة عبر",
        "byline": "غرفة أخبار «تايمز أوف فلسطين»",
        "kind_original": "تقرير أصلي", "kind_brief": "موجز تايمز أوف فلسطين",
        "kind_curated": "ملخص محرَّر", "based_on": "استناداً إلى تقرير",
        "keep_reading": "تابع القراءة",
        "toc": "دليل القصة",
        "back_home": "كل الأخبار ←",
        "breadcrumbs_home": "الرئيسية",
        "section_latest": "آخر تحديث",
        "section_fresh": "جديد",
        "story_published": "نُشر",
        "story_updated": "حُدّث",
        "summary_note": "الملخص من إعداد «تايمز أوف فلسطين». المادة الكاملة ملك لناشرها الأصلي.",
        "special_nav": "تحقيق خاص",
        "tips_nav": "أرسل معلومة",
        "tips_kicker": "خط المعلومات الآمن",
        "tips_title": "تعرف شيئاً يستحق أن يعرفه الناس؟",
        "tips_sub": ("فساد، تجاوز للسلطة، قصة لا يجرؤ أحد على نشرها — أو تقريرك الميداني الخاص. "
                     "أرسله إلى غرفة الأخبار عبر «سيغنال». مشفّر، ومجهول الهوية إن اخترت."),
        "tips_cta": "راسلنا على سيغنال",
        "tips_tg": "أو راسلنا عبر تيليغرام", "tips_tg_note": "تيليغرام أسهل، لكن «سيغنال» أكثر أماناً للمواد الحساسة.",
        "tips_micro": "بلا اسم. بلا رقم. فقط الحقيقة.",
        "tips_scan": "أو امسح الرمز بهاتفك",
        "tips_safety": "لسلامتك: استخدم «سيغنال» من جهازك الشخصي، ولا تشارك أي تفاصيل تكشف هويتك إلا إذا اخترت ذلك.",
    },
}

# Focus sections sit high on the page; each edition leads with its editorial priority.
# Research (think tanks / OSINT) comes first: news before it becomes news.
# WATCH LIVE (owner directive 2026-08-03): a floating «مباشر» pill on the
# Arabic edition opens a docked corner mini-player with Al Jazeera's live
# broadcast — when major news breaks, the reader watches instantly, from any
# page, while continuing to read. The iframe loads only on tap. Empty id
# disables the pill for that edition. Al Jazeera English's stream
# (gCNeDWCI0vo) can switch the EN edition on with one line.
LIVE_TV = {
    "en": {"id": "", "label": "Al Jazeera English — Live", "word": "LIVE"},
    "ar": {"id": "bNyUyrR0PHo", "label": "الجزيرة — البث الحي", "word": "مباشر"},
}

_LIVE_JS = """
(function(){var f=document.getElementById("livefab");if(!f)return;
try{if(sessionStorage.getItem("top-live-hide")){f.hidden=true;return}}catch(e){}
var ID=f.dataset.video,TITLE=f.dataset.title,dock=null;
function close(){if(dock){dock.remove();dock=null}f.hidden=false}
f.querySelector(".fab-x").addEventListener("click",function(e){e.stopPropagation();
 f.hidden=true;try{sessionStorage.setItem("top-live-hide","1")}catch(err){}});
f.addEventListener("click",function(){f.hidden=true;
 dock=document.createElement("div");dock.className="livedock";
 var bar=document.createElement("div");bar.className="ld-bar";
 var cap=document.createElement("span");cap.textContent=TITLE;
 var x=document.createElement("button");x.className="ld-x";x.textContent="\\u2715";
 x.setAttribute("aria-label",f.dataset.close);x.addEventListener("click",close);
 bar.appendChild(cap);bar.appendChild(x);
 var fr=document.createElement("div");fr.className="ld-frame";
 var i=document.createElement("iframe");
 i.src="https://www.youtube-nocookie.com/embed/"+ID+"?autoplay=1";
 i.title=TITLE;i.setAttribute("allow","autoplay; encrypted-media; picture-in-picture; web-share");
 i.setAttribute("allowfullscreen","");
 fr.appendChild(i);dock.appendChild(bar);dock.appendChild(fr);
 document.body.appendChild(dock)});
})();
"""


def live_fab_html(lang):
    """The floating live-TV pill + its script, or empty when disabled."""
    tv = LIVE_TV.get(lang) or {}
    if not tv.get("id"):
        return ""
    close_label = "إغلاق البث" if lang == "ar" else "Close the stream"
    hide_label = "إخفاء زر البث" if lang == "ar" else "Hide the live button"
    return (f'<button id="livefab" class="livefab" data-video="{esc(tv["id"])}" '
            f'data-title="{esc(tv["label"])}" data-close="{esc(close_label)}" '
            f'aria-label="{esc(tv["label"])}">'
            f'<span class="dot"></span>{esc(tv["word"])}'
            f'<span class="fab-x" role="button" aria-label="{esc(hide_label)}">✕</span></button>'
            f'<script>{_LIVE_JS}</script>')

SECTION_ORDER = {
    "en": ["gaza", "westbank", "women", "arabaid", "research", "health", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news", "archive"],
    "ar": ["gaza", "westbank", "women", "arabaid", "research", "health", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news", "archive"],
}
FOCUS_SECTIONS = {"research", "diaspora", "arts", "sports", "accountability", "bitcoin", "social", "health", "archive", "arabaid", "women"}  # shown even with one story

WEEKDAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS_AR = ["كانون الثاني/يناير", "شباط/فبراير", "آذار/مارس", "نيسان/أبريل", "أيار/مايو",
             "حزيران/يونيو", "تموز/يوليو", "آب/أغسطس", "أيلول/سبتمبر", "تشرين الأول/أكتوبر",
             "تشرين الثاني/نوفمبر", "كانون الأول/ديسمبر"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]

def full_date(dt, lang):
    d = dt.astimezone(GAZA)
    if lang == "ar":
        return f"{WEEKDAYS_AR[d.weekday()]}، {d.day} {MONTHS_AR[d.month - 1]} {d.year}"
    return f"{WEEKDAYS_EN[d.weekday()]}, {MONTHS_EN[d.month - 1]} {d.day}, {d.year}"

def ar_count(n, one, two, few, many):
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"

def new_mark(it, lang):
    """A pulsing NEW mark on stories under 90 minutes old — the page must feel alive."""
    mins = (datetime.now(timezone.utc) - it["date"]).total_seconds() / 60
    if mins > 90:
        return ""
    label = "جديد" if lang == "ar" else "NEW"
    return f'<span class="newmark">{label}</span>'


def time_ago(date, lang):
    mins = max(1, round((datetime.now(timezone.utc) - date).total_seconds() / 60))
    if lang == "ar":
        if mins < 60:
            return "قبل " + ar_count(mins, "دقيقة", "دقيقتين", "دقائق", "دقيقة")
        hours = round(mins / 60)
        if hours < 24:
            return "قبل " + ar_count(hours, "ساعة", "ساعتين", "ساعات", "ساعة")
        return "قبل " + ar_count(round(hours / 24), "يوم", "يومين", "أيام", "يوماً")
    if mins < 60:
        return f"{mins}m ago"
    hours = round(mins / 60)
    if hours < 24:
        return f"{hours}h ago"
    return f"{round(hours / 24)}d ago"


def is_fresh(date):
    return (datetime.now(timezone.utc) - date).total_seconds() / 60 <= 90


def compact_stamp(date, lang):
    d = date.astimezone(GAZA)
    return f"{d.day:02d}/{d.month:02d} · {d.hour:02d}:{d.minute:02d}"


def full_stamp(date, lang):
    d = date.astimezone(GAZA)
    return f"{full_date(d, lang)} · {d.hour:02d}:{d.minute:02d} {STR[lang]['tz']}"


def time_tag(date, lang, cls="t", fresh=False):
    """Card timestamp: one relative time only (design pass 2026-08-06 —
    '8m ago · 06/08 · 01:18' was three clocks saying one thing). The full
    minute-level stamp stays honest in the title tooltip and datetime attr;
    story pages carry the complete published/updated stamps."""
    prefix = new_mark({"date": date}, lang) if fresh else ""
    return (f'<time class="{cls}" datetime="{utc_iso(date)}" '
            f'title="{esc(full_stamp(date, lang))}">{prefix}'
            f'{time_ago(date, lang)}</time>')


def story_count_label(n, lang):
    if lang == "ar":
        return ar_count(n, "قصة واحدة", "قصتان", "قصص", "قصة")
    return f"{n} story" if n == 1 else f"{n} stories"


def section_meta(items, lang):
    if not items:
        return ""
    latest = max(items, key=lambda i: i["date"])
    bits = [story_count_label(len(items), lang)]
    fresh = sum(1 for item in items if is_fresh(item["date"]))
    if fresh:
        bits.append(
            (f"{fresh} {STR[lang]['section_fresh']}")
            if lang == "en" else f"{fresh} {STR[lang]['section_fresh']}"
        )
    bits.append(f"{STR[lang]['section_latest']} {compact_stamp(latest['date'], lang)}")
    return f'<p class="sec-meta">{" · ".join(bits)}</p>'


HEADING_RX = re.compile(r'<h2 class="sub">(.+?)</h2>')


def fragment_id(text):
    value = strip_html(text).lower()
    value = re.sub(r"[^\w\s؀-ۿ-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[-\s]+", "-", value).strip("-")
    return value[:64] or "section"


def add_story_outline(rendered, lang):
    seen = {}
    entries = []
    anchor_label = "Jump to this section" if lang == "en" else "انتقل إلى هذا القسم"

    def repl(match):
        title_html = match.group(1)
        title_text = strip_html(title_html)
        fid = fragment_id(title_text)
        seen[fid] = seen.get(fid, 0) + 1
        if seen[fid] > 1:
            fid = f"{fid}-{seen[fid]}"
        entries.append((fid, title_text))
        return (f'<h2 class="sub" id="{fid}">{title_html}'
                f'<a class="anchor" href="#{fid}" aria-label="{esc(anchor_label)}">#</a></h2>')

    outlined = HEADING_RX.sub(repl, rendered)
    if len(entries) < 3:
        return outlined, ""
    toc_items = "".join(
        f'<li><a href="#{fid}">{esc(title)}</a></li>' for fid, title in entries
    )
    toc = (f'<nav class="story-toc" aria-label="{esc(STR[lang]["toc"])}">'
           f'<p class="toc-title">{esc(STR[lang]["toc"])}</p><ol>{toc_items}</ol></nav>')
    return outlined, toc

# ---------- CSS (shared by both languages; logical properties handle RTL) ----------
# Arabic type: Noto Kufi Arabic (SIL OFL, self-hosted variable font) — the
# closest open-licensed face to Al Jazeera's exclusive Atrissi typeface,
# giving the Arabic edition the same modern low-contrast Kufi register.
CSS = """
@font-face{font-family:"Noto Kufi Arabic";src:url("/fonts/NotoKufiArabic-var.woff2") format("woff2");font-weight:100 900;font-style:normal;font-display:swap;unicode-range:U+0600-06FF,U+0750-077F,U+0870-088E,U+08A0-08FF,U+200C-200E,U+2010-2011,U+FB50-FDFF,U+FE70-FEFC}
:root{
  --red:#C8102E; --green:#00753A; --green-deep:#00602F; --black:#0b0b0c; --ink:#141419; --muted:#595962;
  --paper:#f8f7f2; --card:#ffffff; --line:#e6e3da; --line-dark:#c9c5b8;
  --serif:Georgia,"Times New Roman",Times,serif; --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --max:1300px;
  --sh:0 2px 8px rgba(0,0,0,.07),0 1px 3px rgba(0,0,0,.05);
  --sh-h:0 6px 22px rgba(0,0,0,.11),0 2px 6px rgba(0,0,0,.06);
  --tr:.18s ease; --r:3px;
}
[lang=ar]{--serif:"Noto Kufi Arabic",Tahoma,"Noto Naskh Arabic","Amiri",serif;--sans:"Noto Kufi Arabic",Tahoma,"Noto Sans Arabic",Arial,sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.65;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}
.wrap{max-width:var(--max);margin-inline:auto;padding-inline:clamp(16px,2.5vw,26px)}
.topbar{background:var(--black);color:#cfcfd6;font-size:.75rem}
.topbar .wrap{display:flex;align-items:center;gap:.8rem 1.1rem;min-height:40px;flex-wrap:wrap;padding-block:.25rem}
.topbar .date{color:#fff;font-weight:600;letter-spacing:.02em}
.topbar .upd{display:flex;align-items:center;gap:.4rem}
.topbar .dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.35}}
.topbar .lang{margin-inline-start:auto;color:#fff;font-weight:700;border:1px solid #3a3a42;padding:.2rem .7rem;border-radius:var(--r)}
.topbar .lang:hover{background:var(--red);border-color:var(--red)}
.ticker{background:var(--red);color:#fff;overflow:hidden;display:flex;align-items:stretch}
.ticker .label{background:var(--black);font-weight:800;letter-spacing:.12em;font-size:.72rem;display:flex;align-items:center;padding:.45rem .9rem;flex-shrink:0;z-index:2}
[lang=ar] .ticker .label{letter-spacing:.02em}
.ticker .rail{overflow:hidden;flex:1;display:flex;align-items:center}
.ticker .track{display:flex;gap:2.5rem;white-space:nowrap;animation:tick 80s linear infinite;padding-inline:1.5rem}
[dir=rtl] .ticker .track{animation-name:tick-rtl}
.ticker:hover .track,.ticker:focus-within .track,.ticker.paused .track{animation-play-state:paused}
.tick-pause{background:transparent;border:0;color:#fff;cursor:pointer;font-size:.8rem;padding:.45rem .7rem;flex-shrink:0;z-index:2;opacity:.85}
.tick-pause:hover,.tick-pause:focus-visible{opacity:1}
.ticker a{font-size:.82rem;font-weight:600}
.ticker a::before{content:"●";color:rgba(255,255,255,.55);margin-inline-end:.7rem;font-size:.55rem;vertical-align:2px}
@keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@keyframes tick-rtl{from{transform:translateX(0)}to{transform:translateX(50%)}}
/* Masthead — the newsweekly register (owner order 2026-08-06): a towering
   flag-red Roman-serif TIMES inside the slim red cover frame the world
   already knows how to read, OF PALESTINE running beneath in spaced caps.
   The Palestinian flag rule stays under the frame — the frame carries the
   authority, the flag says whose. House --red only; no new hex family. */
.masthead{background:var(--card);border-bottom:2px solid var(--line);text-align:center;padding:1.5rem 0 1.1rem}
.masthead .logotype{display:inline-block;border:3px solid var(--red);padding:.5rem 1.7rem .62rem}
.masthead .wrap::after{content:"";display:block;margin:.9rem auto 0;width:130px;height:5px;background:linear-gradient(90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
[dir=rtl] .masthead .wrap::after{background:linear-gradient(-90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
.masthead h1,.masthead .wordmark{display:flex;flex-direction:column;align-items:center;gap:.3rem;line-height:1;white-space:nowrap}
.masthead .l1{font-family:"Times New Roman",Times,var(--serif);font-weight:700;letter-spacing:-.02em;color:var(--red);font-size:clamp(2.5rem,7vw,4rem);transform:scaleY(1.05)}
.masthead .l2{font-family:var(--serif);font-weight:700;color:var(--ink);font-size:clamp(.66rem,1.75vw,.94rem);letter-spacing:.42em;text-indent:.42em}
[lang=ar] .masthead .l1{font-family:"Noto Kufi Arabic","Amiri",serif;font-weight:800;letter-spacing:0;transform:none;font-size:clamp(2.1rem,6.4vw,3.3rem);line-height:1.2}
[lang=ar] .masthead .l2{letter-spacing:0;text-indent:0;font-family:"Noto Kufi Arabic","Amiri",serif;font-size:clamp(.92rem,2.2vw,1.16rem);line-height:1.45}
.masthead.compact{padding:.8rem 0 .6rem}
.masthead.compact .logotype{border-width:2px;padding:.28rem .95rem .38rem}
.masthead.compact .l1{font-size:1.5rem}
.masthead.compact .l2{font-size:.5rem;letter-spacing:.34em;text-indent:.34em}
[lang=ar] .masthead.compact .l1{font-size:1.3rem}
[lang=ar] .masthead.compact .l2{font-size:.64rem}
nav.sections{position:sticky;top:0;background:rgba(11,11,12,.97);z-index:50;box-shadow:0 2px 12px rgba(0,0,0,.3);backdrop-filter:blur(4px)}
nav.sections .wrap{display:flex;flex-wrap:wrap;align-items:stretch;gap:.15rem;padding-block:.15rem}
nav.sections a{color:#d8d8e2;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:.68rem .7rem;white-space:nowrap;border-block-end:2px solid transparent;transition:color var(--tr),border-color var(--tr)}
[lang=ar] nav.sections a{letter-spacing:0;font-size:.8rem}
nav.sections a:hover{color:#fff;border-block-end-color:#3a3a42}
nav.sections a.home{color:#f93549}
nav.sections a.home:hover{border-block-end-color:#f93549}
nav.sections a.tip{color:#3fd07c}
nav.sections a.tip:hover{border-block-end-color:#3fd07c}
/* Grouped nav (owner order 2026-08-05, after the two-tier bar reached ~19
   visible links): one line-tab bar — THE LATEST, four dropdown groups, the
   gold nav-primary specials, and the search/tip utilities inline-end. The
   line-tab language of #117/#118 is kept: no pills, 2px indicator, black
   band. Dropdowns open on hover/focus on pointer devices and on tap
   everywhere (button carries aria-expanded; opening one closes the rest). */
nav.sections .nav-group{position:relative}
nav.sections .nav-gbtn{background:none;border:0;cursor:pointer;color:#f2eee8;font-family:var(--sans);font-size:.78rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase;padding:.68rem .7rem;white-space:nowrap;border-block-end:2px solid transparent;transition:color var(--tr),border-color var(--tr)}
[lang=ar] nav.sections .nav-gbtn{letter-spacing:0;font-size:.9rem}
nav.sections a.home{font-size:.78rem;font-weight:800}
[lang=ar] nav.sections a.home{font-size:.9rem}
nav.sections .nav-gbtn .chev{font-size:.6em;opacity:.7;margin-inline-start:.25rem;vertical-align:2px}
nav.sections .nav-gbtn:hover,nav.sections .nav-group.open .nav-gbtn{color:#fff;border-block-end-color:var(--red)}
nav.sections .nav-drop{display:none;position:absolute;inset-inline-start:0;top:100%;min-width:15rem;background:#0b0b0c;border:1px solid rgba(255,255,255,.12);border-top:2px solid var(--red);box-shadow:0 10px 24px rgba(0,0,0,.45);padding:.3rem 0;z-index:60}
nav.sections .nav-group.open .nav-drop{display:block}
@media(hover:hover){nav.sections .nav-group:hover .nav-drop,nav.sections .nav-group:focus-within .nav-drop{display:block}}
nav.sections .nav-drop a{display:block;padding:.6rem 1rem;border-block-end:0;font-size:.7rem}
[lang=ar] nav.sections .nav-drop a{font-size:.8rem}
nav.sections .nav-drop a:hover{background:rgba(255,255,255,.07);color:#fff}
nav.sections a.special{color:#c7a86b}
nav.sections .nav-util{display:flex;gap:.15rem;margin-inline-start:auto}
nav.sections a.util{color:#d8d8e2}
nav.sections a.util:hover{border-block-end-color:#3a3a42}
/* Quick search (evaluation 2026-08-05): the SEARCH utility slides a query
   bar down from the sticky band; the form submits to the search page, which
   reads ?q=. No-JS fallback: the link itself still goes to the search page. */
nav.sections .nav-search{background:#0b0b0c;border-top:2px solid var(--red);box-shadow:0 10px 24px rgba(0,0,0,.45)}
nav.sections .nav-search[hidden]{display:none}
nav.sections .nav-search form{display:flex;gap:.55rem;max-width:var(--max);margin-inline:auto;padding:.65rem clamp(16px,2.5vw,26px)}
nav.sections .nav-search input{flex:1;min-width:0;font-size:1rem;padding:.55rem .8rem;border:1px solid #3a3a42;border-radius:var(--r);background:#141419;color:#f2eee8}
nav.sections .nav-search input::placeholder{color:#8f8f99}
nav.sections .nav-search input:focus{outline:2px solid var(--red);outline-offset:1px}
nav.sections .nav-search button{background:var(--red);color:#fff;border:0;border-radius:var(--r);font:800 .8rem/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;padding:.55rem 1.1rem;cursor:pointer;min-width:44px}
[lang=ar] nav.sections .nav-search button{letter-spacing:0;font-size:.9rem}
nav.sections .nav-search button:hover{filter:brightness(1.12)}
/* Phones: ONE swipeable line of tabs (the app pattern readers know), never
   a two-or-three-row block eating the viewport (owner report 2026-08-06 —
   the wrapped bar pushed the lead story below the fold). Dropdowns and the
   search panel anchor to the sticky nav itself, so they stay full-width and
   unclipped by the scrolling row. ~44px tap targets throughout. */
@media(max-width:740px){
  nav.sections .wrap{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
  nav.sections .wrap::-webkit-scrollbar{display:none}
  nav.sections a{padding-block:.85rem}
  nav.sections .nav-gbtn{padding-block:.85rem}
  nav.sections .nav-group{position:static}
  nav.sections .nav-drop{inset-inline:0;top:100%;min-width:0;border-inline:0}
  .masthead{padding:.85rem 0 .65rem}
  .masthead .wrap::after{margin-top:.5rem}
  /* Tap targets (a11y, evaluation 2026-08-05): utility controls reach the
     house ~44px tap height on touch widths, matching the nav rows above. */
  .themetoggle,.litetoggle,.tick-pause{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px}
  .topbar .lang{display:inline-flex;align-items:center;min-height:38px;padding-inline:.9rem}
}
/* ── hero ── */
.hero-zone{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:1.55rem;padding-block:1.5rem}
.hero{border-inline-end:1px solid var(--line);padding-inline-end:1.6rem}
.hero-imgwrap{position:relative;overflow:hidden;border-radius:var(--r);background:#141419}
.hero-imgwrap>a{display:block}
.hero-imgwrap>a>img{aspect-ratio:16/9;object-fit:cover;object-position:50% 22%;width:100%;background:#141419;transition:transform .55s ease}
.hero-imgwrap:hover>a>img{transform:scale(1.03)}
.hero-overlay{position:absolute;bottom:0;inset-inline:0;padding:3.5rem 1.5rem 1.5rem;background:linear-gradient(to top,rgba(4,4,6,.96) 0%,rgba(4,4,6,.82) 42%,rgba(4,4,6,.42) 74%,transparent 100%)}
.hero-overlay .label{color:#ff606d;font-size:.68rem;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin-bottom:.45rem;display:block}
[lang=ar] .hero-overlay .label{letter-spacing:.04em;font-size:.78rem}
.hero-overlay h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.5rem,2.9vw,2.5rem);line-height:1.14;color:#fff;text-shadow:0 1px 6px rgba(0,0,0,.5)}
[lang=ar] .hero-overlay h2{line-height:1.5;font-weight:800}
.hero-overlay h2 a{color:#fff}
.hero-overlay h2 a:hover{color:#ffd0d4}
.hero .dek{margin-top:.8rem;font-size:1rem;color:var(--muted);font-family:var(--serif);line-height:1.6;max-width:64ch}
.hero .dek a,.research-feat .dek a{text-decoration:underline;text-underline-offset:2px}
.hero .dek a{color:var(--fg)}
[lang=ar] .hero .dek{line-height:1.8}
.hero-overlay .meta{display:flex;align-items:center;gap:.6rem;margin-top:.65rem;font-size:.74rem;color:rgba(255,255,255,.62)}
.hero-overlay .meta .src{color:#3fd07c;font-weight:800;text-transform:uppercase;letter-spacing:.06em}
[lang=ar] .hero-overlay .meta .src{letter-spacing:0}
.hero-overlay .meta .t{font-weight:600;color:rgba(255,255,255,.7)}
.photocredit{font-size:.66rem;color:#9a9aa2;margin-top:.35rem}
.meta{display:flex;align-items:center;gap:.6rem;margin-top:.8rem;font-size:.74rem;color:var(--muted)}
.meta .src{color:var(--green);font-weight:800;text-transform:uppercase;letter-spacing:.06em}
[lang=ar] .meta .src{letter-spacing:0}
.meta .t{font-weight:600}
/* ── hero sub-stories: thumbnail + headline rows ── */
.hero-sub{margin-top:1.35rem;padding-top:1.1rem;border-top:1px solid var(--line);display:grid;grid-template-columns:1fr 1fr;gap:.9rem}
.sub-item{display:flex;gap:.65rem;align-items:flex-start;padding:.45rem;border-radius:var(--r);transition:background var(--tr)}
.sub-item:hover{background:rgba(0,0,0,.03)}
.sub-thumb{flex-shrink:0}
.sub-thumb img{width:82px;aspect-ratio:3/2;object-fit:cover;object-position:50% 22%;background:#e8e6df;border-radius:2px;transition:opacity var(--tr)}
.sub-item:hover .sub-thumb img{opacity:.82}
.sub-body .chip{font-size:.62rem;font-weight:800;color:var(--green-deep);text-transform:uppercase;letter-spacing:.06em;display:block}
[lang=ar] .sub-body .chip{letter-spacing:0;font-size:.72rem}
.sub-body h3{font-family:var(--serif);font-weight:700;font-size:.93rem;line-height:1.28;margin-top:.18rem}
[lang=ar] .sub-body h3{line-height:1.6}
.sub-body h3 a:hover{color:var(--red)}
.sub-body .t{font-size:.7rem;color:var(--muted);font-weight:600;margin-top:.2rem;display:block}
[lang=ar] .sub-body .t{font-size:.72rem}
/* ── latest rail ── */
.latest{background:var(--card);border:1px solid var(--line);box-shadow:var(--sh);padding:1rem .95rem;height:fit-content;position:sticky;top:58px}
.latest h2{font-size:.79rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:var(--black);border-bottom:3px solid var(--red);padding-bottom:.5rem;display:flex;align-items:center;gap:.5rem;margin-bottom:.15rem}
[lang=ar] .latest h2{letter-spacing:.02em;font-size:.94rem}
.latest h2::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--red);animation:pulse 2s infinite}
.latest ol{list-style:none;position:relative;padding-inline-start:1.1rem}
.latest ol::before{content:"";position:absolute;inset-inline-start:3px;inset-block:1rem;width:2px;background:var(--line)}
.latest li{position:relative;display:flex;gap:.6rem;align-items:flex-start;padding-block:.72rem;border-bottom:1px solid var(--line);transition:background var(--tr);animation:railin .5s ease backwards}
.latest li:last-child{border-bottom:none}
.latest li::before{content:"";position:absolute;inset-inline-start:-1.1rem;top:1rem;width:9px;height:9px;border-radius:50%;box-sizing:border-box;background:var(--card);border:2px solid var(--muted);transition:background var(--tr),border-color var(--tr),transform var(--tr)}
.latest li.fresh::before{background:var(--red);border-color:var(--red);animation:pulse 2s infinite}
.latest li:hover{background:rgba(0,0,0,.03)}
.latest li:hover::before{background:var(--red);border-color:var(--red);transform:scale(1.35)}
.latest li:nth-child(1){animation-delay:.04s}.latest li:nth-child(2){animation-delay:.1s}.latest li:nth-child(3){animation-delay:.16s}.latest li:nth-child(4){animation-delay:.22s}.latest li:nth-child(5){animation-delay:.28s}.latest li:nth-child(6){animation-delay:.34s}.latest li:nth-child(7){animation-delay:.4s}.latest li:nth-child(8){animation-delay:.46s}.latest li:nth-child(9){animation-delay:.52s}.latest li:nth-child(10){animation-delay:.58s}
.latest .lt-body{flex:1;min-width:0}
.latest .lt-thumb{flex-shrink:0;margin-top:.25rem}
.latest .lt-thumb img{width:52px;height:52px;object-fit:cover;object-position:50% 25%;background:#e8e6df;border-radius:3px;transition:opacity var(--tr)}
.latest li:hover .lt-thumb img{opacity:.82}
@keyframes railin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.latest .t{color:var(--red);font-weight:800;font-size:.72rem;letter-spacing:.04em;display:inline-block;margin-bottom:.18rem}
[lang=ar] .latest .t{letter-spacing:0;font-size:.74rem}
.latest h3{font-size:.9rem;font-weight:600;line-height:1.35}
[lang=ar] .latest h3{line-height:1.65;font-size:.96rem}
.latest h3 a:hover{color:var(--red)}
.latest .s{font-size:.7rem;color:var(--muted);font-weight:600;text-transform:uppercase;margin-top:.18rem;display:block}
[lang=ar] .latest .s{text-transform:none;font-size:.72rem}
/* ── section headers ── */
section.block{padding-block:1.8rem;border-top:1px solid var(--line-dark)}
.sec-head{display:flex;align-items:center;gap:.8rem;margin-bottom:1.3rem}
.sec-head::before{content:"";width:4px;height:1.55rem;background:var(--green);border-radius:2px;flex-shrink:0;align-self:center}
.sec-head.focus::before{background:var(--red)}
.sec-head h2{font-family:var(--serif);font-weight:900;font-size:1.45rem;color:var(--black);letter-spacing:-.01em}
[lang=ar] .sec-head h2{font-weight:700;letter-spacing:0}
.sec-head .rule{flex:1;height:1px;background:var(--line-dark)}
.sec-head .viewall{font-size:.76rem;font-weight:800;letter-spacing:.03em;color:var(--red);white-space:nowrap}
.sec-head .count{font-size:.8rem;color:var(--muted);white-space:nowrap}
.sectionpage{padding-block:1.6rem}
.searchpage{padding-block:1.6rem;max-width:760px}
.searchpage h1{font-family:var(--serif);font-weight:900;font-size:1.6rem;margin-bottom:1rem}
.browse{margin-top:1.4rem}
.browse .bl{display:block;font-size:.7rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:.6rem}
[lang=ar] .browse .bl{letter-spacing:0;font-size:.8rem;text-transform:none}
.browse nav{display:flex;flex-wrap:wrap;gap:.5rem}
.browse a{border:1px solid var(--line-dark);border-radius:2rem;padding:.35rem .85rem;font-size:.82rem;font-weight:700;color:var(--ink);transition:color var(--tr),border-color var(--tr)}
.browse a:hover{border-color:var(--red);color:var(--red)}
.sectionpage .morehead{margin-top:2.4rem}
.listenbtn{display:inline-flex;align-items:center;gap:.4rem;margin-block:.5rem .2rem;border:1px solid var(--line-dark);border-radius:2rem;background:transparent;color:var(--ink);font:700 .82rem/1 var(--sans);padding:.45rem 1rem;cursor:pointer;transition:color var(--tr),border-color var(--tr)}
.listenbtn:hover{border-color:var(--red);color:var(--red)}
[lang=ar] .listenbtn{font-size:.9rem}
/* Floating live-TV pill and its docked corner mini-player */
.livefab{position:fixed;bottom:calc(1rem + env(safe-area-inset-bottom,0px));inset-inline-start:1rem;z-index:70;display:inline-flex;align-items:center;gap:.4rem;background:var(--red);color:#fff;border:0;border-radius:2rem;font:800 .74rem/1 var(--sans);letter-spacing:.06em;padding:.48rem .55rem .48rem .9rem;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.35)}
[dir=rtl] .livefab{padding:.48rem .9rem .48rem .55rem}
[lang=ar] .livefab{letter-spacing:0;font-size:.84rem}
.livefab .dot{width:8px;height:8px;border-radius:50%;background:#fff;animation:pulse 1.6s infinite}
.livefab .fab-x{display:inline-flex;align-items:center;justify-content:center;width:1.15rem;height:1.15rem;margin-inline-start:.15rem;border-radius:50%;background:rgba(0,0,0,.25);font-size:.68rem;font-weight:400;line-height:1}
.livefab .fab-x:hover{background:rgba(0,0,0,.45)}
.livefab:hover{filter:brightness(1.12)}
.livefab[hidden]{display:none}
.livedock{position:fixed;bottom:1rem;inset-inline-start:1rem;z-index:70;width:min(420px,calc(100vw - 2rem));background:#0b0b0c;border-radius:6px;overflow:hidden;box-shadow:0 10px 34px rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.14)}
.livedock .ld-bar{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:.5rem .75rem;color:#f2eee8;font:700 .78rem/1.2 var(--sans);background:#141419}
.livedock .ld-x{background:none;border:0;color:#aaa9a5;font-size:1rem;cursor:pointer;padding:.1rem .35rem}
.livedock .ld-x:hover{color:#fff}
.livedock .ld-frame{aspect-ratio:16/9;background:#000}
.livedock .ld-frame iframe{width:100%;height:100%;border:0;display:block}
/* Theme toggle + pull quotes (owner review 2026-08-03) */
.themetoggle{background:none;border:0;cursor:pointer;font-size:1.02rem;line-height:1;padding:.2rem .4rem;color:inherit;opacity:.85}
.themetoggle:hover{opacity:1}
.topbar .themetoggle{margin-inline-start:auto}
.litetoggle{background:none;border:1px solid transparent;border-radius:3px;cursor:pointer;font-family:var(--sans);font-size:.74rem;font-weight:800;line-height:1;padding:.24rem .4rem;color:inherit;opacity:.85}
.litetoggle:hover{opacity:1}
[data-lite] .litetoggle{color:var(--green);border-color:var(--green);opacity:1}
[data-lite] .hero-imgwrap>a,[data-lite] .sub-thumb,[data-lite] .lt-thumb,[data-lite] .card>a:first-child,[data-lite] .card .ph,[data-lite] .rowcard img,[data-lite] .rowcard .ph,[data-lite] .research-feat img,[data-lite] .research-feat .noimg,[data-lite] .fr-card img,[data-lite] .livedock,[data-lite] .story img.lede,[data-lite] .story div.lede,[data-lite] .photocredit,[data-lite] .embed,[data-lite] .qrbox,[data-lite] .live-fab{display:none!important}
[data-lite] .hero-imgwrap{background:none;border-radius:0}
[data-lite] .hero-overlay{position:static;padding:0;background:none}
[data-lite] .hero-overlay .label{color:var(--red)}
[data-lite] .hero-overlay h2,[data-lite] .hero-overlay h2 a{color:var(--ink);text-shadow:none}
[data-lite] .hero-overlay .meta{color:var(--muted)}
[data-lite] .hero-overlay .meta .t{color:var(--muted)}
[data-lite] .hero-overlay .meta .src{color:var(--green)}
.topbar .lang{margin-inline-start:.3rem}
.backbar .bb-tools{display:flex;align-items:center;gap:.6rem}
.story blockquote.pull{margin:1.7rem 0;padding-inline-start:1.1rem;border-inline-start:4px solid #c7a86b;font-family:var(--serif);font-size:1.32rem;line-height:1.5;font-weight:700;max-width:42.5rem}
.story blockquote.pull p{margin:0}
.story blockquote.pull p+p{margin-top:.55rem;font-size:.9rem;font-weight:600;color:var(--muted);font-family:var(--sans)}
[lang=ar] .story blockquote.pull{line-height:1.85;font-size:1.28rem}
.searchbox{width:100%;font-size:1.05rem;padding:.7rem .9rem;border:2px solid var(--line-dark);border-radius:8px;background:var(--card);color:var(--ink)}
.searchres{list-style:none;margin-top:1.2rem}
.searchres li{padding:.8rem 0;border-bottom:1px solid var(--line)}
.searchres a{font-weight:800;color:var(--black)}
.searchres .c{font-size:.72rem;color:var(--red);font-weight:700;margin-inline-start:.6rem;text-transform:uppercase}
.searchres p{font-size:.88rem;color:var(--muted);margin-top:.2rem}
.sec-copy{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem 1.4rem;flex-wrap:wrap;margin-bottom:1.3rem}
.sec-copy .sec-head{margin-bottom:0}
.sec-meta{font-size:.74rem;font-weight:700;color:var(--muted);white-space:nowrap}
[lang=ar] .sec-meta{font-size:.82rem}
/* ── card grid ── */
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.65rem}
.grid.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.card{background:var(--card);border-radius:var(--r);overflow:hidden;box-shadow:var(--sh);border:1px solid var(--line);transition:box-shadow var(--tr),transform var(--tr)}
.card:hover{box-shadow:var(--sh-h);transform:translateY(-2px)}
.card>a:first-child{display:block;overflow:hidden}
.card img{aspect-ratio:16/9;object-fit:cover;object-position:50% 22%;width:100%;background:#e8e6df;transition:transform .45s ease}
/* Portrait wire images (tagged onload): cards keep a face-friendly upper
   crop; the big 16/9 surfaces letterbox the frame whole — no crop can fit
   a face into the band a wide slot cuts from a tall photo. */
.card img.portrait,.rowcard img.portrait,.sub-thumb img.portrait,.fr-card img.portrait{object-position:50% 15%}
.hero-imgwrap>a>img.portrait,.story img.lede.portrait,.hero-imgwrap>a>img.boxy,.story img.lede.boxy{object-fit:contain;background:#101013}
.card:hover img{transform:scale(1.04)}
.card .ph{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}
.card .ph svg{width:44px;height:44px;opacity:.9}
.card-body{padding:.75rem .9rem .95rem}
.card .chip{font-size:.62rem;font-weight:800;color:var(--green-deep);text-transform:uppercase;letter-spacing:.07em;display:block}
[lang=ar] .card .chip{letter-spacing:0;font-size:.72rem}
.card h3{font-family:var(--serif);font-weight:700;font-size:1.02rem;line-height:1.36;margin-top:.3rem}
[lang=ar] .card h3{line-height:1.6}
.card h3 a:hover{color:var(--red)}
.card .t{font-size:.72rem;color:var(--muted);font-weight:600;margin-top:.38rem;display:block}
[lang=ar] .card .t{font-size:.72rem}
/* sparse sections (<4 stories): full-width horizontal rows */
.rowlist{display:flex;flex-direction:column}
.rowcard{display:flex;gap:1.1rem;align-items:flex-start;padding-block:1rem;border-bottom:1px solid var(--line);transition:transform var(--tr)}
.rowcard:hover{transform:translateY(-2px)}
.rowcard:last-child{border-bottom:none}
.rowcard>a:first-child,.rowcard>.ph{flex-shrink:0}
.rowcard img,.rowcard .ph{width:clamp(152px,23vw,220px);aspect-ratio:16/9;object-fit:cover;object-position:50% 22%;background:#e8e6df;margin:0;display:flex;align-items:center;justify-content:center;border-radius:2px;transition:opacity var(--tr)}
.rowcard:hover img{opacity:.87}
.rowcard .ph{background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}
.rowcard .ph svg{width:40px;height:40px;opacity:.9}
.rowcard h3{font-family:var(--serif);font-weight:700;font-size:1.08rem;line-height:1.36;margin-top:.2rem}
[lang=ar] .rowcard h3{line-height:1.6}
.rowcard h3 a:hover{color:var(--red)}
.rowcard .chip{font-size:.63rem;font-weight:800;color:var(--green-deep);text-transform:uppercase;letter-spacing:.07em;display:block}
[lang=ar] .rowcard .chip{letter-spacing:0;font-size:.72rem}
.rowcard .t{font-size:.72rem;color:var(--muted);font-weight:600;margin-top:.32rem;display:block}
/* solo band: one story carries the section — bigger art, headline and dek */
.rowcard.solo img,.rowcard.solo .ph{width:clamp(220px,30vw,320px)}
.rowcard.solo h3{font-size:1.4rem;line-height:1.3;max-width:34em}
[lang=ar] .rowcard.solo h3{line-height:1.55}
.rowcard.solo .dek{margin-top:.45rem;font-size:.93rem;line-height:1.55;color:var(--muted);max-width:62ch}
[lang=ar] .rowcard.solo .dek{line-height:1.75;font-size:.98rem}
/* ── research featured ── */
.research-feat{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:0;background:var(--card);border:1px solid var(--line-dark);border-inline-start:5px solid var(--red);margin-bottom:1.6rem;box-shadow:var(--sh)}
.research-feat .body{padding:1.6rem 1.8rem}
.research-feat .kick{color:var(--red);font-size:.66rem;font-weight:800;letter-spacing:.2em;margin-bottom:.55rem;text-transform:uppercase}
[lang=ar] .research-feat .kick{letter-spacing:.04em;font-size:.78rem}
.research-feat h3{font-family:var(--serif);font-weight:900;font-size:clamp(1.25rem,2.2vw,1.7rem);line-height:1.18}
[lang=ar] .research-feat h3{font-weight:700;line-height:1.5}
.research-feat h3 a:hover{color:var(--red)}
.research-feat .dek{margin-top:.8rem;font-family:var(--serif);font-size:.97rem;line-height:1.6;color:#33333b}
[lang=ar] .research-feat .dek{line-height:1.85}
.research-feat img{width:100%;height:100%;object-fit:cover;background:#e8e6df;min-height:240px}
.research-feat .noimg{background:linear-gradient(135deg,#0b0b0c 0 55%,#14241b 55% 100%);display:flex;align-items:center;justify-content:center;min-height:240px}
.research-feat .noimg span{font-family:var(--serif);color:#3fd07c;font-size:3.2rem;font-weight:900}
/* ── opinion ── */
section.opinion{background:#f1efe8;border-top:4px solid var(--black);padding-block:1.8rem;margin-block:1.2rem}
section.opinion .sec-head::before{background:var(--red)}
.op-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.6rem}
.op-card{border-inline-start:3px solid var(--red);padding-inline-start:1rem}
.op-card .q{font-family:var(--serif);font-size:2.2rem;color:var(--red);line-height:.6;display:block;margin-bottom:.4rem}
.op-card h3{font-family:var(--serif);font-style:italic;font-weight:700;font-size:1.12rem;line-height:1.35}
[lang=ar] .op-card h3{line-height:1.65;font-style:normal}
.op-card h3 a:hover{color:var(--red)}
/* ── tips band ── */
section.specialband{background:var(--black);color:#fff;margin-block:1.2rem;border-block:4px solid var(--red)}
.specialband .wrap{display:flex;align-items:center;justify-content:space-between;gap:1.5rem;padding-block:1.35rem;flex-wrap:wrap}
.specialband .kick{font:700 .72rem/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:#c7a86b;margin:0 0 .45rem}
[dir=rtl] .specialband .kick{letter-spacing:0}
.specialband h2{font:700 1.6rem/1.2 var(--serif);margin:0 0 .35rem}
.specialband h2 a{color:#fff;text-decoration:none}
.specialband h2 a:hover{text-decoration:underline}
.specialband .dek{margin:0;font:400 .95rem/1.55 var(--serif);color:#c9c9d2;max-width:46rem}
.specialband .cta{flex-shrink:0;font:700 .82rem/1 var(--sans);text-decoration:none;border:1px solid #c7a86b;color:#c7a86b;padding:.7rem 1.1rem;border-radius:2px;white-space:nowrap}
.specialband .cta:hover{background:#c7a86b;color:var(--black)}
.specialband .sbimg{display:block;flex-shrink:0;width:210px;height:140px;overflow:hidden;border-radius:2px;margin-inline-start:auto}
@media(max-width:640px){.specialband .sbimg{width:100%;height:180px;margin-inline-start:0;order:-1}}
.specialband .sbimg img{width:100%;height:100%;object-fit:cover;opacity:.82;transition:opacity .25s}
.specialband .sbimg:hover img{opacity:1}
nav.sections a.special{color:#c7a86b;border-color:rgba(199,168,107,.35)}
section.tipband{background:var(--black);color:#fff;margin-block:1.2rem;border-block:4px solid var(--green);position:relative;overflow:hidden}
section.tipband::after{content:"";position:absolute;inset-block:0;inset-inline-end:-60px;width:280px;background:linear-gradient(120deg,transparent 0 40%,rgba(0,122,61,.35) 40% 55%,rgba(206,17,38,.30) 55% 70%,transparent 70%);pointer-events:none}
.tipband .wrap{display:flex;align-items:center;gap:1.8rem;padding-block:1.5rem;flex-wrap:wrap;position:relative;z-index:1}
.tipband .lock{flex-shrink:0}
.tipband .txt{flex:1;min-width:260px}
.tipband .kick{color:#3fd07c;font-size:.68rem;font-weight:800;letter-spacing:.22em;margin-bottom:.35rem}
[lang=ar] .tipband .kick{letter-spacing:.04em;font-size:.8rem}
.tipband h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.25rem,2.4vw,1.7rem);line-height:1.2}
[lang=ar] .tipband h2{font-weight:700;line-height:1.5}
.tipband .sub{color:#c9c9d2;font-size:.9rem;margin-top:.45rem;max-width:56ch;line-height:1.6}
.tipband .cta{flex-shrink:0;text-align:center}
.tipband .btn{display:inline-block;background:var(--green);color:#fff;font-weight:800;font-size:.92rem;padding:.85rem 1.6rem;border-radius:var(--r);border:2px solid #3fd07c;transition:var(--tr)}
.tipband .btn:hover{background:#3fd07c;color:var(--black)}
.tipband .alt{margin-top:.65rem;font-size:.76rem;color:#9a9aa4;line-height:1.55}.tipband .alt a{color:#cfe9ff;font-weight:700}.tipband .alt a:hover{color:#fff}.tipband .micro{display:block;margin-top:.55rem;font-size:.72rem;color:#8f8f99}
[lang=ar] .tipband .micro{font-style:normal}
.tipband .qrbox{background:#fff;padding:.45rem .45rem .35rem;border-radius:8px;display:inline-block;margin-top:.7rem}
.tipband .qrbox img{width:84px;height:84px;display:block;image-rendering:pixelated}
.tipband .qrbox span{display:block;font-size:.7rem;font-weight:800;color:#111;margin-top:.25rem;text-align:center;direction:ltr}
.tipband .safety{flex-basis:100%;font-size:.7rem;color:#77777f;border-top:1px solid #26262c;padding-top:.7rem}
/* ── story page ── */
.story{max-width:820px;margin-inline:auto;padding:2rem 20px 1rem}
.breadcrumbs{display:flex;flex-wrap:wrap;gap:.35rem .55rem;margin-bottom:1rem;font-size:.74rem;font-weight:700;color:var(--muted)}
.breadcrumbs a:hover{color:var(--red)}
.breadcrumbs .sep{color:#9a9aa2}
.breadcrumbs [aria-current=page]{color:var(--ink)}
.story .kick{color:var(--red);font-size:.7rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;margin-bottom:.7rem}
[lang=ar] .story .kick{letter-spacing:.03em;font-size:.82rem}
.story h1{font-family:var(--serif);font-weight:900;font-size:clamp(1.9rem,4.4vw,3.1rem);line-height:1.12;letter-spacing:-.012em}
[lang=ar] .story h1{font-weight:800;line-height:1.5;letter-spacing:0}
.story .meta{margin-top:1rem;font-size:.78rem;gap:.55rem}
.story-stamp{margin-top:.55rem;font-size:.74rem;color:var(--muted);font-weight:700;display:flex;gap:.55rem;flex-wrap:wrap}
.story-stamp time{font-variant-numeric:tabular-nums}
.story div.lede{width:100%;aspect-ratio:16/9;margin-top:1.5rem;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}.story div.lede svg{width:64px;height:64px;opacity:.9}.story img.lede{width:100%;aspect-ratio:16/9;object-fit:cover;object-position:50% 18%;background:#e8e6df;margin-top:1.5rem;border-radius:var(--r)}
.story .kind{margin-top:1.5rem;display:inline-block;background:var(--red);color:#fff;font-size:.66rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;padding:.28rem .65rem;border-radius:2px}[lang=ar] .story .kind{letter-spacing:0;font-size:.78rem}.story .based{display:block;margin-top:.3rem;font-weight:600;color:var(--muted);text-transform:none;letter-spacing:0}.story .byline{margin-top:.7rem;font-size:.74rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.1em}
[lang=ar] .story .byline{letter-spacing:0;text-transform:none;font-size:.85rem}
.story-toc{margin-top:1.35rem;padding:1rem 1.1rem;border:1px solid var(--line-dark);background:var(--card);border-radius:var(--r)}
.story-toc .toc-title{font-size:.72rem;font-weight:900;letter-spacing:.1em;text-transform:uppercase;color:var(--red);margin-bottom:.7rem}
[lang=ar] .story-toc .toc-title{letter-spacing:.03em;font-size:.82rem}
.story-toc ol{padding-inline-start:1.2rem;display:grid;gap:.45rem}
.story-toc a{font-weight:700;text-decoration:underline;text-underline-offset:2px}
.story h2.sub[id]{scroll-margin-top:84px;position:relative}
.story h2.sub .anchor{margin-inline-start:.45rem;color:var(--muted);font-size:.8rem;opacity:0;transition:opacity var(--tr)}
.story h2.sub:hover .anchor,.story h2.sub:focus-within .anchor{opacity:1}
.story .summary{margin-top:1.1rem;font-family:var(--serif);font-size:1.14rem;line-height:1.82;color:#26262e;max-width:42.5rem}
.story .summary+.summary{margin-top:.95rem}
[lang=ar] .story .summary{line-height:2.05}
.story .summary a{text-decoration:underline;text-underline-offset:2px}
.story .cta{margin-top:1.8rem;text-align:center;border-block:1px solid var(--line);padding-block:1.5rem}
.story .cta a{display:inline-block;background:var(--red);color:#fff;font-weight:800;font-size:1rem;padding:.9rem 2rem;border-radius:var(--r)}
.story .cta a:hover{background:#a50d1e}
.story .note{margin-top:.8rem;font-size:.72rem;color:var(--muted)}
.keep{padding-block:1.8rem}
.keep .latest{position:static;top:auto}
.backbar{background:var(--black);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:55}
.backbar a{display:block;max-width:800px;padding:.6rem 20px;color:#fff;font-size:.8rem;font-weight:700}
.backbar a:hover{color:#f93549}
/* ── footer ── */
footer{background:var(--black);color:#b9b9c2;margin-top:2.5rem;padding-block:2.5rem;font-size:.84rem}
footer .cols{display:grid;grid-template-columns:1.4fr 1fr;gap:3rem}
footer h2{color:#fff;font-family:var(--serif);font-size:1.2rem;margin-bottom:.8rem;display:flex;align-items:center;gap:.6rem}
footer h2::before{content:"";width:10px;height:10px;background:var(--red)}
footer .mission{line-height:1.75}
[lang=ar] footer .mission{line-height:2}
footer ul{list-style:none;columns:2;gap:1.5rem}
footer li{margin-bottom:.45rem}
footer a{color:#e6e6ec;font-weight:600}
footer a:hover{color:#fff;text-decoration:underline}
footer .legal{margin-top:2rem;padding-top:1.2rem;border-top:1px solid #2a2a30;font-size:.72rem;color:#8b8b94;display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
footer .flagline{height:4px;background:linear-gradient(90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%);border-top:4px solid var(--red);max-width:200px;margin-bottom:1.5rem}
[dir=rtl] footer .flagline{background:linear-gradient(-90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%)}
/* ── dark mode ── */
%%DARK%%
/* ── reduced motion ── */
@media(prefers-reduced-motion:reduce){.ticker .track{animation:none}.topbar .dot,.latest h2::before{animation:none}.latest li,.latest li.fresh::before{animation:none}.hero-imgwrap>a>img,.card img{transition:none}}
.skiplink{position:absolute;inset-inline-start:-999px;top:0;background:var(--red);color:#fff;padding:.6rem 1rem;z-index:99;font-weight:800}
.skiplink:focus{inset-inline-start:0}
.share{margin-top:1.2rem;display:flex;gap:.6rem;flex-wrap:wrap}
.share span{font-size:.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;align-self:center}
.share a{border:1px solid var(--line-dark);padding:.35rem .8rem;border-radius:var(--r);font-size:.8rem;font-weight:700}
.share a:hover{background:var(--red);color:#fff;border-color:var(--red)}
.share .copybtn{border:1px solid var(--line-dark);background:transparent;color:inherit;font-family:inherit;cursor:pointer;padding:.35rem .8rem;border-radius:var(--r);font-size:.8rem;font-weight:700}
.share .copybtn:hover{background:var(--red);color:#fff;border-color:var(--red)}
/* Floating share rail: travels with the reader in the story gutter on wide
   desktops; the inline row above stays as the universal fallback. */
.share-rail{display:none}
@media(min-width:1200px){
.share-rail{display:flex;flex-direction:column;gap:.5rem;position:fixed;top:42vh;inset-inline-start:calc(50vw - 410px - 4.6rem);z-index:40}
.share-rail a{width:2.5rem;height:2.5rem;display:flex;align-items:center;justify-content:center;border:1px solid var(--line-dark);border-radius:50%;background:var(--card);font-weight:800;font-size:.78rem;box-shadow:var(--sh);transition:background var(--tr),color var(--tr),border-color var(--tr)}
.share-rail a:hover{background:var(--red);color:#fff;border-color:var(--red)}
}
.review-note{margin:.8rem 0;padding:.7rem .9rem;border-inline-start:3px solid var(--red);background:var(--paper);font-size:.86rem;font-weight:700;line-height:1.45}
.newmark{display:inline-block;margin-inline-end:.4rem;color:var(--red);font-size:.62rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;animation:newpulse 2s ease-in-out infinite}
@keyframes newpulse{0%,100%{opacity:1}50%{opacity:.45}}
@media(prefers-reduced-motion:reduce){.newmark{animation:none}}
.review-chip{display:inline-block;margin-inline-start:.45rem;color:var(--red);font-size:.66rem;font-weight:900;text-transform:uppercase;letter-spacing:.04em}
.revisions{margin-top:2rem;padding:1rem 1.2rem;border:1px solid var(--line-dark);background:var(--card);border-radius:var(--r)}.revisions h2{font-family:var(--serif);font-size:1.1rem}.revisions ol{margin:.7rem 0 0;padding-inline-start:1.2rem}.revisions li{margin-top:.45rem;font-size:.86rem;line-height:1.6}.revisions time{font-variant-numeric:tabular-nums;color:var(--muted)}.revisions .ledgerlink{margin-top:.7rem;font-size:.82rem}.revisions .ref{color:var(--muted);font-size:.8rem}
.social-note{margin:-.5rem 0 1.2rem;font-size:.9rem;color:var(--muted);max-width:75ch}.social-note a{color:var(--green);font-weight:700}
.footer-contact{margin-top:.9rem}.footer-contact.secondary{margin-top:.5rem}.contact-id{direction:ltr;display:inline-block;margin-inline-start:.6rem;color:#8f8f94}
.about-section{font-family:var(--serif);font-size:1.25rem;margin-top:1.6rem}.about-telegram{margin-top:.9rem}.about-telegram a{font-weight:700;color:var(--green)}
@media(max-width:1200px){
  .hero-zone{grid-template-columns:minmax(0,1.7fr) minmax(0,1fr)}
  .grid{grid-template-columns:repeat(3,minmax(0,1fr))}
}
/* ── responsive ── */
@media(max-width:960px){
  .research-feat{grid-template-columns:1fr}
  .research-feat img,.research-feat .noimg{min-height:180px;order:-1}
  .hero-zone{grid-template-columns:1fr}
  .hero{border-inline-end:none;padding-inline-end:0}
  .latest{position:static;top:auto}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .rowcard img,.rowcard .ph{width:150px}
  .op-grid{grid-template-columns:1fr}
  footer .cols{grid-template-columns:1fr}
}
.franchise{margin-block:1.2rem}
.fr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}
.fr-card{display:flex;flex-direction:column;background:var(--black);color:#f2eee8;border-radius:var(--r);overflow:hidden;border:1px solid rgba(199,168,107,.4);transition:transform .25s,box-shadow .25s}
.fr-card:hover{transform:translateY(-2px);box-shadow:var(--sh-h)}
.fr-card img{width:100%;aspect-ratio:16/6;object-fit:cover;opacity:.85}
.fr-card .body{display:block;padding:.7rem .9rem .85rem}
.fr-card .kick{display:block;color:#c7a86b;font-size:.62rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
[lang=ar] .fr-card .kick{letter-spacing:.02em;font-size:.74rem}
.fr-card .ttl{display:block;font-family:var(--serif);font-weight:800;font-size:1rem;line-height:1.3;margin-top:.3rem}
[lang=ar] .fr-card .ttl{line-height:1.55;font-weight:700}
.fr-card .go{display:block;color:#c7a86b;font-size:.78rem;font-weight:700;margin-top:.5rem}
@media(max-width:960px){.fr-grid{grid-template-columns:1fr}.fr-card img{aspect-ratio:16/5}}
.fr-card.vote{position:relative;isolation:isolate;background:linear-gradient(145deg,#0d121a,#141c28);border-color:rgba(101,130,175,.7)}
.fr-card.vote::after{content:"";position:absolute;inset:0;background:radial-gradient(120% 110% at 90% 0%,rgba(143,168,207,.24),transparent 48%);pointer-events:none;z-index:0}
.fr-card.vote:hover{border-color:rgba(143,168,207,.95);box-shadow:0 10px 30px rgba(20,35,60,.55)}
.fr-card.vote img{aspect-ratio:16/7;opacity:1}
.fr-card.vote .body{position:relative;z-index:1;background:linear-gradient(180deg,rgba(10,13,20,.78),rgba(10,13,20,.95));border-top:1px solid rgba(143,168,207,.35)}
.fr-card.vote .kick,.fr-card.vote .go{color:#b6c6e3}
.fr-card.vote .ttl{font-size:1.03rem}
.fr-card.vote .days{position:absolute;top:.55rem;inset-inline-end:.6rem;z-index:2;display:flex;align-items:baseline;gap:.3rem;background:rgba(8,11,17,.82);border:1px solid rgba(199,168,107,.55);border-radius:6px;padding:.28rem .55rem;backdrop-filter:blur(3px)}
.fr-card.vote .days::before{content:"";width:7px;height:7px;border-radius:50%;background:#c7a86b;align-self:center;animation:newpulse 1.6s infinite}
.fr-card.vote .days b{font-family:ui-monospace,Menlo,monospace;font-size:1.3rem;font-weight:700;color:#f2eee8;line-height:1}
.fr-card.vote .days i{font-style:normal;font-size:.6rem;font-weight:800;letter-spacing:.12em;color:#c7a86b}
[lang=ar] .fr-card.vote .days i{letter-spacing:0;font-size:.74rem}
.latest .orig{display:inline-block;background:var(--green);color:#fff;font-size:.56rem;font-weight:800;letter-spacing:.08em;padding:.1rem .35rem;border-radius:2px;margin-inline-start:.4rem;vertical-align:middle}
@media(max-width:560px){
  /* Topbar: one tidy utility row (owner report 2026-08-06 — the wrapped
     date + toggles read as two ragged lines). The pulsing updated-at stamp
     IS the alive signal and stays; the long weekday date and timezone
     suffix yield the room. */
  .topbar .wrap{gap:.45rem .6rem;flex-wrap:nowrap}
  .topbar .date{display:none}
  .topbar .tz{display:none}
  .topbar .upd{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
  .topbar .lang,.topbar .themetoggle,.topbar .litetoggle{flex-shrink:0}
  /* Hero: the headline sits UNDER the photo, newspaper-app style — an
     overlay atop a letterboxed portrait frame buried both photo and text.
     Mirrors the lite-mode static hero, tokens keep light/dark honest. */
  .hero-imgwrap{background:none;overflow:visible}
  .hero-imgwrap>a{background:#141419;border-radius:var(--r);overflow:hidden}
  .hero-overlay{position:static;padding:.85rem 0 0;background:none}
  .hero-overlay .label{color:var(--red)}
  .hero-overlay h2,.hero-overlay h2 a{color:var(--ink);text-shadow:none}
  .hero-overlay h2 a:hover{color:var(--red)}
  .hero-overlay .meta{color:var(--muted)}
  .hero-overlay .meta .t{color:var(--muted)}
  .hero-overlay .meta .src{color:var(--green)}
  .hero-sub{grid-template-columns:1fr}
  .grid{grid-template-columns:1fr}
  .latest{padding:.9rem .8rem}
  .sub-thumb img{width:72px}
  .rowcard img,.rowcard .ph{width:110px}
  footer ul{columns:1}
}
"""

# Dark rules, written once. They apply under the system's dark scheme unless
# the reader forced light, AND whenever the reader forced dark — the theme
# toggle stores its choice as html[data-theme] (owner request 2026-08-03).
_DARK_RULES = """
:root{--paper:#121417;--card:#1a1d22;--ink:#e8eaed;--muted:#a3a8b2;--line:#2a2e35;--line-dark:#3f454e;--red:#d43049}
.masthead h1,.masthead .wordmark,.sec-head h2,.latest h2,.story h1,.card h3,.rowcard h3,.sub-body h3,.research-feat h3,.op-card h3{color:var(--ink)}
.hero-overlay h2,.hero-overlay h2 a{color:#fff}
.story .summary{color:#d6d6de}
.research-feat .dek{color:#c5c5cf}
section.opinion{background:#17171c;border-top-color:var(--red)}
.card{box-shadow:0 1px 4px rgba(0,0,0,.35)}
.card:hover{box-shadow:0 5px 18px rgba(0,0,0,.5)}
.sub-item:hover{background:rgba(255,255,255,.04)}
.latest li:hover{background:rgba(255,255,255,.04)}
.card img,.hero-imgwrap>a>img,.rowcard img,.story img.lede,.sub-thumb img,.latest .lt-thumb img{opacity:.9}
.card img,.hero-imgwrap>a>img,.rowcard img,.rowcard .ph,.story img.lede,.sub-thumb img,.latest .lt-thumb img,.research-feat img{background:#232328}
.hero-overlay .label,.latest .t,.research-feat .kick,.story .kick,.op-card .q{color:#f93549}
.hero-overlay h2 a:hover{color:#ffb8be}
.card h3 a:hover,.rowcard h3 a:hover,.latest h3 a:hover,.op-card h3 a:hover,.research-feat h3 a:hover,.sub-body h3 a:hover{color:#f93549}
.meta .src,.card .chip,.rowcard .chip,.sub-body .chip{color:#3fd07c}
"""


def _scope_dark(scope):
    """Prefix every dark rule's selectors with a theme scope. `:root` becomes
    the scope itself; everything else nests under it."""
    out = []
    for rule in _DARK_RULES.strip().split("}"):
        if "{" not in rule:
            continue
        sels, body = rule.split("{", 1)
        scoped = ",".join(
            scope if s.strip() == ":root" else f"{scope} {s.strip()}"
            for s in sels.split(","))
        out.append(f"{scoped}{{{body}}}")
    return "".join(out)


CSS = CSS.replace("%%DARK%%",
                  "@media(prefers-color-scheme:dark){"
                  + _scope_dark("html:not([data-theme=light])") + "}\n"
                  + _scope_dark("html[data-theme=dark]"))

# Theme toggle (owner request 2026-08-03): restore the stored choice before
# first paint (no flash), then cycle auto → dark → light on tap.
_THEME_JS = (
    '<script>(function(){try{var t=localStorage.getItem("top-theme");'
    'if(t)document.documentElement.dataset.theme=t}catch(e){}'
    # Reader chrome preferences run from <head> so they apply before the body
    # parses — for lite mode that matters twice: no flash of imagery, and
    # display:none lazy images below the fold are never requested at all.
    'try{if(localStorage.getItem("top-lite")==="1")'
    'document.documentElement.dataset.lite="1"}catch(e){}'
    'document.addEventListener("DOMContentLoaded",function(){'
    'var b=document.getElementById("themetoggle");if(!b)return;'
    'function icon(){var t=document.documentElement.dataset.theme||"";'
    'b.textContent=t==="dark"?"☀":t==="light"?"◐":"🌙"}icon();'
    'b.addEventListener("click",function(){'
    'var cur=document.documentElement.dataset.theme||"";'
    'var nxt=cur===""?"dark":cur==="dark"?"light":"";'
    'try{if(nxt)localStorage.setItem("top-theme",nxt);'
    'else localStorage.removeItem("top-theme")}catch(e){}'
    'if(nxt)document.documentElement.dataset.theme=nxt;'
    'else delete document.documentElement.dataset.theme;icon()});'
    'var l=document.getElementById("litetoggle");if(!l)return;'
    'function lst(){l.setAttribute("aria-pressed",'
    'document.documentElement.dataset.lite==="1"?"true":"false")}lst();'
    'l.addEventListener("click",function(){'
    'var on=document.documentElement.dataset.lite==="1";'
    'try{if(on)localStorage.removeItem("top-lite");'
    'else localStorage.setItem("top-lite","1")}catch(e){}'
    'if(on)delete document.documentElement.dataset.lite;'
    'else document.documentElement.dataset.lite="1";lst()})})})();</script>')


def theme_btn(lang):
    label = "المظهر: تلقائي / داكن / فاتح" if lang == "ar" else "Theme: auto / dark / light"
    return (f'<button id="themetoggle" class="themetoggle" '
            f'aria-label="{label}" title="{label}">🌙</button>')


def lite_btn(lang):
    # Text-only mode for unstable connections (owner-forwarded review,
    # 2026-08-04). The toggle rides beside the theme button on every chrome
    # bar; the preference persists in localStorage and is applied from <head>
    # (see _THEME_JS), so below-the-fold lazy images are never fetched at all.
    label = ("وضع النص فقط — يوفّر البيانات على الاتصال الضعيف" if lang == "ar"
             else "Text-only mode — saves data on weak connections")
    return (f'<button id="litetoggle" class="litetoggle" aria-pressed="false" '
            f'aria-label="{label}" title="{label}">Aa</button>')


# The page is alive between rebuilds: every <time datetime> re-renders its
# relative half ("12m ago" / «قبل ١٢ دقيقة») each half-minute, mirroring
# time_ago()/ar_count() exactly, and NEW marks + fresh rail dots retire
# client-side once a story crosses the 90-minute line.
_CLOCK_JS = """
(function(){var AR=(document.documentElement.lang||"en")==="ar";
function arc(n,one,two,few,many){return n===1?one:n===2?two:(n>=3&&n<=10)?n+" "+few:n+" "+many}
function rel(m){
 if(AR){if(m<60)return"\\u0642\\u0628\\u0644 "+arc(m,"\\u062f\\u0642\\u064a\\u0642\\u0629","\\u062f\\u0642\\u064a\\u0642\\u062a\\u064a\\u0646","\\u062f\\u0642\\u0627\\u0626\\u0642","\\u062f\\u0642\\u064a\\u0642\\u0629");
  var h=Math.round(m/60);if(h<24)return"\\u0642\\u0628\\u0644 "+arc(h,"\\u0633\\u0627\\u0639\\u0629","\\u0633\\u0627\\u0639\\u062a\\u064a\\u0646","\\u0633\\u0627\\u0639\\u0627\\u062a","\\u0633\\u0627\\u0639\\u0629");
  return"\\u0642\\u0628\\u0644 "+arc(Math.round(h/24),"\\u064a\\u0648\\u0645","\\u064a\\u0648\\u0645\\u064a\\u0646","\\u0623\\u064a\\u0627\\u0645","\\u064a\\u0648\\u0645\\u0627\\u064b")}
 if(m<60)return m+"m ago";var h=Math.round(m/60);if(h<24)return h+"h ago";return Math.round(h/24)+"d ago"}
function tick(){var now=Date.now();
 document.querySelectorAll("time[datetime]").forEach(function(t){
  if(t.closest(".story-stamp")||t.closest(".revisions"))return; // absolute record stays absolute
  var d=Date.parse(t.getAttribute("datetime"));if(!d)return;
  var m=Math.max(1,Math.round((now-d)/6e4));
  var n=t.lastChild;
  if(n&&n.nodeType===3){
   if(t.classList.contains("t")){n.nodeValue=rel(m)}
   else{var v=n.nodeValue,i=v.indexOf("\\u00b7");
    if(i>=0)n.nodeValue=rel(m)+" "+v.slice(i)}}
  if(m>90){var nm=t.querySelector(".newmark");if(nm)nm.remove();
   var li=t.closest("li.fresh");if(li)li.classList.remove("fresh")}})}
tick();setInterval(tick,30000)})();
"""

FLAG_SVG = ('<svg class="flagmark" width="46" height="46" viewBox="0 0 46 46" aria-hidden="true">'
            '<rect width="46" height="15.3" fill="#0b0b0c"/>'
            '<rect y="15.3" width="46" height="15.3" fill="#fff" stroke="#e5e2d9" stroke-width=".5"/>'
            '<rect y="30.6" width="46" height="15.4" fill="#007A3D"/>'
            '<path d="M0 0 L21 23 L0 46 Z" fill="#CE1126"/></svg>')

LOCK_SVG = ('<svg class="lock" width="54" height="54" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
            '<rect x="4" y="10" width="16" height="11" rx="1.5" fill="#007A3D" stroke="#3fd07c" stroke-width="1.2"/>'
            '<path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="#3fd07c" stroke-width="1.8" fill="none"/>'
            '<circle cx="12" cy="15" r="1.6" fill="#0b0b0c"/><rect x="11.3" y="15.5" width="1.4" height="2.6" rx=".7" fill="#0b0b0c"/></svg>')

# ---------- components ----------

def href(it, pfx):
    """Internal story-page URL — readers stay on the site; the source link lives on the story page."""
    return f"{pfx}{quote(story_file_name(it['title'], it['pid']))}"


def story_url(it, lang=None):
    """Absolute, percent-encoded story-page URL (slug + pid filename)."""
    return BASE_URL + story_url_path(
        it["title"], it["pid"], lang or it.get("lang", "en"))


def jsonld_dump(record):
    """Serialize JSON-LD for inline <script> embedding. A literal '</script>'
    inside any string value (a hostile dek or headline) would otherwise close
    the block and inject markup — escaping '<' keeps the JSON identical to
    parsers and inert to the HTML tokenizer."""
    return json.dumps(record, ensure_ascii=False).replace("<", "\\u003c")


def org_jsonld(lang):
    """NewsMediaOrganization record with the trust-signal links Google's
    quality raters and NewsGuard-style checkers look for: logo, publishing
    principles, corrections policy, ownership/funding disclosure, and the
    newsroom's off-site presence."""
    t = STR[lang]
    return jsonld_dump({
        "@context": "https://schema.org",
        "@type": "NewsMediaOrganization",
        "name": t["site_name"],
        "url": f"{BASE_URL}/{lang}/",
        "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/icon-512.png"},
        "sameAs": [f"{BASE_URL}/en/", f"{BASE_URL}/ar/", TELEGRAM_CHANNEL_URL],
        "publishingPrinciples": f"{BASE_URL}/{lang}/about.html",
        "correctionsPolicy": f"{BASE_URL}/{lang}/corrections.html",
        "ownershipFundingInfo": f"{BASE_URL}/{lang}/about.html",
        "actionableFeedbackPolicy": f"{BASE_URL}/{lang}/about.html",
    })


def ticker_html(t, lang, ticker_track, ticker_track_hidden):
    """Breaking ticker with an explicit pause control (WCAG 2.2.2 — hover-pause
    alone leaves touch and keyboard readers without a way to stop the motion)."""
    pause_label = "أوقف شريط الأخبار العاجلة" if lang == "ar" else "Pause breaking-news ticker"
    return (f'<div class="ticker" role="region" aria-label="{t["breaking"]}">'
            f'<span class="label">{t["breaking"]}</span>'
            f'<button class="tick-pause" aria-pressed="false" aria-label="{pause_label}" '
            'onclick="var k=this.closest(\'.ticker\'),p=k.classList.toggle(\'paused\');'
            'this.setAttribute(\'aria-pressed\',p);this.textContent=p?\'▶\':\'⏸\'">⏸</button>'
            f'<div class="rail"><div class="track">{ticker_track}{ticker_track_hidden}</div></div></div>')


def meta_line(it, lang):
    # Owner decisions 2026-07-30: review status never appears on reader-facing
    # pages, and rewritten (brief-carrying) stories are OUR copy — the outlet
    # is credited inline in the prose, so the meta line never links out to it.
    # Only dek-fallback pages (source's own summary as body) keep the link.
    if it.get("original") or it.get("brief"):
        source = f'<span class="src">{esc(TOP_SOURCE[lang])}</span>'
    else:
        source = (f'<a class="src" href="{esc(it["source_url"])}" target="_blank" '
                  f'rel="noopener">{esc(it["source"])}</a>')
    return (f'<p class="meta">{source}'
            f'{time_tag(it["date"], lang, "t", fresh=True)}</p>')


def media_credit(it, lang):
    media = it.get("media")
    if not media:
        return ""
    license_html = ""
    if media.get("licenseUrl"):
        license_label = "الترخيص" if lang == "ar" else "License"
        license_html = (
            f' · <a href="{esc(media["licenseUrl"])}" target="_blank" '
            f'rel="license noopener">{license_label}</a>')
    credit = media["credit"]
    # A caption reads as a sentence, never as a stacked label: credits that
    # already carry their own label ("Graphic: …", "Photo: …") render as-is.
    if re.match(r"^(Graphic|Photo|Image|صورة|رسم|غرافيك)\s*:", credit, re.I):
        return f'<p class="photocredit">{esc(credit)}{license_html}</p>'
    label = "حقوق الصورة" if lang == "ar" else "Image credit"
    return f'<p class="photocredit">{label}: {esc(credit)}{license_html}</p>'

def display_source(it, lang):
    """Wire protocol (owner decision 2026-07-30): rewritten stories are our
    copy — cards and meta lines carry the paper's name; the outlet is credited
    inline in the prose. Dek-fallback items still show the outlet."""
    if it.get("original") or it.get("brief"):
        return TOP_SOURCE[lang]
    return it["source"]


def card_kicker(it, lang):
    """Card kicker: the section tag (design pass 2026-08-06). Rewritten wire
    is our copy, so a masthead chip repeated on every card said nothing —
    the section name orients the reader instead. The story page's meta line
    keeps display_source per the wire-attribution protocol."""
    return STR[lang]["sections"].get(it["cat"], STR[lang]["sections"]["news"])


def lede_fallback_attrs(it):
    """Remote ledes can die after publish — hotlink walls, deleted uploads,
    CDN churn. no-referrer defeats referer-based blocking; onerror swaps a
    dead photo for the branded category cover so readers never see a broken
    frame. Local /media/ assets ship with the site and need neither.

    Wire images also arrive with unpredictable framing — portrait video
    posters and Wikimedia head-shots lose most of their height in a
    landscape slot, and no crop position can fit a face into a band that
    small on the big surfaces. onload tags portrait images with a class:
    small card slots keep a face-friendly upper crop, while the story lede
    and hero letterbox the portrait whole on the house-black backdrop
    (owner report 2026-08-03). Landscape images keep the CSS bias."""
    if not (it.get("image") or "").startswith("http"):
        return ""
    cover = f"times-of-palestine-cover-{it.get('cat', 'news')}.svg"
    if not (ROOT / "originals" / "media" / cover).is_file():
        cover = "times-of-palestine-cover-news.svg"
    return (' referrerpolicy="no-referrer"'
            " onload=\"if(this.naturalWidth&&this.naturalWidth<200)"
            f"{{this.onerror=null;this.src='/media/{cover}'}}"
            "else if(this.naturalHeight>this.naturalWidth)"
            "this.classList.add('portrait');"
            "else if(this.naturalWidth<1.55*this.naturalHeight)"
            "this.classList.add('boxy')\""
            f" onerror=\"this.onerror=null;this.src='/media/{cover}'\"")

def card_media(it, pfx):
    """Image if we have one; otherwise a branded flag panel — never an empty column."""
    if it["image"]:
        return (f'<a href="{href(it, pfx)}"><img src="{esc(it["image"])}" '
                f'alt="{esc(it["title"])}" loading="lazy"{lede_fallback_attrs(it)}></a>')
    return f'<a href="{href(it, pfx)}"><div class="ph">{FLAG_SVG}</div></a>'

def card(it, lang, pfx):
    # Uniform card: headline, source, time. Summaries belong to the hero, the
    # featured report, and the story pages — mixed previews in a grid look broken.
    return (f'<article class="card">{card_media(it, pfx)}'
            f'<div class="card-body">'
            f'<span class="chip">{esc(card_kicker(it, lang))}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'{time_tag(it["date"], lang, "t", fresh=True)}'
            f'</div></article>')

def rowcard(it, lang, pfx, solo=False):
    # A lone story carrying a whole section band gets the full treatment —
    # bigger art, bigger headline, and its dek — so the band never reads as
    # an orphan card floating in empty space.
    dek = (f'<p class="dek">{summary_html(truncate(it["dek"], 220))}</p>'
           if solo and it.get("dek") else "")
    cls = "rowcard solo" if solo else "rowcard"
    return (f'<article class="{cls}">{card_media(it, pfx)}'
            f'<div><span class="chip">{esc(card_kicker(it, lang))}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>{dek}'
            f'{time_tag(it["date"], lang, "t", fresh=True)}</div></article>')

def op_card(it, lang, pfx):
    return (f'<article class="op-card"><span class="q">“</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'{meta_line(it, lang)}</article>')

def sub_item(it, lang, pfx):
    thumb = (f'<a class="sub-thumb" href="{href(it, pfx)}" tabindex="-1" aria-hidden="true">'
             f'<img src="{esc(it["image"])}" alt="" loading="lazy"{lede_fallback_attrs(it)}></a>'
             if it["image"] else '')
    return (f'<article class="sub-item">'
            f'{thumb}'
            f'<div class="sub-body">'
            f'<span class="chip">{esc(card_kicker(it, lang))}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'{time_tag(it["date"], lang, "t", fresh=True)}'
            f'</div></article>')

def latest_item(it, lang, pfx):
    """Live-wire timeline entry: a marker dot on a vertical rule (pulsing while
    the story is under 90 minutes old), a thumbnail when the story has art, and
    a relative timestamp that _CLOCK_JS keeps ticking between rebuilds."""
    mark = '<span class="orig">TOP</span>' if it.get("original") else ""
    cls = ' class="fresh"' if is_fresh(it["date"]) else ""
    thumb = (f'<a class="lt-thumb" href="{href(it, pfx)}" tabindex="-1" aria-hidden="true">'
             f'<img src="{esc(it["image"])}" alt="" loading="lazy" '
             f'referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></a>'
             if it["image"] else "")
    return (f'<li{cls}><div class="lt-body">'
            f'{time_tag(it["date"], lang, "t", fresh=True)}{mark}'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'<span class="s">{esc(card_kicker(it, lang))}</span></div>'
            f'{thumb}</li>')

# ---------- page ----------
# Standing specials featured on both front pages (owner-curated). Each entry
# links to a standalone feature page; the band sits directly under the live
# hero so the news cycle keeps the top slot (charter: nothing squats the hero).
def _original_header_title(slug, lang):
    """The title: header of an originals source file — the same value the
    loader publishes, so slugs derived here match the rendered page name."""
    path = ROOT / "originals" / f"{slug}.{lang}.txt"
    try:
        head = path.read_text(encoding="utf-8").partition("\n---\n")[0]
    except OSError:
        return ""
    for line in head.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "title":
            return value.strip()
    return ""


def _original_story_href(slug):
    """Front-page links to a published original's story pages, both editions.
    Mirrors the pid derivation in load_originals so specials never 404."""
    return {lang: story_url_path(
                _original_header_title(slug, lang),
                hashlib.md5(f"original:{slug}.{lang}".encode()).hexdigest()[:10],
                lang)
            for lang in ("en", "ar")}


SPECIALS = [
    {
        # Story-page special: renders only when this original is in the build,
        # so offline/skip-originals runs never emit broken band links.
        "requires_original": "palestine-top100-2026",
        "href": _original_story_href("palestine-top100-2026"),
        "kicker": {"en": "The annual list", "ar": "القائمة السنوية"},
        "title": {"en": "The TOP 100: the most influential Palestinians",
                  "ar": "قائمة المئة: أكثر فلسطينيي العالم تأثيراً"},
        "dek": {"en": "From presidents and prisoners to laureates, surgeons and strikers — the hundred Palestinians who moved the world this year.",
                "ar": "من الرؤساء والأسرى إلى الحائزين الجوائز والجرّاحين والمهاجمين — مئة فلسطيني حرّكوا العالم هذا العام."},
        "cta": {"en": "Meet the 100 →", "ar": "تعرّف إلى المئة ←"},
        "img": "/media/times-of-palestine-top100-2026.svg",
        "img_alt": {"en": "The TOP 100: the most influential Palestinians of 2026",
                    "ar": "قائمة المئة: أكثر فلسطينيي العالم تأثيراً 2026"},
        "ticker": {"en": "The Annual List: The TOP 100 Most Influential Palestinians",
                   "ar": "القائمة السنوية: المئة الأكثر تأثيراً"},
        "nav": {"en": "TOP 100", "ar": "قائمة المئة"},
    },
    {
        # Standing reader service (owner directive 2026-08-02): the scholarship
        # guide stays pinned on the front page and is updated as cycles move.
        "requires_original": "palestine-scholarships-guide-2026",
        "href": _original_story_href("palestine-scholarships-guide-2026"),
        "kicker": {"en": "Standing guide for students", "ar": "دليل دائم للطلبة"},
        "title": {"en": "The Scholarship Map: funded study for Palestinians worldwide",
                  "ar": "خريطة المنح: دراسة ممولة للفلسطينيين حول العالم"},
        "dek": {"en": "100+ universities in 25+ countries fund Palestinian students, bachelor's to PhD. Every major channel, every window, updated as deadlines move.",
                "ar": "أكثر من مئة جامعة في أكثر من ٢٥ دولة تموّل الطلبة الفلسطينيين من البكالوريوس إلى الدكتوراه. كل القنوات الكبرى ونوافذها، محدّثة أولاً بأول."},
        "cta": {"en": "Find your scholarship →", "ar": "اعثر على منحتك ←"},
        "img": "/media/times-of-palestine-scholarships-2026.svg",
        "img_alt": {"en": "The scholarship map: routes from Palestine to the world's universities",
                    "ar": "خريطة المنح: طرق من فلسطين إلى جامعات العالم"},
        "ticker": {"en": "The Scholarship Map: funded study for Palestinians, updated",
                   "ar": "خريطة المنح الدراسية للفلسطينيين — محدّثة"},
        "nav": {"en": "Scholarships", "ar": "المنح الدراسية"},
    },
    {
        "href": {"en": "/suha-arafat/index-en.html", "ar": "/suha-arafat/index-ar.html"},
        "kicker": {"en": "Special investigation", "ar": "تحقيق خاص"},
        "title": {"en": "The Widow and the Ledger", "ar": "الأرملة والدفتر"},
        "dek": {"en": "How a number nobody could source became a fact everybody knows — and what it cost Palestinians.",
                "ar": "كيف صار رقمٌ لا يستطيع أحد إسناده حقيقةً يعرفها الجميع — وما الذي كلّفه ذلك الفلسطينيين."},
        "cta": {"en": "Read the full investigation →", "ar": "اقرأ التحقيق كاملاً ←"},
        # Image path relative to dist root — the suha-arafat/ dir is a static feature
        "img": "/suha-arafat/media/suha-arafat-hillary-clinton-gaza-1998.jpg",
        # Faces sit in the upper third of this archival frame; bias the crop up
        # so the card ribbon never decapitates the subjects.
        "focus": "50% 28%",
        "img_alt": {"en": "Suha Arafat accompanies Hillary Clinton in Gaza, 1998",
                    "ar": "سهى عرفات ترافق هيلاري كلينتون في غزة، ١٩٩٨"},
        "ticker": {"en": "Special Investigation: The Widow and the Ledger",
                   "ar": "تحقيق خاص: الأرملة والدفتر"},
        "nav": {"en": "Special Report", "ar": "تحقيق خاص"},
    },
]


def available_specials(lang, items=()):
    """Specials whose targets exist in this build: static features always,
    story-page specials only when their original is among the items."""
    out = []
    for s in SPECIALS:
        slug = s.get("requires_original")
        if slug and not any(
                it.get("link") == f"original:{slug}.{lang}" for it in items):
            continue
        out.append(s)
    return out


def specials_band_html(lang, items=(), extra=""):
    """The standing franchises as ONE compact row — a card per special —
    instead of stacked full-height bands (owner-approved compression,
    2026-08-02). The row sits under the hero; news keeps the page.
    `extra` is a pre-rendered card prepended to the row (the election box)."""
    cards = [extra] if extra else []
    for s in available_specials(lang, items):
        img_html = ""
        if s.get("img"):
            # Optional per-special focal point: object-position keeps faces in
            # frame when the card ribbon crops a photo (esp. mobile 16/5).
            _focus = f' style="object-position:{esc(s["focus"])}"' if s.get("focus") else ""
            img_html = (f'<img src="{esc(s["img"])}" alt="{esc(s["img_alt"][lang])}"'
                        f'{_focus} loading="lazy">')
        cards.append(
            f'<a class="fr-card" href="{esc(s["href"][lang])}">{img_html}'
            f'<span class="body"><span class="kick">{esc(s["kicker"][lang])}</span>'
            f'<span class="ttl">{esc(s["title"][lang])}</span>'
            f'<span class="go">{esc(s["cta"][lang])}</span></span></a>')
    if not cards:
        return ""
    return (f'<section class="franchise"><div class="wrap"><div class="fr-grid">'
            + "".join(cards) + '</div></div></section>')


def render_page(lang, items, built_at):
    t = STR[lang]
    order = SECTION_ORDER[lang]
    by_score = sorted(items, key=lambda i: i["score"], reverse=True)  # editorial ranking
    by_latest = sorted(items, key=lambda i: (i["date"], i["score"]), reverse=True)
    used = set()

    def take(pool, pred, n):
        out = []
        for it in pool:
            if len(out) >= n:
                break
            if id(it) in used:
                continue
            if pred(it):
                used.add(id(it))
                out.append(it)
        return out

    # Hero & second tier are chosen by score (importance); Latest rail and the
    # breaking ticker stay strictly chronological. The hero must be real, recent
    # hard news — never an opinion piece, review, or multi-day-old feature.
    now = datetime.now(timezone.utc)

    def within_hours(i, max_age):
        return (now - i["date"]).total_seconds() / 3600 <= max_age

    def evergreen(i):
        """Standing reference pages — the scholarship map, a section's launch
        charter, directories — are not the news cycle and must never squat
        the top slot. They declare it EXPLICITLY with a `standing: yes`
        header. (A long maxAgeHours alone is NOT the signal: ordinary
        reports keep long shelf lives just to stay in the archive, and the
        earlier shelf-life heuristic wrongly locked the daily desk's fresh
        reporting out of the hero — owner report 2026-08-03.)"""
        return bool(i.get("standing"))

    def hero_ok(i, max_age=HERO_MAX_AGE_H):
        return (bool(i["image"]) and len(i["title"]) > 30
                and i["cat"] not in ("social", "research", "opinion", "culture")
                and not evergreen(i)
                and PALESTINE_RX.search(f"{i['title']} {i['dek']}")  # the top story IS Palestine
                and not REVIEWISH_RX.search(i["title"])
                and within_hours(i, max_age))

    # The hero follows the news cycle: pick the strongest story from the
    # FRESHEST window that has one (last 6h, then 12h, then 18h). A boosted
    # multi-day original can never squat the top slot while new reporting
    # arrives — every build, the reader sees the newest strong story.
    hero_pool = by_latest
    heroes = []
    for window in HERO_WINDOWS_H:
        heroes = take(hero_pool, lambda i, w=window: hero_ok(i, max_age=w), 1)
        if heroes:
            break
    heroes = (heroes
              or take(by_latest, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research")
                      and PALESTINE_RX.search(f"{i['title']} {i['dek']}")
                      and within_hours(i, HERO_MAX_AGE_H), 1)
              or take(by_latest, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research")
                      and within_hours(i, HERO_MAX_AGE_H), 1))
    hero = heroes[0] if heroes else None
    # Eight items (2×4) under the hero: four left the column trailing dead
    # space beside the taller Latest rail (owner decision 2026-08-03).
    hero_subs = take(by_latest, lambda i: i["cat"] not in ("opinion", "social", "research", "bitcoin")
                     and not evergreen(i), 8)
    # Latest rail and breaking ticker: chronological, Palestine coverage first.
    # The rail is an index — it lists stories without claiming them from sections.
    def palestine(i):
        return bool(PALESTINE_RX.search(f"{i['title']} {i['dek']}"))
    # Rail length pairs with the 2×4 hero-sub grid so the two columns end
    # together — neither side trails dead space (owner decision 2026-08-03).
    latest = [i for i in by_latest if id(i) not in used and i["cat"] != "social" and palestine(i)][:8]
    rail_ids = {id(i) for i in latest}
    latest += [i for i in by_latest if id(i) not in used and i["cat"] != "social"
               and id(i) not in rail_ids][:8 - len(latest)]
    if len(latest) < 8:
        # Small builds: the rail is an index, not an owner of stories — it
        # may re-list what the hero tier already shows rather than run short.
        rail_ids = {id(i) for i in latest}
        latest += [i for i in by_latest if i["cat"] != "social"
                   and id(i) not in rail_ids][:8 - len(latest)]
    pal_news = [i for i in by_latest if i["cat"] != "social" and palestine(i)]
    ticker_items = (pal_news or [i for i in by_latest if i["cat"] != "social"])[:6]

    # Topical sections carry Palestine coverage only; world items from Palestinian
    # outlets live in More News. Research and Bitcoin are thematic by construction.
    sections = {k: diversify(take(by_score, lambda i, k=k: i["cat"] == k
                                  and (k in ("research", "bitcoin", "news") or palestine(i)), 8))
                for k in order}
    sections["news"] += take(by_score, lambda i: True, max(0, 8 - len(sections["news"])))
    P = "story/"  # homepage → story pages live one level down

    date_str = full_date(built_at, lang)
    d = built_at.astimezone(GAZA)
    time_str = f"{d.hour:02d}:{d.minute:02d}"

    ticker_track = "".join(f'<a href="{href(i, P)}">{esc(i["title"])}</a>' for i in ticker_items)
    # Israel-votes election box: a card in the franchise row, not a banner —
    # important, but not the top of the paper (owner decision 2026-08-02).
    # Alive until 27 October 2026.
    vote_card = ""
    _eday = datetime(2026, 10, 27, tzinfo=timezone.utc)
    if now < _eday and any(
            it.get("link") == f"original:israel-election-2026-tracker.{lang}" for it in items):
        _days = (_eday - now).days
        _vhref = _original_story_href("israel-election-2026-tracker")[lang]
        if lang == "ar":
            _vkick = "🗳 إسرائيل تنتخب · ٢٧ أكتوبر"
            _vttl = "مرصد الانتخابات: من يتقدّم، ومن يتراجع، وأي ائتلاف يتشكّل"
            _vcta = "تابع المرصد ←"
            _vdays = f"<b>{_days}</b><i>يوماً</i>"
            _valt = "خريطة مقاعد الكنيست بحسب الكتل: لا كتلة تبلغ 61 مقعداً من دون الأحزاب العربية"
        else:
            _vkick = "🗳 ISRAEL VOTES · 27 OCT"
            _vttl = "The coalition tracker: who leads, who gains, who falls"
            _vcta = "Follow the tracker →"
            _vdays = f"<b>{_days}</b><i>DAYS</i>"
            _valt = "Knesset seat map by bloc: neither side reaches the 61-seat majority without the Arab parties"
        vote_card = (f'<a class="fr-card vote" href="{esc(_vhref)}">'
                     f'<span class="days">{_vdays}</span>'
                     f'<img src="/media/times-of-palestine-israel-votes-card.svg" alt="{esc(_valt)}" loading="lazy">'
                     f'<span class="body"><span class="kick">{esc(_vkick)}</span>'
                     f'<span class="ttl">{esc(_vttl)}</span>'
                     f'<span class="go">{esc(_vcta)}</span></span></a>')
    specials_band = specials_band_html(lang, items, extra=vote_card)
    # Standing specials ride at the END of the loop — breaking news leads.
    for sp in available_specials(lang, items):
        ticker_track += f'<a href="{esc(sp["href"][lang])}">{esc(sp["ticker"][lang])}</a>'
    # The marquee's second copy is cloned AFTER the specials join the loop —
    # a shorter clone makes the loop jump, and it must stay hidden from
    # screen readers and the tab order (it repeats every headline).
    ticker_track_hidden = ticker_track.replace('<a href', '<a aria-hidden="true" tabindex="-1" href')

    def visible(k):
        return len(sections[k]) >= (1 if k in FOCUS_SECTIONS else 2)
    # Grouped nav (owner order 2026-08-05, after the two-tier bar reached
    # ~19 visible links): THE LATEST plus four dropdown groups, in the
    # spine's reading order — regions and power, depth, people, money.
    # A section missing from every group still appears (end of the first
    # group) — nothing silently vanishes. Gold specials ride inside
    # In-Depth; nav_primary specials (Sanad — owner order 2026-08-04)
    # stay top-level on the bar itself, never folded into a dropdown.
    _nav_groups = [
        ("regions", {"en": "News & Regions", "ar": "الأخبار والمناطق"},
         ["gaza", "westbank", "politics", "diaspora", "news"]),
        ("depth", {"en": "In-Depth", "ar": "في العمق"},
         ["accountability", "research", "social", "opinion", "archive"]),
        ("society", {"en": "Society & Culture", "ar": "المجتمع والثقافة"},
         ["women", "health", "humans", "arts", "sports"]),
        ("economy", {"en": "Economy & Aid", "ar": "الاقتصاد والإسناد"},
         ["economy", "arabaid", "bitcoin"]),
    ]
    _grouped_keys = {k for _, _, keys in _nav_groups for k in keys}
    _leftovers = [k for k in order if visible(k) and k not in _grouped_keys]
    nav_specials_top = ""
    _specials_depth = ""
    for sp in available_specials(lang, items):  # gold standing specials
        _sp_link = f'<a class="special" href="{esc(sp["href"][lang])}">{esc(sp["nav"][lang])}</a>'
        if sp.get("nav_primary"):
            nav_specials_top += _sp_link
        else:
            _specials_depth += _sp_link
    _gbtn_js = (
        "var g=this.parentNode,v=!g.classList.contains('open'),n=this.closest('nav');"
        "n.querySelectorAll('.nav-group.open').forEach(function(x){x.classList.remove('open');"
        "x.querySelector('button').setAttribute('aria-expanded','false')});"
        "if(v){g.classList.add('open');this.setAttribute('aria-expanded','true')}")
    nav_groups = ""
    for _gid, _label, _keys in _nav_groups:
        _keys = [k for k in _keys if k in sections and visible(k)]
        if _gid == "regions":
            _keys += _leftovers
        _links = "".join(f'<a href="#{k}">{t["sections"][k]}</a>' for k in _keys)
        if _gid == "depth":
            _links += _specials_depth
        if not _links:
            continue
        nav_groups += (
            f'<div class="nav-group"><button class="nav-gbtn" type="button" '
            f'aria-expanded="false" aria-controls="navg-{_gid}" aria-haspopup="true" '
            f'onclick="{_gbtn_js}">{_label[lang]} <span class="chev" aria-hidden="true">▾</span></button>'
            f'<div class="nav-drop" id="navg-{_gid}">{_links}</div></div>')

    def research_featured(it):
        media = (f'<a href="{href(it, P)}"><img src="{esc(it["image"])}" alt="{esc(it["title"])}" loading="lazy"{lede_fallback_attrs(it)}></a>'
                 if it["image"] else '<div class="noimg"><span>§</span></div>')
        return (f'<article class="research-feat"><div class="body">'
                f'<p class="kick">{t["research_kicker"]}</p>'
                f'<h3><a href="{href(it, P)}">{esc(it["title"])}</a></h3>'
                f'<p class="dek">{summary_html(it["dek"])}</p>{meta_line(it, lang)}'
                f'</div>{media}</article>')

    section_blocks = ""
    cats_present = {it["cat"] for it in items}  # archive pages exist only for real cats
    for k in order:
        if k == "opinion" or not visible(k):
            continue
        pool = sections[k][:4]
        featured = ""
        if k == "research":  # lead report gets the full featured-summary treatment
            featured, pool = research_featured(pool[0]), pool[1:]
        if not pool:
            grid = ""
        elif len(pool) == 1:  # a lone story reads better full width than as an orphan card
            grid = f'<div class="rowlist">{rowcard(pool[0], lang, P, solo=True)}</div>'
        else:
            cols = f" g{min(len(pool), 4)}"; grid = f'<div class="grid{cols}">{"".join(card(it, lang, P) for it in pool)}</div>'
        focus_cls = " focus" if k in FOCUS_SECTIONS else ""
        viewall = (f'<a class="viewall" href="section-{k}.html">{t["view_all"]}</a>'
                   if k in cats_present else "")
        section_blocks += (f'<section class="block" id="{k}"><div class="wrap">'
                           f'<div class="sec-copy"><div class="sec-head{focus_cls}"><h2>{t["sections"][k]}</h2><span class="rule"></span>{viewall}</div>{section_meta(sections[k], lang)}</div>'
                           + (('<p class="social-note">' + ("تقارير عامة من صحفيين مواطنين وشهود على الأرض. لا يُنشر أي تقرير حساس قبل موافقة محرر بشري على نسخته المحددة. " if lang == "ar" else "Public dispatches from citizen journalists and witnesses. Sensitive reports publish only after a human editor approves the exact version. ") + '<a href="#tips">' + ("أرسل تقريرك عبر خط «سيغنال» الآمن ←" if lang == "ar" else "Send yours via the secure Signal line →") + "</a></p>") if k == "social" else "") + f'{featured}{grid}</div></section>')

    opinion_block = ""
    if len(sections["opinion"]) >= 2:
        ops = "".join(op_card(it, lang, P) for it in sections["opinion"][:6])
        opinion_block = (f'<section class="opinion" id="opinion"><div class="wrap">'
                         f'<div class="sec-head"><h2>{t["sections"]["opinion"]}</h2><span class="rule"></span></div>'
                         f'<div class="op-grid">{ops}</div></div></section>')

    hero_html = ""
    if hero:
        hero_dek = f'<p class="dek">{summary_html(hero["dek"])}</p>' if hero["dek"] else ""
        hero_html = (
            f'<div class="hero-imgwrap">'
            f'<a href="{href(hero, P)}"><img src="{esc(hero["image"])}" alt="{esc(hero["title"])}" loading="eager" fetchpriority="high"{lede_fallback_attrs(hero)}></a>'
            f'<div class="hero-overlay">'
            f'<p class="label">{t["hero_label"]}</p>'
            f'<h2><a href="{href(hero, P)}">{esc(hero["title"])}</a></h2>'
            f'{meta_line(hero, lang)}'
            f'</div></div>'
            f'{media_credit(hero, lang)}'
            f'{hero_dek}'
        )

    hero_subs_html = "".join(sub_item(it, lang, P) for it in hero_subs)
    latest_html = "".join(latest_item(it, lang, P) for it in latest)
    gaza_panel = __import__("gaza_panel").panel(lang); tips_band = (
        f'<section class="tipband" id="tips"><div class="wrap">{LOCK_SVG}'
        f'<div class="txt"><p class="kick">{t["tips_kicker"]}</p>'
        f'<h2>{t["tips_title"]}</h2><p class="sub">{t["tips_sub"]}</p>'
        f'<p class="alt">{t["tips_tg"]} <a href="{TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{TELEGRAM_BOT_NAME}</a> — {t["tips_tg_note"]}</p></div>'
        f'<div class="cta"><a class="btn" href="{SIGNAL_URL}" target="_blank" rel="noopener">{t["tips_cta"]}</a>'
        f'<span class="micro">{t["tips_micro"]}</span>'
        f'<div class="qrbox"><img src="../signal-qr.png" alt="Signal QR — {SIGNAL_USERNAME}">'
        f'<span>{SIGNAL_USERNAME}</span></div></div>'
        f'<p class="safety">{t["tips_safety"]}</p>'
        f'</div></section>')

    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="max-image-preview:large">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/icon-192.png"><link rel="manifest" href="/manifest.json"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js")</script>
<title>{t['site_name']} — {t['title_suffix']}</title>
<meta name="description" content="{esc(meta_desc(t['mission']))}">
<link rel="canonical" href="{BASE_URL}/{lang}/">
<link rel="alternate" hreflang="en" href="{BASE_URL}/en/">
<link rel="alternate" hreflang="ar" href="{BASE_URL}/ar/">
<link rel="alternate" hreflang="x-default" href="{BASE_URL}/en/">
<link rel="alternate" type="application/rss+xml" title="{t['site_name']}" href="{BASE_URL}/{lang}/rss.xml">
<link rel="alternate" type="application/feed+json" title="{t['site_name']}" href="{BASE_URL}/{lang}/feed.json">
<meta property="og:type" content="website">
<meta property="og:locale" content="{'ar_AR' if lang == 'ar' else 'en_US'}">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{t['site_name']} — {t['title_suffix']}">
<meta property="og:description" content="{esc(meta_desc(t['mission']))}">
<meta property="og:url" content="{BASE_URL}/{lang}/">
<meta property="og:image" content="{BASE_URL}/og-banner.png"><meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{org_jsonld(lang)}</script>
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="topbar"><div class="wrap">
  <span class="date">{date_str}</span>
  <span class="upd"><span class="dot"></span>{t['updated']} {time_str}<span class="tz"> · {t['tz']}</span></span>
  {theme_btn(lang)}{lite_btn(lang)}<a class="lang" href="{t['switch_href']}">{t['switch_lang']}</a>
</div></div>

{ticker_html(t, lang, ticker_track, ticker_track_hidden)}

<header class="masthead"><div class="wrap">
  <a class="logotype" href="#top"><h1><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></h1></a>
</div></header>

<nav class="sections" aria-label="Primary"><div class="wrap"><a class="home" href="#top">{t['latest']}</a>{nav_groups}{nav_specials_top}<span class="nav-util"><a class="util" id="searchtoggle" href="search.html" aria-expanded="false" aria-controls="navsearch">{t['search_nav']}</a><a class="tip" href="#tips">🔒 {t['tips_nav']}</a></span></div><div class="nav-search" id="navsearch" hidden><form action="search.html" method="get" role="search"><input name="q" type="search" placeholder="{esc(t['search_prompt'])}" aria-label="{esc(t['search_title'])}" autocomplete="off"><button type="submit">{t['search_go']}</button></form></div></nav>
<script>(function(){{function closeGroups(){{document.querySelectorAll("nav.sections .nav-group.open").forEach(function(x){{x.classList.remove("open");x.querySelector("button").setAttribute("aria-expanded","false")}})}}
var st=document.getElementById("searchtoggle"),sp=document.getElementById("navsearch");
function closeSearch(){{if(sp&&!sp.hidden){{sp.hidden=true;st.setAttribute("aria-expanded","false")}}}}
if(st&&sp)st.addEventListener("click",function(e){{e.preventDefault();var open=!sp.hidden;closeGroups();if(open)closeSearch();else{{sp.hidden=false;st.setAttribute("aria-expanded","true");sp.querySelector("input").focus()}}}});
document.addEventListener("click",function(e){{if(e.target.closest("nav.sections .nav-drop a")||!e.target.closest("nav.sections")){{closeGroups();closeSearch()}}}});
document.addEventListener("keydown",function(e){{if(e.key==="Escape"){{closeGroups();if(sp&&!sp.hidden){{closeSearch();st.focus()}}}}}})}})()</script>

<main id="top">
  <div class="wrap hero-zone">
    <div class="hero">
      {hero_html}
      <div class="hero-sub">{hero_subs_html}</div>
    </div>
    <aside class="latest">
      <h2>{t['latest']}</h2>
      <ol>{latest_html}</ol>
    </aside>
  </div>
  {specials_band}{gaza_panel}
  {opinion_block}
  {section_blocks}
  {tips_band}
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="cols">
    <div><h2>{t['mission_title']}</h2><p class="mission">{t['mission']}</p></div>
    <div><h2>{t['tips_kicker']}</h2><p class="mission">{t['tips_sub']}</p>
      <p class="footer-contact"><a href="{SIGNAL_URL}" target="_blank" rel="noopener">🔒 {t['tips_cta']} {"←" if lang == "ar" else "→"}</a>
      <span class="contact-id">{SIGNAL_USERNAME}</span></p><p class="footer-contact secondary"><a href="{TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{t['tips_tg']} {"←" if lang == "ar" else "→"}</a> <span class="contact-id">{TELEGRAM_BOT_NAME}</span></p></div>
  </div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com · timesofpalestine.tv</span> <a href="about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a> <a href="corrections.html">{'التصويبات' if lang == 'ar' else 'Corrections'}</a> <a href="status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a> <a href="{TELEGRAM_CHANNEL_URL}" target="_blank" rel="noopener">{t['follow_tg']}</a> <a href="rss.xml">RSS</a>
    <span>{t['attribution']}</span>
    <a href="{t['switch_href']}">{t['footer_lang']}</a>
  </div>
</div></footer>
<script>(()=>{{const initial={json.dumps(utc_iso(built_at))};let timer;async function check(){{if(document.hidden||!navigator.onLine)return;try{{const r=await fetch("/data.json",{{cache:"no-store"}});if(r.ok&&((await r.json()).builtAt)!==initial)location.reload();}}catch(_error){{}}}}document.addEventListener("visibilitychange",()=>{{if(!document.hidden)check();}});timer=setInterval(check,900000);}})();</script>
<script>{_CLOCK_JS}</script>
{live_fab_html(lang)}
</body>
</html>"""
_LISTEN_JS = """
(function(){var b=document.getElementById("listen");if(!b)return;
if(!("speechSynthesis"in window)||!window.SpeechSynthesisUtterance)return;
b.hidden=false;var S=speechSynthesis,L=document.documentElement.lang||"en";
var LOC=L==="ar"?"ar-SA":L==="en"?"en-US":L;
var parts=[],idx=0,state="idle",voice=null;
function pick(){var vs=S.getVoices();if(!vs.length)return;
  voice=vs.find(function(v){return v.lang&&v.lang.slice(0,2)===L&&v.localService})
    ||vs.find(function(v){return v.lang&&v.lang.slice(0,2)===L})||null;}
pick();if(S.onvoiceschanged!==undefined)S.addEventListener("voiceschanged",pick);
function collect(){var out=[];var h=document.querySelector(".story h1");
  if(h)out.push(h.textContent.trim());
  var ps=document.querySelectorAll(".story p.summary, .story .summary p, .story .summary h2, .story .summary li");
  ps.forEach(function(p){var x=p.textContent.trim();if(x)out.push(x)});
  var chunks=[];function push(s){
    while(s.length>170){var cut=s.lastIndexOf(" ",170);if(cut<80)cut=170;
      chunks.push(s.slice(0,cut));s=s.slice(cut)}
    if(/[A-Za-z\\u0600-\\u06FF]/.test(s))chunks.push(s)}
  out.forEach(function(txt){
    var bits=txt.split(/([.!?\\u061F\\u06D4]+["\\u00BB\\u201D']?\\s+)/),acc="";
    for(var i=0;i<bits.length;i+=2){
      var s=(bits[i]||"")+(bits[i+1]||"");if(!s.trim())continue;
      if(acc&&(acc+s).length>170){push(acc);acc=s}else acc+=s}
    push(acc)});
  return chunks}
function label(k){b.textContent=b.dataset[k]}
function reset(){state="idle";idx=0;label("play")}
function next(){if(idx>=parts.length){reset();return}
  var u=new SpeechSynthesisUtterance(parts[idx++]);
  u.lang=LOC;if(voice)u.voice=voice;u.rate=1;
  u.onend=function(){if(state==="speaking")next()};
  u.onerror=function(){if(state==="speaking")next()};
  S.speak(u)}
b.addEventListener("click",function(){
  if(state==="idle"){pick();parts=collect();if(!parts.length)return;
    S.cancel();state="speaking";label("pause");next()}
  else if(state==="speaking"){S.pause();state="paused";label("resume")}
  else{S.resume();state="speaking";label("pause")}});
window.addEventListener("pagehide",function(){S.cancel()});
})();
"""


def render_story(it, lang, related, rail, built_at):
    """Internal story page: brief, breaking ticker, Keep Reading grid, Latest rail.
    Every page links onward to many others — readers always circulate."""
    t = STR[lang]
    # Listen button (owner directive 2026-08-03, Economist/WaPo pattern):
    # reads the story aloud with the device's own voices via the Web Speech
    # API — no third-party audio service, nothing leaves the reader's device,
    # works in both languages. Hidden until JS confirms support.
    _l_play = "استمع 🎧" if lang == "ar" else "🎧 Listen"
    _l_pause = "إيقاف مؤقت ⏸" if lang == "ar" else "⏸ Pause"
    _l_resume = "متابعة ▶" if lang == "ar" else "▶ Resume"
    listen_btn = (f'<button id="listen" class="listenbtn" hidden '
                  f'data-play="{esc(_l_play)}" data-pause="{esc(_l_pause)}" '
                  f'data-resume="{esc(_l_resume)}" '
                  f'aria-label="{"استمع إلى هذا التقرير" if lang == "ar" else "Listen to this story"}">'
                  f'{esc(_l_play)}</button>')
    lede = (
        f'<img class="lede" src="{esc(it["image"])}" alt="{esc(it["title"])}"{lede_fallback_attrs(it)}>'
        f'{media_credit(it, lang)}'
    ) if it["image"] else f'<div class="lede">{FLAG_SVG}</div>'
    brief = it.get("brief")
    # Hard stop: AI-refusal text must never render. Originals are exempt here —
    # they are editor-authored and refusal-screened LOUDLY at validation time
    # (a match skips the article with a warning), so innocent phrases like
    # "النص الكامل" can never silently degrade a published page to its dek.
    if brief and not it.get("original") and REFUSAL_RX.search(brief):
        brief = None
    if brief:  # original TOP Newsdesk brief, written by Claude, cached per story
        if not it.get("original"):  # pacing guard: no wall-of-text blocks
            brief = reflow_paragraphs(brief)
        paras = __import__("longform").body_html(brief)
        paras, story_toc = add_story_outline(paras, lang)
        # Owner decision 2026-07-30, wire protocol: a rewritten story is OUR
        # copy. The source is credited once, inline, in the prose ("…, Ma'an
        # reported") — no byline credit-link and no read-at-source button.
        # A Telegram-sourced story embeds the source post itself below our
        # copy — video and photos play natively, like a photo with credit.
        source_embed = ""
        if not it.get("original"):
            tme = re.match(r"https://t\.me/([A-Za-z0-9_]{3,40})/(\d+)$",
                           str(it.get("link", "")))
            if tme:
                emb_cap = ("المنشور المصدر كما بثّته القناة" if lang == "ar"
                           else "The source post as published on Telegram")
                source_embed = (
                    f'<figure class="lf video"><div class="embed tme">'
                    f'<iframe src="https://t.me/{tme.group(1)}/{tme.group(2)}?embed=1" '
                    f'title="{emb_cap}" loading="lazy" frameborder="0"></iframe></div>'
                    f'<figcaption>{emb_cap}</figcaption></figure>')
        kind = t["kind_original"] if it.get("original") else t["kind_brief"]
        summary = (f'<p class="kind">{kind}</p>'
                   f'<p class="byline">{t["byline"]} · {reading_time_label(brief, lang)}</p>'
                   f'{story_toc}{paras}{source_embed}')
    else:
        story_toc = ""
        if it.get("original"):
            summary = f'<p class="summary">{summary_html(it["dek"])}</p>' if it["dek"] else ""
        else:
            source_credit = (
                f'<span class="based">{t["based_on"]} '
                f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">'
                f'{esc(it["source"])}</a></span>')
            summary = (
                f'<p class="kind">{t["kind_curated"]}</p>'
                f'<p class="byline">{source_credit}</p>'
                f'<p class="summary">{summary_html(it["dek"])}</p>')
    rail_items = [r for r in rail if r is not it]
    ticker_track = "".join(f'<a href="{href(r, "")}">{esc(r["title"])}</a>' for r in rail_items[:6])
    ticker_track_hidden = ticker_track.replace('<a href', '<a aria-hidden="true" tabindex="-1" href')
    latest_html = "".join(latest_item(r, lang, "") for r in rail_items[:10])
    if it.get("original") or brief:
        cta = ""  # our copy: attribution lives inline in the prose, wire-style
    else:
        # dek-fallback only (briefs layer down): the body is the source's own
        # summary, so the credit-link and read-at-source button stay.
        cta = (f'<div class="cta">'
               f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">{t["read_original"]} {esc(it["source"])} {"←" if lang == "ar" else "→"}</a>'
               f'<p class="note">{t["summary_note"]}</p></div>')
    corroborating = [
        source for source in it.get("corroborating_sources", [])
        if source.get("article") and source.get("article") != it.get("link")
    ]
    # Owner decision 2026-07-30: no reader-facing review labels on any story.
    # review_status stays internal (review-queue.json) for editors only.
    review_note = ""
    corrections = ""
    if it.get("corrections"):
        heading = "سجل التحديثات والتصويبات" if lang == "ar" else "Updates & corrections"
        rows = "".join(
            f'<li><time datetime="{esc(row["at"])}">{esc(row["at"][:10])}</time> '
            f'<strong>{"تصويب" if lang == "ar" and row["type"] == "correction" else "تحديث" if lang == "ar" else row["type"].title()}:</strong> '
            f'{esc(row["note"])}</li>' for row in it["corrections"])
        ledger_label = ("سجل التصويبات الكامل ←" if lang == "ar"
                        else "Full corrections ledger →")
        corrections = (
            f'<section class="revisions" aria-labelledby="revision-title">'
            f'<h2 id="revision-title">{esc(heading)}</h2><ol>{rows}</ol>'
            f'<p class="ledgerlink"><a href="../corrections.html">{ledger_label}</a></p></section>')
    related_primary = [r for r in related if r is not it and r["cat"] == it["cat"]]
    related_secondary = [r for r in related if r is not it and r["cat"] != it["cat"]]
    related_cards = "".join(card(r, lang, "") for r in (related_primary + related_secondary)[:8])
    page_url = story_url(it, lang)
    # What readers copy and send is the SHORT link (owner call 2026-08-05):
    # an Arabic slug percent-encodes to hundreds of characters, while the
    # bare-pid stub URL stays tweet-length and forwards to this canonical.
    share_url = BASE_URL + story_short_path(it["pid"], lang)
    _q = __import__("urllib.parse", fromlist=["quote"]).quote
    copy_btn = ('<button class="copybtn" data-copied="' + ("تم النسخ ✓" if lang == "ar" else "Copied ✓")
                + '" onclick="var b=this;navigator.clipboard.writeText(b.dataset.url).then(function(){var t=b.textContent;b.textContent=b.dataset.copied;setTimeout(function(){b.textContent=t},1600)})" data-url="'
                + share_url + '">' + ("انسخ الرابط" if lang == "ar" else "Copy link") + "</button>")
    share_row = ('<div class="share"><span>' + ("شارك" if lang == "ar" else "Share") + '</span><a href="https://twitter.com/intent/tweet?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener">X</a><a href="https://www.facebook.com/sharer/sharer.php?u=' + _q(share_url) + '" target="_blank" rel="noopener">Facebook</a><a href="https://wa.me/?text=' + _q(it["title"] + " " + share_url) + '" target="_blank" rel="noopener">WhatsApp</a><a href="https://t.me/share/url?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener">Telegram</a>' + copy_btn + '</div>')
    share_rail = ('<nav class="share-rail" aria-label="' + ("شارك الخبر" if lang == "ar" else "Share this story") + '"><a href="https://twitter.com/intent/tweet?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener" title="X">X</a><a href="https://www.facebook.com/sharer/sharer.php?u=' + _q(share_url) + '" target="_blank" rel="noopener" title="Facebook">f</a><a href="https://wa.me/?text=' + _q(it["title"] + " " + share_url) + '" target="_blank" rel="noopener" title="WhatsApp">Wa</a><a href="https://t.me/share/url?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener" title="Telegram">Tg</a></nav>')
    plain_desc = meta_desc(summary_text(
        (it.get("brief") or it["dek"]).replace(chr(10), " ")))
    desc = esc(plain_desc)
    og_img_url = (BASE_URL + it["image"]) if (it.get("image") or "").startswith("/") else it.get("image")
    og_image = f'<meta property="og:image" content="{esc(og_img_url)}">' if it["image"] else ""
    story_stamp = (
        f'<p class="story-stamp"><time datetime="{utc_iso(it["date"])}">{t["story_published"]} {full_stamp(it["date"], lang)}</time>'
        + (f'<time datetime="{utc_iso(it["modified"])}">{t["story_updated"]} {full_stamp(it["modified"], lang)}</time>'
           if it.get("modified") else "")
        + "</p>"
    )
    section_name = t["sections"].get(it["cat"], t["sections"]["news"])
    # Breadcrumbs land on the real section archive, not a homepage anchor —
    # the archive is the crawlable, linkable landing page for the section.
    section_href = f"section-{it['cat']}.html"
    breadcrumb_nav = (
        f'<nav class="breadcrumbs" aria-label="Breadcrumb">'
        f'<a href="../">{t["breadcrumbs_home"]}</a><span class="sep">/</span>'
        f'<a href="../{section_href}">{section_name}</a><span class="sep">/</span>'
        f'<span aria-current="page">{esc(it["title"])}</span></nav>'
    )
    breadcrumb_jsonld = jsonld_dump({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1,
             "name": t["breadcrumbs_home"], "item": f"{BASE_URL}/{lang}/"},
            {"@type": "ListItem", "position": 2, "name": section_name,
             "item": f"{BASE_URL}/{lang}/{section_href}"},
            {"@type": "ListItem", "position": 3, "name": it["title"]},
        ]})
    hreflang = ""
    # Default language switch lands on the other edition's front page; when a
    # bilingual pair exists it deep-links to the story's own translation.
    switch_href = f"../../{'en' if lang == 'ar' else 'ar'}/"
    if it["source_id"] == "top-original" and str(it.get("link", "")).startswith("original:"):
        stem = it["link"].split(":", 1)[1]
        if "." in stem:
            slug, source_lang = stem.rsplit(".", 1)
            if source_lang in ("en", "ar"):
                other_lang = "ar" if source_lang == "en" else "en"
                other_title = _original_header_title(slug, other_lang)
                if other_title:
                    this_pid = hashlib.md5(f"original:{slug}.{source_lang}".encode()).hexdigest()[:10]
                    other_pid = hashlib.md5(f"original:{slug}.{other_lang}".encode()).hexdigest()[:10]
                    this_url = BASE_URL + story_url_path(it["title"], this_pid, source_lang)
                    other_url = BASE_URL + story_url_path(other_title, other_pid, other_lang)
                    en_url = this_url if source_lang == "en" else other_url
                    switch_href = other_url
                    hreflang = (f'<link rel="alternate" hreflang="{source_lang}" href="{this_url}">\n'
                                f'<link rel="alternate" hreflang="{other_lang}" href="{other_url}">\n'
                                f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    jsonld_record = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": it["title"], "datePublished": utc_iso(it["date"]),
        "mainEntityOfPage": page_url,
        "url": page_url,
        "description": plain_desc,
        "image": [og_img_url] if it["image"] else [],
        "publisher": {"@type": "NewsMediaOrganization", "name": t["site_name"],
                      "url": f"{BASE_URL}/{lang}/",
                      "logo": {"@type": "ImageObject",
                               "url": f"{BASE_URL}/icon-512.png"}},
        "articleSection": t["sections"].get(it["cat"], t["sections"]["news"]),
        "inLanguage": lang,
        "author": ({"@type": "Organization", "name": t["site_name"],
                    "url": f"{BASE_URL}/{lang}/about.html"}
                   if brief or it.get("original")
                   else {"@type": "Organization", "name": it["source"],
                         "url": it["source_url"]}),
    }
    if it.get("modified"):
        jsonld_record["dateModified"] = utc_iso(it["modified"])
    if not it.get("original"):
        jsonld_record["isBasedOn"] = it["link"]
        jsonld_record["citation"] = [it["link"]] + [
            source["article"] for source in corroborating]
    if it.get("media"):
        _media = it["media"]
        _src_name = _media.get("source") or t["site_name"]
        _img_obj = {
            "@type": "ImageObject",
            "url": og_img_url,
            "creditText": _media["credit"],
            "creator": {"@type": "Organization", "name": _src_name},
            "copyrightNotice": f"© {_src_name}",
            "acquireLicensePage": f"{BASE_URL}/{lang}/about.html",
        }
        if _media.get("licenseUrl"):
            _img_obj["license"] = _media["licenseUrl"]
        jsonld_record["image"] = [_img_obj]
    jsonld = jsonld_dump(jsonld_record)
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/icon-192.png"><link rel="manifest" href="/manifest.json"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js")</script>
<title>{esc(it['title'])} — {t['site_name']}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="max-image-preview:large">
<link rel="canonical" href="{page_url}">
{hreflang}
<meta property="og:type" content="article">
<meta property="og:locale" content="{'ar_AR' if lang == 'ar' else 'en_US'}">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(it['title'])}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{page_url}">
{og_image}
<meta name="twitter:card" content="{'summary_large_image' if it['image'] else 'summary'}">
<script type="application/ld+json">{jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}
</head>
<body>
<div class="backbar"><a href="../">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="{switch_href}">{t['switch_lang']}</a></span></div>
{ticker_html(t, lang, ticker_track, ticker_track_hidden)}
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="../"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>

<main>
  <article class="story">
    {breadcrumb_nav}
    <p class="kick">{t['sections'].get(it['cat'], t['sections']['news'])}</p>
    <h1>{esc(it['title'])}</h1>
    {meta_line(it, lang)}
    {story_stamp}
    {listen_btn}
    {review_note}
    {lede}
    {summary}
    {cta}{corrections}{share_row}
  </article>
  {share_rail}
  <section class="keep"><div class="wrap">
    <div class="sec-head focus"><h2>{t['keep_reading']}</h2><span class="rule"></span></div>
    <div class="grid">{related_cards}</div>
  </div></section>
  <section class="keep"><div class="wrap latest">
    <h2>{t['latest']}</h2>
    <ol>{latest_html}</ol>
  </div></section>
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span> <a href="../about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a> <a href="../corrections.html">{'التصويبات' if lang == 'ar' else 'Corrections'}</a> <a href="../status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a>
    <a href="../">{t['back_home']}</a>
  </div>
</div></footer>
<script>{_LISTEN_JS}</script>
<script>{_CLOCK_JS}</script>
{live_fab_html(lang)}
</body>
</html>"""
def story_redirect_stub(it, lang):
    """Tiny page at the bare-pid URL forwarding to the slugged canonical.
    This IS the share link (owner call 2026-08-05 — an Arabic slug
    percent-encodes to hundreds of characters), so it carries the full
    OpenGraph set: Telegram, WhatsApp and Facebook build their link previews
    from THIS page's meta and do not follow the meta refresh."""
    target = story_url(it, lang)
    desc = esc(meta_desc(summary_text(
        (it.get("brief") or it["dek"]).replace(chr(10), " "))))
    og_img_url = (BASE_URL + it["image"]) if (it.get("image") or "").startswith("/") else it.get("image")
    og_image = f'<meta property="og:image" content="{esc(og_img_url)}">' if it["image"] else ""
    return (f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<title>{esc(it["title"])}</title>'
            f'<link rel="canonical" href="{target}">'
            '<meta name="robots" content="noindex">'
            f'<meta name="description" content="{desc}">'
            '<meta property="og:type" content="article">'
            f'<meta property="og:site_name" content="{STR[lang]["site_name"]}">'
            f'<meta property="og:title" content="{esc(it["title"])}">'
            f'<meta property="og:description" content="{desc}">'
            f'<meta property="og:url" content="{BASE_URL}{story_short_path(it["pid"], lang)}">'
            f'{og_image}'
            f'<meta name="twitter:card" content="{"summary_large_image" if it["image"] else "summary"}">'
            f'<meta http-equiv="refresh" content="0;url={target}">'
            f'<script>location.replace({json.dumps(target)});</script>'
            f'</head><body><p><a href="{target}">{esc(it["title"])}</a></p></body></html>')


def render_rss(lang, items, built_at):
    """Standard RSS 2.0 feed so readers, apps and other sites can syndicate TOP."""
    t = STR[lang]
    from email.utils import format_datetime
    entries = []
    for it in sorted([i for i in items if i["cat"] != "social"],
                     key=lambda i: i["date"], reverse=True)[:30]:
        u = story_url(it, lang)
        desc = summary_text(
            (it.get("brief") or it["dek"]).split(chr(10))[0])
        modified = (
            f"<atom:updated>{utc_iso(it['modified'])}</atom:updated>"
            if it.get("modified") else "")
        source = ("" if it.get("original") else
                  f'<source url="{esc(it["source_url"])}">{esc(it["source"])}</source>')
        entries.append(f"<item><title>{esc(it['title'])}</title><link>{u}</link>"
                       f'<guid isPermaLink="true">{u}</guid>'
                       f"<pubDate>{format_datetime(it['date'], usegmt=True)}</pubDate>"
                       f"{modified}{source}"
                       f"<description>{esc(desc[:400])}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f"<title>{esc(t['site_name'])}</title><link>{BASE_URL}/{lang}/</link>"
            f"<description>{esc(t['title_suffix'])}</description><language>{lang}</language>"
            f'<atom:link href="{BASE_URL}/{lang}/rss.xml" rel="self" type="application/rss+xml"/>'
            f"<lastBuildDate>{format_datetime(built_at, usegmt=True)}</lastBuildDate>"
            + "".join(entries) + "</channel></rss>")

def reading_time_label(text, lang):
    """Honest minute-level estimate; Arabic reads slightly denser per word."""
    words = len(re.findall(r"\S+", text or ""))
    minutes = max(1, round(words / (180 if lang == "ar" else 200)))
    if lang == "ar":
        if minutes == 1:
            return "قراءة دقيقة واحدة"
        if minutes == 2:
            return "قراءة دقيقتين"
        if minutes <= 10:
            return f"قراءة {minutes} دقائق"
        return f"قراءة {minutes} دقيقة"
    return f"{minutes} min read"


def render_section_page(lang, cat, items, built_at, more_items=()):
    """Real category archive page: every live story in the section, own URL,
    own meta description — the SEO landing page the one-page front can't be.
    `more_items` (newest stories from other sections) keeps thin sections
    from dead-ending — every page offers a way deeper into the paper."""
    t = STR[lang]
    name = t["sections"].get(cat, cat)
    desc = (f"كل تغطية «{name}» في تايمز أوف فلسطين — أخبار فلسطينية مستقلة تُحدَّث باستمرار."
            if lang == "ar" else
            f"All {name} coverage from Times of Palestine — independent Palestinian news, updated continuously.")
    n = len(items)
    if lang == "ar":
        count_label = "قصة واحدة" if n == 1 else ("قصتان" if n == 2 else f"{n} قصص" if n <= 10 else f"{n} قصة")
    else:
        count_label = f"{n} story" if n == 1 else f"{n} stories"
    cards = "".join(card(it, lang, "story/") for it in items)
    more_html = ""
    if more_items:
        more_label = "المزيد من تايمز أوف فلسطين" if lang == "ar" else "More from Times of Palestine"
        more_cards = "".join(card(it, lang, "story/") for it in more_items)
        more_html = (f'<div class="sec-head focus morehead"><h2>{more_label}</h2>'
                     f'<span class="rule"></span></div>'
                     f'<div class="grid g4">{more_cards}</div>')
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48">
<title>{esc(name)} — {t['site_name']}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="max-image-preview:large">
<link rel="canonical" href="{BASE_URL}/{lang}/section-{cat}.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(name)} — {t['site_name']}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE_URL}/{lang}/section-{cat}.html">
<meta property="og:image" content="{BASE_URL}/og-banner.png">
<meta name="twitter:card" content="summary_large_image">
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}
</head>
<body>
<div class="backbar"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
<main class="wrap sectionpage">
  <div class="sec-head focus"><h2>{esc(name)}</h2><span class="rule"></span><span class="count">{count_label}</span></div>
  <div class="grid g4">{cards}</div>
  {more_html}
</main>
<footer><div class="wrap"><div class="flagline"></div>
  <div class="legal"><span>© {built_at.year} {t['site_name']}</span> <a href="./">{t['back_home']}</a> <a href="about.html">{'من نحن' if lang == 'ar' else 'About'}</a></div>
</div></footer>
<script>{_CLOCK_JS}</script>
</body></html>"""


def render_corrections_page(lang, items, built_at):
    """Public corrections & updates ledger — every dated revision note from
    editorial/corrections.json on one page, newest first. The per-story
    stamps already run on the articles themselves; this page is the standing
    trust signal (NewsGuard/JTI checklist) that the practice is systematic.
    Entries whose story has rotated off the live site keep their note and
    reference id — the record does not expire with the page."""
    t = STR[lang]
    title = "التصويبات والتحديثات" if lang == "ar" else "Corrections & updates"
    intro = (
        "حين نخطئ نصحّح فوراً ونثبّت التعديل بتاريخه على المادة نفسها. "
        "هذه الصفحة تجمع سجل التصويبات والتحديثات التحريرية كاملاً. "
        "لطلب تصويب راسل غرفة الأخبار عبر صفحة «من نحن» مع رابط المادة وبيان الخطأ."
        if lang == "ar" else
        "When we get something wrong we correct it promptly and note the change, "
        "dated, on the story itself. This page carries the full ledger of those "
        "corrections and editorial updates. To request a correction, contact the "
        "newsroom via the About page with the story link and the error.")
    live = {it["pid"]: it for it in items}
    # One editorial event, one entry: the ledger stores the same note under
    # each edition's story id, so identical (date, note) pairs collapse —
    # keeping the id that is live in THIS edition when there is one.
    by_event = {}
    for pid, raw in CORRECTIONS["stories"].items():
        for note in validate_corrections(raw, pid, lang):
            key = (note["at"], note["type"], note["note"])
            if key not in by_event or (pid in live and by_event[key] not in live):
                by_event[key] = pid
    rows = sorted(((at, kind, note, pid) for (at, kind, note), pid
                   in by_event.items()), reverse=True)
    if rows:
        entries = []
        for at, kind, note, pid in rows:
            kind_label = (("تصويب" if kind == "correction" else "تحديث")
                          if lang == "ar" else kind.title())
            it = live.get(pid)
            if it:
                story_ref = (f'<a href="story/{quote(story_file_name(it["title"], it["pid"]))}">'
                             f'{esc(it["title"])}</a>')
            else:
                archived = ("المادة خرجت من الموقع الحي · مرجع "
                            if lang == "ar" else "Story rotated off the live site · ref ")
                story_ref = f'<span class="ref">{archived}{esc(pid)}</span>'
            entries.append(
                f'<li><time datetime="{esc(at)}">{esc(at[:10])}</time> '
                f'<strong>{kind_label}:</strong> {esc(note)}<br>{story_ref}</li>')
        body = f'<ol class="corrections-log">{"".join(entries)}</ol>'
    else:
        body = ('<p class="summary">' + (
            "لا توجد تصويبات مسجّلة حالياً." if lang == "ar"
            else "No corrections are currently on the record.") + "</p>")
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48">
<title>{esc(title)} — {t['site_name']}</title>
<meta name="description" content="{esc(meta_desc(intro))}">
<link rel="canonical" href="{BASE_URL}/{lang}/corrections.html">
<link rel="alternate" hreflang="en" href="{BASE_URL}/en/corrections.html">
<link rel="alternate" hreflang="ar" href="{BASE_URL}/ar/corrections.html">
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}
</head>
<body>
<div class="backbar"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/corrections.html">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
<main>
  <article class="story">
    <p class="kick">{t['site_name']}</p>
    <h1>{esc(title)}</h1>
    <p class="summary">{intro}</p>
    <section class="revisions">{body}</section>
  </article>
</main>
<footer><div class="wrap"><div class="flagline"></div>
  <div class="legal"><span>© {built_at.year} {t['site_name']}</span> <a href="./">{t['back_home']}</a> <a href="about.html">{'من نحن' if lang == 'ar' else 'About'}</a></div>
</div></footer>
<script>{_CLOCK_JS}</script>
</body></html>"""


_SEARCH_JS = """
(function(){var IDX=null;var q=document.getElementById("q"),res=document.getElementById("res");
function load(){if(IDX)return Promise.resolve(IDX);
  return fetch("search-index.json").then(function(r){return r.json()}).then(function(d){IDX=d;return d});}
function render(hits,none){res.textContent="";
  if(!hits.length){var li=document.createElement("li");li.className="none";li.textContent=none;res.appendChild(li);return;}
  hits.forEach(function(e){var li=document.createElement("li");
    var a=document.createElement("a");a.href=e.u;a.textContent=e.t;
    var c=document.createElement("span");c.className="c";c.textContent=e.c;
    var p=document.createElement("p");p.textContent=e.d;
    li.appendChild(a);li.appendChild(c);li.appendChild(p);res.appendChild(li);});}
function go(){var v=q.value.trim().toLowerCase();if(v.length<2){res.textContent="";return;}
  load().then(function(ix){var terms=v.split(/\\s+/);
    var hits=ix.filter(function(e){var hay=(e.t+" "+e.d+" "+e.c).toLowerCase();
      return terms.every(function(w){return hay.indexOf(w)!==-1});}).slice(0,40);
    render(hits,q.dataset.none);});}
q.addEventListener("input",go);
var init=new URLSearchParams(location.search).get("q");
if(init){q.value=init;go();}})();
"""


def render_search_page(lang, built_at, cats=()):
    """Client-side archive search: fetches the build's index, filters locally.
    No third-party code; results built with textContent, never innerHTML.
    `cats` renders browse chips so the empty page still leads somewhere."""
    t = STR[lang]
    browse = ""
    if cats:
        bl = "تصفح الأقسام" if lang == "ar" else "Or browse the sections"
        chips = "".join(
            f'<a href="section-{c}.html">{esc(t["sections"].get(c, c))}</a>'
            for c in cats if c in t["sections"])
        browse = (f'<div class="browse"><span class="bl">{bl}</span>'
                  f'<nav>{chips}</nav></div>')
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48">
<title>{t['search_title']} — {t['site_name']}</title>
<meta name="description" content="{esc(t['search_prompt'])}">
<meta name="robots" content="noindex">
<link rel="canonical" href="{BASE_URL}/{lang}/search.html">
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}
</head>
<body>
<div class="backbar"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/search.html">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
<main class="wrap searchpage">
  <h1>{t['search_title']}</h1>
  <input id="q" class="searchbox" type="search" placeholder="{esc(t['search_prompt'])}" data-none="{esc(t['search_none'])}" autofocus autocomplete="off">
  <ol id="res" class="searchres"></ol>
  {browse}
</main>
<script>{_SEARCH_JS}</script>
</body></html>"""


def render_sitemap(langs_items, built_at):
    day = built_at.strftime("%Y-%m-%d")
    urls = []
    for lang, items in langs_items:
        urls.append(f"<url><loc>{BASE_URL}/{lang}/</loc><lastmod>{day}</lastmod>"
                    "<changefreq>hourly</changefreq><priority>1.0</priority></url>")
        for cat in sorted({it["cat"] for it in items}):
            urls.append(f"<url><loc>{BASE_URL}/{lang}/section-{cat}.html</loc>"
                        f"<lastmod>{day}</lastmod><changefreq>daily</changefreq>"
                        "<priority>0.7</priority></url>")
        for it in items:
            changed = it.get("modified") or it["date"]
            urls.append(f"<url><loc>{story_url(it, lang)}</loc>"
                        f"<lastmod>{utc_iso(changed)}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls) + "</urlset>")

ROBOTS_TXT = f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""

REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Times of Palestine</title>
<meta name="description" content="Independent Palestine news, in English and Arabic — updated continuously.">
<script>location.replace((navigator.language||"").toLowerCase().indexOf("ar")===0?"ar/":"en/");</script>
<meta http-equiv="refresh" content="1;url=en/">
</head><body><p><a href="en/">English</a> · <a href="ar/">العربية</a></p></body></html>"""

# ---------- main ----------

def main():
    global HEALTH
    built_at = datetime.now(timezone.utc)
    HEALTH = BuildHealth(built_at)
    remote_media_mode()
    if os.environ.get("TOP_SKIP_ORIGINALS") != "1":
        import originals_gen
        print(originals_gen.run())
    for lang in ("en", "ar"):
        for feed in FEEDS[lang]:
            HEALTH.register_source(feed, lang)
    en_items = build_lang("en")
    ar_items = build_lang("ar")
    all_fetched_items = en_items + ar_items
    try:
        brief_status = generate_briefs(all_fetched_items)
    except Exception as e:  # a desk outage must not stop originals or cached briefs
        print(
            f"\nBriefs: stage failed ({type(e).__name__}) — "
            "only complete cached newsroom briefs will publish.")
        HEALTH.checks["brief_generation"] = "degraded"
    else:
        HEALTH.checks["brief_generation"] = brief_status
    # Second event-dedupe pass, on the FINAL headlines (owner report
    # 2026-08-03: two pages of one story reached readers). The first pass
    # compares raw feed titles; the briefs desk then rewrites them, and two
    # different source headlines for one incident can converge into
    # near-identical house headlines. What the reader sees twice is what
    # must be deduped — so the same gate runs again on published titles.
    _before = len(en_items) + len(ar_items)
    en_items = dedupe_events(en_items)
    ar_items = dedupe_events(ar_items)
    HEALTH.deduplicated += _before - len(en_items) - len(ar_items)
    candidates = select_publishable_copy(en_items, ar_items)
    approvals = load_reviews(ROOT / "editorial" / "reviews.json")
    gate_mode = review_gate_mode()
    # The review gate is for third-party copy (wires, Telegram) whose sourcing
    # we cannot see. Our own signed reporting — desk originals and the
    # Washington Brief — is validated at generation (sourced-or-INSUFFICIENT,
    # validate_original) and never carries the "developing report" label.
    own_reporting = [i for i in candidates if i.get("source_id") == "top-original"]
    for item in own_reporting:
        item.pop("review_status", None)
        item.pop("risk_reasons", None)
    third_party = [i for i in candidates if i.get("source_id") != "top-original"]
    eligible, pending = apply_review_gate(third_party, approvals, mode=gate_mode)
    eligible = own_reporting + eligible
    held = pending if gate_mode == "hold" else []
    HEALTH.review_held = len(held)
    HEALTH.review_approved = sum(1 for item in eligible if item.get("risk_reasons"))
    for item in held:
        for reason in item["risk_reasons"]:
            HEALTH.hold(f"review:{reason}")
    en_items = [item for item in eligible if item["lang"] == "en"]
    ar_items = [item for item in eligible if item["lang"] == "ar"]
    dist = ROOT / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    assets.joinpath("site.css").write_text(
        CSS + __import__("longform").CSS + __import__("gaza_panel").PANEL_CSS,
        encoding="utf-8",
    )
    for lang, items in (("en", en_items), ("ar", ar_items)):
        import shutil
        shutil.rmtree(dist / lang / "story", ignore_errors=True)  # drop stale story pages
        (dist / lang / "story").mkdir(parents=True, exist_ok=True)
        for stale in (dist / lang).glob("section-*.html"):  # archives rebuild fresh too
            stale.unlink()
        (dist / lang / "index.html").write_text(render_page(lang, items, built_at), encoding="utf-8")
        for cat in sorted({it["cat"] for it in items}):
            cat_items = sorted((i2 for i2 in items if i2["cat"] == cat),
                               key=lambda r: r["date"], reverse=True)
            more_items = sorted((i2 for i2 in items if i2["cat"] != cat),
                                key=lambda r: r["date"], reverse=True)[:8]
            (dist / lang / f"section-{cat}.html").write_text(
                render_section_page(lang, cat, cat_items, built_at,
                                    more_items=more_items), encoding="utf-8")
        (dist / lang / "search.html").write_text(
            render_search_page(lang, built_at,
                               cats=sorted({it["cat"] for it in items})), encoding="utf-8")
        (dist / lang / "corrections.html").write_text(
            render_corrections_page(lang, items, built_at), encoding="utf-8")
        (dist / lang / "search-index.json").write_text(json.dumps(
            [{"t": it["title"], "u": story_url_path(it["title"], it["pid"], lang),
              "d": truncate(it["dek"], 160),
              "c": STR[lang]["sections"].get(it["cat"], it["cat"])} for it in items],
            ensure_ascii=False), encoding="utf-8")
        news = [r for r in items if r["cat"] != "social"]
        rail = ([r for r in news if PALESTINE_RX.search(f"{r['title']} {r['dek']}")] +
                [r for r in news if not PALESTINE_RX.search(f"{r['title']} {r['dek']}")])[:11]
        for it in items:
            same_cat = [r for r in items if r is not it and r["cat"] == it["cat"]]
            others = [r for r in items if r is not it and r["cat"] != it["cat"]]
            related = diversify((same_cat + sorted(others, key=lambda r: r["score"], reverse=True))[:8])[:8]
            story_html = render_story(it, lang, related, rail, built_at)
            if it["source_id"] == "top-original" and len(re.findall(r"<h1(?:\s|>)", story_html)) != 1:
                raise RuntimeError(f"original story {it['pid']} rendered with invalid <h1> count")
            (dist / lang / "story" / story_file_name(it["title"], it["pid"])).write_text(
                story_html, encoding="utf-8")
            # Every link ever shared used the bare-pid path — keep it resolving.
            (dist / lang / "story" / f"{it['pid']}.html").write_text(
                story_redirect_stub(it, lang), encoding="utf-8")
        (dist / lang / "rss.xml").write_text(render_rss(lang, items, built_at), encoding="utf-8")
    (dist / "sitemap.xml").write_text(
        render_sitemap((("en", en_items), ("ar", ar_items)), built_at), encoding="utf-8")
    (dist / "robots.txt").write_text(ROBOTS_TXT, encoding="utf-8")
    __import__("seo_extras").write_extras(
        dist, (("en", en_items), ("ar", ar_items)), built_at, BASE_URL, HEALTH)
    __import__("longform").copy_media(dist, en_items + ar_items)
    # Front-page furniture referenced from index cards (not from any story
    # file) ships explicitly — copy_media only walks story-referenced media.
    # The ENTIRE category-cover family ships unconditionally: lede_fallback_attrs
    # embeds covers inside onerror attributes as the browser-side fallback for
    # dying remote images, and copy_media cannot see those references — a
    # missing cover there turns a reader's failed image into a 404 white card.
    _furniture = ["times-of-palestine-israel-votes-card.svg"] + sorted(
        f.name for f in (ROOT / "originals" / "media").glob("times-of-palestine-cover-*.svg"))
    for _furn in _furniture:
        _ff = ROOT / "originals" / "media" / _furn
        if _ff.is_file():
            (dist / "media").mkdir(parents=True, exist_ok=True)
            (dist / "media" / _furn).write_bytes(_ff.read_bytes())
    (dist / "index.html").write_text(REDIRECT_HTML, encoding="utf-8")
    (dist / ".nojekyll").write_text("")
    cname = ROOT / "CNAME"  # optional custom domain (e.g. timesofpalestine.com)
    if cname.exists():
        (dist / "CNAME").write_text(cname.read_text())
    qr = ROOT / "signal-qr.png"  # Signal tip-line QR shown in the tip band
    if qr.exists():
        (dist / "signal-qr.png").write_bytes(qr.read_bytes()); ob = ROOT / "og-banner.png"; ob.exists() and (dist / "og-banner.png").write_bytes(ob.read_bytes())
    fonts_src = ROOT / "fonts"  # self-hosted webfonts (Arabic: Noto Kufi Arabic, OFL)
    if fonts_src.is_dir():
        (dist / "fonts").mkdir(exist_ok=True)
        for fp in sorted(fonts_src.glob("*.woff2")):
            (dist / "fonts" / fp.name).write_bytes(fp.read_bytes())
    # Standalone static features: a top-level directory with a .static-feature
    # marker deploys verbatim at /<dir>/ (e.g. suha-arafat/). The pages inside
    # still pass the output validator like everything else in dist/.
    import shutil
    for feature in sorted(ROOT.iterdir()):
        if feature.is_dir() and (feature / ".static-feature").is_file():
            shutil.copytree(feature, dist / feature.name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".static-feature"))
    # SANAD outbreak watch (owner directive 2026-08-04): the newsroom's
    # disease monitor over this build's wire items, published as ready-made
    # case events the SANAD page pulls and the mesh then carries offline.
    try:
        _watch = __import__("outbreak_watch").watch_events(en_items + ar_items)
        if (dist / "sanad").is_dir():
            (dist / "sanad" / "watch.json").write_text(
                json.dumps({"events": _watch}, ensure_ascii=False),
                encoding="utf-8")
            print(f"  → SANAD outbreak watch: {len(_watch)} alert(s)")
    except Exception as e:   # the watch must never break the news build
        print(f"  ⚠ outbreak watch failed open: {type(e).__name__}: {e}")
    (dist / "data.json").write_text(json.dumps(
        {"builtAt": utc_iso(built_at), "en": len(en_items), "ar": len(ar_items),
         "briefs": sum(1 for i in en_items + ar_items if i.get("brief"))}, indent=2))
    # Live figures for the Gaza by the Numbers panel: the page polls this file
    # between rebuilds and animates any figure the Ministry has revised.
    _gp = __import__("gaza_panel")
    moh_payload = _gp.payload()
    if moh_payload:
        (dist / "data").mkdir(exist_ok=True)
        (dist / "data" / "gaza-numbers.json").write_text(
            json.dumps(moh_payload, ensure_ascii=False), encoding="utf-8")
        # The same ledger as CSV — the panel's "Open data" line links both.
        (dist / "data" / "gaza-numbers.csv").write_text(
            _gp.payload_csv(moh_payload), encoding="utf-8")
    (dist / "review-queue.json").write_text(
        json.dumps(sanitized_review_queue(pending), indent=2), encoding="utf-8")
    health = HEALTH.public_dict({"en": len(en_items), "ar": len(ar_items)})
    (dist / "health.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    output_errors = __import__("validate_build").validate(dist)
    if output_errors:
        raise PublishingError(
            "generated output validation failed: " + "; ".join(output_errors[:8]))
    HEALTH.checks["output_integrity"] = "ok"
    health = HEALTH.public_dict({"en": len(en_items), "ar": len(ar_items)})
    (dist / "health.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nBuilt dist/ — EN {len(en_items)} stories, AR {len(ar_items)} stories.")
    if not en_items and not ar_items:
        print("No items fetched from any feed — failing so the last good deploy stays live.")
        sys.exit(1)

if __name__ == "__main__":
    main()
