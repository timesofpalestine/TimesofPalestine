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
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from editorial import (
    apply_review_gate, classify_risk, cluster_duplicates, load_reviews,
    sanitized_review_queue,
)
from publishing import (
    BuildHealth, PublishingError, canonicalize_url, is_http_url,
    load_editorial_json, load_media_manifest, media_rights_for, parse_timestamp,
    safe_urlopen, utc_iso, validate_corrections, validate_feed_config, validate_story,
)

ROOT = Path(__file__).parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 TimesOfPalestine/1.0")
GAZA = ZoneInfo("Asia/Gaza")

# Anonymous tip line — the newsroom's Signal account (username TOP.972).
# Link decoded from the official Signal share QR; signal-qr.png in the repo root
# is the matching scannable code, copied into dist/ at build time.
SIGNAL_URL = "https://signal.me/#eu/0_b-q0RDCIq5joH5eX1lR_jVWkiLrah-MdXuqpiCawImwuEDAfdN1Z14HJk-6mRg"
SIGNAL_USERNAME = "@TOP.972"; TELEGRAM_BOT_URL = "https://t.me/TOPnewsdeskbot"; TELEGRAM_BOT_NAME = "@TOPnewsdeskbot"; swg = lambda lang: '<script async type="application/javascript" src="https://news.google.com/swg/js/v1/swg-basic.js"></script><script>(function(){const theme=(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";(self.SWG_BASIC=self.SWG_BASIC||[]).push(basicSubscriptions=>{basicSubscriptions.init({type:"NewsArticle",isPartOfType:["Product"],isPartOfProductId:"CAowqpHhCw:openaccess",clientOptions:{theme:theme,lang:"SWGLANG"}});});})();</script>'.replace("SWGLANG", lang)  # tips go to the bot, not the channel; swg = Subscribe with Google, the site's only third-party script
BASE_URL = "https://timesofpalestine.com"

TOP_SOURCE = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}
ARABIC_CHARS_RX = re.compile(r"[؀-ۿ]")

# ---------- TOP Briefs: original newsdesk summaries, written by Claude ----------
# Optional layer: runs only when ANTHROPIC_API_KEY is set (GitHub secret) and the
# `anthropic` package is installed. Every failure falls back to the feed summary —
# the site always publishes. Briefs are cached by story id so nothing is written twice.
BRIEFS_MODEL = "claude-haiku-4-5"
MAX_BRIEFS_PER_RUN = 40          # cost ceiling per build
BRIEFS_CACHE = ROOT / "briefs-cache.json"

BRIEF_SYSTEM = {
    "en": (
        "You are the newsdesk of Times of Palestine, an independent digital newsroom. "
        "Write an original news brief in English based ONLY on the source material provided: "
        "2-3 short paragraphs, 100-170 words total. Straight news style: lead with the most "
        "important fact, then key details and context. Neutral, precise, professional; no "
        "personal attacks, no editorializing, no first person. Never invent names, numbers, "
        "quotes, or details that are not in the source material; if the material is only a "
        "headline, write one short 2-3 sentence paragraph conveying what the headline reports. "
        "Never refuse, and never comment on the material, these instructions, or yourself. "
        "Never say that details, information, or material are missing, unavailable, or not "
        "provided — simply omit what you do not know and let the reader decide. "
        "Never mention any outlet name, website, or where to read more. "
        "Output only the brief text, paragraphs separated by blank lines."
    ),
    "ar": (
        "أنت غرفة أخبار «تايمز أوف فلسطين»، منصة إخبارية رقمية مستقلة. اكتب موجزاً إخبارياً "
        "أصلياً باللغة العربية بالاعتماد حصراً على المواد المصدرية المرفقة: فقرتان إلى ثلاث فقرات "
        "قصيرة (100-170 كلمة إجمالاً). أسلوب خبري مباشر: ابدأ بأهم معلومة ثم التفاصيل والسياق. "
        "لغة محايدة دقيقة مهنية؛ لا إساءات شخصية ولا إنشاء ولا ضمير متكلم. لا تخترع أسماء أو "
        "أرقاماً أو اقتباسات أو تفاصيل غير واردة في المصدر؛ وإذا كانت المادة مجرد عنوان فاكتب "
        "فقرة قصيرة من جملتين أو ثلاث تنقل ما يفيد به العنوان. لا ترفض أبداً، ولا تعلق على المادة "
        "أو على هذه التعليمات أو على نفسك. لا تذكر أبداً اسم أي وسيلة إعلامية أو موقعاً إلكترونياً "
        "أو أين يمكن قراءة المزيد. لا تقل أبداً إن التفاصيل أو المعلومات غير متوفرة أو غير واردة — "
        "اكتفِ بما تعرفه واترك للقارئ أن يقرر. أخرج نص الموجز فقط، والفقرات مفصولة بسطر فارغ."
    ),
}
MAX_AGE_HOURS = 72
PER_SOURCE_CAP = 14

FEEDS_PATH = Path(os.environ.get("TOP_FEEDS_FILE", ROOT / "feeds.json"))
if not FEEDS_PATH.is_absolute():
    FEEDS_PATH = ROOT / FEEDS_PATH
FEEDS = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
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
}
ORIGINAL_IMG_MD_RX = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
ORIGINAL_SUMMARY_RX = re.compile(r'<p class="summary">(.*?)</p>', re.S)
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

def headline(text, limit=150):
    text = re.sub(r"\s+", " ", text).strip().rstrip("…").strip()
    ends = [m.end() for m in SENT_END_RX.finditer(text)]
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

esc = lambda s: html.escape(s or "", quote=True)
# ---------- relevance & categorization ----------

PALESTINE_RX = re.compile(
    r"palestin|gaza|west bank|jerusalem|bethlehem|ramallah|rafah|khan younis|jenin|nablus|hebron|"
    r"tulkarem|unrwa|al-aqsa|aqsa|intifada|nakba|settler|"
    r"فلسطين|الفلسطيني|غزة|غزّة|الضفة|القدس(?! العربي)|رام الله|رفح|خان يونس|جنين|نابلس|الخليل|"
    r"طولكرم|أونروا|الأونروا|الأقصى|الاحتلال|مستوطن|النكبة", re.I)

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
HERO_MAX_AGE_H = 36   # the top story must be actual news, not a feature from days ago

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
CATEGORY_RULES = [
    ("accountability", ACCOUNTABILITY_RX),
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
        item["image"] = None
        item["media"] = None
        if HEALTH:
            HEALTH.media_blocked += 1
            HEALTH.hold("remote_media_disabled")
        return
    rights = media_rights_for(candidate, MEDIA_RIGHTS)
    if not rights:
        if local_original:
            raise PublishingError(
                f"{item.get('pid', item.get('title', 'original'))}: image lacks rights metadata")
        item["image"] = None
        item["media"] = None
        if HEALTH:
            HEALTH.media_blocked += 1
            HEALTH.hold("media_rights_missing")
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


def finish_item(item, feed):
    """Apply per-feed relevance filters, then categorize and score. Returns item or None."""
    if JUNK_TITLE_RX.search(item["title"]):
        return None
    # Google News indexes our own site now — never re-aggregate ourselves.
    if item["source"] in ("Times of Palestine", "تايمز أوف فلسطين") \
            or "timesofpalestine." in item["link"]:
        return None
    hay = f"{item['title']} {item['dek']} {item['link']}"
    if feed.get("filterPalestine") and not PALESTINE_RX.search(hay):
        return None
    # For general/foreign outlets and shows (Tucker Carlson, Religion News Service):
    # keep only stories with Palestine or Israel context — not their unrelated coverage.
    if feed.get("filterPalestineChristians"):
        if not (PALESTINE_RX.search(hay) or ISRAEL_CONTEXT_RX.search(hay)):
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
    item["date"] = min(item["date"], datetime.now(timezone.utc))
    item["max_age_hours"] = feed.get("maxAgeHours", MAX_AGE_HOURS)
    item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]  # stable internal page id
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

def write_brief(client, item):
    material = (f"OUTLET: {item['source']}\n"
                f"HEADLINE: {item['title']}\n"
                f"FEED SUMMARY: {item['dek'] or '(none)'}")
    system = BRIEF_SYSTEM[item["lang"]]
    if item.get("needs_translation"):  # Arabic wire copy feeding the English edition
        system += (" The source material is in Arabic. Start your response with a single line "
                   "beginning 'HEADLINE: ' giving a concise English news headline for this story, "
                   "then a blank line, then the brief in English.")
    response = client.messages.create(
        model=BRIEFS_MODEL,
        max_tokens=700,
        system=system,
        messages=[{"role": "user", "content": material}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if item.get("needs_translation") and text.startswith("HEADLINE:"):
        first, _, rest = text.partition(chr(10))
        item["title"] = truncate(first[len("HEADLINE:"):].strip(" *"), 200)
        text = rest.strip()
    if REFUSAL_RX.search(text) or len(text) <= 60:
        item["brief_refused"] = True  # the model had nothing to report — do not publish a stub
        return None
    return text
def generate_briefs(all_items):
    """Attach an original TOP Newsdesk brief to each story, cached across builds."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nBriefs: ANTHROPIC_API_KEY not set — publishing with feed summaries.")
        return "disabled"
    try:
        import anthropic
    except ImportError:
        print("\nBriefs: `anthropic` package not installed — publishing with feed summaries.")
        return "disabled"
    try:
        cache = json.loads(BRIEFS_CACHE.read_text(encoding="utf-8")) if BRIEFS_CACHE.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Briefs: cache unreadable ({type(exc).__name__}); rebuilding entries.")
        if HEALTH:
            HEALTH.checks["brief_cache"] = "degraded"
        cache = {}
    cache = {k: v for k, v in cache.items() if not REFUSAL_RX.search(v.get("brief", ""))}
    cache_dirty = False
    now_ts = datetime.now(timezone.utc).timestamp()
    for it in all_items:
        if classify_risk(it):
            # Repository originals already contain editor-authored body copy.
            if it.get("original"):
                continue
            # Sensitive aggregated items publish only the exact upstream text reviewed.
            it.pop("brief", None)
            for cache_key in (f"{it['lang']}:{it['pid']}", it["pid"]):
                if cache.pop(cache_key, None) is not None:
                    cache_dirty = True
            continue
        # Keys are lang-scoped so the same wire story can carry an Arabic brief in /ar/
        # and an English one in /en/; bare-pid entries are legacy single-language cache.
        entry = cache.get(f"{it['lang']}:{it['pid']}") or cache.get(it["pid"])
        if entry:
            it["brief"] = entry["brief"]
            if entry.get("title"):  # translated headline saved alongside the brief
                it["title"] = entry["title"]
            if classify_risk(it):
                it.pop("brief", None)
                cache.pop(f"{it['lang']}:{it['pid']}", None)
                cache.pop(it["pid"], None)
                cache_dirty = True
    todo = [i for i in sorted(
        all_items,
        key=lambda x: (
            x.get("needs_translation", False), x.get("partner", False),
            not x["dek"], x["score"]),
        reverse=True,
    ) if "brief" not in i and not classify_risk(i)][:MAX_BRIEFS_PER_RUN]
    if not todo:
        if cache_dirty:
            save_brief_cache(cache)
        print("\nBriefs: cache warm — nothing new to write.")
        return "ok"

    # Remove ALL whitespace (including pasted line-wraps) from the secret — a broken
    # key corrupts the auth header and surfaces as APIConnectionError. The log line
    # prints only length + format validity, never the key (build logs are public).
    key = re.sub(r"\s+", "", os.environ["ANTHROPIC_API_KEY"])
    print(f"Briefs: key length {len(key)}, format {'ok' if re.fullmatch(r'sk-ant-[A-Za-z0-9_-]+', key) else 'UNEXPECTED'}")
    client = anthropic.Anthropic(api_key=key)

    def safe(item):
        try:
            return write_brief(client, item)
        except Exception as e:  # any per-story failure falls back to the feed summary
            print(f"  ✗ brief failed ({item['pid']}): {type(e).__name__}")
            return None

    written = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for it, brief in zip(todo, ex.map(safe, todo)):
            if brief:
                it["brief"] = brief
                if classify_risk(it):
                    it.pop("brief", None)
                    if HEALTH:
                        HEALTH.hold("generated_brief_sensitive")
                    continue
                entry = {"brief": brief, "ts": now_ts}
                if it.get("needs_translation") and not ARABIC_CHARS_RX.search(it["title"]):
                    entry["title"] = it["title"]  # keep the English headline across builds
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


def purge_held_briefs(sensitive):
    """Remove generated prose for content that requires exact human review."""
    if not BRIEFS_CACHE.exists() or not sensitive:
        return
    try:
        cache = json.loads(BRIEFS_CACHE.read_text(encoding="utf-8"))
        changed = False
        for item in sensitive:
            for key in (f"{item['lang']}:{item['pid']}", item["pid"]):
                if key in cache:
                    del cache[key]
                    changed = True
        if changed:
            save_brief_cache(cache)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Briefs: held-entry purge failed ({type(exc).__name__}).")
        if HEALTH:
            HEALTH.checks["brief_cache"] = "degraded"


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

    rendered = __import__("longform").body_html(body)
    if "[^" in rendered:
        residue_warnings.append("unrendered footnote marker '[^'")
    if "![" in rendered:
        residue_warnings.append("unrendered image markdown '!['")
    if "**" in rendered:
        residue_warnings.append("unrendered bold marker '**'")
    if re.search(r'<p class="summary">\s*#', rendered):
        residue_warnings.append("line-initial heading marker '#' fell through into paragraph")
    for p in ORIGINAL_SUMMARY_RX.findall(rendered):
        if "|" in strip_html(p):
            residue_warnings.append("pipe table residue '|' remained inside paragraph")
            break

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

    if errors:
        raise PublishingError(f"{path.name}: {'; '.join(errors)}")
    if residue_warnings:
        raise PublishingError(
            f"{path.name}: unsafe rendered markup: {'; '.join(residue_warnings)}")


def load_originals(lang):
    if os.environ.get("TOP_SKIP_ORIGINALS") == "1":
        return []
    orig = ROOT / "originals"
    if not orig.is_dir():
        return []
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
        validate_original(path, meta, body, lang, now, date)
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
        }
        item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]
        attach_media(item, meta.get("image") or None, local_original=True)
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

def build_lang(lang):
    print(f"\nFetching {lang.upper()} feeds…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda f: fetch_feed(f, lang), FEEDS[lang]))
    results.append(load_originals(lang))
    items, removed = cluster_duplicates([i for r in results for i in r])
    if HEALTH:
        HEALTH.deduplicated += removed
    caps = {f["id"]: f.get("cap", PER_SOURCE_CAP) for f in FEEDS[lang]}; caps["top-original"] = 200
    per_source, capped = {}, []
    for it in items:
        per_source[it["source_id"]] = per_source.get(it["source_id"], 0) + 1
        if per_source[it["source_id"]] <= caps.get(it["source_id"], PER_SOURCE_CAP):
            capped.append(it)
    print(f"  → {len(capped)} items after dedupe/cap")
    return capped
# ---------- localization ----------

STR = {
    "en": {
        "dir": "ltr", "lang": "en",
        "site_name": "Times of Palestine",
        "masthead_top": "TIMES", "masthead_bottom": "OF PALESTINE",
        "tagline": "No allegiance except to the truth — and to the people of Palestine.",
        "kicker": "Every outlet · Every story · No censorship",
        "breaking": "BREAKING", "latest": "The Latest",
        "updated": "Updated", "tz": "Jerusalem time",
        "switch_lang": "العربية", "switch_href": "../ar/",
        "hero_label": "TOP STORY",
        "sections": {"gaza": "Gaza", "westbank": "West Bank & Jerusalem",
                     "humans": "Real Lives",
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
        "attribution": ("Headlines and summaries are aggregated automatically and link directly to "
                        "the original publishers, who retain all rights to their work."),
        "footer_lang": "اقرأ بالعربية ←",
        "research_kicker": "FEATURED REPORT",
        "title_suffix": "Independent Palestine News",
        "read_original": "Read the full story at",
        "photo_via": "Photo via",
        "byline": "By TOP Newsdesk",
        "kind_original": "Original Reporting", "kind_brief": "TOP News Brief",
        "kind_curated": "Curated Summary", "based_on": "Based on reporting by",
        "keep_reading": "Keep Reading",
        "back_home": "← All the news",
        "summary_note": "Summary curated by Times of Palestine. The full story belongs to its publisher.",
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
        "masthead_top": "تايمز أوف", "masthead_bottom": "فلسطين",
        "tagline": "لا ولاء إلا للحقيقة — ولشعب فلسطين.",
        "kicker": "كل المصادر · كل الأخبار · بلا رقابة",
        "breaking": "عاجل", "latest": "آخر الأخبار",
        "updated": "آخر تحديث", "tz": "بتوقيت القدس",
        "switch_lang": "English", "switch_href": "../en/",
        "hero_label": "الخبر الأبرز",
        "sections": {"gaza": "غزة", "westbank": "الضفة والقدس",
                     "humans": "حكايات فلسطينية",
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
        "attribution": "تُجمَع العناوين والملخصات تلقائياً وتُحيل مباشرة إلى الناشرين الأصليين الذين يحتفظون بكامل حقوقهم.",
        "footer_lang": "→ Read in English",
        "research_kicker": "تقرير مميز",
        "title_suffix": "أخبار فلسطين المستقلة",
        "read_original": "اقرأ المادة كاملة في",
        "photo_via": "الصورة عبر",
        "byline": "غرفة أخبار «تايمز أوف فلسطين»",
        "kind_original": "تقرير أصلي", "kind_brief": "موجز تايمز أوف فلسطين",
        "kind_curated": "ملخص محرَّر", "based_on": "استناداً إلى تقرير",
        "keep_reading": "تابع القراءة",
        "back_home": "كل الأخبار ←",
        "summary_note": "الملخص من إعداد «تايمز أوف فلسطين». المادة الكاملة ملك لناشرها الأصلي.",
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
SECTION_ORDER = {
    "en": ["research", "gaza", "westbank", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news"],
    "ar": ["research", "gaza", "westbank", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news"],
}
FOCUS_SECTIONS = {"research", "diaspora", "arts", "sports", "accountability", "bitcoin", "social"}  # shown even with one story

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

# ---------- CSS (shared by both languages; logical properties handle RTL) ----------
CSS = """
:root{
  --red:#C8102E; --green:#00753A; --black:#0b0b0c; --ink:#141419; --muted:#595962;
  --paper:#faf9f4; --card:#ffffff; --line:#e6e3da; --line-dark:#c9c5b8;
  --serif:"Source Serif 4",Georgia,serif; --sans:"Libre Franklin",-apple-system,Helvetica,Arial,sans-serif;
  --max:1180px;
}
[lang=ar]{ --serif:"Cairo",Tahoma,sans-serif; --sans:"Cairo",Tahoma,sans-serif; }
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}
.wrap{max-width:var(--max);margin-inline:auto;padding-inline:20px}

.topbar{background:var(--black);color:#cfcfd6;font-size:.75rem}
.topbar .wrap{display:flex;align-items:center;gap:1rem;min-height:36px;flex-wrap:wrap}
.topbar .date{color:#fff;font-weight:600;letter-spacing:.02em}
.topbar .upd{display:flex;align-items:center;gap:.4rem}
.topbar .dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.35}}
.topbar .lang{margin-inline-start:auto;color:#fff;font-weight:700;border:1px solid #3a3a42;padding:.2rem .7rem;border-radius:2px}
.topbar .lang:hover{background:var(--red);border-color:var(--red)}
.ticker{background:var(--red);color:#fff;overflow:hidden;display:flex;align-items:stretch}
.ticker .label{background:var(--black);font-weight:800;letter-spacing:.12em;font-size:.72rem;display:flex;align-items:center;padding:.45rem .9rem;flex-shrink:0;z-index:2}
[lang=ar] .ticker .label{letter-spacing:.02em}
.ticker .rail{overflow:hidden;flex:1;display:flex;align-items:center}
.ticker .track{display:flex;gap:2.5rem;white-space:nowrap;animation:tick 80s linear infinite;padding-inline:1.5rem}
[dir=rtl] .ticker .track{animation-name:tick-rtl}
.ticker:hover .track{animation-play-state:paused}
.ticker a{font-size:.82rem;font-weight:600}
.ticker a::before{content:"●";color:rgba(255,255,255,.55);margin-inline-end:.7rem;font-size:.55rem;vertical-align:2px}
@keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@keyframes tick-rtl{from{transform:translateX(0)}to{transform:translateX(50%)}}

.masthead{background:var(--card);border-bottom:1px solid var(--line);text-align:center;padding:1.5rem 0 1.1rem}
.masthead .logotype{display:inline-flex;align-items:center}
.masthead .wrap::after{content:"";display:block;margin:.85rem auto 0;width:112px;height:4px;background:linear-gradient(90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
[dir=rtl] .masthead .wrap::after{background:linear-gradient(-90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
.masthead h1,.masthead .wordmark{font-family:var(--serif);font-weight:900;line-height:1;letter-spacing:-.01em;color:var(--black);font-size:clamp(1.6rem,4vw,2.6rem);white-space:nowrap}
.masthead h1 .l2,.masthead .wordmark .l2{color:var(--red)}
[lang=ar] .masthead h1,[lang=ar] .masthead .wordmark{font-family:"Amiri",serif;letter-spacing:0;font-weight:700;line-height:1.25}
.masthead.compact{padding:.9rem 0 .7rem}
.masthead.compact h1,.masthead.compact .wordmark{font-size:1.35rem}

nav.sections{position:sticky;top:0;background:var(--black);z-index:50;box-shadow:0 2px 10px rgba(0,0,0,.25)}
nav.sections .wrap{display:flex;flex-wrap:wrap;gap:0 .1rem;padding-block:.2rem}
nav.sections a{color:#e8e8ee;font-size:.73rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:.5rem .6rem;white-space:nowrap;border-bottom:3px solid transparent}
[lang=ar] nav.sections a{letter-spacing:0;font-size:.8rem}
nav.sections a:hover{color:#fff;border-color:var(--red)}
nav.sections a.home{color:#f93549}

.hero-zone{display:grid;grid-template-columns:minmax(0,2.05fr) minmax(0,1fr);gap:2rem;padding-block:1.8rem}
.hero{border-inline-end:1px solid var(--line);padding-inline-end:2rem}
.hero .label{color:var(--red);font-size:.68rem;font-weight:800;letter-spacing:.2em;margin-bottom:.6rem}
[lang=ar] .hero .label{letter-spacing:.03em;font-size:.8rem}
.hero img{aspect-ratio:16/9;object-fit:cover;width:100%;background:#ddd}
.hero h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.5rem,3vw,2.3rem);line-height:1.13;margin-top:1rem}
[lang=ar] .hero h2{line-height:1.5;font-weight:800}
.hero h2 a:hover{color:var(--red)}
.hero .dek{margin-top:.7rem;font-size:1.02rem;color:#3c3c44;font-family:var(--serif);line-height:1.55}
[lang=ar] .hero .dek{line-height:1.8}
.photocredit{font-size:.66rem;color:#9a9aa2;margin-top:.35rem}
.meta{display:flex;align-items:center;gap:.6rem;margin-top:.8rem;font-size:.74rem;color:var(--muted)}
.meta .src{color:var(--green);font-weight:800;text-transform:uppercase;letter-spacing:.06em}
[lang=ar] .meta .src{letter-spacing:0}
.meta .t{font-weight:600}
.hero-sub{margin-top:1.6rem;padding-top:1.4rem;border-top:1px solid var(--line);display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
.hero-sub article .chip{font-size:.64rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.08em}
[lang=ar] .hero-sub article .chip{letter-spacing:0;font-size:.72rem}
.hero-sub article h3{font-family:var(--serif);font-weight:700;font-size:1.05rem;line-height:1.3;margin-top:.25rem}
[lang=ar] .hero-sub article h3{line-height:1.6}
.hero-sub article h3 a:hover{color:var(--red)}
.hero-sub article .t{font-size:.68rem;color:var(--muted);font-weight:600;margin-top:.3rem}

.latest h2{font-size:.8rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:var(--black);border-bottom:3px solid var(--red);padding-bottom:.5rem;display:flex;align-items:center;gap:.5rem}
[lang=ar] .latest h2{letter-spacing:.02em;font-size:.95rem}
.latest h2::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--red);animation:pulse 2s infinite}
.latest ol{list-style:none}
.latest li{padding-block:.8rem;border-bottom:1px solid var(--line)}
.latest .t{color:var(--red);font-weight:800;font-size:.68rem;letter-spacing:.05em;display:block;margin-bottom:.2rem}
[lang=ar] .latest .t{letter-spacing:0;font-size:.75rem}
.latest h3{font-size:.92rem;font-weight:600;line-height:1.35}
[lang=ar] .latest h3{line-height:1.65;font-size:.98rem}
.latest h3 a:hover{color:var(--red)}
.latest .s{font-size:.68rem;color:var(--muted);font-weight:600;text-transform:uppercase;margin-top:.2rem;display:block}
[lang=ar] .latest .s{text-transform:none;font-size:.75rem}

section.block{padding-block:1.6rem;border-top:1px solid var(--line-dark)}
.sec-head{display:flex;align-items:baseline;gap:.8rem;margin-bottom:1.2rem}
.sec-head::before{content:"";width:12px;height:12px;background:var(--green);align-self:center}
.sec-head.focus::before{background:var(--red)}
.sec-head h2{font-family:var(--serif);font-weight:900;font-size:1.45rem;color:var(--black)}
[lang=ar] .sec-head h2{font-weight:700}
.sec-head .rule{flex:1;height:1px;background:var(--line-dark)}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.4rem}.grid.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.card img{aspect-ratio:16/10;object-fit:cover;width:100%;background:#e8e6df;margin-bottom:.7rem;transition:opacity .18s}
.card:hover img,.rowcard:hover img{opacity:.9}
.card:hover h3 a,.rowcard:hover h3 a{color:var(--red)}
.card .ph{aspect-ratio:16/10;margin-bottom:.7rem;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}
.card .ph svg{width:44px;height:44px;opacity:.9}
.card .chip{font-size:.64rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.08em}
[lang=ar] .card .chip{letter-spacing:0;font-size:.72rem}
.card h3{font-family:var(--serif);font-weight:700;font-size:1.02rem;line-height:1.3;margin-top:.3rem}
[lang=ar] .card h3{line-height:1.6}
.card h3 a:hover{color:var(--red)}
.card .t{font-size:.68rem;color:var(--muted);font-weight:600;margin-top:.4rem}
[lang=ar] .card .t{font-size:.75rem}

/* sparse sections (<4 stories): full-width horizontal rows — no half-empty grids */
.rowlist{display:flex;flex-direction:column}
.rowcard{display:flex;gap:1.3rem;align-items:flex-start;padding-block:1rem;border-bottom:1px solid var(--line)}
.rowcard:last-child{border-bottom:none}
.rowcard>a:first-child,.rowcard>.ph{flex-shrink:0}
.rowcard img,.rowcard .ph{width:220px;aspect-ratio:16/10;object-fit:cover;background:#e8e6df;margin:0;display:flex;align-items:center;justify-content:center}
.rowcard .ph{background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}
.rowcard .ph svg{width:40px;height:40px;opacity:.9}
.rowcard h3{font-family:var(--serif);font-weight:700;font-size:1.15rem;line-height:1.3;margin-top:.25rem}
[lang=ar] .rowcard h3{line-height:1.6}
.rowcard h3 a:hover{color:var(--red)}
.rowcard .chip{font-size:.64rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.08em}
[lang=ar] .rowcard .chip{letter-spacing:0;font-size:.72rem}
.rowcard .t{font-size:.68rem;color:var(--muted);font-weight:600;margin-top:.35rem}

/* featured research report — the "news before it becomes news" card */
.research-feat{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:0;background:var(--card);border:1px solid var(--line-dark);border-inline-start:5px solid var(--red);margin-bottom:1.6rem;box-shadow:0 2px 14px rgba(0,0,0,.05)}
.research-feat .body{padding:1.6rem 1.8rem}
.research-feat .kick{color:var(--red);font-size:.66rem;font-weight:800;letter-spacing:.2em;margin-bottom:.55rem}
[lang=ar] .research-feat .kick{letter-spacing:.04em;font-size:.78rem}
.research-feat h3{font-family:var(--serif);font-weight:900;font-size:clamp(1.25rem,2.2vw,1.7rem);line-height:1.18}
[lang=ar] .research-feat h3{font-weight:700;line-height:1.5}
.research-feat h3 a:hover{color:var(--red)}
.research-feat .dek{margin-top:.8rem;font-family:var(--serif);font-size:.97rem;line-height:1.6;color:#33333b}
[lang=ar] .research-feat .dek{line-height:1.85}
.research-feat img{width:100%;height:100%;object-fit:cover;background:#e8e6df;min-height:240px}
.research-feat .noimg{background:linear-gradient(135deg,#0b0b0c 0 55%,#14241b 55% 100%);display:flex;align-items:center;justify-content:center;min-height:240px}
.research-feat .noimg span{font-family:var(--serif);color:#3fd07c;font-size:3.2rem;font-weight:900}

section.opinion{background:#f1efe8;border-top:4px solid var(--black);padding-block:1.8rem;margin-block:1.2rem}
section.opinion .sec-head::before{background:var(--red)}
.op-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.6rem}
.op-card{border-inline-start:3px solid var(--red);padding-inline-start:1rem}
.op-card .q{font-family:var(--serif);font-size:2.2rem;color:var(--red);line-height:.6;display:block;margin-bottom:.4rem}
.op-card h3{font-family:var(--serif);font-style:italic;font-weight:700;font-size:1.12rem;line-height:1.35}
[lang=ar] .op-card h3{line-height:1.65;font-style:normal}
.op-card h3 a:hover{color:var(--red)}

section.tipband{background:var(--black);color:#fff;margin-block:1.2rem;border-block:4px solid var(--green);position:relative;overflow:hidden}
section.tipband::after{content:"";position:absolute;inset-block:0;inset-inline-end:-60px;width:280px;background:linear-gradient(120deg,transparent 0 40%,rgba(0,122,61,.35) 40% 55%,rgba(206,17,38,.30) 55% 70%,transparent 70%);pointer-events:none}
.tipband .wrap{display:flex;align-items:center;gap:2rem;padding-block:1.8rem;flex-wrap:wrap;position:relative;z-index:1}
.tipband .lock{flex-shrink:0}
.tipband .txt{flex:1;min-width:260px}
.tipband .kick{color:#3fd07c;font-size:.68rem;font-weight:800;letter-spacing:.22em;margin-bottom:.35rem}
[lang=ar] .tipband .kick{letter-spacing:.04em;font-size:.8rem}
.tipband h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.25rem,2.4vw,1.7rem);line-height:1.2}
[lang=ar] .tipband h2{font-weight:700;line-height:1.5}
.tipband .sub{color:#c9c9d2;font-size:.9rem;margin-top:.45rem;max-width:56ch;line-height:1.6}
.tipband .cta{flex-shrink:0;text-align:center}
.tipband .btn{display:inline-block;background:#2f6bff;background:var(--green);color:#fff;font-weight:800;font-size:.92rem;padding:.85rem 1.6rem;border-radius:3px;border:2px solid #3fd07c;transition:.15s}
.tipband .btn:hover{background:#3fd07c;color:var(--black)}
.tipband .tgbtn{display:inline-block;margin-top:.7rem;border:1px solid #3a3a42;color:#cfe9ff;font-weight:700;font-size:.82rem;padding:.5rem 1rem;border-radius:3px}.tipband .tgbtn:hover{background:#229ED9;border-color:#229ED9;color:#fff}.tipband .micro{display:block;margin-top:.55rem;font-size:.72rem;color:#8f8f99;font-style:italic}
[lang=ar] .tipband .micro{font-style:normal}
.tipband .qrbox{background:#fff;padding:.55rem .55rem .45rem;border-radius:8px;display:inline-block;margin-top:.8rem}
.tipband .qrbox img{width:104px;height:104px;display:block;image-rendering:pixelated}
.tipband .qrbox span{display:block;font-size:.7rem;font-weight:800;color:#111;margin-top:.25rem;text-align:center;direction:ltr}
.tipband .scanhint{display:block;margin-top:.4rem;font-size:.68rem;color:#8f8f99}
.tipband .safety{flex-basis:100%;font-size:.7rem;color:#77777f;border-top:1px solid #26262c;padding-top:.7rem}
nav.sections a.tip{color:#3fd07c;border-color:#3fd07c}

/* story page */
.story{max-width:780px;margin-inline:auto;padding:2rem 20px 1rem}
.story .kick{color:var(--red);font-size:.7rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;margin-bottom:.7rem}
[lang=ar] .story .kick{letter-spacing:.03em;font-size:.82rem}
.story h1{font-family:var(--serif);font-weight:900;font-size:clamp(1.6rem,3.6vw,2.5rem);line-height:1.15}
[lang=ar] .story h1{font-weight:800;line-height:1.5}
.story .meta{margin-top:1rem;font-size:.8rem}
.story div.lede{width:100%;aspect-ratio:16/9;margin-top:1.4rem;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}.story div.lede svg{width:64px;height:64px;opacity:.9}.story img.lede{width:100%;height:auto;max-height:68vh;object-fit:cover;object-position:top;background:#e8e6df;margin-top:1.4rem}
.story .kind{margin-top:1.4rem;display:inline-block;background:var(--red);color:#fff;font-size:.66rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;padding:.25rem .6rem;border-radius:2px}[lang=ar] .story .kind{letter-spacing:0;font-size:.78rem}.story .based{display:block;margin-top:.3rem;font-weight:600;color:var(--muted);text-transform:none;letter-spacing:0}.story .byline{margin-top:.7rem;font-size:.74rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.1em}
[lang=ar] .story .byline{letter-spacing:0;text-transform:none;font-size:.85rem}
.story .summary{margin-top:1rem;font-family:var(--serif);font-size:1.13rem;line-height:1.7;color:#26262e}
.story .summary+.summary{margin-top:.9rem}
[lang=ar] .story .summary{line-height:2}
.story .cta{margin-top:1.8rem;text-align:center;border-block:1px solid var(--line);padding-block:1.5rem}
.story .cta a{display:inline-block;background:var(--red);color:#fff;font-weight:800;font-size:1rem;padding:.9rem 2rem;border-radius:3px}
.story .cta a:hover{background:#a50d1e}
.story .note{margin-top:.8rem;font-size:.72rem;color:var(--muted)}
.keep{padding-block:1.8rem}
.backbar{background:var(--black);display:flex;justify-content:space-between;align-items:center}
.backbar a{display:block;max-width:780px;margin-inline:auto;padding:.6rem 20px;color:#fff;font-size:.8rem;font-weight:700}
.backbar a:hover{color:#f93549}

footer{background:var(--black);color:#b9b9c2;margin-top:2.5rem;padding-block:2.5rem;font-size:.85rem}
footer .cols{display:grid;grid-template-columns:1.4fr 1fr;gap:3rem}
footer h2{color:#fff;font-family:var(--serif);font-size:1.2rem;margin-bottom:.8rem;display:flex;align-items:center;gap:.6rem}
footer h2::before{content:"";width:10px;height:10px;background:var(--red)}
footer .mission{line-height:1.75}
[lang=ar] footer .mission{line-height:2}
footer ul{list-style:none;columns:2;gap:2rem}
footer li{margin-bottom:.45rem}
footer a{color:#e6e6ec;font-weight:600}
footer a:hover{color:#fff;text-decoration:underline}
footer .legal{margin-top:2rem;padding-top:1.2rem;border-top:1px solid #2a2a30;font-size:.72rem;color:#8b8b94;display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
footer .flagline{height:4px;background:linear-gradient(90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%);border-top:4px solid var(--red);max-width:200px;margin-bottom:1.5rem}
[dir=rtl] footer .flagline{background:linear-gradient(-90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%)}@media (prefers-color-scheme:dark){:root{--paper:#101013;--card:#16161a;--ink:#e9e9ef;--muted:#a0a0aa;--line:#26262c;--line-dark:#3a3a42}.masthead h1,.masthead .wordmark,.sec-head h2,.latest h2,.story h1,.hero h2,.card h3,.rowcard h3,.hero-sub article h3,.research-feat h3,.op-card h3{color:var(--ink)}.hero .dek{color:#c5c5cf}.story .summary{color:#d6d6de}.research-feat .dek{color:#c5c5cf}section.opinion{background:#17171c}.card img,.hero img,.rowcard img,.story img.lede{opacity:.92}/* The flag palette never changes: fills, rules, markers and the masthead stay true brand red and green in dark mode. Only small red/green TEXT lifts to a lighter tint of the SAME hue, because #C8102E on near-black is 3.2:1 — fine for large type and graphics, unreadable at .66rem. */.hero .label,.latest .t,.research-feat .kick,.story .kick,.op-card .q,.hero h2 a:hover,.card h3 a:hover,.rowcard h3 a:hover,.latest h3 a:hover,.op-card h3 a:hover,.research-feat h3 a:hover,.hero-sub article h3 a:hover{color:#f93549}.meta .src,.card .chip,.rowcard .chip,.hero-sub article .chip{color:#3fd07c}}@media (prefers-reduced-motion:reduce){.ticker .track{animation:none}.topbar .dot,.latest h2::before{animation:none}}.skiplink{position:absolute;inset-inline-start:-999px;top:0;background:var(--red);color:#fff;padding:.6rem 1rem;z-index:99;font-weight:800}.skiplink:focus{inset-inline-start:0}.share{margin-top:1.2rem;display:flex;gap:.6rem;flex-wrap:wrap}.share span{font-size:.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;align-self:center}.share a{border:1px solid var(--line-dark);padding:.35rem .8rem;border-radius:3px;font-size:.8rem;font-weight:700}.share a:hover{background:var(--red);color:#fff;border-color:var(--red)}
.corroboration{margin-top:1rem;font-size:.85rem;color:var(--muted);line-height:1.6}.corroboration a{text-decoration:underline}
.revisions{margin-top:2rem;padding:1rem 1.2rem;border:1px solid var(--line-dark);background:var(--card)}.revisions h2{font-family:var(--serif);font-size:1.1rem}.revisions ol{margin:.7rem 0 0;padding-inline-start:1.2rem}.revisions li{margin-top:.45rem;font-size:.86rem;line-height:1.6}.revisions time{font-variant-numeric:tabular-nums;color:var(--muted)}
.social-note{margin:-.5rem 0 1.2rem;font-size:.9rem;color:var(--muted);max-width:75ch}.social-note a{color:var(--green);font-weight:700}
.footer-contact{margin-top:.9rem}.footer-contact.secondary{margin-top:.5rem}.contact-id{direction:ltr;display:inline-block;margin-inline-start:.6rem;color:#8f8f94}
.about-section{font-family:var(--serif);font-size:1.25rem;margin-top:1.6rem}.about-telegram{margin-top:.9rem}.about-telegram a{font-weight:700;color:var(--green)}

@media(max-width:700px){nav.sections .wrap{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}nav.sections .wrap::after{content:"";position:sticky;inset-inline-end:0;min-width:26px;margin-inline-start:-26px;background:linear-gradient(to left,var(--black),transparent);pointer-events:none;flex-shrink:0}[dir=rtl] nav.sections .wrap::after{background:linear-gradient(to right,var(--black),transparent)}} @media(max-width:960px){
  .research-feat{grid-template-columns:1fr}
  .research-feat img,.research-feat .noimg{min-height:180px;order:-1}
  .hero-zone{grid-template-columns:1fr}
  .hero{border-inline-end:none;padding-inline-end:0}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .rowcard img,.rowcard .ph{width:150px}
  .op-grid{grid-template-columns:1fr}
  footer .cols{grid-template-columns:1fr}
}
@media(max-width:560px){
  .grid{grid-template-columns:1fr}
  .hero-sub{grid-template-columns:1fr}
  .rowcard img,.rowcard .ph{width:110px}
  footer ul{columns:1}
}
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

FONTS = {
    "en": ("https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;600;700;800"
           "&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;"
           "0,8..60,700;0,8..60,900;1,8..60,700&display=swap"),
    "ar": ("https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900"
           "&display=swap"),
}

# ---------- components ----------

def href(it, pfx):
    """Internal story-page URL — readers stay on the site; the source link lives on the story page."""
    return f"{pfx}{it['pid']}.html"

def meta_line(it, lang):
    source = (f'<span class="src">{esc(it["source"])}</span>' if it.get("original")
              else f'<a class="src" href="{esc(it["source_url"])}" target="_blank" '
                   f'rel="noopener">{esc(it["source"])}</a>')
    return (f'<p class="meta">{source}'
            f'<span class="t">{time_ago(it["date"], lang)}</span></p>')


def media_credit(it, lang):
    media = it.get("media")
    if not media:
        return ""
    label = "حقوق الصورة" if lang == "ar" else "Image credit"
    license_html = ""
    if media.get("licenseUrl"):
        license_label = "الترخيص" if lang == "ar" else "License"
        license_html = (
            f' · <a href="{esc(media["licenseUrl"])}" target="_blank" '
            f'rel="license noopener">{license_label}</a>')
    return f'<p class="photocredit">{label}: {esc(media["credit"])}{license_html}</p>'

def card_media(it, pfx):
    """Image if we have one; otherwise a branded flag panel — never an empty column."""
    if it["image"]:
        return f'<a href="{href(it, pfx)}"><img src="{esc(it["image"])}" alt="{esc(it["title"])}" loading="lazy"></a>'
    return f'<a href="{href(it, pfx)}"><div class="ph">{FLAG_SVG}</div></a>'

def card(it, lang, pfx):
    # Uniform card: headline, source, time. Summaries belong to the hero, the
    # featured report, and the story pages — mixed previews in a grid look broken.
    return (f'<article class="card">{card_media(it, pfx)}'
            f'<span class="chip">{esc(it["source"])}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'<p class="t">{time_ago(it["date"], lang)}</p></article>')

def rowcard(it, lang, pfx):
    return (f'<article class="rowcard">{card_media(it, pfx)}'
            f'<div><span class="chip">{esc(it["source"])}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'<p class="t">{time_ago(it["date"], lang)}</p></div></article>')

def op_card(it, lang, pfx):
    return (f'<article class="op-card"><span class="q">“</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'{meta_line(it, lang)}</article>')

def sub_item(it, lang, pfx):
    return (f'<article><span class="chip">{esc(it["source"])}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'<p class="t">{time_ago(it["date"], lang)}</p></article>')

def latest_item(it, lang, pfx):
    return (f'<li><span class="t">{time_ago(it["date"], lang)}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'<span class="s">{esc(it["source"])}</span></li>')

# ---------- page ----------
def render_page(lang, items, built_at):
    t = STR[lang]
    order = SECTION_ORDER[lang]
    by_score = sorted(items, key=lambda i: i["score"], reverse=True)  # editorial ranking
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

    def hero_ok(i, max_age=HERO_MAX_AGE_H):
        return (bool(i["image"]) and len(i["title"]) > 30
                and i["cat"] not in ("social", "research", "opinion", "culture")
                and PALESTINE_RX.search(f"{i['title']} {i['dek']}")  # the top story IS Palestine
                and not REVIEWISH_RX.search(i["title"])
                and (now - i["date"]).total_seconds() / 3600 <= max_age)

    # Freshness-weighted hero ranking: a strong new story overtakes yesterday's
    # boosted one, so the top of the page visibly rotates through the day.
    def hero_rank(i):
        age = (now - i["date"]).total_seconds() / 3600
        return i["score"] + max(0.0, HERO_MAX_AGE_H - age) * 0.9

    hero_pool = sorted(items, key=hero_rank, reverse=True)
    heroes = (take(hero_pool, hero_ok, 1)
              or take(hero_pool, lambda i: hero_ok(i, max_age=MAX_AGE_HOURS), 1)
              or take(by_score, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research")
                      and PALESTINE_RX.search(f"{i['title']} {i['dek']}"), 1)
              or take(by_score, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research"), 1))
    hero = heroes[0] if heroes else None
    hero_subs = take(by_score, lambda i: i["cat"] not in ("opinion", "social", "research", "bitcoin"), 4)
    # Latest rail and breaking ticker: chronological, Palestine coverage first.
    # The rail is an index — it lists stories without claiming them from sections.
    def palestine(i):
        return bool(PALESTINE_RX.search(f"{i['title']} {i['dek']}"))
    latest = [i for i in items if id(i) not in used and i["cat"] != "social" and palestine(i)][:10]
    rail_ids = {id(i) for i in latest}
    latest += [i for i in items if id(i) not in used and i["cat"] != "social"
               and id(i) not in rail_ids][:10 - len(latest)]
    pal_news = [i for i in items if i["cat"] != "social" and palestine(i)]
    ticker_items = (pal_news or [i for i in items if i["cat"] != "social"])[:6]

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

    def visible(k):
        return len(sections[k]) >= (1 if k in FOCUS_SECTIONS else 2)
    nav_links = "".join(f'<a href="#{k}">{t["sections"][k]}</a>' for k in order if visible(k))

    def research_featured(it):
        media = (f'<a href="{href(it, P)}"><img src="{esc(it["image"])}" alt="{esc(it["title"])}" loading="lazy"></a>'
                 if it["image"] else '<div class="noimg"><span>§</span></div>')
        return (f'<article class="research-feat"><div class="body">'
                f'<p class="kick">{t["research_kicker"]}</p>'
                f'<h3><a href="{href(it, P)}">{esc(it["title"])}</a></h3>'
                f'<p class="dek">{esc(it["dek"])}</p>{meta_line(it, lang)}'
                f'</div>{media}</article>')

    section_blocks = ""
    for k in order:
        if k == "opinion" or not visible(k):
            continue
        pool = sections[k][:8]
        featured = ""
        if k == "research":  # lead report gets the full featured-summary treatment
            featured, pool = research_featured(pool[0]), pool[1:]
        if not pool:
            grid = ""
        elif len(pool) == 1:  # a lone story reads better full width than as an orphan card
            grid = f'<div class="rowlist">{"".join(rowcard(it, lang, P) for it in pool)}</div>'
        else:
            cols = f" g{min(len(pool), 4)}"; grid = f'<div class="grid{cols}">{"".join(card(it, lang, P) for it in pool)}</div>'
        focus_cls = " focus" if k in FOCUS_SECTIONS else ""
        section_blocks += (f'<section class="block" id="{k}"><div class="wrap">'
                           f'<div class="sec-head{focus_cls}"><h2>{t["sections"][k]}</h2><span class="rule"></span></div>'
                           + (('<p class="social-note">' + ("تقارير عامة من صحفيين مواطنين وشهود على الأرض. لا يُنشر أي تقرير حساس قبل موافقة محرر بشري على نسخته المحددة. " if lang == "ar" else "Public dispatches from citizen journalists and witnesses. Sensitive reports publish only after a human editor approves the exact version. ") + '<a href="#tips">' + ("أرسل تقريرك عبر خط «سيغنال» الآمن ←" if lang == "ar" else "Send yours via the secure Signal line →") + "</a></p>") if k == "social" else "") + f'{featured}{grid}</div></section>')

    opinion_block = ""
    if len(sections["opinion"]) >= 2:
        ops = "".join(op_card(it, lang, P) for it in sections["opinion"][:6])
        opinion_block = (f'<section class="opinion" id="opinion"><div class="wrap">'
                         f'<div class="sec-head"><h2>{t["sections"]["opinion"]}</h2><span class="rule"></span></div>'
                         f'<div class="op-grid">{ops}</div></div></section>')

    hero_html = ""
    if hero:
        hero_dek = f'<p class="dek">{esc(hero["dek"])}</p>' if hero["dek"] else ""
        hero_html = (f'<p class="label">{t["hero_label"]}</p>'
                     f'<a href="{href(hero, P)}"><img src="{esc(hero["image"])}" alt="{esc(hero["title"])}"></a>'
                     f'{media_credit(hero, lang)}'
                     f'<h2><a href="{href(hero, P)}">{esc(hero["title"])}</a></h2>'
                     f'{hero_dek}{meta_line(hero, lang)}')

    hero_subs_html = "".join(sub_item(it, lang, P) for it in hero_subs)
    latest_html = "".join(latest_item(it, lang, P) for it in latest)
    gaza_panel = __import__("gaza_panel").panel(lang); tips_band = (
        f'<section class="tipband" id="tips"><div class="wrap">{LOCK_SVG}'
        f'<div class="txt"><p class="kick">{t["tips_kicker"]}</p>'
        f'<h2>{t["tips_title"]}</h2><p class="sub">{t["tips_sub"]}</p></div>'
        f'<div class="cta"><a class="btn" href="{SIGNAL_URL}" target="_blank" rel="noopener">{t["tips_cta"]}</a>'
        f'<span class="micro">{t["tips_micro"]}</span>'
        f'<a class="tgbtn" href="{TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{t["tips_tg"]} → {TELEGRAM_BOT_NAME}</a>'
        f'<span class="micro">{t["tips_tg_note"]}</span>'
        f'<span class="scanhint">{t["tips_scan"]}</span>'
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
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 46'><rect width='46' height='15.3' fill='%230b0b0c'/><rect y='15.3' width='46' height='15.3' fill='%23fff'/><rect y='30.6' width='46' height='15.4' fill='%23007A3D'/><path d='M0 0 L21 23 L0 46 Z' fill='%23CE1126'/></svg>"><link rel="manifest" href="/manifest.json"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js")</script>
<title>{t['site_name']} — {t['title_suffix']}</title>
<meta name="description" content="{esc(t['mission'][:155])}">
<link rel="canonical" href="{BASE_URL}/{lang}/">
<link rel="alternate" hreflang="en" href="{BASE_URL}/en/">
<link rel="alternate" hreflang="ar" href="{BASE_URL}/ar/">
<link rel="alternate" hreflang="x-default" href="{BASE_URL}/en/">
<link rel="alternate" type="application/rss+xml" title="{t['site_name']}" href="{BASE_URL}/{lang}/rss.xml">
<link rel="alternate" type="application/feed+json" title="{t['site_name']}" href="{BASE_URL}/{lang}/feed.json">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{t['site_name']} — {t['title_suffix']}">
<meta property="og:description" content="{esc(t['mission'][:155])}">
<meta property="og:url" content="{BASE_URL}/{lang}/">
<meta property="og:image" content="{BASE_URL}/og-banner.png"><meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"NewsMediaOrganization","name":"{t['site_name']}","url":"{BASE_URL}/{lang}/","sameAs":["{BASE_URL}/en/","{BASE_URL}/ar/"]}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS[lang]}" rel="stylesheet">
<link href="/assets/site.css" rel="stylesheet">{swg(lang)}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="topbar"><div class="wrap">
  <span class="date">{date_str}</span>
  <span class="upd"><span class="dot"></span>{t['updated']} {time_str} · {t['tz']}</span>
  <a class="lang" href="{t['switch_href']}">{t['switch_lang']}</a>
</div></div>

<div class="ticker" role="region" aria-label="{t['breaking']}"><span class="label">{t['breaking']}</span><div class="rail"><div class="track">{ticker_track}{ticker_track}</div></div></div>

<header class="masthead"><div class="wrap">
  <a class="logotype" href="#top"><h1><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></h1></a>
</div></header>

<nav class="sections" aria-label="Primary"><div class="wrap"><a class="home" href="#top">{t['latest']}</a>{nav_links}<a class="tip" href="#tips">🔒 {t['tips_nav']}</a></div></nav>

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
  {tips_band}{gaza_panel}
  {opinion_block}
  {section_blocks}
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="cols">
    <div><h2>{t['mission_title']}</h2><p class="mission">{t['mission']}</p></div>
    <div><h2>{t['tips_kicker']}</h2><p class="mission">{t['tips_sub']}</p>
      <p class="footer-contact"><a href="{SIGNAL_URL}" target="_blank" rel="noopener">🔒 {t['tips_cta']} →</a>
      <span class="contact-id">{SIGNAL_USERNAME}</span></p><p class="footer-contact secondary"><a href="{TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{t['tips_tg']} →</a> <span class="contact-id">{TELEGRAM_BOT_NAME}</span></p></div>
  </div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com · timesofpalestine.tv</span> <a href="about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a> <a href="status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a>
    <span>{t['attribution']}</span>
    <a href="{t['switch_href']}">{t['footer_lang']}</a>
  </div>
</div></footer>
<script>(()=>{{const initial={json.dumps(utc_iso(built_at))};let timer;async function check(){{if(document.hidden||!navigator.onLine)return;try{{const r=await fetch("/data.json",{{cache:"no-store"}});if(r.ok&&((await r.json()).builtAt)!==initial)location.reload();}}catch(_error){{}}}}document.addEventListener("visibilitychange",()=>{{if(!document.hidden)check();}});timer=setInterval(check,900000);}})();</script>
</body>
</html>"""
def render_story(it, lang, related, rail, built_at):
    """Internal story page: brief, breaking ticker, Keep Reading grid, Latest rail.
    Every page links onward to many others — readers always circulate."""
    t = STR[lang]
    lede = (
        f'<img class="lede" src="{esc(it["image"])}" alt="{esc(it["title"])}">'
        f'{media_credit(it, lang)}'
    ) if it["image"] else f'<div class="lede">{FLAG_SVG}</div>'
    brief = it.get("brief")
    if brief and REFUSAL_RX.search(brief):  # hard stop: refusal text must never render
        brief = None
    if brief:  # original TOP Newsdesk brief, written by Claude, cached per story
        paras = __import__("longform").body_html(brief)  # was: [re.sub(r"\*\*|__|^#+\s*", "", p).strip() for p in brief.split("\n")]
        # long-form subset: subheads, figures with captions, tables, lists
        kind = (t["kind_original"] if it.get("original")
                else t["kind_brief"] if it.get("brief") else t["kind_curated"])
        credit = ("" if it.get("original") else
                  f'<span class="based">{t["based_on"]} '
                  f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">'
                  f'{esc(it["source"])}</a></span>')
        summary = (f'<p class="kind">{kind}</p><p class="byline">{t["byline"]}{credit}</p>{paras}')
    else:
        if it.get("original"):
            summary = f'<p class="summary">{esc(it["dek"])}</p>' if it["dek"] else ""
        else:
            source_credit = (
                f'<span class="based">{t["based_on"]} '
                f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">'
                f'{esc(it["source"])}</a></span>')
            summary = (
                f'<p class="kind">{t["kind_curated"]}</p>'
                f'<p class="byline">{source_credit}</p>'
                f'<p class="summary">{esc(it["dek"])}</p>')
    rail_items = [r for r in rail if r is not it]
    ticker_track = "".join(f'<a href="{href(r, "")}">{esc(r["title"])}</a>' for r in rail_items[:6])
    latest_html = "".join(latest_item(r, lang, "") for r in rail_items[:10])
    if it.get("original"):
        cta = ""
    else:
        cta = (f'<div class="cta">'
               f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">{t["read_original"]} {esc(it["source"])} →</a>'
               f'<p class="note">{t["summary_note"]}</p></div>')
    corroborating = [
        source for source in it.get("corroborating_sources", [])
        if source.get("article") and source.get("article") != it.get("link")
    ]
    corroboration = ""
    if corroborating:
        label = "تغطية ذات صلة" if lang == "ar" else "Related reporting"
        links = " · ".join(
            f'<a href="{esc(source["article"])}" target="_blank" rel="noopener">'
            f'{esc(source["name"])}</a>' for source in corroborating)
        corroboration = f'<p class="corroboration"><strong>{label}:</strong> {links}</p>'
    corrections = ""
    if it.get("corrections"):
        heading = "سجل التحديثات والتصويبات" if lang == "ar" else "Updates & corrections"
        rows = "".join(
            f'<li><time datetime="{esc(row["at"])}">{esc(row["at"][:10])}</time> '
            f'<strong>{"تصويب" if lang == "ar" and row["type"] == "correction" else "تحديث" if lang == "ar" else row["type"].title()}:</strong> '
            f'{esc(row["note"])}</li>' for row in it["corrections"])
        corrections = (
            f'<section class="revisions" aria-labelledby="revision-title">'
            f'<h2 id="revision-title">{esc(heading)}</h2><ol>{rows}</ol></section>')
    related_cards = "".join(card(r, lang, "") for r in related)
    page_url = f"{BASE_URL}/{lang}/story/{it['pid']}.html"; _q = __import__("urllib.parse", fromlist=["quote"]).quote; share_row = ('<div class="share"><span>' + ("شارك" if lang == "ar" else "Share") + '</span><a href="https://twitter.com/intent/tweet?url=' + _q(page_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener">X</a><a href="https://www.facebook.com/sharer/sharer.php?u=' + _q(page_url) + '" target="_blank" rel="noopener">Facebook</a><a href="https://wa.me/?text=' + _q(it["title"] + " " + page_url) + '" target="_blank" rel="noopener">WhatsApp</a><a href="https://t.me/share/url?url=' + _q(page_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener">Telegram</a></div>')
    desc = esc((it.get("brief") or it["dek"]).replace(chr(10), " ")[:155])
    og_image = f'<meta property="og:image" content="{esc(it["image"])}">' if it["image"] else ""
    hreflang = ""
    if it["source_id"] == "top-original" and str(it.get("link", "")).startswith("original:"):
        stem = it["link"].split(":", 1)[1]
        if "." in stem:
            slug, source_lang = stem.rsplit(".", 1)
            if source_lang in ("en", "ar"):
                other_lang = "ar" if source_lang == "en" else "en"
                if (ROOT / "originals" / f"{slug}.{other_lang}.txt").is_file():
                    this_pid = hashlib.md5(f"original:{slug}.{source_lang}".encode()).hexdigest()[:10]
                    other_pid = hashlib.md5(f"original:{slug}.{other_lang}".encode()).hexdigest()[:10]
                    this_url = f"{BASE_URL}/{source_lang}/story/{this_pid}.html"
                    other_url = f"{BASE_URL}/{other_lang}/story/{other_pid}.html"
                    en_url = this_url if source_lang == "en" else other_url
                    hreflang = (f'<link rel="alternate" hreflang="{source_lang}" href="{this_url}">\n'
                                f'<link rel="alternate" hreflang="{other_lang}" href="{other_url}">\n'
                                f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    jsonld_record = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": it["title"], "datePublished": utc_iso(it["date"]),
        "mainEntityOfPage": page_url,
        "image": [it["image"]] if it["image"] else [],
        "publisher": {"@type": "NewsMediaOrganization", "name": t["site_name"], "url": f"{BASE_URL}/{lang}/"},
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
        jsonld_record["image"] = [{
            "@type": "ImageObject", "url": it["image"],
            "creditText": it["media"]["credit"],
        }]
    jsonld = json.dumps(jsonld_record, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 46'><rect width='46' height='15.3' fill='%230b0b0c'/><rect y='15.3' width='46' height='15.3' fill='%23fff'/><rect y='30.6' width='46' height='15.4' fill='%23007A3D'/><path d='M0 0 L21 23 L0 46 Z' fill='%23CE1126'/></svg>"><link rel="manifest" href="/manifest.json"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js")</script>
<title>{esc(it['title'])} — {t['site_name']}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{page_url}">
{hreflang}
<meta property="og:type" content="article">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(it['title'])}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{page_url}">
{og_image}
<meta name="twitter:card" content="{'summary_large_image' if it['image'] else 'summary'}">
<script type="application/ld+json">{jsonld}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS[lang]}" rel="stylesheet">
<link href="/assets/site.css" rel="stylesheet">{swg(lang)}
</head>
<body>
<div class="backbar"><a href="../">{t['back_home']}</a><a href="../../{'en' if lang == 'ar' else 'ar'}/">{t['switch_lang']}</a></div>
<div class="ticker" role="region" aria-label="{t['breaking']}"><span class="label">{t['breaking']}</span><div class="rail"><div class="track">{ticker_track}{ticker_track}</div></div></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="../"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>

<main>
  <article class="story">
    <p class="kick">{t['sections'].get(it['cat'], t['sections']['news'])}</p>
    <h1>{esc(it['title'])}</h1>
    {meta_line(it, lang)}
    {lede}
    {summary}
    {cta}{corroboration}{corrections}{share_row}
  </article>
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
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span> <a href="../about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a> <a href="../status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a>
    <a href="../">{t['back_home']}</a>
  </div>
</div></footer>
</body>
</html>"""
def render_rss(lang, items, built_at):
    """Standard RSS 2.0 feed so readers, apps and other sites can syndicate TOP."""
    t = STR[lang]
    from email.utils import format_datetime
    entries = []
    for it in sorted([i for i in items if i["cat"] != "social"],
                     key=lambda i: i["date"], reverse=True)[:30]:
        u = f"{BASE_URL}/{lang}/story/{it['pid']}.html"
        desc = (it.get("brief") or it["dek"]).split(chr(10))[0]
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

def render_sitemap(langs_items, built_at):
    day = built_at.strftime("%Y-%m-%d")
    urls = []
    for lang, items in langs_items:
        urls.append(f"<url><loc>{BASE_URL}/{lang}/</loc><lastmod>{day}</lastmod>"
                    "<changefreq>hourly</changefreq><priority>1.0</priority></url>")
        for it in items:
            changed = it.get("modified") or it["date"]
            urls.append(f"<url><loc>{BASE_URL}/{lang}/story/{it['pid']}.html</loc>"
                        f"<lastmod>{utc_iso(changed)}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls) + "</urlset>")

ROBOTS_TXT = f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""

REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Times of Palestine</title>
<script>location.replace((navigator.language||"").toLowerCase().indexOf("ar")===0?"ar/":"en/");</script>
<meta http-equiv="refresh" content="1;url=en/">
</head><body><p><a href="en/">English</a> · <a href="ar/">العربية</a></p></body></html>"""

# ---------- main ----------

def main():
    global HEALTH
    built_at = datetime.now(timezone.utc)
    HEALTH = BuildHealth(built_at)
    for lang in ("en", "ar"):
        for feed in FEEDS[lang]:
            HEALTH.register_source(feed, lang)
    en_items = build_lang("en")
    ar_items = build_lang("ar")
    all_fetched_items = en_items + ar_items
    try:
        brief_status = generate_briefs(all_fetched_items)
    except Exception as e:  # the briefs layer must never block publication
        print(f"\nBriefs: stage failed ({type(e).__name__}) — publishing with feed summaries.")
        HEALTH.checks["brief_generation"] = "degraded"
    else:
        HEALTH.checks["brief_generation"] = brief_status
    purge_held_briefs([
        item for item in all_fetched_items if classify_risk(item)])
    # Arabic-wire stories appear in the English edition only once their headline
    # has been translated (translation rides along with brief generation, cached);
    # their Arabic feed summaries never render on English pages.
    en_items = [i for i in en_items
                if not (i.get("needs_translation") and ARABIC_CHARS_RX.search(i["title"]))]
    for i in en_items:
        if i.get("needs_translation") and ARABIC_CHARS_RX.search(i["dek"]):
            i["dek"] = ""

    keep = lambda i: not i.get("vetoed") and not i.get("brief_refused") and (i.get("brief") or i["dek"])
    candidates = [i for i in en_items + ar_items if keep(i)]
    approvals = load_reviews(ROOT / "editorial" / "reviews.json")
    eligible, held = apply_review_gate(candidates, approvals)
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
        (dist / lang / "index.html").write_text(render_page(lang, items, built_at), encoding="utf-8")
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
            (dist / lang / "story" / f"{it['pid']}.html").write_text(story_html, encoding="utf-8")
        (dist / lang / "rss.xml").write_text(render_rss(lang, items, built_at), encoding="utf-8")
    (dist / "sitemap.xml").write_text(
        render_sitemap((("en", en_items), ("ar", ar_items)), built_at), encoding="utf-8")
    (dist / "robots.txt").write_text(ROBOTS_TXT, encoding="utf-8")
    __import__("seo_extras").write_extras(
        dist, (("en", en_items), ("ar", ar_items)), built_at, BASE_URL, HEALTH)
    __import__("longform").copy_media(dist, en_items + ar_items)
    (dist / "index.html").write_text(REDIRECT_HTML, encoding="utf-8")
    (dist / ".nojekyll").write_text("")
    cname = ROOT / "CNAME"  # optional custom domain (e.g. timesofpalestine.com)
    if cname.exists():
        (dist / "CNAME").write_text(cname.read_text())
    qr = ROOT / "signal-qr.png"  # Signal tip-line QR shown in the tip band
    if qr.exists():
        (dist / "signal-qr.png").write_bytes(qr.read_bytes()); ob = ROOT / "og-banner.png"; ob.exists() and (dist / "og-banner.png").write_bytes(ob.read_bytes())
    (dist / "data.json").write_text(json.dumps(
        {"builtAt": utc_iso(built_at), "en": len(en_items), "ar": len(ar_items),
         "briefs": sum(1 for i in en_items + ar_items if i.get("brief"))}, indent=2))
    (dist / "review-queue.json").write_text(
        json.dumps(sanitized_review_queue(held), indent=2), encoding="utf-8")
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
