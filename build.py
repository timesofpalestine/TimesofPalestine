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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 TimesOfPalestine/1.0")
GAZA = ZoneInfo("Asia/Gaza")

# Anonymous tip line — the newsroom's Signal account (username TOP.972).
# Link decoded from the official Signal share QR; signal-qr.png in the repo root
# is the matching scannable code, copied into dist/ at build time.
SIGNAL_URL = "https://signal.me/#eu/0_b-q0RDCIq5joH5eX1lR_jVWkiLrah-MdXuqpiCawImwuEDAfdN1Z14HJk-6mRg"
SIGNAL_USERNAME = "@TOP.972"

# Feeds marked "exclusive": true in feeds.json are partner wires TOP has standing
# permission to publish under its own label, with no external attribution or link-out.
EXCLUSIVE_SOURCE = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}
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
        "Output only the brief text, paragraphs separated by blank lines."
    ),
    "ar": (
        "أنت غرفة أخبار «تايمز أوف فلسطين»، منصة إخبارية رقمية مستقلة. اكتب موجزاً إخبارياً "
        "أصلياً باللغة العربية بالاعتماد حصراً على المواد المصدرية المرفقة: فقرتان إلى ثلاث فقرات "
        "قصيرة (100-170 كلمة إجمالاً). أسلوب خبري مباشر: ابدأ بأهم معلومة ثم التفاصيل والسياق. "
        "لغة محايدة دقيقة مهنية؛ لا إساءات شخصية ولا إنشاء ولا ضمير متكلم. لا تخترع أسماء أو "
        "أرقاماً أو اقتباسات أو تفاصيل غير واردة في المصدر؛ وإذا كانت المادة مجرد عنوان فاكتب "
        "فقرة قصيرة من جملتين أو ثلاث تنقل ما يفيد به العنوان. لا ترفض أبداً، ولا تعلق على المادة "
        "أو على هذه التعليمات أو على نفسك. أخرج نص الموجز فقط، والفقرات مفصولة بسطر فارغ."
    ),
}
MAX_AGE_HOURS = 72
PER_SOURCE_CAP = 14

FEEDS = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))

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
    r"فلسطين|الفلسطيني|غزة|غزّة|الضفة|القدس|رام الله|رفح|خان يونس|جنين|نابلس|الخليل|"
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
    r"palestinian communit|palestinian expat|refugees? in (?:lebanon|jordan|syria|europe|chile|"
    r"the us|america)|"
    r"الشتات|الجالية الفلسطينية|جاليات|مغترب|فلسطينيو الخارج|فلسطينيي الخارج|"
    r"مخيمات لبنان|مخيمات الأردن|مخيمات سوريا|اللاجئون الفلسطينيون في", re.I)

# Palestinian art & artists worldwide — culture as identity and testimony.
ARTS_RX = re.compile(
    r"artist|painter|sculpt|exhibit|gallery|mural|filmmaker|documentary|"
    r"\bpoet\b|poetry|novelist|musician|singer|\bdabke\b|embroidery|tatreez|"
    r"فنان|فنانة|تشكيلي|معرض|لوحة|جدارية|مخرج|وثائقي|شاعر|شاعرة|روائي|"
    r"موسيقي|مغني|مغنية|دبكة|تطريز", re.I)

# Real lives — the human stories behind the headlines: profiles, testimony, memory.
REAL_LIVES_RX = re.compile(
    r"story of|life of|survivor|remembers|testimony|his story|her story|"
    r"قصة|حكاية|يروي|تروي|شهادة|ناجٍ|ناجية|شاهد على|صرخة", re.I)

# Corruption, transparency & democratic accountability — wherever it sits, incl. the PA.
ACCOUNTABILITY_RX = re.compile(
    r"corrupt|nepotis|briber|embezzl|cronyis|\bgraft\b|kleptocra|"
    r"فساد|الفساد|محسوبية|رشوة|رشاوى|اختلاس|نزاهة|مساءلة|شفافية|مكافحة الفساد|"
    r"اعتقال سياسي|معتقل سياسي|معتقلي الرأي|تكميم|استبداد", re.I)

ISRAEL_CONTEXT_RX = re.compile(r"israel|settler|idf|zionis|إسرائيل|مستوطن", re.I)

# Bitcoin & financial freedom — adoption in Palestine, the HRF/Gladstein/Dorsey
# freedom-money track: money that cannot be frozen, censored, or occupied.
BITCOIN_RX = re.compile(
    r"bitcoin|\bbtc\b|satoshi|lightning network|\bsats\b|"
    r"بيتكوين|بتكوين|البيتكوين|ساتوشي|شبكة البرق", re.I)

# For Bitcoin Magazine etc.: keep the freedom/rights/adoption stories, drop pure market noise.
BTC_FREEDOM_RX = re.compile(
    r"financial freedom|human rights|gladstein|dorsey|palestin|gaza|west bank|middle east|"
    r"remittance|censorship|authoritarian|unbanked|self.?custody|circular econom|"
    r"global south|sanction|dictator|freedom money|financial repression", re.I)

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
    s = max(0.0, (horizon - hours) / horizon) * RECENCY_MAX
    hay = f"{item['title']} {item['dek']}"
    if CHRISTIANS_RX.search(hay):
        s += FOCUS_BOOST
    if ACCOUNTABILITY_RX.search(hay):
        s += FOCUS_BOOST
    if BITCOIN_RX.search(hay):
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
    ("bitcoin", BITCOIN_RX),
    ("diaspora", DIASPORA_RX),
    ("arts", ARTS_RX),
    ("humans", REAL_LIVES_RX),
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
    ("culture", re.compile(
        r"culture|\bart\b|artist|film|cinema|book|poet|music|heritage|museum|cuisine|"
        r"sport|football|olympi|"
        r"ثقافة|فنان|فيلم|سينما|شاعر|موسيقى|تراث|متحف|مطبخ|رياضة|كرة القدم", re.I)),
]

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

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(s)
        if d:
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:  # ISO with colon-less offset, e.g. 2026-07-21T14:22:51+0300 (AJ Studies)
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        pass
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2}):(\d{2})", s)  # Arab48: DD/MM/YYYY - HH:MM (local)
    if m:
        day, mon, yr, hh, mm = map(int, m.groups())
        try:
            return datetime(yr, mon, day, hh, mm, tzinfo=GAZA)
        except ValueError:
            return None
    return None

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
    with urllib.request.urlopen(req, timeout=25) as r:
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
JUNK_TITLE_RX = re.compile(r"#\d+\s*$")  # database-row titles like "Israel 3 July 2026 #1"

def finish_item(item, feed):
    """Apply per-feed relevance filters, then categorize and score. Returns item or None."""
    if JUNK_TITLE_RX.search(item["title"]):
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
    if feed.get("exclusive"):  # permissioned wire published under TOP's own label
        item["exclusive"] = True
        item["source"] = EXCLUSIVE_SOURCE[item["lang"]]
        if feed.get("translate"):  # Arabic-only wire feeding the English edition
            item["needs_translation"] = True
        item["cat"] = categorize(item)
    elif feed.get("type") == "telegram":
        item["cat"] = "social"
    elif feed.get("research"):
        item["cat"] = "research"
    elif feed.get("category"):  # query-scoped feeds (e.g. Bitcoin radar) pre-decide their section
        item["cat"] = feed["category"]
    else:
        item["cat"] = categorize(item)
    item["max_age_hours"] = feed.get("maxAgeHours", MAX_AGE_HOURS)
    item["score"] = score_item(item)
    item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]  # stable internal page id
    return item

def gnews_url(feed):
    from urllib.parse import quote
    return (f"https://news.google.com/rss/search?q={quote(feed['query'])}"
            f"&hl={feed.get('hl', 'en-US')}&gl={feed.get('gl', 'US')}&ceid={quote(feed.get('ceid', 'US:en'))}")

def fetch_rss(feed, lang, now, max_age):
    url = gnews_url(feed) if feed.get("type") == "gnews" else feed["url"]
    root = parse_xml(fetch_bytes(url))
    items = []
    for el in [e for e in root.iter() if local(e.tag) in ("item", "entry")]:
        title = strip_html(item_field(el, {"title"}))
        source_name = feed["name"]
        if feed.get("type") == "gnews":  # per-item real outlet; strip " - Outlet" title suffix
            outlet = item_field(el, {"source"})
            if outlet:
                source_name = outlet
                if title.endswith(outlet):
                    title = title[: -len(outlet)].rstrip(" -—–|·")
        if len(title) < 8:
            continue
        date = parse_date(item_field(el, {"pubdate", "published", "updated", "date"}))
        if not date or now - date > max_age or date > now + timedelta(hours=2):
            continue
        if feed.get("type") == "gnews":  # gnews descriptions are just related-link clusters
            dek = ""
        else:
            dek = truncate(clean_dek(strip_html(item_field(el, {"description", "summary", "encoded", "content"},
                                                           nested=feed.get("type") == "youtube"))),
                           420 if feed.get("research") else 260)
        if dek == title:
            dek = ""
        cats = [strip_html(n.text or n.get("term") or "") for n in el if local(n.tag) == "category"]
        item = {
            "title": truncate(title, 200), "dek": dek,
            "link": item_link(el) or feed["site"], "date": date,
            "source": source_name, "source_id": feed["id"],
            "image": find_image(el), "categories": [c for c in cats if c], "lang": lang,
        }
        item = finish_item(item, feed)
        if item:
            items.append(item)
    return items

TG_MSG_RX = re.compile(r'class="tgme_widget_message_wrap.*?(?=class="tgme_widget_message_wrap|$)', re.S)
TG_TEXT_RX = re.compile(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
TG_DATE_RX = re.compile(r'<time datetime="([^"]+)"')
TG_LINK_RX = re.compile(r'class="tgme_widget_message_date"[^>]*href="([^"]+)"')
TG_PHOTO_RX = re.compile(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)")
# Channel posts carry emoji and hashtags; neither belongs in a news headline.
EMOJI_RX = re.compile("[\\U0001F000-\\U0001FAFF\\U0001FB00-\\U0001FBFF"
                      "\\u2600-\\u27BF\\u2B00-\\u2BFF\\u2190-\\u21FF\\u2300-\\u23FF\\uFE0F\\u200D]")

def fetch_telegram(feed, lang, now, max_age):
    """Parse a public Telegram channel's t.me/s/<channel> preview page (no API needed)."""
    html_page = fetch_bytes(f"https://t.me/s/{feed['channel']}").decode("utf-8", errors="replace")
    items = []
    for block in TG_MSG_RX.findall(html_page):
        m_text, m_date, m_link = TG_TEXT_RX.search(block), TG_DATE_RX.search(block), TG_LINK_RX.search(block)
        if not (m_text and m_date and m_link):
            continue
        raw = strip_html(m_text.group(1))
        m_art = re.search(r"https?://(?!t\.me/)\S+", raw)  # channels often append the article URL
        link = html.unescape(m_art.group(0).rstrip(".,)…")) if m_art else m_link.group(1)
        text = re.sub(r"https?://\S+", "", raw)
        text = EMOJI_RX.sub("", text).replace("#", "")
        text = re.sub(r"\s+", " ", text).strip(" .|-—·")
        text = re.sub(r"^\s*وكالة معا\s*[|:ـ—-]+\s*", "", text)  # agency name prefixed to some posts
        if len(text) < 25:
            continue
        date = parse_date(m_date.group(1))
        if not date or now - date > max_age:
            continue
        m_photo = TG_PHOTO_RX.search(block)
        item = {
            "title": truncate(text, 130), "dek": truncate(text, 260) if len(text) > 130 else "",
            "link": link, "date": date,
            "source": feed["name"], "source_id": feed["id"],
            "image": m_photo.group(1) if m_photo else None, "categories": [], "lang": lang,
        }
        item = finish_item(item, feed)
        if item:
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
        return items
    except Exception as e:
        print(f"  ✗ {feed['name']}: {type(e).__name__}: {e}")
        return []
OG_IMAGE_RXES = [
    re.compile(r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', re.I),
]
EXTERNAL_LINK_RX = re.compile(r'href="(https?://(?!news\.google|accounts\.google|policies\.google)[^"]+)"')

def fetch_og_image(url, hop=0):
    """Pull the article's own social-preview image so no story card goes photoless."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read(150000).decode("utf-8", errors="replace")
            final_host = r.url
        for rx in OG_IMAGE_RXES:
            m = rx.search(text)
            if m and m.group(1).startswith("http"):
                return html.unescape(m.group(1))
        # Google News interstitial: follow the first external link to the real article
        if hop == 0 and "news.google.com" in final_host:
            m = EXTERNAL_LINK_RX.search(text)
            if m:
                return fetch_og_image(html.unescape(m.group(1)), hop=1)
    except Exception:
        pass
    return None

def enrich_images(items, limit=35):
    targets = [i for i in sorted(items, key=lambda x: x["score"], reverse=True)
               if not i["image"] and "maannews.net" not in i["link"]][:limit]  # Ma'an blocks server fetches
    if not targets:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        found = list(ex.map(lambda i: fetch_og_image(i["link"]), targets))
    hits = 0
    for it, img in zip(targets, found):
        if img:
            it["image"], hits = img, hits + 1
            it["score"] = score_item(it)  # image boost now applies
    print(f"  → og:image enrichment: {hits}/{len(targets)} photos recovered")

P_TAG_RX = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)

BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

def fetch_article_text(url, hop=0):
    """Pull readable paragraph text from the article page to ground the brief in facts.
    Tries a browser agent first, then a crawler agent — outlets gate one or the other."""
    best = ""
    for ua in (UA, BOT_UA):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=12) as r:
                page = r.read(400000).decode("utf-8", errors="replace")
                final_url = r.url
            paras = [strip_html(p) for p in P_TAG_RX.findall(page)]
            text = " ".join(p for p in paras if len(p) > 60)
            if len(text) < 200 and hop == 0 and "news.google.com" in final_url:
                m = EXTERNAL_LINK_RX.search(page)
                if m:
                    text = fetch_article_text(html.unescape(m.group(1)), hop=1)
            if len(text) > len(best):
                best = text
            if len(best) >= 200:
                break
        except Exception:
            continue
    return best[:2800]

# A brief must never talk about itself or its sources' availability. Any output that
# does (a model refusal / meta-commentary) is rejected and scrubbed from the cache.
REFUSAL_RX = re.compile(
    r"cannot (?:produce|write|provide|generate)|insufficient (?:source|material|information)|"
    r"source material|news brief|لا يمكن(?:نا)? (?:إنتاج|كتابة|تقديم)|المادة المصدرية|هذه التعليمات", re.I)

def write_brief(client, item):
    excerpt = fetch_article_text(item["link"])
    material = (f"OUTLET: {item['source']}\n"
                f"HEADLINE: {item['title']}\n"
                f"FEED SUMMARY: {item['dek'] or '(none)'}\n"
                f"ARTICLE EXCERPT: {excerpt or '(unavailable)'}")
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
    return text if len(text) > (120 if excerpt else 60) and not REFUSAL_RX.search(text) else None
def generate_briefs(all_items):
    """Attach an original TOP Newsdesk brief to each story, cached across builds."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nBriefs: ANTHROPIC_API_KEY not set — publishing with feed summaries.")
        return
    try:
        import anthropic
    except ImportError:
        print("\nBriefs: `anthropic` package not installed — publishing with feed summaries.")
        return
    try:
        cache = json.loads(BRIEFS_CACHE.read_text(encoding="utf-8")) if BRIEFS_CACHE.exists() else {}
    except Exception:
        cache = {}
    cache = {k: v for k, v in cache.items() if not REFUSAL_RX.search(v.get("brief", ""))}
    now_ts = datetime.now(timezone.utc).timestamp()
    for it in all_items:
        # Keys are lang-scoped so the same wire story can carry an Arabic brief in /ar/
        # and an English one in /en/; bare-pid entries are legacy single-language cache.
        entry = cache.get(f"{it['lang']}:{it['pid']}") or cache.get(it["pid"])
        if entry:
            it["brief"] = entry["brief"]
            if entry.get("title"):  # translated headline saved alongside the brief
                it["title"] = entry["title"]
    todo = [i for i in sorted(all_items, key=lambda x: (x.get("needs_translation", False), not x["dek"], x["score"]),
                              reverse=True) if "brief" not in i][:MAX_BRIEFS_PER_RUN]
    if not todo:
        print("\nBriefs: cache warm — nothing new to write.")
        return

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
                entry = {"brief": brief, "ts": now_ts}
                if it.get("needs_translation") and not ARABIC_CHARS_RX.search(it["title"]):
                    entry["title"] = it["title"]  # keep the English headline across builds
                cache[f"{it['lang']}:{it['pid']}"] = entry
                written += 1
    cache = {k: v for k, v in cache.items() if now_ts - v.get("ts", now_ts) < 60 * 86400}
    try:
        BRIEFS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    print(f"\nBriefs: wrote {written} new of {len(todo)} attempted; cache holds {len(cache)}.")

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

def load_originals(lang):
    orig = ROOT / "originals"
    if not orig.is_dir():
        return []
    now = datetime.now(timezone.utc)
    items = []
    for path in sorted(orig.glob(f"*.{lang}.txt")):
        try:
            head, _, body = path.read_text(encoding="utf-8").partition("\n---\n")
            meta = {}
            for line in head.splitlines():
                k, _, v = line.partition(":")
                if v:
                    meta[k.strip().lower()] = v.strip()
            body = body.strip()
            date = parse_date(meta.get("date", "")) or now
            hours_kept = float(meta.get("maxagehours", 336))
            if not meta.get("title") or not body or (now - date).total_seconds() / 3600 > hours_kept:
                continue
            item = {
                "title": truncate(meta["title"], 200),
                "dek": truncate(re.sub(r"\s+", " ", body.split("\n\n")[0]), 260),
                "link": f"original:{path.stem}", "date": date,
                "source": EXCLUSIVE_SOURCE[lang], "source_id": "top-original",
                "image": meta.get("image") or None, "categories": [], "lang": lang,
                "exclusive": True, "brief": body,
                "cat": meta.get("category", "news"), "max_age_hours": hours_kept,
            }
            item["score"] = score_item(item) + FOCUS_BOOST  # our own journalism leads
            item["pid"] = hashlib.md5(item["link"].encode()).hexdigest()[:10]
            items.append(item)
            print(f"  ✓ original: {item['title'][:60]}")
        except Exception as e:
            print(f"  ✗ original {path.name}: {type(e).__name__}")
    return items

def build_lang(lang):
    print(f"\nFetching {lang.upper()} feeds…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda f: fetch_feed(f, lang), FEEDS[lang]))
    results.append(load_originals(lang))
    items = sorted(dedupe([i for r in results for i in r]), key=lambda i: i["date"], reverse=True)
    caps = {f["id"]: f.get("cap", PER_SOURCE_CAP) for f in FEEDS[lang]}
    per_source, capped = {}, []
    for it in items:
        per_source[it["source_id"]] = per_source.get(it["source_id"], 0) + 1
        if per_source[it["source_id"]] <= caps.get(it["source_id"], PER_SOURCE_CAP):
            capped.append(it)
    print(f"  → {len(capped)} items after dedupe/cap")
    enrich_images(capped)
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
                     "arts": "Art & Artists",
                     "accountability": "Transparency & Accountability",
                     "research": "Research & Investigations",
                     "bitcoin": "Bitcoin & Financial Freedom",
                     "politics": "Politics & Diplomacy", "economy": "Economy & Aid",
                     "culture": "Culture & Society", "social": "Social Pulse",
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
        "keep_reading": "Keep Reading",
        "back_home": "← All the news",
        "summary_note": "Summary curated by Times of Palestine. The full story belongs to its publisher.",
        "tips_nav": "Send a Tip",
        "tips_kicker": "SECURE TIP LINE",
        "tips_title": "Know something the public should know?",
        "tips_sub": ("Corruption, abuse of power, a story no one will touch — send it to our "
                     "newsroom on Signal. Encrypted. Anonymous. Seen by no one else."),
        "tips_cta": "Message us on Signal",
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
                     "arts": "الفن والفنانون",
                     "accountability": "شفافية ومساءلة",
                     "research": "أبحاث وتحقيقات",
                     "bitcoin": "بيتكوين والحرية المالية",
                     "politics": "سياسة ودبلوماسية", "economy": "اقتصاد وإغاثة",
                     "culture": "ثقافة ومجتمع", "social": "نبض المنصات",
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
        "keep_reading": "تابع القراءة",
        "back_home": "كل الأخبار ←",
        "summary_note": "الملخص من إعداد «تايمز أوف فلسطين». المادة الكاملة ملك لناشرها الأصلي.",
        "tips_nav": "أرسل معلومة",
        "tips_kicker": "خط المعلومات الآمن",
        "tips_title": "تعرف شيئاً يستحق أن يعرفه الناس؟",
        "tips_sub": ("فساد، تجاوز للسلطة، قصة لا يجرؤ أحد على نشرها — أرسلها إلى غرفة الأخبار عبر "
                     "«سيغنال». مشفّرة. مجهولة الهوية. لا يطّلع عليها أحد سوانا."),
        "tips_cta": "راسلنا على سيغنال",
        "tips_micro": "بلا اسم. بلا رقم. فقط الحقيقة.",
        "tips_scan": "أو امسح الرمز بهاتفك",
        "tips_safety": "لسلامتك: استخدم «سيغنال» من جهازك الشخصي، ولا تشارك أي تفاصيل تكشف هويتك إلا إذا اخترت ذلك.",
    },
}

# Focus sections sit high on the page; each edition leads with its editorial priority.
# Research (think tanks / OSINT) comes first: news before it becomes news.
SECTION_ORDER = {
    "en": ["research", "gaza", "westbank", "humans", "diaspora", "arts", "accountability",
           "bitcoin", "politics", "economy", "culture", "social", "opinion", "news"],
    "ar": ["research", "gaza", "westbank", "accountability", "humans", "diaspora", "arts",
           "bitcoin", "politics", "economy", "culture", "social", "opinion", "news"],
}
FOCUS_SECTIONS = {"research", "humans", "diaspora", "arts", "accountability", "bitcoin", "social"}  # shown even with one story

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
  --red:#CE1126; --green:#007A3D; --black:#0b0b0c; --ink:#17171c; --muted:#5d5d66;
  --paper:#fdfcf9; --card:#ffffff; --line:#e5e2d9; --line-dark:#c9c5b8;
  --serif:"Source Serif 4",Georgia,serif; --sans:"Libre Franklin",-apple-system,Helvetica,Arial,sans-serif;
  --max:1180px;
}
[lang=ar]{ --serif:"Amiri",serif; --sans:"Cairo",Tahoma,sans-serif; }
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

.masthead{background:var(--card);border-bottom:1px solid var(--line);text-align:center;padding:1.5rem 0 1rem}
.masthead .logotype{display:inline-flex;align-items:center}
.masthead h1{font-family:var(--serif);font-weight:900;line-height:1;letter-spacing:-.01em;color:var(--black);font-size:clamp(1.6rem,4vw,2.6rem);white-space:nowrap}
.masthead h1 .l2{color:var(--red)}
[lang=ar] .masthead h1{letter-spacing:0;font-weight:700;line-height:1.25}
.masthead.compact{padding:.9rem 0 .7rem}
.masthead.compact h1{font-size:1.35rem}

nav.sections{position:sticky;top:0;background:var(--black);z-index:50;box-shadow:0 2px 10px rgba(0,0,0,.25)}
nav.sections .wrap{display:flex;gap:.25rem;overflow-x:auto;scrollbar-width:none}
nav.sections a{color:#e8e8ee;font-size:.78rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:.75rem .85rem;white-space:nowrap;border-bottom:3px solid transparent}
[lang=ar] nav.sections a{letter-spacing:0;font-size:.85rem}
nav.sections a:hover{color:#fff;border-color:var(--red)}
nav.sections a.home{color:#ff8896}

.hero-zone{display:grid;grid-template-columns:minmax(0,2.05fr) minmax(0,1fr);gap:2rem;padding-block:1.8rem}
.hero{border-inline-end:1px solid var(--line);padding-inline-end:2rem}
.hero .label{color:var(--red);font-size:.68rem;font-weight:800;letter-spacing:.2em;margin-bottom:.6rem}
[lang=ar] .hero .label{letter-spacing:.03em;font-size:.8rem}
.hero img{aspect-ratio:16/9;object-fit:cover;width:100%;background:#ddd}
.hero h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.5rem,3vw,2.3rem);line-height:1.13;margin-top:1rem}
[lang=ar] .hero h2{line-height:1.5;font-weight:700}
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
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.4rem}
.card img{aspect-ratio:16/10;object-fit:cover;width:100%;background:#e8e6df;margin-bottom:.7rem}
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
.tipband .micro{display:block;margin-top:.55rem;font-size:.72rem;color:#8f8f99;font-style:italic}
[lang=ar] .tipband .micro{font-style:normal}
.tipband .qrbox{background:#fff;padding:.55rem .55rem .45rem;border-radius:8px;display:inline-block;margin-top:.8rem}
.tipband .qrbox img{width:104px;height:104px;display:block;image-rendering:pixelated}
.tipband .qrbox span{display:block;font-size:.7rem;font-weight:800;color:#111;margin-top:.25rem;text-align:center;direction:ltr}
.tipband .scanhint{display:block;margin-top:.4rem;font-size:.68rem;color:#8f8f99}
.tipband .safety{flex-basis:100%;font-size:.7rem;color:#77777f;border-top:1px solid #26262c;padding-top:.7rem}
nav.sections a.tip{color:#3fd07c;border-color:#3fd07c;margin-inline-start:auto}

/* story page */
.story{max-width:780px;margin-inline:auto;padding:2rem 20px 1rem}
.story .kick{color:var(--red);font-size:.7rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;margin-bottom:.7rem}
[lang=ar] .story .kick{letter-spacing:.03em;font-size:.82rem}
.story h1{font-family:var(--serif);font-weight:900;font-size:clamp(1.6rem,3.6vw,2.5rem);line-height:1.15}
[lang=ar] .story h1{font-weight:700;line-height:1.5}
.story .meta{margin-top:1rem;font-size:.8rem}
.story div.lede{width:100%;aspect-ratio:16/9;margin-top:1.4rem;display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#101013 0 55%,rgba(0,122,61,.28) 55% 72%,rgba(206,17,38,.24) 72% 86%,#101013 86%)}.story div.lede svg{width:64px;height:64px;opacity:.9}.story img.lede{width:100%;aspect-ratio:16/9;object-fit:cover;background:#e8e6df;margin-top:1.4rem}
.story .byline{margin-top:1.4rem;font-size:.74rem;font-weight:800;color:var(--green);text-transform:uppercase;letter-spacing:.1em}
[lang=ar] .story .byline{letter-spacing:0;text-transform:none;font-size:.85rem}
.story .summary{margin-top:1rem;font-family:var(--serif);font-size:1.13rem;line-height:1.7;color:#26262e}
.story .summary+.summary{margin-top:.9rem}
[lang=ar] .story .summary{line-height:2}
.story .cta{margin-top:1.8rem;text-align:center;border-block:1px solid var(--line);padding-block:1.5rem}
.story .cta a{display:inline-block;background:var(--red);color:#fff;font-weight:800;font-size:1rem;padding:.9rem 2rem;border-radius:3px}
.story .cta a:hover{background:#a50d1e}
.story .note{margin-top:.8rem;font-size:.72rem;color:var(--muted)}
.keep{padding-block:1.8rem}
.backbar{background:var(--black)}
.backbar a{display:block;max-width:780px;margin-inline:auto;padding:.6rem 20px;color:#fff;font-size:.8rem;font-weight:700}
.backbar a:hover{color:#ff8896}

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
[dir=rtl] footer .flagline{background:linear-gradient(-90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%)}

@media(max-width:960px){
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

FONTS = ("https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;600;700;800"
         "&family=Source+Serif+4:ital,opsz,wght@0,8..60,600;0,8..60,700;0,8..60,900;1,8..60,700"
         "&family=Cairo:wght@400;600;700;800;900&family=Amiri:ital,wght@0,700;1,400&display=swap")
# ---------- components ----------

def href(it, pfx):
    """Internal story-page URL — readers stay on the site; the source link lives on the story page."""
    return f"{pfx}{it['pid']}.html"

def meta_line(it, lang):
    return (f'<p class="meta"><span class="src">{esc(it["source"])}</span>'
            f'<span class="t">{time_ago(it["date"], lang)}</span></p>')

def card_media(it, pfx):
    """Image if we have one; otherwise a branded flag panel — never an empty column."""
    if it["image"]:
        return f'<a href="{href(it, pfx)}"><img src="{esc(it["image"])}" alt="" loading="lazy"></a>'
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
    hero_subs = take(by_score, lambda i: i["cat"] not in ("opinion", "social", "research"), 4)
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

    sections = {k: diversify(take(by_score, lambda i, k=k: i["cat"] == k, 8)) for k in order}
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
        media = (f'<a href="{href(it, P)}"><img src="{esc(it["image"])}" alt="" loading="lazy"></a>'
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
        elif len(pool) < 4:  # too few for a grid row — full-width rows, no dead space
            grid = f'<div class="rowlist">{"".join(rowcard(it, lang, P) for it in pool)}</div>'
        else:
            grid = f'<div class="grid">{"".join(card(it, lang, P) for it in pool)}</div>'
        focus_cls = " focus" if k in FOCUS_SECTIONS else ""
        section_blocks += (f'<section class="block" id="{k}"><div class="wrap">'
                           f'<div class="sec-head{focus_cls}"><h2>{t["sections"][k]}</h2><span class="rule"></span></div>'
                           f'{featured}{grid}</div></section>')

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
                     f'<a href="{href(hero, P)}"><img src="{esc(hero["image"])}" alt=""></a>'
                     f'<p class="photocredit">{t["photo_via"]} {esc(hero["source"])}</p>'
                     f'<h2><a href="{href(hero, P)}">{esc(hero["title"])}</a></h2>'
                     f'{hero_dek}{meta_line(hero, lang)}')

    hero_subs_html = "".join(sub_item(it, lang, P) for it in hero_subs)
    latest_html = "".join(latest_item(it, lang, P) for it in latest)

    tips_band = (
        f'<section class="tipband" id="tips"><div class="wrap">{LOCK_SVG}'
        f'<div class="txt"><p class="kick">{t["tips_kicker"]}</p>'
        f'<h2>{t["tips_title"]}</h2><p class="sub">{t["tips_sub"]}</p></div>'
        f'<div class="cta"><a class="btn" href="{SIGNAL_URL}" target="_blank" rel="noopener">{t["tips_cta"]}</a>'
        f'<span class="micro">{t["tips_micro"]}</span>'
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
<meta http-equiv="refresh" content="600">
<title>{t['site_name']} — {t['title_suffix']}</title>
<meta name="description" content="{esc(t['mission'][:155])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <span class="date">{date_str}</span>
  <span class="upd"><span class="dot"></span>{t['updated']} {time_str} · {t['tz']}</span>
  <a class="lang" href="{t['switch_href']}">{t['switch_lang']}</a>
</div></div>

<div class="ticker"><span class="label">{t['breaking']}</span><div class="rail"><div class="track">{ticker_track}{ticker_track}</div></div></div>

<header class="masthead"><div class="wrap">
  <a class="logotype" href="#top"><h1><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></h1></a>
</div></header>

<nav class="sections"><div class="wrap"><a class="home" href="#top">{t['latest']}</a>{nav_links}<a class="tip" href="#tips">🔒 {t['tips_nav']}</a></div></nav>

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
  {tips_band}
  {opinion_block}
  {section_blocks}
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="cols">
    <div><h2>{t['mission_title']}</h2><p class="mission">{t['mission']}</p></div>
    <div><h2>{t['tips_kicker']}</h2><p class="mission">{t['tips_sub']}</p>
      <p style="margin-top:.9rem"><a href="{SIGNAL_URL}" target="_blank" rel="noopener">🔒 {t['tips_cta']} →</a>
      <span style="direction:ltr;display:inline-block;margin-inline-start:.6rem;color:#8f8f94">{SIGNAL_USERNAME}</span></p></div>
  </div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com · timesofpalestine.tv</span>
    <span>{t['attribution']}</span>
    <a href="{t['switch_href']}">{t['footer_lang']}</a>
  </div>
</div></footer>
</body>
</html>"""

def render_story(it, lang, related, rail, built_at):
    """Internal story page: brief, breaking ticker, Keep Reading grid, Latest rail.
    Every page links onward to many others — readers always circulate."""
    t = STR[lang]
    credit = "" if it.get("exclusive") else f'<p class="photocredit">{t["photo_via"]} {esc(it["source"])}</p>'
    lede = (f'<img class="lede" src="{esc(it["image"])}" alt="">{credit}') if it["image"] else f'<div class="lede">{FLAG_SVG}</div>'
    brief = it.get("brief")
    if brief and REFUSAL_RX.search(brief):  # hard stop: refusal text must never render
        brief = None
    if brief:  # original TOP Newsdesk brief, written by Claude, cached per story
        clean = [re.sub(r"\*\*|__|^#+\s*", "", p).strip() for p in brief.split(chr(10))]
        paras = "".join(f'<p class="summary">{esc(p)}</p>' for p in clean if p)
        summary = f'<p class="byline">{t["byline"]}</p>{paras}'
    else:
        summary = f'<p class="summary">{esc(it["dek"])}</p>' if it["dek"] else ""
    rail_items = [r for r in rail if r is not it]
    ticker_track = "".join(f'<a href="{href(r, "")}">{esc(r["title"])}</a>' for r in rail_items[:6])
    latest_html = "".join(latest_item(r, lang, "") for r in rail_items[:10])
    if it.get("exclusive"):  # our own wire — no external credit or link-out
        cta = ""
    else:
        cta = (f'<div class="cta">'
               f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">{t["read_original"]} {esc(it["source"])} →</a>'
               f'<p class="note">{t["summary_note"]}</p></div>')
    related_cards = "".join(card(r, lang, "") for r in related)
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(it['title'])} — {t['site_name']}</title>
<meta name="description" content="{esc((it.get('brief') or it['dek']).replace(chr(10), ' ')[:155])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="backbar"><a href="../">{t['back_home']}</a></div>
<div class="ticker"><span class="label">{t['breaking']}</span><div class="rail"><div class="track">{ticker_track}{ticker_track}</div></div></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="../"><h1><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></h1></a>
</div></header>

<main>
  <article class="story">
    <p class="kick">{t['sections'].get(it['cat'], t['sections']['news'])}</p>
    <h1>{esc(it['title'])}</h1>
    {meta_line(it, lang)}
    {lede}
    {summary}
    {cta}
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
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span>
    <a href="../">{t['back_home']}</a>
  </div>
</div></footer>
</body>
</html>"""

REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Times of Palestine</title>
<script>location.replace((navigator.language||"").toLowerCase().indexOf("ar")===0?"ar/":"en/");</script>
<meta http-equiv="refresh" content="1;url=en/">
</head><body><p><a href="en/">English</a> · <a href="ar/">العربية</a></p></body></html>"""

# ---------- main ----------

def main():
    built_at = datetime.now(timezone.utc)
    en_items = build_lang("en")
    ar_items = build_lang("ar")
    try:
        generate_briefs(en_items + ar_items)
    except Exception as e:  # the briefs layer must never block publication
        print(f"\nBriefs: stage failed ({type(e).__name__}) — publishing with feed summaries.")
    # Arabic-wire stories appear in the English edition only once their headline
    # has been translated (translation rides along with brief generation, cached);
    # their Arabic feed summaries never render on English pages.
    en_items = [i for i in en_items
                if not (i.get("needs_translation") and ARABIC_CHARS_RX.search(i["title"]))]
    for i in en_items:
        if i.get("needs_translation") and ARABIC_CHARS_RX.search(i["dek"]):
            i["dek"] = ""

    en_items = [i for i in en_items if i["cat"] == "social" or i.get("brief") or i["dek"]]; ar_items = [i for i in ar_items if i["cat"] == "social" or i.get("brief") or i["dek"]]; dist = ROOT / "dist"
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
            (dist / lang / "story" / f"{it['pid']}.html").write_text(
                render_story(it, lang, related, rail, built_at), encoding="utf-8")
    (dist / "index.html").write_text(REDIRECT_HTML, encoding="utf-8")
    (dist / ".nojekyll").write_text("")
    cname = ROOT / "CNAME"  # optional custom domain (e.g. timesofpalestine.com)
    if cname.exists():
        (dist / "CNAME").write_text(cname.read_text())
    qr = ROOT / "signal-qr.png"  # Signal tip-line QR shown in the tip band
    if qr.exists():
        (dist / "signal-qr.png").write_bytes(qr.read_bytes())
    (dist / "data.json").write_text(json.dumps(
        {"builtAt": built_at.isoformat(), "en": len(en_items), "ar": len(ar_items),
         "briefs": sum(1 for i in en_items + ar_items if i.get("brief"))}, indent=2))

    print(f"\nBuilt dist/ — EN {len(en_items)} stories, AR {len(ar_items)} stories.")
    if not en_items and not ar_items:
        print("No items fetched from any feed — failing so the last good deploy stays live.")
        sys.exit(1)

if __name__ == "__main__":
    main()
