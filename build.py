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
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.entities import name2codepoint
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from zoneinfo import ZoneInfo

import story_archive
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
# Reader-growth hooks (owner approval 2026-08-08; newsletter + analytics
# ordered ON 2026-08-10). All OFF until the repo variables exist — no
# third-party request, no signup band and no footer link is emitted without
# them. No pop-ups ever (owner rule 2026-08-02): the newsletter is a quiet
# inline band above the footer (newsletter_band), analytics a cookieless
# GoatCounter tag on every template (analytics_tag).
#   ANALYTICS_GOATCOUNTER  e.g. "timesofpalestine" → GoatCounter site code
#   NEWSLETTER_URL         e.g. https://buttondown.com/<name> (real inline
#                          form) or any provider's subscribe page (link)
#   SUPPORT_URL            e.g. a support/donate page
GOATCOUNTER_CODE = os.environ.get("ANALYTICS_GOATCOUNTER", "").strip()
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "").strip()
SUPPORT_URL = os.environ.get("SUPPORT_URL", "").strip()
BASE_URL = "https://www.timesofpalestine.com"
# Public corrections-ledger page (owner decision 2026-08-06): the page goes
# live only once a READER-REQUESTED correction is on the record — none has
# been yet, so it stays down. Flip to True to publish /{lang}/corrections.html
# and restore every link to it (footers, story stamps, sitemap, schema).
CORRECTIONS_PAGE_LIVE = True  # public corrections log, both editions (owner order 2026-08-16)

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
RETRACTED_PIDS = {"23ffbc910f", "7b5ecb12e4", "4b6ac6121b", "33a0debafc",
                  # 2026-08-16 owner order: six Arabic briefs published desk
                  # meta-commentary («المادة المرسلة تتضمن عنواناً فقط…») as
                  # article bodies — headline-only Telegram items the refusal
                  # screen missed in Arabic. Net extended the same day.
                  "53ab09a3cc", "0b27c584e6", "bb71af3551",
                  "cdbc2183ca", "8e66be8ab8", "cb2e25be5e",
                  # 2026-08-16 owner order: Democracy Now! daily-headlines
                  # DIGEST entries published as stories (Ecuador/CIA item
                  # categorized gaza — the bundle's tail mentioned Palestine,
                  # its head did not). The skipUrl net now blocks the class.
                  "85db8d3f64", "b575571cc3",
                  # 2026-08-09 owner order: two Ma'an items covered the same
                  # JDECO announcement; the winter-maintenance framing goes,
                  # the power-cut schedule (times, areas) stays.
                  "7eb4993857",
                  # 2026-08-22 owner order: the Netanyahu/Mamdani billboard
                  # brief misidentified New York's mayor as a "Palestinian-
                  # American legislator" — he is neither Palestinian nor a
                  # legislator. Replaced by the original
                  # netanyahu-mamdani-billboard-2026-08-22, which carries
                  # the correction note.
                  "b29d35926d"}
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
    "health", "archive", "arabaid", "women", "israelipress", "uspress",
    "prisoners", "pal48",
}
ORIGINAL_IMG_MD_RX = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
ORIGINAL_BODY_STATS = {}
ORIGINAL_SKIPS = {}      # lang -> {slug}: validator skips, for the parity gate
ORIGINALS_LOADED = {}    # lang -> {slug}: published originals, for the parity gate
STORY_PAGES_RENDERED = {}  # lang -> {href}: story pages this build ships (live + archive)
TOPIC_HUBS_LIVE = {}     # lang -> [(file-config, matched stories)]: running-file hub pages

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

# Owner decision 2026-08-06: this section covers Palestinian economic survival —
# banking access, remittances, cash and payment rails under closure — not the
# crypto industry. The freedom filter alone was too loose: a hardware-wallet
# breach story matches "self-custody" and reached the front page, which reads as
# product news under a Palestinian masthead. Anything matching the noise pattern
# is dropped unless it also carries a Palestine/region nexus, so "Gaza traders
# move to ecash after the banks close" stays and "Coldcard breach" does not.
BTC_NOISE_RX = re.compile(
    r"hardware wallet|cold ?card|ledger nano|trezor|seed phrase|firmware|"
    r"price (?:target|prediction|analysis)|all.?time high|rally|rebound|sell.?off|"
    r"bull(?:ish)?|bear(?:ish)?|market cap|etf|halving|mining (?:rig|profit|difficulty)|"
    r"hash ?rate|altcoin|memecoin|token launch|airdrop|exchange listing|"
    r"محفظة (?:أجهزة|صلبة)|سعر البيتكوين|تحليل فني|صناديق المؤشرات", re.I)
BTC_NEXUS_RX = re.compile(
    r"palestin|gaza|west bank|jerusalem|israel|middle east|arab|jordan|egypt|lebanon|"
    r"remittance|unbanked|correspondent bank|de-?risk|sanction|closure|blockade|"
    r"فلسطين|غزة|الضفة|القدس|الشرق الأوسط|تحويلات|حصار|إغلاق|عقوبات|البنوك المراسلة", re.I)

FOCUS_BOOST = 30      # score boost for editorial focus topics
RESEARCH_BOOST = 22   # think-tank / OSINT reports: "news before it becomes news"
BREAKING_BOOST = 14   # hard-news urgency: casualties, strikes, raids, ceasefires
IMAGE_BOOST = 8
RECENCY_MAX = 50      # points for a just-published story, linear decay over MAX_AGE_HOURS
HERO_MAX_AGE_H = 18   # the top story must be actual news, not a feature from days ago
HERO_WINDOWS_H = (6, 12, HERO_MAX_AGE_H)  # prefer the freshest qualifying window
# The page is alive (owner order 2026-08-09): the lead ROTATES with the build
# clock instead of squatting for hours. Every 10-minute deploy advances the
# hero among the strongest fresh stories — but only among stories of
# comparable weight, so a minor item never displaces a major one.
HERO_ROTATE_MIN = 10     # rotation step, matched to the build cadence
HERO_ROTATE_POOL = 3     # at most this many candidates share the top slot
HERO_ROTATE_FLOOR = 0.5  # a candidate needs at least half the leader's score

# Urgent hard-news markers — these stories are what readers check the site for.
BREAKING_RX = re.compile(
    r"\bkill|dead|death toll|casualt|wound|injur|strike|airstrike|bomb|shell|raid|storm|"
    r"assassinat|ceasefire|truce|escalat|evacuat|massacre|explosion|"
    r"شهيد|شهداء|قتل|مقتل|قصف|غارة|اقتحام|إصاب|جرحى|انفجار|مجزرة|تصعيد|عاجل|إخلاء", re.I)

# Features that should never lead the page, however well they score.
REVIEWISH_RX = re.compile(r"book review|review:|film review|مراجعة كتاب|عرض كتاب", re.I)

# Routine utility service notices — a distribution company announcing scheduled
# power cuts, grid maintenance, winter preparations. Useful reader service,
# never the lead of a serious front page (owner report 2026-08-09: a JDECO
# power-cut schedule ran as the main headline). The patterns require the
# UTILITY AS ACTOR doing scheduled work, so weaponized cuts — "Israel cuts
# electricity to Gaza" — stay hard news and keep their full rank.
ROUTINE_NOTICE_RX = re.compile(
    r"(?:electric(?:ity)?|power|water|telecom|internet)\s+"
    r"(?:compan(?:y|ies)|corporation|authority|distribut\w*|provider)"
    r"[^.]{0,80}?\b(?:schedul\w*|maintenance|maintain\w*|upgrad\w*|prepar\w*|"
    r"outage|cuts?|interrupt\w*|works)|"
    r"\bjerusalem (?:district )?electric(?:ity)?\b"
    r"[^.]{0,80}?\b(?:schedul\w*|maintenance|maintain\w*|prepar\w*|"
    r"read(?:y|ies|ying)|upgrad\w*|winteri[sz]\w*|grid|network)|"
    r"scheduled (?:power|electricity|water) (?:cut|outage|interruption)|"
    r"load[- ]?shedding|"
    r"شركة (?:ال)?كهرباء[^.]{0,80}?(?:قطع|فصل|صيانة|جدول|أعمال)|"
    r"كهرباء (?:القدس|محافظة)[^.]{0,80}?(?:تصون|صيانة|قطع|فصل|جدول|شبك)|"
    r"قطع مبرمج|فصل التيار[^.]{0,40}?(?:المبرمج|مبرمج|مجدول)", re.I)

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
    # Service notices inform; they don't compete with the news of the day.
    if ROUTINE_NOTICE_RX.search(hay):
        s -= 25
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

# Prisoners & Detainees (owner directive 2026-08-11): the أسرى file is a
# first-class standing section of the Palestinian press — prisoner counts,
# administrative detention, hunger strikes, releases and exchanges, prison
# conditions, the prisoners' institutions (نادي الأسير, هيئة شؤون الأسرى).
# Routed AFTER Her Story: a female prisoner's account (أسيرة/معتقلة) stays
# a Her Story lead per that section's charter rules.
PRISONERS_RX = re.compile(
    r"prisoner|detainee|administrative detention|hunger strike|"
    r"prison(?:er)?s'? (?:club|society|affairs)|prisoner (?:swap|exchange|release)|"
    r"أسير|أسرى|الأسير|الأسرى|معتقل|نادي الأسير|هيئة شؤون الأسرى|"
    r"الاعتقال الإداري|اعتقال إداري|إضراب عن الطعام|"
    r"سجون الاحتلال|السجون الإسرائيلية|تبادل أسرى|صفقة تبادل", re.I)

# Palestinians in Israel (owner directive 2026-08-21): the فلسطينيو الداخل
# file as a first-class daily section — the two million Palestinian
# citizens of Israel, the crime wave the police leave unsolved, the Naqab
# demolitions, speech prosecutions since October 7, the Follow-Up
# Committee and the Arab lists, and the workforce (40% of Israeli health
# care) treated as an internal threat. Routed AFTER Her Story and the
# prisoners file so those charters keep their leads. «الطيرة» is excluded
# deliberately — it is also Ramallah's neighborhood (the Barakat file).
PAL48_RX = re.compile(
    r"palestinian (?:citizens?|community|communities|minority) (?:of|in) israel|"
    r"arab (?:citizens?|society|communities|towns) (?:of|in) israel|"
    r"'?48 palestinians?|palestinians? inside israel|"
    r"umm al-?fahm|sakhnin|kafr qasi?m|shefa-?'?amr|shfaram|"
    r"rahat\b|tayibe|kafr kanna|arraba\b|"
    r"(?:naqab|negev) bedouin|unrecogni[sz]ed villages?|"
    r"higher (?:arab )?follow-?up committee|"
    r"فلسطيني[وي] الداخل|عرب الداخل|أهل الداخل|الداخل الفلسطيني|"
    r"عرب 48|فلسطيني[وي] 48|أراضي (?:ال)?48|الجماهير العربية|"
    r"المجتمع العربي في إسرائيل|الجريمة في المجتمع العربي|"
    r"لجنة المتابعة العليا|القائمة العربية الموحدة|"
    r"أم الفحم|سخنين|كفر قاسم|كفر كنا|شفاعمرو|عرابة البطوف|"
    r"رهط|اللقية|حورة|تل السبع|بدو النقب|قرى النقب|"
    r"القرى غير المعترف بها|مسلوب[ةي] الاعتراف", re.I)

CATEGORY_RULES = [
    ("women", WOMEN_RX),
    ("prisoners", PRISONERS_RX),
    ("pal48", PAL48_RX),
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
    # One quiet retry after a pause: Cloudflare/Substack hosts throw
    # transient 403/429/5xx at CI runner IPs, and a feed dropped for one
    # build starves its section for ten minutes (sweep 2026-08-19: eight
    # outlets 403'd in a single run). Hard failures still raise on the
    # second try and land in the feed-health warning.
    for attempt in (0, 1):
        try:
            with safe_urlopen(req, timeout=25) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            if attempt == 0 and e.code in (403, 408, 429, 500, 502, 503, 504):
                time.sleep(3)
                continue
            raise

def resolve_html_entities(text):
    """Turn WordPress HTML entities (&nbsp;, &rsquo;, …) into real characters.

    XML defines only five named entities, so a feed that publishes the HTML
    set either kills the parse outright or — because the bare-ampersand
    escape below rewrites `&rsquo;` to `&amp;rsquo;` — survives the parse and
    puts the literal string "&rsquo;" into a headline. Both are wrong. The
    five XML names are left alone; an unknown name is dropped rather than
    guessed at. Fail-open: this only ever runs over already-fetched text.
    """
    def sub(m):
        name = m.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        cp = name2codepoint.get(name)
        if cp is None:
            return ""
        ch = chr(cp)
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;"}.get(ch, ch)

    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", sub, text)


def parse_xml(raw):
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    resolved = resolve_html_entities(text)
    try:
        return ET.fromstring(resolved.encode("utf-8"))
    except ET.ParseError:
        text = re.sub(r"^.*?<\?xml", "<?xml", resolved, count=1, flags=re.S)
        text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        # A bare '<' inside text ("a < b", "<3") is an "invalid token" the
        # scrubs above miss — it cost the Amnesty AR feed a whole build
        # (sweep 2026-08-19). Escape any '<' that cannot open real markup.
        text = re.sub(r"<(?![A-Za-z/?!])", "&lt;", text)
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


# ---------- Remote lede verification: memory, pacing, transient failures ----------
# Owner report 2026-08-08: story cover PHOTOS were flickering to house SVGs at
# random between builds. Nothing was dead — the build checked twenty Wikimedia
# portraits in one burst and Commons answered HTTP 429 for a varying subset,
# which the verifier read as "no image". Three defences, in order:
#   1. A verification is remembered on disk and reused for a few hours, so the
#      site does not re-check the same twenty portraits 144 times a day — that
#      burst is what earns the 429 in the first place.
#   2. Requests to a rate-limiting host are serialised and spaced.
#   3. A 429/5xx/timeout is retried once, politely, before it counts — and if
#      it still fails, a verification inside the TTL keeps the photo published.
# A DEFINITIVE failure (404/410/403, HTML body, tracking-pixel size) still
# demotes on the spot and forgets the entry — a genuinely dead file must never
# survive behind the cache, so a removed portrait leaves the front page within
# the freshness window at worst.
REMOTE_IMAGE_CACHE = ROOT / "remote-image-cache.json"   # build state, never committed
REMOTE_IMAGE_FRESH = 6 * 3600       # re-verify at most every six hours
REMOTE_IMAGE_TTL = 3 * 86400        # a verified image stays trusted three days
REMOTE_IMAGE_MAX = 4000             # newest verifications kept, oldest dropped
REMOTE_IMAGE_TIMEOUT = 8
# Hosts that answer a rapid burst with 429. Commons is also slow under load,
# so it gets a longer timeout as well as a pacer.
THROTTLED_HOSTS = ("wikimedia.org", "wikipedia.org")
THROTTLED_TIMEOUT = 20
THROTTLE_INTERVAL = 0.5             # seconds between two requests to one host
THROTTLE_BACKOFF = 2.0              # pause before the single retry after a 429
TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}

_remote_image_lock = threading.Lock()
_remote_image_seen = None           # url -> epoch of last successful verification
_remote_image_dirty = False
_throttle_lock = threading.Lock()
_throttle_next = {}                 # host -> monotonic clock of its next free slot


def _remote_image_entries():
    """Load the on-disk verification memory once per build. Caller holds the lock."""
    global _remote_image_seen
    if _remote_image_seen is not None:
        return _remote_image_seen
    entries, now = {}, time.time()
    try:
        raw = json.loads(REMOTE_IMAGE_CACHE.read_text(encoding="utf-8"))
        for url, stamp in (raw.get("verified") or {}).items():
            # A stamp from the future is a corrupt or skewed state file, not a
            # verification: one hour of tolerance, then the entry is dropped.
            if isinstance(url, str) and isinstance(stamp, (int, float)) \
                    and -3600 < now - stamp < REMOTE_IMAGE_TTL:
                entries[url] = float(stamp)
    except (OSError, ValueError, AttributeError):
        entries = {}   # unreadable state is not a build problem — verify live
    _remote_image_seen = entries
    return entries


def remote_image_verified_within(url, window):
    with _remote_image_lock:
        stamp = _remote_image_entries().get(url)
    return stamp is not None and time.time() - stamp < window


def remember_remote_image(url, verified):
    """Record a verification, or forget one the host has definitively refused."""
    global _remote_image_dirty
    with _remote_image_lock:
        entries = _remote_image_entries()
        if verified:
            entries[url] = time.time()
        elif entries.pop(url, None) is None:
            return
        _remote_image_dirty = True


def save_remote_image_cache():
    global _remote_image_dirty
    with _remote_image_lock:
        if _remote_image_seen is None or not _remote_image_dirty:
            return
        if len(_remote_image_seen) > REMOTE_IMAGE_MAX:
            keep = sorted(_remote_image_seen.items(),
                          key=lambda kv: kv[1], reverse=True)[:REMOTE_IMAGE_MAX]
            _remote_image_seen.clear()
            _remote_image_seen.update(keep)
        payload = {"verified": dict(_remote_image_seen)}
        _remote_image_dirty = False
    try:
        REMOTE_IMAGE_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"::warning::remote image cache write failed ({type(exc).__name__})")


def throttle_key(url):
    """The pacing bucket for a URL, or "" when the host needs no pacing."""
    host = (urlsplit(url).hostname or "").lower()
    for base in THROTTLED_HOSTS:
        if host == base or host.endswith("." + base):
            return base
    return ""


def pace_request(key):
    """Space requests to a rate-limiting host so a build never bursts at it."""
    if not key:
        return
    with _throttle_lock:
        slot = max(time.monotonic(), _throttle_next.get(key, 0.0))
        _throttle_next[key] = slot + THROTTLE_INTERVAL
    delay = slot - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def probe_remote_image(url, timeout, pace=""):
    """One HEAD-then-GET probe. Returns (serves_an_image, failure_was_transient)."""
    transient = False
    for method in ("HEAD", "GET"):
        pace_request(pace)
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": UA, "Accept": "image/*,*/*;q=0.5"})
        if method == "GET":
            req.add_header("Range", "bytes=0-2047")
        try:
            with safe_urlopen(req, timeout=timeout) as r:
                if r.status not in (200, 206):
                    if method == "HEAD":
                        continue  # many CDNs reject HEAD; the ranged GET decides
                    return False, False
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if not ctype and method == "HEAD":
                    continue
                if not (ctype.startswith("image/") or (not ctype and IMAGEISH_RX.search(url))):
                    return False, False
                # Reject tracking-pixel-sized files when the server states a size.
                total = r.headers.get("Content-Range", "").rpartition("/")[2] \
                    or (r.headers.get("Content-Length") or "" if r.status == 200 else "")
                if total.isdigit() and int(total) < 600:
                    return False, False
                return True, False
        except urllib.error.HTTPError as exc:
            # 429 and the 5xx family say the host is busy, not that the file is
            # gone; 404/403/410 say the file is gone. The ranged GET is the
            # decisive probe, so its own verdict stands whatever HEAD answered.
            transient = exc.code in TRANSIENT_STATUS
            if method == "HEAD":
                continue
            return False, transient
        except (OSError, ValueError, PublishingError):
            # Resets, DNS blips and read timeouts say nothing about whether the
            # file exists — never demote a photo on their word alone.
            transient = True
            if method == "HEAD":
                continue
            return False, True
    return False, transient


@functools.lru_cache(maxsize=2048)
def remote_image_ok(url):
    """A remote lede must actually serve an image before we publish it.

    Dead og:image links, soft-404 HTML pages, hotlink walls and tracking
    pixels all render as a broken photo on the reader's side. A URL that
    fails here is treated as photoless, so the branded category cover takes
    over — never an empty frame. A host that is merely rate-limiting or
    unreachable is not evidence of a dead image: when the URL verified on a
    recent build, the photo stays published (see the section note above).
    """
    if not is_http_url(url) or not is_public_http_url(url):
        return False
    if remote_image_verified_within(url, REMOTE_IMAGE_FRESH):
        return True
    pace = throttle_key(url)
    timeout = THROTTLED_TIMEOUT if pace else REMOTE_IMAGE_TIMEOUT
    ok, transient = probe_remote_image(url, timeout, pace)
    if not ok and transient and pace:
        # The paced hosts are the ones that answer a burst with 429; give them
        # one slow retry rather than adding seconds to every wire image check.
        time.sleep(THROTTLE_BACKOFF)
        ok, transient = probe_remote_image(url, timeout, pace)
    if ok:
        remember_remote_image(url, True)
        return True
    if transient:
        if remote_image_verified_within(url, REMOTE_IMAGE_TTL):
            print(f"::warning::remote image check failed transiently — keeping the "
                  f"photo verified on an earlier build: {url}")
            return True
        return False
    remember_remote_image(url, False)
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
        # Last resort, and the riskiest: the first external href on a Google News
        # interstitial is usually googleusercontent's thumbnail, not the article.
        # Publishing that as the source URL is worse than publishing nothing —
        # it puts a CDN image in isBasedOn and misattributes the story. Exclude
        # every Google-owned host and anything that is plainly an asset.
        for candidate in re.findall(r'href=["\'](https?://[^"\']+)', page, re.I):
            host = urlsplit(candidate).netloc.lower()
            if host.endswith("google.com") or host.endswith("googleusercontent.com") \
                    or host.endswith("gstatic.com") or host.endswith("googleapis.com") \
                    or host.endswith("youtube.com") or host.endswith("youtu.be"):
                continue
            if re.search(r"\.(?:jpe?g|png|gif|webp|avif|svg|ico|css|js)(?:$|\?)", candidate, re.I):
                continue
            return canonicalize_url(html.unescape(candidate))
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
            if remote_image_ok(candidate):
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
    # Digest/roundup entries are bundles, not stories (owner report
    # 2026-08-16: a Democracy Now! daily-headlines digest published as an
    # Ecuador story categorized gaza, because Palestine appeared further
    # down the bundle). A feed's `skipUrl` regex drops such items before
    # any relevance filter can be fooled by the bundle's mixed contents.
    if feed.get("skipUrl") and re.search(feed["skipUrl"], item.get("link") or ""):
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
    if feed.get("filterBitcoinFreedom"):
        if not BTC_FREEDOM_RX.search(hay):
            return None
        # Product and market copy needs a Palestine/region nexus to earn the slot.
        if BTC_NOISE_RX.search(hay) and not BTC_NEXUS_RX.search(hay):
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
        if not date or now - date > max_age or date > now + timedelta(hours=2):
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
        observed = int(feed.get("_observed", len(items)))
        if observed == 0:
            # Feed-health visibility (site sweep 2026-08-15, issue #286): a
            # feed that yields nothing at all — before any age or Palestine
            # filter — is a dead URL or an empty source, and a section can
            # starve silently behind it. Say so where the Actions page shows
            # it. Filter-trimmed feeds (observed > 0, kept 0) stay quiet.
            print(f"::warning::feed '{feed['id']}' returned zero items — "
                  "dead URL, moved feed, or empty source; check feeds.json")
        if HEALTH:
            HEALTH.source_result(
                feed["id"], "ok", fetched=observed, accepted=len(items),
                withheld=max(0, observed - len(items)))
        return items
    except Exception as e:
        print(f"  ✗ {feed['name']}: {type(e).__name__}: {e}")
        print(f"::warning::feed '{feed['id']}' fetch failed "
              f"({type(e).__name__}) — the section it supplies gets nothing "
              "this build")
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
    r"لا (?:أستطيع|يمكنني|نستطيع|يمكن(?:نا)?)\s*(?:إنتاج|كتابة|تقديم|صياغة|إعداد)|"
    # «يتعذر» alone is an ordinary Arabic verb ("cannot be done") that belongs in
    # news prose — it once cost the PNC diaspora report its whole Arabic edition
    # (daily editor 2026-08-13). Only the refusal shape counts: the verb aimed at
    # the act of producing copy, with or without «عليّ/علينا».
    r"يتعذّ?ر\s*(?:علي(?:ّ|نا|نَا)?\s*)?(?:إنتاج|كتابة|تقديم|صياغة|إعداد|تلخيص)|"
    r"بناءً? على هذه المادة|لا (?:تتضمن|تحتوي|توجد).{0,20}(?:معلومات|أخبار)|"
    # Desk-voice meta about the source material itself (owner takedown
    # 2026-08-16: six Arabic briefs narrated «المادة المرسلة…» as bodies).
    # These phrasings are newsroom-referential and never occur in news prose.
    # «عنوان واحد/فقط» needs its desk-voice verb: bare «في عنوان واحد» is
    # ordinary prose ("summed it up in one headline") and once cost a feature
    # its whole Arabic edition (2026-08-18).
    r"المادة المرسلة|"
    r"(?:تتضمن|يتضمن|تقتصر على|يقتصر على|تحتوي على|يحتوي على)\s*"
    r"عنوانا?ً? (?:فقط|واحدا?ً?)|"
    r"دون نص (?:خبري|توضيحي)|"
    r"لا تتوفر في المصدر|(?:يستلزم|تستلزم|يتطلب) معلومات إضافية|"
    r"كموجز (?:صحفي|إخباري)|عنوان إشاري|"
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
    # تم كفعل تام («تم دون علم العائلة»، «تمت قبل عام») سليمة — الركيك هو
    # «تم» + المصدر. تُستثنى أدوات وظروف شائعة بعد تم كي لا يُتَّهم نصٌّ سليم.
    (re.compile(r"(?:^|[\s،.:«»)(])تم(?:ت)?\s+"
                r"(?!دون|بدون|ذلك|هذا|بالفعل|فعلاً|رغم|قبل|بعد|خلال|عبر|بموجب|بنجاح|أمس|اليوم)\S"),
     "«تم/تمت» مع المصدر ركيكة — استعمل الفعل المبني للمعلوم"),
    (re.compile(r"يُ?ذكر أن|تجدر الإشارة|الجدير بالذكر|ومن الجدير"),
     "حشو صحفي آلي — احذفه وادخل في المعلومة"),
]

# Foreign-script homoglyphs (owner report 2026-08-17: a published title
# carried «ترامప» with THAI ป U+0E1B for ب — and a second brief shipped the
# same character hours after the advisory net went live). Model output
# sometimes substitutes a lookalike letter from another script; no Arabic
# news sentence legitimately contains Thai, CJK, Cyrillic, Devanagari,
# Kana, Hangul — or the Persian-only letters پ/چ/ژ/گ (house style writes
# foreign names with Arabic letters: ترامب never ترامپ). Unlike style
# diction this is text CORRUPTION, so it gates HARD: a fresh brief that
# still carries one after the editor retry is refused (it regenerates next
# build), and a cached brief carrying one is scrubbed regardless of its
# style era.
# Ranges: Cyrillic (+supplement), Thaana, all Indic scripts through Sinhala
# (the second live leak was TELUGU ప U+0C2A), Thai, Lao, Myanmar, Georgian,
# Hangul jamo, Kana, CJK, Hangul syllables — plus the Persian-only letters.
FOREIGN_SCRIPT_RX = re.compile(
    "[Ѐ-ԯހ-޿ऀ-෿฀-໿"
    "က-႟Ⴀ-ჿᄀ-ᇿ぀-ヿ"
    "㄰-㆏一-鿿가-힯"
    "پچژگ]")
_AR_DICTION.append(
    (FOREIGN_SCRIPT_RX,
     "محرف من أبجدية أجنبية داخل النص العربي — استبدل الحرف الدخيل بحرف عربي"))
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


# Name-spelling net (owner order 2026-08-11, after «الهدالين» reached the
# Arabic edition for «الهذالين»): names transliterated from English or Hebrew
# are verified against Arabic-language sources and the verified forms live in
# editorial/arabic-names.json; each recorded wrong variant is flagged here
# exactly like machine diction. Variants match on Arabic word boundaries —
# a single attached prefix (و/ف/ب/ل/ك) still matches, but a variant buried
# inside a longer word does not («ادنا» must never flag «أجسادنا»).
# Fail-open: a missing or invalid lexicon disables the net, never the build.
_AR_LETTER = "ء-ي"


def _load_arabic_name_nets():
    try:
        data = json.loads((ROOT / "editorial" / "arabic-names.json")
                          .read_text(encoding="utf-8"))
        nets = []
        for entry in data.get("names", []):
            right = (entry.get("ar") or "").strip()
            for wrong in entry.get("wrong", []):
                wrong = (wrong or "").strip()
                if wrong and right and wrong not in right and right not in wrong:
                    rx = (f"(?<![{_AR_LETTER}])(?:[وفبلك]?ال|لل|[وفبلك])?"
                          f"{re.escape(wrong)}(?![{_AR_LETTER}ً-ْ])")
                    nets.append((re.compile(rx),
                                 f"الإملاء المعتمد «{right}» — راجع editorial/arabic-names.json"))
        return nets
    except Exception:
        return []


_AR_NAME_NETS = _load_arabic_name_nets()


def language_quality_issues(text, lang=None):
    """Wordings that read machine-made rather than newsroom-made.
    lang=None checks both nets (used for the cache scrub, where legacy keys
    carry no language)."""
    nets = []
    if lang in (None, "ar"):
        nets += _AR_DICTION + _AR_NAME_NETS
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
    r"set|shot|shut|sold|struck|torn|thrown|withdrawn|won)\b"
    # auxiliary-less passives (owner review 2026-08-08): a title opening on a
    # bare past participle, or "X financed/run/blocked by Y", hides the actor
    # from the subject slot just as surely as "was killed" does.
    r"|^(?:locked|killed|detained|arrested|jailed|targeted|renamed|trapped|"
    r"forced|displaced|wounded|injured|banned|barred|blocked|expelled)\b"
    r"|\b(?:now\s+|newly\s+)?(?:financed|funded|backed|owned|run|held|"
    r"blocked|banned|approved|controlled)\s+by\b", re.I)
_EN_AGENTLESS_TITLE_RX = re.compile(
    r"\b(?:changes?\s+hands|comes?\s+under|faces?\s+(?:pressure|scrutiny|"
    r"criticism|questions)|under\s+fire|remains?\s+unclear|"
    r"(?:is|are|remains?|stays?)\s+(?:stuck|trapped|frozen|unresolved|"
    r"in\s+limbo|on\s+hold))\b", re.I)
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
    # Corruption gate (2026-08-17): a homoglyph that survived the retry is
    # never "style residue" — refuse the brief; the item regenerates fresh
    # on the next build rather than publishing a corrupted headline.
    if FOREIGN_SCRIPT_RX.search(f"{new_title}\n{text}"):
        print(f"  ⊘ brief {item['pid']}: foreign-script character survived "
              "the retry — refused, will regenerate next build")
        item["brief_refused"] = True
        return None
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
        # Corruption trumps style-era exemptions (2026-08-17: the cached
        # «ترامప» headline kept republishing because current-style entries
        # skipped the quality nets). A homoglyph scrubs unconditionally.
        if FOREIGN_SCRIPT_RX.search(f"{value.get('title', '')}\n{brief}"):
            return False
        if value.get("style") != BRIEF_STYLE:
            if len(brief.split()) < MIN_BRIEF_WORDS:
                return False
            prefix = key.split(":", 1)[0]
            lang = prefix if prefix in ("en", "ar") else None
            if language_quality_issues(f"{value.get('title', '')}\n{brief}", lang):
                return False
        return True

    _pre_scrub = len(cache)
    cache = {key: value for key, value in cache.items() if _entry_ok(key, value)}
    cache_dirty = len(cache) != _pre_scrub  # persist the scrub even on warm runs
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
    # Bounded per-call: the SDK default (600 s × retries) could push the whole
    # build past its job timeout during a provider outage and stall the site.
    client = anthropic.Anthropic(api_key=key, timeout=45.0, max_retries=1)

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
    cache = {k: v for k, v in cache.items() if now_ts - v.get("ts", 0) < 14 * 86400}
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
        if not ARABIC_CHARS_RX.search(item["title"])
    ]
    # Wrong-script deks never render (owner report 2026-08-11: an Arabic feed
    # summary ran under an English hero headline). The old scrub trusted the
    # feed's needs_translation flag, but mixed-language sources ship without
    # it — so the guard reads the text itself, both editions. When the house
    # brief exists, its opening paragraph becomes the dek (our copy, right
    # language); otherwise the dek drops rather than leak.
    def _dek_fits(item):
        dek = item.get("dek") or ""
        if not dek:
            return True
        if item["lang"] == "en":
            return not ARABIC_CHARS_RX.search(dek)
        return bool(ARABIC_CHARS_RX.search(dek)) or not re.search(r"[A-Za-z]", dek)
    for item in en_items + ar_items:
        if item.get("original") or _dek_fits(item):
            continue
        brief = item.get("brief") or ""
        item["dek"] = (truncate(brief.split("\n")[0].strip(), 220)
                       if brief and not REFUSAL_RX.search(brief) else "")

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
    event_tokens, near_identical, place_or_count_veto, same_coverage,
    same_event, same_story,
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
        # The house brief, once written, is the richest same-language account
        # of the story — and for wire items translated from Arabic feeds the
        # dek was blanked, leaving the coverage nets nothing to compare
        # (owner report 2026-08-09: two rewrites of one JDECO announcement
        # ran side by side in The Latest). Prefer it over the feed dek.
        body = it.get("brief") or it.get("dek") or ""
        ext = event_tokens(f"{it['title']} {body[:240]}")
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


# ---------- AI duplicate judge (owner order 2026-08-09) ----------
# Root cause of every "double article" the owner has reported: the lexical
# nets above decide "same event?" by counting shared WORDS, and one event
# written two ways often shares almost none ("Jerusalem Electricity readies
# grid for winter" vs "Jerusalem electricity company cuts power across West
# Bank areas" — one JDECO announcement, two words in common). Each past fix
# added another word-matching net tuned to the last incident; the next
# paraphrase slipped through the gaps by construction. Judging event identity
# is a language-understanding task, so the newsroom model adjudicates it:
# after the lexical nets, suspect pairs (close in time, some shared
# substance, no place/count contradiction) go to the briefs model with one
# question — one story or two? Verdicts are cached by story-pair in the
# briefs cache (14-day prune covers the 72h item lifetime many times over),
# so each pair costs one small call EVER, and the judge is fail-open: no
# key, no package, or a provider outage simply leaves the lexical verdict
# standing.
DEDUPE_JUDGE_SYSTEM = (
    "You are the duplicate desk of a serious newspaper. You are shown two "
    "published news items, each as a headline and summary. Decide whether a "
    "careful newspaper would run them as ONE article or TWO. Answer DUPLICATE "
    "only when both items report the same underlying event, announcement or "
    "development — the same actor taking the same action on the same occasion, "
    "even under different framing (a utility announcing maintenance work and "
    "the outages that work causes is ONE announcement; an updated casualty "
    "toll of the same incident is ONE story). Answer SEPARATE when they are "
    "distinct events, even if related, on the same topic, or involving the "
    "same actor: two different strikes, a statement and a later vote, two "
    "separate announcements. When uncertain, answer SEPARATE. Reply with "
    "exactly one word: DUPLICATE or SEPARATE."
)
MAX_DEDUPE_VERDICTS_PER_RUN = 40   # per build; the pair cache carries the rest
DEDUPE_PAIR_WINDOW_H = 36          # matches the lexical nets' window


def _judge_pair_key(lang, pid_a, pid_b):
    return f"dupe:{lang}:" + ":".join(sorted((pid_a, pid_b)))


def _duplicate_verdict(client, a, b):
    """One story or two, per the newsroom model. None = no usable verdict."""
    def block(it):
        body = (it.get("brief") or it.get("dek") or "")[:400]
        return f"HEADLINE: {it['title']}\nSUMMARY: {body or '(none)'}"
    try:
        response = client.messages.create(
            model=BRIEFS_MODEL, max_tokens=8, system=DEDUPE_JUDGE_SYSTEM,
            messages=[{"role": "user",
                       "content": f"ITEM ONE\n{block(a)}\n\nITEM TWO\n{block(b)}"}])
        word = "".join(
            bk.text for bk in response.content if bk.type == "text").strip().upper()
    except Exception as exc:  # provider outage: the lexical verdict stands
        print(f"  ✗ dedupe verdict failed ({type(exc).__name__})")
        return None
    if word.startswith("DUPLICATE"):
        return True
    if word.startswith("SEPARATE"):
        return False
    return None  # unparseable — not cached, so the next build asks again


def adjudicate_duplicates(en_items, ar_items, client=None):
    """Fold paraphrase-level duplicates the lexical nets cannot see.

    Runs on FINAL published copy (post-briefs), per language. Candidate
    pairs share at least two meaningful tokens across title+summary, sit
    within the lexical window, and pass the place/count veto — the same
    conservative guard the lexical nets use, so items the record already
    contradicts are never even asked about. Two originals never fold (the
    desk curates those). Returns (en, ar, dropped_count)."""
    try:
        cache = json.loads(BRIEFS_CACHE.read_text(encoding="utf-8")) \
            if BRIEFS_CACHE.exists() else {}
    except (OSError, json.JSONDecodeError):
        cache = {}
    budget = MAX_DEDUPE_VERDICTS_PER_RUN
    dirty, dropped_total, out = False, 0, {}
    for lang, items in (("en", en_items), ("ar", ar_items)):
        ranked = sorted(items, key=lambda i: (
            i["source_id"] == "top-original", bool(i.get("partner")), i["score"]
        ), reverse=True)
        ext = {id(i): event_tokens(
            f"{i['title']} {(i.get('brief') or i.get('dek') or '')[:240]}")
            for i in items}
        pairs = []
        for x in range(len(ranked)):
            for y in range(x + 1, len(ranked)):
                a, b = ranked[x], ranked[y]
                if a.get("original") and b.get("original"):
                    continue
                if abs((a["date"] - b["date"]).total_seconds()) > DEDUPE_PAIR_WINDOW_H * 3600:
                    continue
                shared = ext[id(a)] & ext[id(b)]
                if len(shared) < 2:
                    continue
                if place_or_count_veto(ext[id(a)], ext[id(b)]):
                    continue
                pairs.append((len(shared), x, y))
        pairs.sort(reverse=True)  # judge the most suspicious pairs first
        drop = set()
        for _, x, y in pairs:
            a, b = ranked[x], ranked[y]
            if id(a) in drop or id(b) in drop:
                continue
            key = _judge_pair_key(lang, a["pid"], b["pid"])
            entry = cache.get(key)
            verdict = entry.get("same") if isinstance(entry, dict) else None
            if verdict is None:
                if client is None or budget <= 0:
                    continue
                budget -= 1
                verdict = _duplicate_verdict(client, a, b)
                if verdict is None:
                    continue
                cache[key] = {"same": verdict,
                              "ts": datetime.now(timezone.utc).timestamp()}
                dirty = True
            if verdict:
                existing = {(s.get("name", ""), s.get("url", ""))
                            for s in a.get("corroborating_sources", [])}
                for source in b.get("corroborating_sources", []):
                    skey = (source.get("name", ""), source.get("url", ""))
                    if skey not in existing:
                        a.setdefault("corroborating_sources", []).append(source)
                        existing.add(skey)
                drop.add(id(b))
                dropped_total += 1
                print(f"  ⊘ duplicate event dropped (AI judge): "
                      f"{b['source']}: {b['title'][:70]}")
        out[lang] = [i for i in items if id(i) not in drop]
    if dirty:
        save_brief_cache(cache)
    return out["en"], out["ar"], dropped_total


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
    r"key\s+findings?|at\s+a\s+glance|what\s+to\s+watch|why\s+(this|it)\s+matters|"
    r"in\s+summary|summary|conclusions?|bottom\s+line|looking\s+ahead|what('|’)s\s+next|"
    r"sources?(\s+and\s+documents)?|bibliograph\w+|references|further\s+reading|"
    r"methodolog\w+[^\n]{0,30}|corrections?|"
    r"ما\s+(الذي\s+)?(لم\s+يُ?حسم|يبقى\s+(مجهولاً|معلقاً|غامضاً))|"
    r"أسئلة\s+(مفتوحة|بلا\s+إجابة|عالقة)|الخلاصة|خلاصة[^\n]{0,20}|استنتاجات?|ما\s+التالي|"
    r"المصادر(\s+والوثائق)?|المراجع|المنهجية[^\n]{0,30}|التصحيحات|"
    r"أبرز\s+النتائج|النقاط\s+الرئيسية)\s*$",
    re.I | re.M)
_QUESTION_ITEM_RX = re.compile(r"^(?:[-*]|\d{1,2}\.)\s+.*[?؟]\**\s*$", re.M)
_QUESTION_HEADING_RX = re.compile(r"^#{2,4}\s*[^\n]*[?؟]\s*$", re.M)


def memo_style_warnings(body):
    found = []
    m = MEMO_HEADING_RX.search(body)
    if m:
        found.append(f"briefing-memo heading {m.group(0).strip()!r}")
    qh = _QUESTION_HEADING_RX.search(body)
    if qh:
        found.append(f"question-form heading {qh.group(0).strip()!r} — "
                     "subheads state findings, they don't ask")
    # Owner review 2026-08-08: question lists used to hide mid-article, so the
    # scan covers the whole body, not just the closing blocks.
    blocks = [b.strip() for b in body.strip().split("\n\n") if b.strip()]
    for block in blocks:
        q_items = _QUESTION_ITEM_RX.findall(block)
        if len(q_items) >= 2:
            found.append("list of questions — report the "
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
    # Pacing watch (owner order 2026-08-03): originals are hand-paced, so the
    # renderer never reflows them — instead any paragraph past ~70 words is
    # flagged loudly here for the daily editor cycle to split.
    long_paras = sum(
        1 for p in re.split(r"\n\s*\n", body)
        if not p.lstrip().startswith(("#", "-", "*", ">", "|", "!", "1", "2",
                                      "3", "4", "5", "6", "7", "8", "9"))
        and len(p.split()) > 70)
    if long_paras:
        print(f"  ⚠ original pacing {path.name}: {long_paras} paragraph(s) "
              "over 70 words — split at sentence boundaries")

    if errors:
        raise PublishingError(f"{path.name}: {'; '.join(errors)}")
    if residue_warnings:
        raise OriginalSkipError(
            f"{path.name}: unsafe rendered markup: {'; '.join(residue_warnings)}")


def category_cover(cat, lang=None, n=0):
    """Branded category-cover filename for a photoless story.

    Alternates the A/B(/C/D) variants by n so adjacent cards never show twin
    covers, and on the Arabic edition prefers the Arabic-primary `-ar`
    sibling when one exists (owner visual sweep 2026-08-11: house artwork
    must not speak English first on /ar/). Falls back through the base
    category cover to the news cover; always returns a filename, which the
    caller existence-checks before attaching."""
    variants = [""]
    for suf in ("-b", "-c", "-d"):
        if (ROOT / "originals" / "media"
                / f"times-of-palestine-cover-{cat}{suf}.svg").is_file():
            variants.append(suf)
    cover = f"times-of-palestine-cover-{cat}{variants[(n or 0) % len(variants)]}.svg"
    if not (ROOT / "originals" / "media" / cover).is_file():
        cover = f"times-of-palestine-cover-{cat}.svg"
    if not (ROOT / "originals" / "media" / cover).is_file():
        cover = "times-of-palestine-cover-news.svg"
    if lang == "ar":
        ar = cover.replace(".svg", "-ar.svg")
        if (ROOT / "originals" / "media" / ar).is_file():
            cover = ar
    return cover


_shared_cover_cycle = {}


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
        if not meta.get("image"):
            print(f"  ⚠ original {path.name}: no image: header — every original "
                  "carries a lede visual (photo-conversion queue)")
        try:
            validate_original(path, meta, body, lang, now, date)
        except OriginalSkipError as error:
            print(f"::warning::original skipped: {error}")
            if HEALTH:
                HEALTH.hold("original_skipped")
            ORIGINAL_SKIPS.setdefault(lang, set()).add(_original_slug(path.stem))
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
        if item["lang"] == "ar" and (item.get("image") or "").endswith(".svg"):
            # Arabic edition leads with Arabic-first art (owner evaluation
            # 2026-08-07): a house SVG named <lede>-ar.svg, with the text
            # hierarchy flipped, replaces the shared lede on AR pages only.
            _arv = item["image"][:-4] + "-ar.svg"
            if (ROOT / "originals" / "media" / _arv.rsplit("/", 1)[-1]).is_file():
                attach_media(item, _arv, local_original=True)
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
            cover = category_cover(item["cat"], item.get("lang"), _n)
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
        ORIGINALS_LOADED.setdefault(lang, set()).add(_original_slug(path.stem))
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

# Running-file hub definitions (owner order 2026-08-16): slug, bilingual
# name/dek, and the case-insensitive pattern that collects a file's stories.
TOPIC_FILES = load_editorial_json(
    ROOT / "editorial" / "topic-files.json", {}).get("files", [])


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
        # A bad override must never freeze the build (rights error downstream)
        # or publish a dead frame — it degrades to the category cover, loudly.
        if target != "cover":
            problem = None
            if is_http_url(target):
                if not media_rights_for(target, MEDIA_RIGHTS):
                    problem = "remote URL has no media-rights.json entry"
                elif not remote_image_ok(target):
                    problem = "remote image failed live verification"
            else:
                _name = target.rsplit("/", 1)[-1]
                if not (ROOT / "originals" / "media" / _name).is_file():
                    problem = "local media file missing"
                elif (not __import__("longform").house_asset(_name)
                      and not media_rights_for(target, MEDIA_RIGHTS)):
                    problem = "local media lacks rights metadata"
            if problem:
                print(f"::warning::image override {it.get('pid')}: {problem} "
                      "— falling back to the category cover")
                if HEALTH:
                    HEALTH.hold("image_override_invalid")
                target = "cover"
        if target == "cover":
            _n = _shared_cover_cycle.get(it["cat"], 0)
            _shared_cover_cycle[it["cat"]] = _n + 1
            it["image"] = f"/media/{category_cover(it['cat'], it.get('lang'), _n)}"
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
            _n = _shared_cover_cycle.get(it["cat"], 0)
            _shared_cover_cycle[it["cat"]] = _n + 1
            it["image"] = f"/media/{category_cover(it['cat'], it.get('lang'), _n)}"
            it["media"] = {"credit": "Graphic: Times of Palestine",
                           "rightsBasis": "owned",
                           "source": "Times of Palestine", "licenseUrl": None}
        else:
            seen.add(key)

def break_cover_twins(seq):
    """Adjacent cards must never show identical cover art (visual audit
    2026-08-16: two same-variant Gaza covers ran side by side — the
    assignment-order cycle can't see display adjacency). Walk a display
    sequence; when an item repeats the previous card's house cover, step it
    to the next variant that exists on disk. Mutates items — harmless, every
    variant is correct art for its category."""
    prev = None
    for it in seq:
        img = it.get("image") or ""
        if img == prev and img.startswith("/media/times-of-palestine-cover-"):
            m = re.match(r"(/media/times-of-palestine-cover-[a-z]+?)"
                         r"(-b|-c|-d)?((?:-ar)?\.svg)$", img)
            if m:
                base, var, tail = m.group(1), m.group(2) or "", m.group(3)
                order = ["", "-b", "-c", "-d"]
                i = order.index(var) if var in order else 0
                for k in range(1, len(order)):
                    cand = f"{base}{order[(i + k) % len(order)]}{tail}"
                    if (ROOT / "originals" / "media"
                            / cand.rsplit("/", 1)[-1]).is_file():
                        it["image"] = cand
                        break
        prev = it.get("image") or ""
    return seq


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
            cover = category_cover(it["cat"], lang, n)
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
                     "prisoners": "Prisoners & Detainees",
                     "pal48": "Palestinians in Israel",
                     "israelipress": "Israeli Press",
                     "uspress": "US Press",
                     "humans": "Real Lives", "health": "Health & Healing",
                     "women": "Her Story",
                     "arabaid": "Arab Support",
                     "archive": "From the Archive",
                     "diaspora": "The Diaspora",
                     "arts": "Culture & Arts", "sports": "Sport",
                     "accountability": "Transparency & Accountability",
                     "research": "Research & Investigations",
                     "bitcoin": "Money & Access",
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
        "byline": "By the Times of Palestine Newsdesk",
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
                     "prisoners": "الأسرى",
                     "pal48": "فلسطينيو الداخل",
                     "israelipress": "الصحافة الإسرائيلية",
                     "uspress": "الصحافة الأميركية",
                     "humans": "حكايات فلسطينية", "health": "الصحة والتعافي",
                     "women": "حكايتها",
                     "arabaid": "الإسناد العربي",
                     "archive": "من الأرشيف",
                     "diaspora": "الشتات الفلسطيني",
                     "arts": "الثقافة والفنون", "sports": "رياضة",
                     "accountability": "شفافية ومساءلة",
                     "research": "أبحاث وتحقيقات",
                     "bitcoin": "المال والوصول",
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
(function(){var f=document.getElementById("livefab"),w=document.getElementById("livewrap");if(!f||!w)return;
try{if(sessionStorage.getItem("top-live-hide")){w.hidden=true;return}}catch(e){}
var ID=f.dataset.video,TITLE=f.dataset.title,dock=null;
function close(){if(dock){dock.remove();dock=null}w.hidden=false}
document.getElementById("livehide").addEventListener("click",function(){
 w.hidden=true;try{sessionStorage.setItem("top-live-hide","1")}catch(err){}});
f.addEventListener("click",function(){w.hidden=true;
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
    # Two sibling buttons (owner review 2026-08-08): a dismiss control nested
    # inside the open-stream button was unreachable by keyboard.
    return (f'<div id="livewrap" class="livewrap">'
            f'<button id="livefab" class="livefab" data-video="{esc(tv["id"])}" '
            f'data-title="{esc(tv["label"])}" data-close="{esc(close_label)}" '
            f'aria-label="{esc(tv["label"])}">'
            f'<span class="dot"></span>{esc(tv["word"])}</button>'
            f'<button id="livehide" class="fab-x" aria-label="{esc(hide_label)}">'
            f'<span>✕</span></button></div>'
            f'<script>{_LIVE_JS}</script>')

SECTION_ORDER = {
    "en": ["gaza", "westbank", "pal48", "prisoners", "israelipress", "uspress", "women", "arabaid", "research", "health", "humans", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news", "archive"],
    "ar": ["gaza", "westbank", "pal48", "prisoners", "israelipress", "uspress", "women", "arabaid", "research", "health", "humans", "social", "bitcoin", "diaspora", "arts", "sports",
           "accountability", "politics", "economy", "opinion", "news", "archive"],
}
FOCUS_SECTIONS = {"pal48", "prisoners", "israelipress", "uspress", "research", "diaspora", "arts", "sports", "accountability", "bitcoin", "social", "health", "archive", "arabaid", "women"}  # shown even with one story

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
html{scroll-behavior:smooth;scroll-padding-top:64px;-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.65;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}
/* Typographic finish: multi-line headlines balance their rag; running
   story copy avoids orphans. Progressive — older engines ignore both. */
h1,h2,h3{text-wrap:balance}
.story .summary p,.dek,.hero .dek{text-wrap:pretty}
::selection{background:var(--red);color:#fff}
/* One house focus ring for keyboard readers, everywhere — links, buttons,
   controls; replaces the browser's inconsistent defaults. */
:focus-visible{outline:2px solid var(--red);outline-offset:2px}
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
.ticker.paused .rail{overflow-x:auto}
.ticker.paused .track{animation:none;white-space:normal;flex-wrap:wrap}
.tick-pause{background:transparent;border:0;color:#fff;cursor:pointer;font-size:.8rem;padding:.45rem .7rem;flex-shrink:0;z-index:2;opacity:.85}
.tick-pause:hover,.tick-pause:focus-visible{opacity:1}
.ticker a{font-size:.82rem;font-weight:600}
.ticker a::before{content:"●";color:rgba(255,255,255,.55);margin-inline-end:.7rem;font-size:.55rem;vertical-align:2px}
@keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@keyframes tick-rtl{from{transform:translateX(0)}to{transform:translateX(50%)}}
/* Masthead — the newsweekly register (owner orders 2026-08-06): a towering
   flag-red Roman-serif TIMES with OF PALESTINE in spaced caps beneath —
   frameless on the site, the way the great newsweekly runs its own web
   masthead; the red cover FRAME is reserved for brand art (og-banner, app
   icons). The Palestinian flag rule stays under the wordmark — the red
   serif carries the authority, the flag says whose. House --red only. */
.masthead{background:var(--card);border-bottom:2px solid var(--line);text-align:center;padding:1.1rem 0 .8rem}
.masthead .logotype{display:inline-block}
.masthead .wrap::after{content:"";display:block;margin:.55rem auto 0;width:130px;height:5px;background:linear-gradient(90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
[dir=rtl] .masthead .wrap::after{background:linear-gradient(-90deg,var(--black) 0 34%,var(--red) 34% 67%,var(--green) 67% 100%)}
.masthead h1,.masthead .wordmark{display:flex;flex-direction:column;align-items:center;gap:.3rem;line-height:1;white-space:nowrap}
.masthead .l1{font-family:"Times New Roman",Times,var(--serif);font-weight:700;letter-spacing:-.02em;color:var(--red);font-size:clamp(2.7rem,7.6vw,4.4rem);transform:scaleY(1.05)}
.masthead .l2{font-family:var(--serif);font-weight:700;color:var(--ink);font-size:clamp(.68rem,1.8vw,.98rem);letter-spacing:.42em;text-indent:.42em}
[lang=ar] .masthead .l1{font-family:"Noto Kufi Arabic","Amiri",serif;font-weight:800;letter-spacing:0;transform:none;font-size:clamp(2.2rem,6.8vw,3.5rem);line-height:1.2}
[lang=ar] .masthead .l2{letter-spacing:0;text-indent:0;font-family:"Noto Kufi Arabic","Amiri",serif;font-size:clamp(.95rem,2.3vw,1.2rem);line-height:1.45}
/* Tagline removed from the masthead (owner order 2026-08-11: the top of the
   page stays sharp and tight — the About page carries the mission line). */
.masthead.compact{padding:.8rem 0 .6rem}
.masthead.compact .l1{font-size:1.6rem}
.masthead.compact .l2{font-size:.52rem;letter-spacing:.34em;text-indent:.34em}
[lang=ar] .masthead.compact .l1{font-size:1.4rem}
[lang=ar] .masthead.compact .l2{font-size:.66rem}
nav.sections{position:sticky;top:0;background:rgba(11,11,12,.97);z-index:50;box-shadow:0 2px 12px rgba(0,0,0,.3);backdrop-filter:blur(4px);transition:transform .22s ease}
nav.sections.navhide{transform:translateY(-110%)}
@media (prefers-reduced-motion:reduce){nav.sections{transition:none}}
nav.sections .wrap{display:flex;flex-wrap:wrap;align-items:stretch;gap:.15rem;padding-block:.15rem}
nav.sections a{color:#d8d8e2;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:.68rem .7rem;white-space:nowrap;border-block-end:2px solid transparent;transition:color var(--tr),border-color var(--tr)}
[lang=ar] nav.sections a{letter-spacing:0;font-size:.8rem}
nav.sections a:hover{color:#fff;border-block-end-color:#3a3a42}
nav.sections a.home{color:#f93549}
nav.sections a.home:hover{border-block-end-color:#f93549}
nav.sections a.tip{color:#3fd07c}
nav.sections a.tip:hover{border-block-end-color:#3fd07c}
nav.sections a.tip .signal-glyph{vertical-align:-2.5px;margin-inline-end:.15rem}
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
/* The All-Sections index (owner decision 2026-08-06): one full-width panel,
   the old four groups as scannable column headings. Anchors to the nav on
   every width so the flat row's scroll never clips it. */
nav.sections .nav-group.all{position:static}
nav.sections .nav-drop.mega{inset-inline:0;min-width:0;border-inline:0;padding:1rem clamp(16px,2.5vw,26px) 1.2rem}
nav.sections .nav-group.open .nav-drop.mega{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.2rem 1.6rem;align-items:start}
@media(hover:hover){nav.sections .nav-group.all:hover .nav-drop.mega,nav.sections .nav-group.all:focus-within .nav-drop.mega{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.2rem 1.6rem;align-items:start}}
nav.sections .mcol{min-width:0}
nav.sections .mhead{color:#c7a86b;font-size:.62rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;padding:.5rem 1rem .2rem;border-block-end:1px solid rgba(255,255,255,.12);margin-block-end:.25rem}
[lang=ar] nav.sections .mhead{letter-spacing:0;font-size:.76rem}
nav.sections a.special{color:#c7a86b}
/* Gold specials strip: first row of the All-Sections panel, spanning every
   column, so the three gold taps show without scrolling (owner order
   2026-08-11). Links sit inline as chips, not stacked like column links. */
nav.sections .nav-drop.mega .mspecials{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:.1rem .4rem;padding:.15rem .4rem .5rem;border-block-end:1px solid rgba(199,168,107,.35);margin-block-end:.3rem}
nav.sections .nav-drop.mega .mspecials a{display:inline-block;padding:.45rem .6rem;border-block-end:0;font-size:.7rem}
[lang=ar] nav.sections .nav-drop.mega .mspecials a{font-size:.8rem}
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
  nav.sections .wrap{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}
  nav.sections .wrap::-webkit-scrollbar{display:none}
  nav.sections a{padding-block:.85rem}
  nav.sections .nav-gbtn{padding-block:.85rem}
  nav.sections .nav-group{position:static}
  nav.sections .nav-drop{inset-inline:0;top:100%;min-width:0;border-inline:0}
  /* iOS Safari clips absolutely-positioned panels inside a composited
     scroll row even though their anchor (the sticky nav) sits outside it —
     the tap toggled .open but nothing ever painted (owner report
     2026-08-06). An OPEN panel therefore goes position:fixed, pinned
     under the bar at the offset the toggle JS measures into
     --navdrop-top; fixed boxes escape every scroll container by
     construction. Scrolling closes open panels (see nav script). */
  nav.sections .nav-group.open .nav-drop{position:fixed;inset-inline:0;top:var(--navdrop-top,0px)}
  nav.sections .nav-group.open .nav-drop.mega,
  nav.sections .nav-group.all:hover .nav-drop.mega,
  nav.sections .nav-group.all:focus-within .nav-drop.mega{grid-template-columns:1fr;max-height:72vh;overflow-y:auto;gap:.1rem}
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
.hero-imgwrap.graphic>a>img{filter:brightness(.52) saturate(.85)}
.hero-imgwrap.graphic .hero-overlay{background:linear-gradient(to top,rgba(4,4,6,.97) 0%,rgba(4,4,6,.9) 45%,rgba(4,4,6,.62) 78%,rgba(4,4,6,.32) 100%)}
.dupvar1{filter:hue-rotate(12deg) brightness(1.05)}
.dupvar2{filter:hue-rotate(-12deg) saturate(1.1)}
.hero-overlay .label{color:#ff606d;font-size:.68rem;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin-bottom:.45rem;display:block}
[lang=ar] .hero-overlay .label{letter-spacing:.04em;font-size:.78rem}
.hero-overlay h2{font-family:var(--serif);font-weight:900;font-size:clamp(1.5rem,2.9vw,2.5rem);line-height:1.14;color:#fff;text-shadow:0 1px 6px rgba(0,0,0,.5)}
[lang=ar] .hero-overlay h2{line-height:1.5;font-weight:800}
.hero-overlay h2 a{color:#fff}
.hero-overlay h2 a:hover{color:#ffd0d4}
.hero .dek{margin-top:.8rem;font-size:1rem;color:var(--muted);font-family:var(--serif);line-height:1.6;max-width:64ch}
.hero .dek a,.research-feat .dek a{text-decoration:underline;text-underline-offset:2px}
.hero .dek a{color:var(--ink)}
[lang=ar] .hero .dek{line-height:1.8}
.hero-overlay .meta{display:flex;align-items:center;gap:.6rem;margin-top:.65rem;font-size:.74rem;color:rgba(255,255,255,.62)}
.hero-overlay .meta .src{color:#3fd07c;font-weight:800;text-transform:uppercase;letter-spacing:.06em}
[lang=ar] .hero-overlay .meta .src{letter-spacing:0}
.hero-overlay .meta .t{font-weight:600;color:rgba(255,255,255,.7)}
.photocredit{font-size:.66rem;color:var(--muted);margin-top:.35rem}
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
.livewrap{position:fixed;bottom:calc(1rem + env(safe-area-inset-bottom,0px));inset-inline-start:1rem;z-index:70;display:inline-flex;align-items:center}
.livefab{display:inline-flex;align-items:center;gap:.4rem;background:var(--red);color:#fff;border:0;border-radius:2rem;font:800 .74rem/1 var(--sans);letter-spacing:.06em;padding:.48rem .9rem;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.35)}
[lang=ar] .livefab{letter-spacing:0;font-size:.84rem}
.livefab .dot{width:8px;height:8px;border-radius:50%;background:#fff;animation:pulse 1.6s infinite}
.livewrap .fab-x{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;background:none;border:0;padding:0;cursor:pointer}
.livewrap .fab-x span{display:inline-flex;align-items:center;justify-content:center;width:1.35rem;height:1.35rem;border-radius:50%;background:rgba(0,0,0,.38);color:#fff;font-size:.68rem;line-height:1}
.livewrap .fab-x:hover span,.livewrap .fab-x:focus-visible span{background:rgba(0,0,0,.6)}
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
.litetoggle{background:none;border:1px solid rgba(128,128,128,.55);border-radius:3px;cursor:pointer;font-family:var(--sans);font-size:.74rem;font-weight:800;line-height:1;padding:.24rem .4rem;color:inherit;opacity:1}
.litetoggle:hover{opacity:1}
[data-lite] .litetoggle{color:#3fd07c;border-color:#3fd07c;opacity:1}
[data-lite] .hero-imgwrap>a,[data-lite] .sub-thumb,[data-lite] .lt-thumb,[data-lite] .card>a:first-child,[data-lite] .card .ph,[data-lite] .rowcard img,[data-lite] .rowcard .ph,[data-lite] .research-feat img,[data-lite] .research-feat .noimg,[data-lite] .fr-card img,[data-lite] .livedock,[data-lite] .story img.lede,[data-lite] .story div.lede,[data-lite] .photocredit,[data-lite] .embed,[data-lite] .qrbox,[data-lite] .livewrap,[data-lite] .story figure.lf{display:none!important}
[data-lite] .hero-imgwrap{background:none;border-radius:0}
[data-lite] .hero-overlay{position:static;padding:0;background:none}
[data-lite] .hero-imgwrap.graphic .hero-overlay{background:none}
[data-lite] .hero-imgwrap.graphic>a>img{filter:none}
[data-lite] .hero-imgwrap>a>img{height:auto}
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
.searchres a{font-weight:800;color:var(--ink)}
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
.card img[src$=".svg"],.rowcard img[src$=".svg"],.research-feat img[src$=".svg"]{object-fit:contain;background:#101013}
@media(hover:none){h3 a:hover,.card h3 a:hover,.hero-overlay h2 a:hover{color:inherit}}
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
/* Newsletter band (owner order 2026-08-10): a quiet inline signup above the
   footer — never a pop-up (owner rule 2026-08-02). All tokens, so both
   themes come for free. */
.newsband{background:var(--card);border-top:3px solid var(--green);border-bottom:1px solid var(--line);text-align:center;padding-block:1.9rem 1.7rem}
.newsband .kick{font-size:.66rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:var(--green-deep)}
[lang=ar] .newsband .kick{letter-spacing:0;font-size:.8rem}
.newsband h2{font-family:var(--serif);font-weight:900;font-size:1.45rem;margin-top:.45rem;color:var(--ink)}
[lang=ar] .newsband h2{font-weight:700;font-size:1.5rem}
.newsband .nb-form{margin-top:1rem;display:flex;justify-content:center;align-items:stretch;gap:.5rem;flex-wrap:wrap}
.newsband .nb-form input{inline-size:min(340px,72vw);padding:.7rem .9rem;font-size:.9rem;font-family:var(--sans);color:var(--ink);background:var(--paper);border:1px solid var(--line-dark);border-radius:var(--r)}
.newsband .nb-form input:focus-visible{outline:2px solid var(--green);outline-offset:1px}
.newsband .nb-form button,.newsband .nb-link{display:inline-block;background:var(--red);color:#fff;font-family:var(--sans);font-weight:800;font-size:.85rem;padding:.7rem 1.5rem;border:0;border-radius:var(--r);cursor:pointer;transition:opacity var(--tr)}
.newsband .nb-form button:hover,.newsband .nb-link:hover{opacity:.88}
.newsband .nb-sub{margin-top:.7rem;font-size:.72rem;color:var(--muted)}
[lang=ar] .newsband .nb-sub{font-size:.82rem}
/* ── story page ── */
.story{max-width:820px;margin-inline:auto;padding:2rem 20px 1rem}
.breadcrumbs{display:flex;flex-wrap:wrap;gap:.35rem .55rem;margin-bottom:1rem;font-size:.74rem;font-weight:700;color:var(--muted)}
.breadcrumbs a:hover{color:var(--red)}
.breadcrumbs .sep{color:var(--muted)}
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
.story .desk-note{margin-top:.4rem;font-size:.72rem;color:var(--muted);line-height:1.6}
.story .desk-note a{color:var(--green-deep);font-weight:700}
[lang=ar] .story .desk-note{font-size:.82rem}
.story-toc{margin-top:1.35rem;padding:1rem 1.1rem;border:1px solid var(--line-dark);background:var(--card);border-radius:var(--r)}
.story-toc .toc-title{font-size:.72rem;font-weight:900;letter-spacing:.1em;text-transform:uppercase;color:var(--red);margin-bottom:.7rem}
[lang=ar] .story-toc .toc-title{letter-spacing:.03em;font-size:.82rem}
.story-toc ol{padding-inline-start:1.2rem;display:grid;gap:.45rem}
.story-toc a{font-weight:700;text-decoration:underline;text-underline-offset:2px}
.story h2.sub[id]{scroll-margin-top:84px;position:relative}
.story h2.sub .anchor{margin-inline-start:.45rem;color:var(--muted);font-size:.8rem;opacity:0;transition:opacity var(--tr)}
.story h2.sub:hover .anchor,.story h2.sub:focus-within .anchor{opacity:1}
.story .summary{margin-top:1.1rem;font-family:var(--serif);font-size:1.14rem;line-height:1.82;color:#26262e;max-width:42.5rem}
/* Story polish (owner directive 2026-08-11): progress bar, drop cap, end slug */
.readbar{position:fixed;top:0;inset-inline:0;height:3px;z-index:120;pointer-events:none}
.readbar span{display:block;height:100%;width:0;margin-inline-end:auto;background:var(--red)}
.story .opener::first-letter{font-family:var(--serif);font-weight:900;font-size:3.2em;line-height:.82;float:inline-start;padding:.06em .12em 0 0;color:var(--red)}
[lang=ar] .story .opener::first-letter{font-size:inherit;font-weight:inherit;font-family:inherit;line-height:inherit;float:none;padding:0;color:inherit}
.story .closer::after{content:"■";color:var(--red);font-size:.55em;margin-inline-start:.45rem;vertical-align:.15em}
@media(prefers-reduced-motion:reduce){.readbar{display:none}}
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
/* Pages that carry the shared section bar (2026-08-11 UX study) let IT be
   the sticky chrome: the backbar scrolls away — two stacked sticky bars at
   top:0 fought for the same pixel row and hid the nav. */
.backbar.static{position:static}
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
/* Footer section index (owner order 2026-08-11): every page ends with the
   full paper — the bottom of a long read is a junction, not a wall. */
footer .foot-sections{margin-top:1.6rem;padding-top:1.1rem;border-top:1px solid #2a2a30;display:flex;flex-wrap:wrap;gap:.1rem .35rem}
footer .foot-sections a{color:#b9b9c2;font-size:.72rem;font-weight:700;padding:.5rem .55rem;white-space:nowrap;border-radius:3px}
footer .foot-sections a:hover{color:#fff;background:rgba(255,255,255,.07)}
/* On This Day (owner directive 2026-08-11): a slim dark memory band, gold
   kicker, mono year — same face in both themes like the rest of the chrome. */
.otd{background:var(--black);padding-block:.9rem;margin-block:1.1rem}
.otd .wrap{display:flex;flex-wrap:wrap;gap:.45rem 2.2rem;align-items:baseline}
.otd-kick{color:#c7a86b;font:800 .66rem/1 var(--sans);letter-spacing:.16em;text-transform:uppercase;white-space:nowrap}
[lang=ar] .otd-kick{letter-spacing:0;font-size:.8rem}
.otd-ev{display:flex;gap:.7rem;align-items:baseline;min-width:0}
.otd-ev .y{font:800 .95rem/1 ui-monospace,Menlo,monospace;color:#c7a86b}
.otd-ev p{font-family:var(--serif);font-size:.92rem;line-height:1.5;color:#e6e6ec;max-width:72ch}
[lang=ar] .otd-ev p{font-size:1.02rem;line-height:1.7}
/* Back-to-top (owner order 2026-08-11): floats opposite the live dock after
   two screens of scroll; house chrome black in both themes, ~44px tap. */
.totop{position:fixed;bottom:1rem;inset-inline-end:1rem;z-index:65;width:44px;height:44px;border-radius:50%;background:rgba(11,11,12,.92);color:#f2eee8;border:1px solid rgba(255,255,255,.28);display:flex;align-items:center;justify-content:center;font:800 1.15rem/1 var(--sans);text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.35);opacity:0;visibility:hidden;transform:translateY(8px);transition:opacity var(--tr),visibility var(--tr),transform var(--tr)}
.totop.show{opacity:1;visibility:visible;transform:none}
.totop:hover{background:#1c1c22;color:#fff}
@media(prefers-reduced-motion:reduce){.totop{transition:none;transform:none}}
footer .flagline{height:4px;background:linear-gradient(90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%);border-top:4px solid var(--red);max-width:200px;margin-bottom:1.5rem}
[dir=rtl] footer .flagline{background:linear-gradient(-90deg,var(--black) 0 33%,#fff 33% 66%,var(--green) 66% 100%)}
/* ── dark mode ── */
%%DARK%%
/* ── reduced motion ── */
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.ticker .rail{overflow-x:auto}.ticker .track{animation:none;white-space:normal;flex-wrap:wrap}.topbar .dot,.latest h2::before{animation:none}.latest li,.latest li.fresh::before{animation:none}.hero-imgwrap>a>img,.card img{transition:none}}
.skiplink{position:absolute;inset-inline-start:-999px;top:0;background:var(--red);color:#fff;padding:.6rem 1rem;z-index:99;font-weight:800}
.skiplink:focus{inset-inline-start:0}
.share{margin-top:1.2rem;display:flex;gap:.6rem;flex-wrap:wrap}
.share span{font-size:.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;align-self:center}
.share a{border:1px solid var(--line-dark);padding:.35rem .8rem;border-radius:var(--r);font-size:.8rem;font-weight:700}
.share a:hover{background:var(--red);color:#fff;border-color:var(--red)}
.share .copybtn{border:1px solid var(--line-dark);background:transparent;color:inherit;font-family:inherit;cursor:pointer;padding:.35rem .8rem;border-radius:var(--r);font-size:.8rem;font-weight:700}
.share .copybtn:hover{background:var(--red);color:#fff;border-color:var(--red)}
/* Floating share rail: travels with the reader in the story gutter on wide
   desktops; the inline row above stays as the universal fallback. Owner
   reports 2026-08-11 (two rounds): fixed positioning kept it floating over
   the Keep Reading/Latest titles below the article — .on (toggled by the
   scroll check shipped with the rail) now tracks geometry, keeping the rail
   only while the END of the article is still safely below the rail's
   bottom edge; it switches off as the story's end approaches the buttons.
   Without JS it stays hidden and the inline row carries sharing. */
.share-rail{display:none}
@media(min-width:1200px){
.share-rail{display:flex;flex-direction:column;gap:.5rem;position:fixed;top:42vh;inset-inline-start:calc(50vw - 410px - 4.6rem);z-index:40;opacity:0;visibility:hidden;transition:opacity var(--tr),visibility var(--tr)}
.share-rail.on{opacity:1;visibility:visible}
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
  .grid,.grid.g3{grid-template-columns:repeat(2,minmax(0,1fr))}
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
  /* Static hero MUST neutralize every overlay skin at higher specificity
     (owner report 2026-08-12: the .graphic gradient bled into the static
     headline and faded it). Any future .hero-overlay skin needs its
     neutralizer added here AND in the [data-lite] block. */
  .hero-imgwrap.graphic .hero-overlay{background:none}
  .hero-imgwrap.graphic>a>img{filter:none}
  .hero-imgwrap>a>img{height:auto}
  .hero-overlay .label{color:var(--red)}
  .hero-overlay h2,.hero-overlay h2 a{color:var(--ink);text-shadow:none}
  .hero-overlay h2 a:hover{color:var(--red)}
  .hero-overlay .meta{color:var(--muted)}
  .hero-overlay .meta .t{color:var(--muted)}
  .hero-overlay .meta .src{color:var(--green)}
  .hero-sub{grid-template-columns:1fr}
  .grid,.grid.g2,.grid.g3{grid-template-columns:1fr}
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
.meta .src,.card .chip,.rowcard .chip,.sub-body .chip,.gi-src a,.gi-dl a,.gi-method summary,.story .desk-note a,.social-note a,.about-telegram a{color:#3fd07c}
.story ul.lf,.story ol.lf{color:#d6d6de}
.story code{background:rgba(255,255,255,.12)}
.story table.lf th{background:rgba(255,255,255,.06)}
.tc-area{fill:rgba(249,53,73,.16)}
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

def analytics_tag():
    """Privacy-first, cookieless page counting (owner order 2026-08-10):
    GoatCounter, one async script tag, no cookies, no personal data, emitted
    on EVERY page template — a homepage-only counter undercounts a news site
    whose traffic lands on story pages. Off until ANALYTICS_GOATCOUNTER is
    set; the code is public by nature (it ships in the HTML)."""
    if not GOATCOUNTER_CODE:
        return ""
    return (f'<script data-goatcounter="https://{GOATCOUNTER_CODE}.goatcounter.com/count" '
            'async src="https://gc.zgo.at/count.js"></script>')


# Buttondown newsletter page → its embed-subscribe endpoint. Accepts the
# canonical page URL on either domain generation (buttondown.com /
# buttondown.email), with or without the @ prefix.
_BUTTONDOWN_RX = re.compile(
    r"^https://buttondown\.(?:com|email)/@?([A-Za-z0-9_.-]+)/?$")


def newsletter_band(lang):
    """Inline email signup above the footer (owner order 2026-08-10) —
    a quiet band, never a pop-up (owner rule 2026-08-02). Renders only when
    NEWSLETTER_URL is configured. A Buttondown newsletter page gets the real
    inline form (POST to its embed-subscribe endpoint, new tab); any other
    provider URL gets a plain subscribe link, so the band never breaks on a
    provider change."""
    if not NEWSLETTER_URL:
        return ""
    ar = lang == "ar"
    kicker = "النشرة البريدية" if ar else "THE NEWSLETTER"
    title = ("تصلك أبرز تغطياتنا إلى بريدك" if ar
             else "Get Times of Palestine in your inbox")
    sub = ("مجاناً، من دون تتبّع، ويمكنك إلغاء الاشتراك متى شئت. "
           "لا نستخدم بريدك إلا لإرسال النشرة." if ar else
           "Free, no tracking, unsubscribe any time. Your address is used "
           "for the newsletter and nothing else.")
    cta = "اشترك" if ar else "Subscribe"
    m = _BUTTONDOWN_RX.match(NEWSLETTER_URL)
    if m:
        action = f"https://buttondown.com/api/emails/embed-subscribe/{m.group(1)}"
        control = (
            f'<form class="nb-form" action="{esc(action)}" method="post" target="_blank">'
            f'<input type="email" name="email" required '
            f'placeholder="{"بريدك الإلكتروني" if ar else "Your email address"}" '
            f'aria-label="{"البريد الإلكتروني" if ar else "Email address"}" '
            f'autocomplete="email" inputmode="email">'
            f'<button type="submit">{cta}</button></form>')
    else:
        control = (f'<p class="nb-form"><a class="nb-link" href="{esc(NEWSLETTER_URL)}" '
                   f'target="_blank" rel="noopener">{cta} {"←" if ar else "→"}</a></p>')
    return (f'<section class="newsband" aria-label="{title}"><div class="wrap">'
            f'<p class="kick">{kicker}</p><h2>{title}</h2>'
            f'{control}<p class="nb-sub">{sub}</p>'
            f'</div></section>')


FLAG_SVG = ('<svg class="flagmark" width="46" height="46" viewBox="0 0 46 46" aria-hidden="true">'
            '<rect width="46" height="15.3" fill="#0b0b0c"/>'
            '<rect y="15.3" width="46" height="15.3" fill="#fff" stroke="#e5e2d9" stroke-width=".5"/>'
            '<rect y="30.6" width="46" height="15.4" fill="#007A3D"/>'
            '<path d="M0 0 L21 23 L0 46 Z" fill="#CE1126"/></svg>')

LOCK_SVG = ('<svg class="lock" width="54" height="54" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
            '<rect x="4" y="10" width="16" height="11" rx="1.5" fill="#007A3D" stroke="#3fd07c" stroke-width="1.2"/>'
            '<path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="#3fd07c" stroke-width="1.8" fill="none"/>'
            '<circle cx="12" cy="15" r="1.6" fill="#0b0b0c"/><rect x="11.3" y="15.5" width="1.4" height="2.6" rx=".7" fill="#0b0b0c"/></svg>')

# Signal glyph for the nav tip link (owner order 2026-08-11: the app's icon,
# not a padlock — the tip line IS the newsroom's Signal account). A simplified
# speech-bubble silhouette in Signal blue, inline so it needs no asset fetch.
SIGNAL_GLYPH = ('<svg class="signal-glyph" width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">'
                '<path fill="#3A76F0" d="M8 1.1a6.9 6.9 0 1 1-3.32 12.95l-3.02.86a.4.4 0 0 1-.5-.5l.86-2.98A6.9 6.9 0 0 1 8 1.1z"/>'
                '</svg>')

# Story-page polish (owner directive 2026-08-11: keep making the site
# visually better): a thin red reading-progress bar, a drop cap opening the
# English body (Arabic typography carries no drop-cap tradition — CSS
# disables it under [lang=ar]), and the classic end-slug ■ closing every
# story. The opener/closer paragraphs are tagged here because briefs
# (p.summary) and originals (longform .lf) shape their bodies differently.
# Pure enhancement: without JS the story reads exactly as before.
STORY_POLISH_JS = (
    '(function(){var a=document.querySelector("article.story");if(!a)return;'
    'var ps=a.querySelectorAll("p.summary,.lf p");'
    'if(ps.length){ps[0].classList.add("opener");ps[ps.length-1].classList.add("closer")}'
    'var b=document.createElement("div");b.className="readbar";'
    'var s=document.createElement("span");b.appendChild(s);document.body.appendChild(b);'
    'function u(){var d=document.documentElement,m=d.scrollHeight-innerHeight;'
    's.style.width=(m>0?Math.min(100,scrollY/m*100):0)+"%"}'
    # Phones reclaim the sticky nav while reading (visual audit 2026-08-16):
    # scrolling down past the opener hides the bar, any upward scroll brings
    # it back — the standard reading pattern, story pages only.
    'var nav=document.querySelector("nav.sections");var ly=scrollY;'
    'function nv(){if(!nav)return;if(innerWidth>700){nav.classList.remove("navhide");ly=scrollY;return}'
    'var dy=scrollY-ly;'
    'if(scrollY>360&&dy>8)nav.classList.add("navhide");'
    'else if(dy<-8||scrollY<120)nav.classList.remove("navhide");'
    'if(Math.abs(dy)>8)ly=scrollY}'
    'addEventListener("scroll",function(){u();nv()},{passive:true});'
    'addEventListener("resize",u,{passive:true});u()})();')

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
        "correctionsPolicy": (f"{BASE_URL}/{lang}/corrections.html"
                              if CORRECTIONS_PAGE_LIVE else
                              f"{BASE_URL}/{lang}/about.html"),
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
        return (f'<a href="{href(it, pfx)}" tabindex="-1" aria-hidden="true"><img src="{esc(it["image"])}" '
                f'alt="" width="640" height="360" loading="lazy" decoding="async"{lede_fallback_attrs(it)}></a>')
    return (f'<a href="{href(it, pfx)}" tabindex="-1" aria-hidden="true">'
            f'<div class="ph">{FLAG_SVG}</div></a>')

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
    q = "«" if lang == "ar" else "“"
    return (f'<article class="op-card"><span class="q">{q}</span>'
            f'<h3><a href="{href(it, pfx)}">{esc(it["title"])}</a></h3>'
            f'{meta_line(it, lang)}</article>')

def sub_item(it, lang, pfx):
    thumb = (f'<a class="sub-thumb" href="{href(it, pfx)}" tabindex="-1" aria-hidden="true">'
             f'<img src="{esc(it["image"])}" alt="" loading="lazy" decoding="async"{lede_fallback_attrs(it)}></a>'
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
             f'<img src="{esc(it["image"])}" alt="" loading="lazy" decoding="async" '
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
        # Campaign pin (owner order 2026-08-19): the Dima Barakat case leads
        # the specials row until she is released. Clearly labelled as the
        # paper's campaign; the story itself stays attributed news copy.
        "requires_original": "dima-barakat-file-2026",
        "href": _original_story_href("dima-barakat-file-2026"),
        "kicker": {"en": "Times of Palestine campaign", "ar": "حملة تايمز أوف فلسطين"},
        "title": {"en": "Release Dr. Dima Barakat",
                  "ar": "أطلقوا سراح الطبيبة ديما بركات"},
        "dek": {"en": "Israeli forces seized Ramallah's women's-cancer surgeon from her home on 18 August and have announced no charge. We follow her case, both languages, until she is home.",
                "ar": "اقتادت قوات الاحتلال جرّاحة أورام النساء من منزلها في رام الله في 18 آب/أغسطس ولم تعلن أي تهمة. نتابع قضيتها باللغتين حتى تعود إلى بيتها ومريضاتها."},
        "cta": {"en": "Read her file →", "ar": "اقرأ ملفها ←"},
        "img": "/media/times-of-palestine-dima-barakat-2026.svg",
        "img_alt": {"en": "Release Dr. Dima Barakat — the Times of Palestine campaign",
                    "ar": "أطلقوا سراح الطبيبة ديما بركات — حملة تايمز أوف فلسطين"},
        "ticker": {"en": "Campaign: release Dr. Dima Barakat, held without announced charge",
                   "ar": "حملة: أطلقوا سراح الطبيبة ديما بركات المحتجزة بلا تهمة معلنة"},
        "nav": {"en": "Dr. Barakat", "ar": "قضية د. بركات"},
    },
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
                        f'{_focus} loading="lazy" decoding="async">')
        cards.append(
            f'<a class="fr-card" href="{esc(s["href"][lang])}">{img_html}'
            f'<span class="body"><span class="kick">{esc(s["kicker"][lang])}</span>'
            f'<span class="ttl">{esc(s["title"][lang])}</span>'
            f'<span class="go">{esc(s["cta"][lang])}</span></span></a>')
    if not cards:
        return ""
    return (f'<section class="franchise"><div class="wrap"><div class="fr-grid">'
            + "".join(cards) + '</div></div></section>')


# SVG text-overflow guard (owner report 2026-08-11: a desk graphic's headline
# ran off the right edge of the canvas mid-word). LATIN text only: glyph runs
# are estimated at ≈0.55×font-size per character plus letter-spacing against
# the viewBox, honouring text-anchor. Findings are loud warnings at build time
# and a test failure in CI, so a graphic with clipped Latin text can neither
# merge nor ship silently. Arabic runs are deliberately NOT automated: SVG
# bidi (anchor + direction) varies by engine, and measured overflow there
# needs an editorial redraw, not a blind clamp — tracked per-file in the
# repo issues, never auto-mutated.
_SVG_TEXT_TAG_RX = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_SVG_ARABIC_RX = re.compile(r"[؀-ۿ]")


def _svg_text_nodes(svg_src):
    """Yield (match, attrs, plain_text, x, font_size, anchor, est_width) for
    every measurable LATIN <text> node. Nodes that carry textLength are
    skipped — the attribute forces the glyphs to fit by construction."""
    for m in _SVG_TEXT_TAG_RX.finditer(svg_src):
        attrs, inner = m.group(1), m.group(2)
        if "textLength" in attrs or "<tspan" in inner:
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if not text or _SVG_ARABIC_RX.search(text):
            continue
        xm = re.search(r'\bx="([\d.-]+)"', attrs)
        fm = re.search(r'font-size="([\d.]+)"', attrs)
        if not xm or not fm:
            continue
        x, fs = float(xm.group(1)), float(fm.group(1))
        ls = re.search(r'letter-spacing="([\d.]+)"', attrs)
        est = len(text) * (fs * 0.55 + (float(ls.group(1)) if ls else 0))
        anchor_m = re.search(r'text-anchor="(\w+)"', attrs)
        anchor = anchor_m.group(1) if anchor_m else "start"
        if anchor in ("middle", "end") and x <= 0:
            continue  # local coords inside a transform group — not measurable here
        yield m, attrs, text, x, fs, anchor, est


def svg_text_overflows(svg_src):
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_src)
    if not m:
        return []
    width = float(m.group(1))
    findings = []
    for _m, _attrs, text, x, _fs, anchor, est in _svg_text_nodes(svg_src):
        start = {"end": x - est, "middle": x - est / 2}.get(anchor, x)
        end = start + est
        margin = width * 0.02
        if end > width + margin or start < -margin:
            findings.append(
                f"~{max(end - width, -start):.0f}px off canvas ({width:.0f}w): {text[:60]!r}")
    return findings


def clamp_svg_text(svg_src):
    """Repair pass: any text node whose estimated run leaves the canvas gets
    textLength capped to the space it actually has (spacingAndGlyphs), so the
    worst case is compressed type — never clipped words. Used on desk-
    generated illustrations before they are written to disk."""
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_src)
    if not m:
        return svg_src
    width = float(m.group(1))
    pad = width * 0.01
    out, last = [], 0
    for tm, attrs, _text, x, _fs, anchor, est in _svg_text_nodes(svg_src):
        if anchor == "end":
            avail = x - pad
        elif anchor == "middle":
            avail = 2 * min(x - pad, width - pad - x)
        else:
            avail = width - pad - x
        if est <= avail or avail <= 0:
            continue
        tag_end = tm.start(1) + len(attrs)
        out.append(svg_src[last:tag_end])
        out.append(f' textLength="{avail:.0f}" lengthAdjust="spacingAndGlyphs"')
        last = tag_end
    out.append(svg_src[last:])
    return "".join(out)


# On This Day in Palestine (owner directive 2026-08-11): a daily memory line
# on both fronts — the settled historical record, keyed to the Jerusalem
# date from editorial/on-this-day.json. Renders nothing on days without an
# entry (never invented filler); fail-open on a broken data file.
def on_this_day_html(lang, built_at):
    try:
        data = json.loads((ROOT / "editorial" / "on-this-day.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    events = data.get(built_at.astimezone(GAZA).strftime("%m-%d")) or []
    events = [ev for ev in events if ev.get(lang)][:2]
    if not events:
        return ""
    label = "حدث في مثل هذا اليوم" if lang == "ar" else "On this day"
    rows = "".join(
        f'<div class="otd-ev"><span class="y">{int(ev["y"])}</span>'
        f'<p>{esc(ev[lang])}</p></div>' for ev in events)
    return (f'<section class="otd" aria-label="{label}"><div class="wrap">'
            f'<p class="otd-kick">{label}</p>{rows}</div></section>')


# ---------- shared section navigation (owner order 2026-08-11) ----------
# EVERY page carries the front page's wayfinding: most readers land on a
# story from a shared link, and they must be able to reach any desk and the
# search from where they stand — never forced through the homepage first.
# The homepage links its in-page section anchors; interior pages link the
# section archives. Flat priority row + ONE All-Sections panel (owner
# decision 2026-08-06); gold specials lead the panel as the .mspecials
# strip; US Press rides beside Israeli Press (owner orders 2026-08-11).
# Economy & Aid rides second (owner order 2026-08-11): last place put it
# below the fold of the phone panel's single scrolling column.
NAV_GROUPS_DEF = [
    ("regions", {"en": "News & Regions", "ar": "الأخبار والمناطق"},
     ["gaza", "westbank", "pal48", "prisoners", "politics", "diaspora", "news"]),
    ("economy", {"en": "Economy & Aid", "ar": "الاقتصاد والإسناد"},
     ["economy", "arabaid", "bitcoin"]),
    ("depth", {"en": "In-Depth", "ar": "في العمق"},
     ["accountability", "research", "israelipress", "uspress", "social", "opinion", "archive"]),
    ("society", {"en": "Society & Culture", "ar": "المجتمع والثقافة"},
     ["women", "health", "humans", "arts", "sports"]),
]
NAV_SHORT = {
    "en": {"gaza": "Gaza", "westbank": "West Bank",
           "israelipress": "Israeli Press", "uspress": "US Press",
           "politics": "Politics",
           "women": "Her Story", "economy": "Economy"},
    "ar": {"gaza": "غزة", "westbank": "الضفة",
           "israelipress": "الصحافة الإسرائيلية",
           "uspress": "الصحافة الأميركية", "politics": "سياسة",
           "women": "حكايتها", "economy": "اقتصاد"},
}
NAV_PRIORITY = ["gaza", "westbank", "israelipress", "uspress", "politics", "women", "economy"]
NAV_GBTN_JS = (
    "var g=this.parentNode,v=!g.classList.contains('open'),n=this.closest('nav');"
    "n.style.setProperty('--navdrop-top',n.getBoundingClientRect().bottom+'px');"
    "n.dataset.oy=window.scrollY;"
    "n.querySelectorAll('.nav-group.open').forEach(function(x){x.classList.remove('open');"
    "x.querySelector('button').setAttribute('aria-expanded','false')});"
    "if(v){g.classList.add('open');this.setAttribute('aria-expanded','true')}")
NAV_ARCHIVE_CATS = {}  # lang -> cats with a section-*.html this build (set in main)
# Support script shipped WITH the bar on every page (it was homepage-only
# until the 2026-08-11 UX study): outside click / Escape / a real scroll
# close open panels, and the search toggle opens the inline query bar
# where the page carries one.
NAV_SUPPORT_JS = (
    '(function(){function closeGroups(){document.querySelectorAll("nav.sections .nav-group.open")'
    '.forEach(function(x){x.classList.remove("open");x.querySelector("button").setAttribute("aria-expanded","false")})}\n'
    'var st=document.getElementById("searchtoggle"),sp=document.getElementById("navsearch");\n'
    'function closeSearch(){if(sp&&!sp.hidden){sp.hidden=true;st.setAttribute("aria-expanded","false")}}\n'
    'if(st&&sp)st.addEventListener("click",function(e){e.preventDefault();var open=!sp.hidden;closeGroups();'
    'if(open)closeSearch();else{sp.hidden=false;st.setAttribute("aria-expanded","true");sp.querySelector("input").focus()}});\n'
    'document.addEventListener("click",function(e){if(e.target.closest("nav.sections .nav-drop a")'
    '||!e.target.closest("nav.sections")){closeGroups();closeSearch()}});\n'
    'document.addEventListener("keydown",function(e){if(e.key==="Escape"){closeGroups();'
    'if(sp&&!sp.hidden){closeSearch();st.focus()}}});\n'
    'addEventListener("scroll",function(){var n=document.querySelector("nav.sections");\n'
    'if(n&&n.querySelector(".nav-group.open")&&Math.abs(window.scrollY-(+n.dataset.oy||0))>32)closeGroups()},{passive:true})})()')


def sections_nav_html(lang, keys, link_for, home_href, specials_top="",
                      specials_depth="", search_href="search.html",
                      search_toggle=False, tips_href="#tips", search_panel=""):
    """The sticky primary bar. keys = section keys allowed to render;
    link_for(k) -> that section's href on this page."""
    t = STR[lang]
    row = "".join(
        f'<a href="{link_for(k)}">{NAV_SHORT[lang].get(k, t["sections"][k])}</a>'
        for k in NAV_PRIORITY if k in keys)
    grouped = {k for _, _, ks in NAV_GROUPS_DEF for k in ks}
    leftovers = [k for k in SECTION_ORDER[lang] if k in keys and k not in grouped]
    mega_cols = ""
    for gid, label, gkeys in NAV_GROUPS_DEF:
        gkeys = [k for k in gkeys if k in keys]
        if gid == "regions":
            gkeys += leftovers
        links = "".join(f'<a href="{link_for(k)}">{t["sections"][k]}</a>' for k in gkeys)
        if not links:
            continue
        mega_cols += (f'<div class="mcol"><p class="mhead">{label[lang]}</p>'
                      f'{links}</div>')
    # Gold specials lead the panel (owner order 2026-08-11): visible the
    # moment it opens, never below the fold of the phone scroll column.
    if specials_depth:
        mega_cols = f'<div class="mspecials">{specials_depth}</div>' + mega_cols
    all_label = "كل الأقسام" if lang == "ar" else "All Sections"
    row += (
        f'<div class="nav-group all"><button class="nav-gbtn" type="button" '
        f'aria-expanded="false" aria-controls="navg-all" aria-haspopup="true" '
        f'onclick="{NAV_GBTN_JS}">{all_label} <span class="chev" aria-hidden="true">▾</span></button>'
        f'<div class="nav-drop mega" id="navg-all">{mega_cols}</div></div>')
    if search_toggle:
        search_link = (f'<a class="util" id="searchtoggle" href="{search_href}" '
                       f'aria-expanded="false" aria-controls="navsearch">{t["search_nav"]}</a>')
    else:
        search_link = f'<a class="util" href="{search_href}">{t["search_nav"]}</a>'
    return (f'<nav class="sections" aria-label="{"التصفح الرئيسي" if lang == "ar" else "Primary"}">'
            f'<div class="wrap"><a class="home" href="{home_href}">{t["latest"]}</a>{row}{specials_top}'
            f'<span class="nav-util">{search_link}'
            f'<a class="tip" href="{tips_href}">{SIGNAL_GLYPH} {t["tips_nav"]}</a></span></div>{search_panel}</nav>'
            f'<script>{NAV_SUPPORT_JS}</script>')


def interior_nav_html(lang, prefix=""):
    """The shared bar for pages outside the front page: section links go to
    the archive pages. prefix walks up to the edition root ("" at /<lang>/,
    "../" from /<lang>/story/). Specials gate on ORIGINALS_LOADED — the
    published-this-build signal available outside render_page — so the bar
    never links a special whose page did not render."""
    loaded = ORIGINALS_LOADED.get(lang, set())
    rendered = STORY_PAGES_RENDERED.get(lang)
    sp_top = sp_depth = ""
    for sp in SPECIALS:
        slug = sp.get("requires_original")
        if slug and slug not in loaded:
            continue
        # When the build has settled which story pages ship (main sets
        # STORY_PAGES_RENDERED before any interior page renders), that is
        # the gate — parse-time "loaded" is only the pre-render fallback.
        if slug and rendered is not None and sp["href"][lang] not in rendered:
            continue
        link = f'<a class="special" href="{esc(sp["href"][lang])}">{esc(sp["nav"][lang])}</a>'
        if sp.get("nav_primary"):
            sp_top += link
        else:
            sp_depth += link
    keys = NAV_ARCHIVE_CATS.get(lang) or set(SECTION_ORDER[lang])
    return sections_nav_html(
        lang, keys, lambda k: f"{prefix}section-{k}.html",
        home_href=prefix or "./", specials_top=sp_top, specials_depth=sp_depth,
        search_href=f"{prefix}search.html",
        tips_href=f"{prefix or './'}#tips")


def foot_sections_html(lang, prefix=""):
    """Footer section index (owner order 2026-08-11): the bottom of a long
    read is a junction, not a wall — every page ends with the full paper."""
    t = STR[lang]
    have = NAV_ARCHIVE_CATS.get(lang) or set(SECTION_ORDER[lang])
    links = "".join(f'<a href="{prefix}section-{k}.html">{t["sections"][k]}</a>'
                    for k in SECTION_ORDER[lang] if k in have)
    label = "أقسام الصحيفة" if lang == "ar" else "Sections"
    out = f'<nav class="foot-sections" aria-label="{label}">{links}</nav>'
    # Running files ride the same index (owner order 2026-08-16): the hubs
    # that shipped this build, on every page's footer, both editions.
    hubs = TOPIC_HUBS_LIVE.get(lang) or []
    if hubs:
        h_label = "الملفات المتجددة" if lang == "ar" else "Running files"
        h_links = "".join(
            f'<a href="{prefix}topic-{tf["slug"]}.html">{esc(tf[lang]["name"])}</a>'
            for tf, _ in hubs)
        out += (f'<nav class="foot-sections foot-files" '
                f'aria-label="{h_label}">{h_links}</nav>')
    return out


# Back-to-top (owner order 2026-08-11): the front page runs tens of screens
# on a phone — a floating ↑ appears after two screens of scroll, opposite
# the live dock, house ~44px tap size, and rides every page. Owner report
# 2026-08-11: at the very bottom it covered the footer's own links and
# duplicated their job — the arrow now switches off the moment the footer
# rises into its zone (footer top < viewport bottom - button reserve).
_TOTOP_JS = (
    'var tt=document.querySelector(".totop");if(tt){var v=false,'
    'f=document.querySelector("footer");'
    'function c(){var s=scrollY>1400&&(!f||f.getBoundingClientRect().top>innerHeight-76);'
    'if(s!==v){v=s;tt.classList.toggle("show",s)}}'
    'addEventListener("scroll",c,{passive:true});'
    'addEventListener("resize",c,{passive:true});c()}')

# De-twin pass (owner visual sweep 2026-08-11): when one house cover rides a
# run of adjacent cards — an Israeli-press batch is the standing case — the
# repeats get a faint, alternating tone shift so the run reads as a designed
# series instead of a copy-paste artifact. Presentation only, no-JS safe.
_DETWIN_JS = (
    'var dp=null,dn=0;'
    'document.querySelectorAll(".card>a>img,.lt-thumb img,.sub-thumb img,'
    '.fr-card img,.rowcard img,.kr img").forEach(function(im){'
    'var s=im.getAttribute("src")||"";'
    'if(s&&s===dp){dn++;im.classList.add(dn%2?"dupvar1":"dupvar2")}'
    'else{dp=s;dn=0}});')


def totop_html(lang):
    label = "العودة إلى الأعلى" if lang == "ar" else "Back to top"
    return (f'<a class="totop" href="#top" aria-label="{label}" title="{label}">↑</a>'
            f'<script>{_TOTOP_JS}{_DETWIN_JS}</script>')


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
    # Freshness is measured against built_at (the wall clock in production),
    # so a page renders identically for a given input set and build moment.
    now = built_at

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
        # arts joined the exclusions 2026-08-07: a fresh profile took the top
        # slot on a quiet wire — features celebrate, they don't lead the page.
        # Routine service notices joined 2026-08-09: a power-cut schedule ran
        # as the main headline — reader service, never the lead.
        return (bool(i["image"]) and len(i["title"]) > 30
                and i["cat"] not in ("social", "research", "opinion", "culture", "israelipress", "uspress", "arts")
                and not evergreen(i)
                and PALESTINE_RX.search(f"{i['title']} {i['dek']}")  # the top story IS Palestine
                and not REVIEWISH_RX.search(i["title"])
                and not ROUTINE_NOTICE_RX.search(f"{i['title']} {i['dek']}")
                and within_hours(i, max_age))

    # The hero follows the news cycle: pick from the FRESHEST window that has
    # candidates (last 6h, then 12h, then 18h). Within a window the candidates
    # rank by editorial score, so importance leads — not simply whichever wire
    # item arrived last (owner report 2026-08-09: a utility notice led purely
    # because it was newest). And the lead ROTATES (owner order 2026-08-09,
    # after one story sat on top for hours through dozens of deploys): among
    # the strongest comparable candidates, each 10-minute build moment
    # advances the pick, so every refresh cycle shows a live front page.
    # Deterministic for a given input set and build moment; the score floor
    # keeps a minor story from ever displacing a major one mid-rotation.
    hero_pool = by_score
    heroes = []
    for window in HERO_WINDOWS_H:
        candidates = [i for i in hero_pool if id(i) not in used
                      and hero_ok(i, max_age=window)][:HERO_ROTATE_POOL]
        if candidates:
            floor = candidates[0]["score"] * HERO_ROTATE_FLOOR
            candidates = [i for i in candidates
                          if i is candidates[0] or i["score"] >= floor]
            # Covers are photographs (owner order 2026-08-03; visual audit
            # 2026-08-16): among comparable candidates the hero prefers a
            # story leading with a real image over branded category art —
            # rotation then runs within the photo-led subset.
            _photo = [i for i in candidates if not str(i.get("image") or "")
                      .startswith("/media/times-of-palestine-cover-")]
            if _photo:
                candidates = _photo
            step = int(now.timestamp() // (HERO_ROTATE_MIN * 60))
            pick = candidates[step % len(candidates)]
            used.add(id(pick))
            heroes = [pick]
            break
    heroes = (heroes
              or take(by_score, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research", "israelipress", "uspress", "arts")
                      and not evergreen(i)
                      and not ROUTINE_NOTICE_RX.search(f"{i['title']} {i['dek']}")
                      and PALESTINE_RX.search(f"{i['title']} {i['dek']}")
                      and within_hours(i, HERO_MAX_AGE_H), 1)
              or take(by_latest, lambda i: bool(i["image"]) and i["cat"] not in ("social", "research", "israelipress", "uspress")
                      and not evergreen(i)
                      and within_hours(i, HERO_MAX_AGE_H), 1))
    hero = heroes[0] if heroes else None
    # Eight items (2×4) under the hero: four left the column trailing dead
    # space beside the taller Latest rail (owner decision 2026-08-03).
    # Routine service notices don't take top-block slots either — they still
    # run in their section and the chronological Latest rail.
    hero_subs = take(by_latest, lambda i: i["cat"] not in ("opinion", "social", "research", "bitcoin", "israelipress", "uspress")
                     and not evergreen(i)
                     and not ROUTINE_NOTICE_RX.search(f"{i['title']} {i['dek']}"), 8)
    # Latest rail and breaking ticker: chronological, Palestine coverage first.
    # The rail is an index — it lists stories without claiming them from sections.
    def palestine(i):
        return bool(PALESTINE_RX.search(f"{i['title']} {i['dek']}"))
    # Rail length pairs with the 2×4 hero-sub grid so the two columns end
    # together — neither side trails dead space (owner decision 2026-08-03).
    # One desk may not flood the rail (owner audit 2026-08-07: the press
    # review took 9 of 9 slots). Chronology holds; a section past its cap
    # simply yields its slot to the next-freshest story from another desk.
    RAIL_SECTION_CAP = 4

    def rail_take(pred, want, counts, chosen):
        out = []
        for i in by_latest:
            if len(out) >= want:
                break
            if id(i) in chosen or not pred(i):
                continue
            if counts.get(i["cat"], 0) >= RAIL_SECTION_CAP:
                continue
            counts[i["cat"]] = counts.get(i["cat"], 0) + 1
            chosen.add(id(i))
            out.append(i)
        return out

    _counts, _chosen = {}, set()
    latest = rail_take(lambda i: id(i) not in used and i["cat"] != "social" and palestine(i), 8, _counts, _chosen)
    latest += rail_take(lambda i: id(i) not in used and i["cat"] != "social", 8 - len(latest), _counts, _chosen)
    if len(latest) < 8:
        # Small builds: the rail is an index, not an owner of stories — it
        # may re-list what the hero tier already shows rather than run short.
        latest += rail_take(lambda i: i["cat"] != "social", 8 - len(latest), _counts, _chosen)
    if len(latest) < 8:
        # Tiny corpora: an index short of items lists what exists, cap waived.
        latest += [i for i in by_latest if i["cat"] != "social" and id(i) not in _chosen][:8 - len(latest)]
    # The breaking ticker is HARD NEWS only (owner audit 2026-08-07: a music
    # profile ran as "breaking"). Features, reviews, desks and evergreens
    # never scroll here; if the hard-news pool is empty the ticker falls back
    # to the old behaviour rather than rendering blank.
    TICKER_CATS = ("gaza", "westbank", "pal48", "prisoners", "politics", "news", "accountability",
                   "economy", "health", "women", "arabaid")
    _tickerable = [i for i in by_latest if i["cat"] in TICKER_CATS and not evergreen(i)]
    if not _tickerable:
        _tickerable = [i for i in by_latest if i["cat"] not in ("social", "israelipress", "uspress")]
    pal_news = [i for i in _tickerable if palestine(i)]
    ticker_items = (pal_news or _tickerable)[:6]

    # Topical sections carry Palestine coverage only; world items from Palestinian
    # outlets live in More News. Research and Bitcoin are thematic by construction.
    # EVERY section reads newest-first (owner order 2026-08-11, extending the
    # press-desk rule of the same day to the whole paper): a section fronting
    # days-old cards while fresher coverage hides behind View-all reads as
    # dead — "the page is alive". Editorial score still ranks the hero tier;
    # the section blocks are the day's paper, in the order the day happened.
    sections = {k: diversify(take(by_latest,
                                  lambda i, k=k: i["cat"] == k
                                  and (k in ("research", "bitcoin", "news") or palestine(i)), 8))
                for k in order}
    sections["news"] += take(by_latest, lambda i: True, max(0, 8 - len(sections["news"])))
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
                     f'<img src="/media/times-of-palestine-israel-votes-card.svg" alt="{esc(_valt)}" loading="lazy" decoding="async">'
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
    # The sticky bar is built by the shared sections_nav_html (owner order
    # 2026-08-11) so interior pages carry identical wayfinding. Homepage
    # links are in-page anchors; nav_primary specials (Sanad — owner order
    # 2026-08-04) stay top-level on the bar, never folded into a dropdown.
    nav_specials_top = ""
    _specials_depth = ""
    for sp in available_specials(lang, items):  # gold standing specials
        _sp_link = f'<a class="special" href="{esc(sp["href"][lang])}">{esc(sp["nav"][lang])}</a>'
        if sp.get("nav_primary"):
            nav_specials_top += _sp_link
        else:
            _specials_depth += _sp_link
    _search_panel = (
        f'<div class="nav-search" id="navsearch" hidden>'
        f'<form action="search.html" method="get" role="search">'
        f'<input name="q" type="search" placeholder="{esc(t["search_prompt"])}" '
        f'aria-label="{esc(t["search_title"])}" autocomplete="off">'
        f'<button type="submit">{t["search_go"]}</button></form></div>')
    sections_nav = sections_nav_html(
        lang, {k for k in order if visible(k)}, lambda k: f"#{k}",
        home_href="#top", specials_top=nav_specials_top,
        specials_depth=_specials_depth, search_toggle=True,
        search_panel=_search_panel)

    def research_featured(it):
        media = (f'<a href="{href(it, P)}"><img src="{esc(it["image"])}" alt="{esc(it["title"])}" loading="lazy" decoding="async"{lede_fallback_attrs(it)}></a>'
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
        pool = break_cover_twins(sections[k][:4])
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
                           f'<div class="sec-copy"><div class="sec-head{focus_cls}"><h2>{esc(t["sections"][k])}</h2><span class="rule"></span>{viewall}</div>{section_meta(sections[k], lang)}</div>'
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
        # House graphics carry their own internal titles; at hero size that
        # text fights the page headline (and on /ar/ the artwork's English
        # reads first). The .graphic treatment dims the image to a texture
        # and deepens the scrim so the overlay headline owns the frame
        # (owner visual sweep 2026-08-11).
        _hero_graphic = (" graphic"
                         if str(hero.get("image", "")).startswith("/media/")
                         and str(hero.get("image", "")).endswith(".svg") else "")
        # When category art does lead (no photo-led candidate), the hero uses
        # the TEXT-FREE plate of the same cover — the art's big section word
        # otherwise repeats the kicker right above the headline (visual audit
        # 2026-08-16). Plates are generated for every cover at deploy time.
        _hsrc = str(hero.get("image") or "")
        if re.match(r"^/media/times-of-palestine-cover-[a-z-]+\.svg$", _hsrc):
            _hsrc = _hsrc[:-4] + "-hero.svg"
        hero_html = (
            f'<div class="hero-imgwrap{_hero_graphic}">'
            f'<a href="{href(hero, P)}"><img src="{esc(_hsrc)}" alt="{esc(hero["title"])}" width="1200" height="675" loading="eager" fetchpriority="high"{lede_fallback_attrs(hero)}></a>'
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
    # Machine-readable front page (audit 2026-08-07 P2; owner-forwarded review
    # 2026-08-10): an ItemList of the top stories exactly as the page ranks
    # them — hero, then the top block, then the Latest rail — for rich-result
    # eligibility. Alive by construction: it re-ranks with every build.
    _li_seen, _li = set(), []
    for _it in ([hero] if hero else []) + hero_subs + latest:
        _u = story_url(_it, lang)
        if _u in _li_seen:
            continue
        _li_seen.add(_u)
        _li.append({"@type": "ListItem", "position": len(_li) + 1,
                    "url": _u, "name": _it["title"]})
        if len(_li) >= 10:
            break
    itemlist_script = ""
    if _li:
        itemlist_script = ('<script type="application/ld+json">' + jsonld_dump({
            "@context": "https://schema.org", "@type": "ItemList",
            "name": ("أبرز أخبار تايمز أوف فلسطين" if lang == "ar"
                     else "Times of Palestine — top stories"),
            "itemListOrder": "https://schema.org/ItemListOrderAscending",
            "itemListElement": _li}) + "</script>")
    _gp = __import__("gaza_panel")
    gaza_panel = _gp.panel(lang)
    # Key figures surfaced before the first scroll (owner-forwarded review,
    # 2026-08-10) — the strip and the full ledger revise together (PANEL_JS).
    gaza_strip = _gp.strip(lang) if gaza_panel else ""
    tips_band = (
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
<script type="application/ld+json">{org_jsonld(lang)}</script>{itemlist_script}
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}{analytics_tag()}
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

{sections_nav}

<main id="top">
  {gaza_strip}
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
  {on_this_day_html(lang, built_at)}
  {opinion_block}
  {section_blocks}
  {tips_band}{newsletter_band(lang)}
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="cols">
    <div><h2>{t['mission_title']}</h2><p class="mission">{t['mission']}</p></div>
    <div><h2>{t['tips_kicker']}</h2><p class="mission">{t['tips_sub']}</p>
      <p class="footer-contact"><a href="{SIGNAL_URL}" target="_blank" rel="noopener">🔒 {t['tips_cta']} {"←" if lang == "ar" else "→"}</a>
      <span class="contact-id">{SIGNAL_USERNAME}</span></p><p class="footer-contact secondary"><a href="{TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{t['tips_tg']} {"←" if lang == "ar" else "→"}</a> <span class="contact-id">{TELEGRAM_BOT_NAME}</span></p></div>
  </div>
  {foot_sections_html(lang)}
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span> <a href="about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a>{('<a href="corrections.html">' + ('التصويبات' if lang == 'ar' else 'Corrections') + '</a>') if CORRECTIONS_PAGE_LIVE else ''} <a href="status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a> <a href="{TELEGRAM_CHANNEL_URL}" target="_blank" rel="noopener">{t['follow_tg']}</a> <a href="rss.xml">RSS</a>{f'<a href="{NEWSLETTER_URL}" target="_blank" rel="noopener">' + ('النشرة البريدية' if lang == 'ar' else 'Email newsletter') + '</a>' if NEWSLETTER_URL else ''}{f'<a href="{SUPPORT_URL}" target="_blank" rel="noopener">' + ('ادعمنا' if lang == 'ar' else 'Support us') + '</a>' if SUPPORT_URL else ''}
    <span>{t['attribution']}</span>
    <a href="{t['switch_href']}">{t['footer_lang']}</a>
  </div>
</div></footer>
{totop_html(lang)}
<script>(()=>{{const initial={json.dumps(utc_iso(built_at))};let timer;async function check(){{if(document.hidden||!navigator.onLine)return;try{{const r=await fetch("/data.json",{{cache:"no-store"}});if(r.ok&&((await r.json()).builtAt)!==initial)location.reload();}}catch(_error){{}}}}document.addEventListener("visibilitychange",()=>{{if(!document.hidden)check();}});timer=setInterval(check,300000);}})();</script>
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
        # One-line desk note under the byline (owner-forwarded review,
        # 2026-08-10): who the Newsdesk is, in a sentence, with the full
        # account one tap away on the About page.
        desk_note = (
            '<p class="desk-note">'
            + ("تجمع غرفة الأخبار التغطيات من الوكالات والمصادر الأولية "
               "وتعيد صياغة كل مادة داخلياً قبل النشر. "
               '<a href="../about.html">كيف نصنع صحافتنا ←</a>'
               if lang == "ar" else
               "The Newsdesk gathers reporting from wire services and primary "
               "sources and rewrites every story in-house before publication. "
               '<a href="../about.html">How our journalism is made →</a>')
            + "</p>")
        summary = (f'<p class="kind">{kind}</p>'
                   f'<p class="byline">{t["byline"]} · {reading_time_label(brief, lang)}</p>'
                   f'{desk_note}{story_toc}{paras}{source_embed}')
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
        ledger_link = ""
        if CORRECTIONS_PAGE_LIVE:
            ledger_label = ("سجل التصويبات الكامل ←" if lang == "ar"
                            else "Full corrections ledger →")
            ledger_link = (f'<p class="ledgerlink">'
                           f'<a href="../corrections.html">{ledger_label}</a></p>')
        corrections = (
            f'<section class="revisions" aria-labelledby="revision-title">'
            f'<h2 id="revision-title">{esc(heading)}</h2><ol>{rows}</ol>'
            f'{ledger_link}</section>')
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
    share_rail = ('<nav class="share-rail" aria-label="' + ("شارك الخبر" if lang == "ar" else "Share this story") + '"><a href="https://twitter.com/intent/tweet?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener" title="X">X</a><a href="https://www.facebook.com/sharer/sharer.php?u=' + _q(share_url) + '" target="_blank" rel="noopener" title="Facebook">f</a><a href="https://wa.me/?text=' + _q(it["title"] + " " + share_url) + '" target="_blank" rel="noopener" title="WhatsApp">Wa</a><a href="https://t.me/share/url?url=' + _q(share_url) + '&text=' + _q(it["title"]) + '" target="_blank" rel="noopener" title="Telegram">Tg</a></nav>'
                  # Owner reports 2026-08-11 (two rounds): the fixed rail
                  # floated over the Keep Reading/Latest titles below the
                  # article. Visibility now tracks GEOMETRY, not article
                  # visibility — the rail shows only while the article's END
                  # is still safely below the rail's bottom edge, so it
                  # switches off the moment the end of the story approaches
                  # the buttons. Without JS it stays hidden and the inline
                  # share row carries sharing.
                  '<script>(function(){var r=document.querySelector(".share-rail"),'
                  'a=document.querySelector("article.story");if(!r||!a)return;var on=false;'
                  'function chk(){var s=a.getBoundingClientRect().bottom>innerHeight*.42+r.offsetHeight+28;'
                  'if(s!==on){on=s;r.classList.toggle("on",s)}}'
                  'addEventListener("scroll",chk,{passive:true});'
                  'addEventListener("resize",chk,{passive:true});chk()})()</script>')
    plain_desc = meta_desc(summary_text(
        (it.get("brief") or it["dek"]).replace(chr(10), " ")))
    desc = esc(plain_desc)
    og_image, _og_card, og_img_url = og_image_tags(it)
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
        f'<nav class="breadcrumbs" aria-label='
        f'"{"مسار التنقل" if lang == "ar" else "Breadcrumb"}">'
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
{_THEME_JS}{analytics_tag()}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar static"><a href="../">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="{switch_href}">{t['switch_lang']}</a></span></div>
{ticker_html(t, lang, ticker_track, ticker_track_hidden)}
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="../"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
{interior_nav_html(lang, "../")}
<main id="top">
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
  <script>{STORY_POLISH_JS}</script>
  {share_rail}
  <section class="keep"><div class="wrap">
    <div class="sec-head focus"><h2>{t['keep_reading']}</h2><span class="rule"></span></div>
    <div class="grid">{related_cards}</div>
  </div></section>
  <section class="keep"><div class="wrap latest">
    <h2>{t['latest']}</h2>
    <ol>{latest_html}</ol>
  </div></section>
  {newsletter_band(lang)}
</main>

<footer><div class="wrap">
  <div class="flagline"></div>
  {foot_sections_html(lang, "../")}
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span> <a href="../about.html">{'من نحن — اتصل بنا' if lang == 'ar' else 'About & Contact'}</a>{('<a href="../corrections.html">' + ('التصويبات' if lang == 'ar' else 'Corrections') + '</a>') if CORRECTIONS_PAGE_LIVE else ''} <a href="../status.html">{'حالة النشر' if lang == 'ar' else 'Publishing status'}</a>
    <a href="../">{t['back_home']}</a>
  </div>
</div></footer>
<script>{_LISTEN_JS}</script>
<script>{_CLOCK_JS}</script>
{live_fab_html(lang)}
{totop_html(lang)}
</body>
</html>"""

def og_image_tags(it):
    """OpenGraph image tags that social crawlers can actually use.

    Facebook and friends REJECT SVG og:images outright and then scrape the
    page for any large image — which on a story page is the Keep Reading
    rail, i.e. a DIFFERENT story's art (owner report 2026-08-24: a
    remittance-costs share card showed the bitchat drill infographic).
    House SVGs therefore advertise their build-rasterized .png sibling
    (the workflow's rsvg step writes one for every dist/media SVG), with
    the site banner as a second og:image so a failed raster still shows
    OUR branding, never a neighboring story's graphic. Raster ledes pass
    through unchanged; photoless stories get the banner alone.
    """
    image = it.get("image") or ""
    url = (BASE_URL + image) if image.startswith("/") else image
    banner = f'<meta property="og:image" content="{BASE_URL}/og-banner.png">'
    if not image:
        return banner, "summary", f"{BASE_URL}/og-banner.png"
    if image.lower().endswith(".svg"):
        raster = url[:-4] + ".png"
        return (f'<meta property="og:image" content="{esc(raster)}">' + banner,
                "summary_large_image", raster)
    return f'<meta property="og:image" content="{esc(url)}">', "summary_large_image", url

def story_redirect_stub(it, lang):
    """Tiny page at the bare-pid URL forwarding to the slugged canonical.
    This IS the share link (owner call 2026-08-05 — an Arabic slug
    percent-encodes to hundreds of characters), so it carries the full
    OpenGraph set: Telegram, WhatsApp and Facebook build their link previews
    from THIS page's meta and do not follow the meta refresh."""
    target = story_url(it, lang)
    desc = esc(meta_desc(summary_text(
        (it.get("brief") or it["dek"]).replace(chr(10), " "))))
    og_image, _og_card, og_img_url = og_image_tags(it)
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
        # Wire attribution protocol: a rewritten brief is OUR copy — feed
        # readers see Times of Palestine, not the wire outlet. Only
        # dek-fallback items (no brief) keep the outlet credit.
        source = ("" if it.get("original") or it.get("brief") else
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
    cards = "".join(card(it, lang, "story/") for it in break_cover_twins(list(items)))
    more_html = ""
    if more_items:
        more_label = "المزيد من تايمز أوف فلسطين" if lang == "ar" else "More from Times of Palestine"
        more_cards = "".join(card(it, lang, "story/") for it in break_cover_twins(list(more_items)))
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
<link rel="alternate" hreflang="en" href="{BASE_URL}/en/section-{cat}.html">
<link rel="alternate" hreflang="ar" href="{BASE_URL}/ar/section-{cat}.html">
<link rel="alternate" hreflang="x-default" href="{BASE_URL}/en/section-{cat}.html">
<meta property="og:type" content="website">
<meta property="og:locale" content="{'ar_PS' if lang == 'ar' else 'en_US'}">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(name)} — {t['site_name']}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE_URL}/{lang}/section-{cat}.html">
<meta property="og:image" content="{BASE_URL}/og-banner.png">
<meta name="twitter:card" content="summary_large_image">
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}{analytics_tag()}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar static"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
{interior_nav_html(lang)}
<main class="wrap sectionpage" id="top">
  <div class="sec-head focus"><h2>{esc(name)}</h2><span class="rule"></span><span class="count">{count_label}</span></div>
  <div class="grid g4">{cards}</div>
  {more_html}
</main>
<footer><div class="wrap"><div class="flagline"></div>
  {foot_sections_html(lang)}
  <div class="legal"><span>© {built_at.year} {t['site_name']}</span> <a href="./">{t['back_home']}</a> <a href="about.html">{'من نحن' if lang == 'ar' else 'About'}</a></div>
</div></footer>
<script>{_CLOCK_JS}</script>
{totop_html(lang)}
</body></html>"""


def render_corrections_page(lang, items, built_at, archived_pids=frozenset()):
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
                # Permalinks never die (owner order 2026-08-09): when this
                # build re-renders the story from the archive, its bare-pid
                # stub resolves — link the ref. Pre-archive-era pids (no
                # stored record, no stub) keep the plain reference.
                if pid in archived_pids:
                    label = ("المادة في الأرشيف الدائم · مرجع "
                             if lang == "ar" else "Story in the permanent archive · ref ")
                    story_ref = (f'<span class="ref">{label}'
                                 f'<a href="story/{esc(pid)}.html">{esc(pid)}</a></span>')
                else:
                    label = ("المادة خرجت من الموقع الحي · مرجع "
                             if lang == "ar" else "Story rotated off the live site · ref ")
                    story_ref = f'<span class="ref">{label}{esc(pid)}</span>'
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
{_THEME_JS}{analytics_tag()}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar static"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/corrections.html">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
{interior_nav_html(lang)}
<main id="top">
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
    var hits=ix.filter(function(e){var hay=(e.t+" "+e.d+" "+(e.b||"")+" "+e.c).toLowerCase();
      return terms.every(function(w){return hay.indexOf(w)!==-1});}).slice(0,40);
    render(hits,q.dataset.none);});}
q.addEventListener("input",go);
var init=new URLSearchParams(location.search).get("q");
if(init){q.value=init;go();}})();
"""


def render_topic_page(lang, tf, items, built_at, more_items=()):
    """A running file's living page (owner order 2026-08-16): newest
    development first, the whole documented trail beneath — the page a
    reader follows for Qusra or The Hague the way they follow a section."""
    t = STR[lang]
    name, dek = tf[lang]["name"], tf[lang]["dek"]
    slug = tf["slug"]
    n = len(items)
    if lang == "ar":
        count_label = "قصة واحدة" if n == 1 else ("قصتان" if n == 2 else f"{n} قصص" if n <= 10 else f"{n} قصة")
        kicker = "ملف متجدد"
    else:
        count_label = f"{n} story" if n == 1 else f"{n} stories"
        kicker = "Running file"
    cards = "".join(card(it, lang, "story/") for it in break_cover_twins(list(items)))
    more_html = ""
    if more_items:
        more_label = "المزيد من تايمز أوف فلسطين" if lang == "ar" else "More from Times of Palestine"
        more_cards = "".join(card(it, lang, "story/") for it in break_cover_twins(list(more_items)))
        more_html = (f'<div class="sec-head focus morehead"><h2>{more_label}</h2>'
                     f'<span class="rule"></span></div>'
                     f'<div class="grid g4">{more_cards}</div>')
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48">
<title>{esc(name)} — {t['site_name']}</title>
<meta name="description" content="{esc(dek)}">
<meta name="robots" content="max-image-preview:large">
<link rel="canonical" href="{BASE_URL}/{lang}/topic-{slug}.html">
<link rel="alternate" hreflang="en" href="{BASE_URL}/en/topic-{slug}.html">
<link rel="alternate" hreflang="ar" href="{BASE_URL}/ar/topic-{slug}.html">
<link rel="alternate" hreflang="x-default" href="{BASE_URL}/en/topic-{slug}.html">
<meta property="og:type" content="website">
<meta property="og:locale" content="{'ar_PS' if lang == 'ar' else 'en_US'}">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(name)} — {t['site_name']}">
<meta property="og:description" content="{esc(dek)}">
<meta property="og:url" content="{BASE_URL}/{lang}/topic-{slug}.html">
<meta property="og:image" content="{BASE_URL}/og-banner.png">
<meta name="twitter:card" content="summary_large_image">
{'<link rel="preload" href="/fonts/NotoKufiArabic-var.woff2" as="font" type="font/woff2" crossorigin>' if lang == "ar" else ""}<link href="/assets/site.css" rel="stylesheet">
{_THEME_JS}{analytics_tag()}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar static"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
{interior_nav_html(lang)}
<main class="wrap sectionpage" id="top">
  <div class="sec-head focus"><h2>{esc(name)}</h2><span class="rule"></span><span class="count">{esc(kicker)} · {count_label}</span></div>
  <p class="summary" style="max-inline-size:52rem">{esc(dek)}</p>
  <div class="grid g4">{cards}</div>
  {more_html}
</main>
<footer><div class="wrap"><div class="flagline"></div>
  {foot_sections_html(lang)}
  <div class="legal"><span>© {built_at.year} {t['site_name']}</span> <a href="./">{t['back_home']}</a> <a href="about.html">{'من نحن' if lang == 'ar' else 'About'}</a></div>
</div></footer>
<script>{_CLOCK_JS}</script>
{totop_html(lang)}
</body></html>"""


def render_search_page(lang, built_at, cats=()):
    """Client-side archive search: fetches the build's index, filters locally.
    No third-party code; results built with textContent, never innerHTML.
    `cats` renders browse chips so the empty page still leads somewhere."""
    t = STR[lang]
    browse = ""
    if cats:
        bl = "تصفح الأقسام" if lang == "ar" else "Or browse the sections"
        # Chips follow the paper's section order (owner order 2026-08-11) —
        # Gaza and the West Bank first, never an arbitrary alphabet.
        ordered = ([k for k in SECTION_ORDER[lang] if k in cats]
                   + [c for c in cats if c not in SECTION_ORDER[lang]])
        chips = "".join(
            f'<a href="section-{c}.html">{esc(t["sections"].get(c, c))}</a>'
            for c in ordered if c in t["sections"])
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
{_THEME_JS}{analytics_tag()}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar static"><a href="./">{t['back_home']}</a><span class="bb-tools">{theme_btn(lang)}{lite_btn(lang)}<a href="../{'en' if lang == 'ar' else 'ar'}/search.html">{t['switch_lang']}</a></span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
{interior_nav_html(lang)}
<main class="wrap searchpage" id="top">
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
<link rel="canonical" href="https://timesofpalestine.com/en/">
<link rel="alternate" hreflang="en" href="https://timesofpalestine.com/en/">
<link rel="alternate" hreflang="ar" href="https://timesofpalestine.com/ar/">
<link rel="alternate" hreflang="x-default" href="https://timesofpalestine.com/en/">
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
    # Persist what verified this run before anything downstream can fail: the
    # next build's photos depend on this memory surviving.
    save_remote_image_cache()
    # Both editions are first-class (charter §3): a one-language validator
    # skip must never publish a story monolingual in silence.
    for slug in sorted(ORIGINALS_LOADED.get("en", set())
                       ^ ORIGINALS_LOADED.get("ar", set())):
        only = "en" if slug in ORIGINALS_LOADED.get("en", set()) else "ar"
        print(f"::warning::original {slug} is publishing {only}-only — "
              "both language editions are first-class")
        HEALTH.hold("original_monolingual")
    # A wire blackout must not be masked by long-lived originals: with zero
    # aggregated items the front page would quietly go archive-only.
    wire_total = sum(1 for i in en_items + ar_items if not i.get("original"))
    if wire_total == 0:
        print("::error::0 wire items survived fetching across all feeds — "
              "failing so the last good deploy stays live.")
        HEALTH.checks["wire"] = "down"
        sys.exit(1)
    elif wire_total < 10:
        print(f"::warning::only {wire_total} wire items fetched — "
              "possible large-scale feed outage")
        HEALTH.checks["wire"] = "degraded"
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
    # Publishability first (owner review 2026-08-08): the dedupe rank knows
    # nothing about briefs, so a refused/incomplete cluster winner could
    # absorb — and then take down — siblings whose briefs were publishable.
    candidates = select_publishable_copy(en_items, ar_items)
    _before = len(candidates)
    en_items = dedupe_events([i for i in candidates if i["lang"] == "en"])
    ar_items = dedupe_events([i for i in candidates if i["lang"] == "ar"])
    HEALTH.deduplicated += _before - len(en_items) - len(ar_items)
    # AI duplicate judge (owner order 2026-08-09): paraphrase-level duplicates
    # share too few words for the lexical nets — the newsroom model settles
    # them. Runs here, on final published copy, so what it judges is exactly
    # what the reader would see twice. Fail-open on every route.
    judge = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            judge = anthropic.Anthropic(
                api_key=re.sub(r"\s+", "", os.environ["ANTHROPIC_API_KEY"]),
                timeout=30.0, max_retries=1)
        except ImportError:
            pass
    try:
        en_items, ar_items, _ai_dropped = adjudicate_duplicates(
            en_items, ar_items, judge)
        HEALTH.deduplicated += _ai_dropped
    except Exception as exc:  # a judge outage never stops the paper
        print(f"  dedupe judge stage failed ({type(exc).__name__}) — "
              "lexical dedupe only this build.")
    candidates = en_items + ar_items
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
    archived_all = []  # both languages, for copy_media below
    for lang, items in (("en", en_items), ("ar", ar_items)):
        import shutil
        shutil.rmtree(dist / lang / "story", ignore_errors=True)  # drop stale story pages
        (dist / lang / "story").mkdir(parents=True, exist_ok=True)
        news = [r for r in items if r["cat"] != "social"]
        rail = ([r for r in news if PALESTINE_RX.search(f"{r['title']} {r['dek']}")] +
                [r for r in news if not PALESTINE_RX.search(f"{r['title']} {r['dek']}")])[:11]
        # Permalink permanence (owner order 2026-08-09): stories that left the
        # live feeds keep their published URLs — re-rendered from the committed
        # story-archive/ ledger, never re-entering the live surfaces. Rendered
        # first so sections and the search index only reference pages that
        # actually shipped. Fail-open per story: one stale record must never
        # stop the live newsroom, and a page that would trip today's
        # validators is skipped loudly, not shipped.
        arch_related = diversify(sorted(
            items, key=lambda r: r["score"], reverse=True)[:8])[:8]
        archived = []
        _arch_pool = list(story_archive.load(
            lang, exclude={i["pid"] for i in items} | RETRACTED_PIDS))
        # Every section that will get an archive page this build — the shared
        # nav and footer index on interior pages link only these (owner order
        # 2026-08-11), so no bar ever links a section that didn't render.
        NAV_ARCHIVE_CATS[lang] = ({i["cat"] for i in items}
                                  | {a["cat"] for a in _arch_pool})
        # The interior nav's specials gate (2026-08-15): a special is linkable
        # only when its story page ships THIS build — live items or archive
        # re-renders. ORIGINALS_LOADED is a parse-time signal; an original the
        # pipeline later drops (or an archive skipped offline) must not leave
        # nav links to a page that never rendered.
        STORY_PAGES_RENDERED[lang] = {
            story_url_path(it["title"], it["pid"], lang)
            for it in list(items) + _arch_pool}
        # Running-file topic hubs (owner order 2026-08-16, site audit rec 6):
        # the paper's spine is its standing files — give each a living page
        # collecting every matching live and archived story. Selected here,
        # before any interior page renders, so footers only link hubs that
        # ship this build. Fail-open: a bad pattern drops one hub, loudly.
        TOPIC_HUBS_LIVE[lang] = []
        for _tf in TOPIC_FILES:
            try:
                _rx = re.compile(_tf["pattern"], re.I)
                _hits = [h for h in list(items) + _arch_pool
                         if _rx.search(f"{h.get('title', '')} "
                                       f"{h.get('link', '') or ''}")]
                if len(_hits) >= int(_tf.get("min", 2)):
                    try:
                        _hits.sort(key=lambda r: r.get("date"), reverse=True)
                    except TypeError:  # datetime/str mix across live+archive
                        _hits.sort(key=lambda r: str(r.get("date") or ""),
                                   reverse=True)
                    TOPIC_HUBS_LIVE[lang].append((_tf, _hits))
            except Exception as exc:
                print(f"::warning::topic hub "
                      f"'{_tf.get('slug', '?')}' failed open "
                      f"({type(exc).__name__}: {exc})")
        if TOPIC_HUBS_LIVE[lang]:
            print(f"  ✓ topic hubs {lang}: " + ", ".join(
                f"{tf['slug']}({len(h)})" for tf, h in TOPIC_HUBS_LIVE[lang]))
        for it in _arch_pool:
            try:
                attach_corrections(it)  # late corrections reach archived pages too
                # Rights-strict mode (opt-in, default OFF) never ships
                # unrighted remote hotlinks — mirror the live pipeline for
                # archived pages, without re-fetching every old image.
                if (remote_media_mode() != "source"
                        and is_http_url(it.get("image") or "")
                        and media_rights_for(it["image"], MEDIA_RIGHTS) is None):
                    it["image"] = None
                    it["media"] = None
                story_html = render_story(it, lang, arch_related, rail, built_at)
                errors = []
                _vb = __import__("validate_build")
                rel = f"{lang}/story/{it['pid']}"
                _vb.check_editorial_hygiene(rel, story_html, errors)
                _vb.check_body_starts_clean(rel, story_html, errors)
                if errors:
                    raise PublishingError("; ".join(errors))
                (dist / lang / "story" / story_file_name(it["title"], it["pid"])).write_text(
                    story_html, encoding="utf-8")
                # The bare-pid path IS the link that went out — keep it resolving.
                (dist / lang / "story" / f"{it['pid']}.html").write_text(
                    story_redirect_stub(it, lang), encoding="utf-8")
                archived.append(it)
            except Exception as exc:
                print(f"::warning::story archive: could not re-render "
                      f"{lang}:{it['pid']} ({type(exc).__name__}: {exc})")
        if archived:
            print(f"  ✓ archive: {len(archived)} past {lang} story pages kept resolving")
        archived_all.extend(archived)
        for stale in (dist / lang).glob("section-*.html"):  # archives rebuild fresh too
            stale.unlink()
        (dist / lang / "index.html").write_text(render_page(lang, items, built_at), encoding="utf-8")
        live_cats = {it["cat"] for it in items}
        for cat in sorted(live_cats):
            cat_items = sorted((i2 for i2 in items if i2["cat"] == cat),
                               key=lambda r: r["date"], reverse=True)
            more_items = sorted((i2 for i2 in items if i2["cat"] != cat),
                                key=lambda r: r["date"], reverse=True)[:8]
            (dist / lang / f"section-{cat}.html").write_text(
                render_section_page(lang, cat, cat_items, built_at,
                                    more_items=more_items), encoding="utf-8")
        # Archived stories breadcrumb to their section page; a section that no
        # longer has live coverage still renders, filled from the archive.
        for cat in sorted({a["cat"] for a in archived} - live_cats):
            cat_items = [a for a in archived if a["cat"] == cat]
            more_items = sorted(items, key=lambda r: r["date"], reverse=True)[:8]
            (dist / lang / f"section-{cat}.html").write_text(
                render_section_page(lang, cat, cat_items, built_at,
                                    more_items=more_items), encoding="utf-8")
        # Running-file hub pages — selected earlier alongside the nav gate,
        # written here so their footers see the full section index.
        for _tf, _hits in TOPIC_HUBS_LIVE.get(lang, []):
            _more = sorted(items, key=lambda r: r["date"], reverse=True)[:8]
            (dist / lang / f"topic-{_tf['slug']}.html").write_text(
                render_topic_page(lang, _tf, _hits, built_at, _more),
                encoding="utf-8")
        (dist / lang / "search.html").write_text(
            render_search_page(lang, built_at,
                               cats=sorted({it["cat"] for it in items})), encoding="utf-8")
        if CORRECTIONS_PAGE_LIVE:
            (dist / lang / "corrections.html").write_text(
                render_corrections_page(
                    lang, items, built_at,
                    archived_pids={a["pid"] for a in archived}), encoding="utf-8")
        (dist / lang / "search-index.json").write_text(json.dumps(
            [{"t": it["title"], "u": story_url_path(it["title"], it["pid"], lang),
              "d": truncate(it.get("dek") or "", 160),
              # Body excerpt so a name mentioned mid-story is findable
              # (site audit 2026-08-16) — plain text, capped to keep the
              # whole index a lightweight single fetch.
              "b": truncate(re.sub(r"<[^>]+>|[#*>`\[\]|]", " ",
                                   str(it.get("brief") or ""))
                            .replace("\n", " "), 400),
              "c": STR[lang]["sections"].get(it["cat"], it["cat"])}
             for it in items + archived],
            ensure_ascii=False), encoding="utf-8")
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
            story_archive.save(it)  # the permalink outlives the news cycle
        (dist / lang / "rss.xml").write_text(render_rss(lang, items, built_at), encoding="utf-8")
    (dist / "sitemap.xml").write_text(
        render_sitemap((("en", en_items), ("ar", ar_items)), built_at), encoding="utf-8")
    (dist / "robots.txt").write_text(ROBOTS_TXT, encoding="utf-8")
    __import__("seo_extras").write_extras(
        dist, (("en", en_items), ("ar", ar_items)), built_at, BASE_URL, HEALTH)
    # Archived stories count too: their pages still reference their /media/
    # assets, and a kept permalink with a dead infographic is half a page.
    # The SPECIALS band's own art must ship as well: it renders on every
    # index page independently of any story's lede, so a card SVG that only
    # a story's unused imageFallback names would otherwise never be copied
    # (production failure 2026-08-19: the campaign card 404'd its SVG the
    # moment the story's remote cover verified live).
    _specials_media = [
        {"image": s["img"]} for s in SPECIALS
        if str(s.get("img", "")).startswith("/media/")]
    __import__("longform").copy_media(
        dist, en_items + ar_items + archived_all + _specials_media)
    # Text-free hero plates (visual audit 2026-08-16): every category cover
    # gets a companion <name>-hero.svg with its <text> layers stripped, so a
    # cover-led hero shows pure art under the overlay headline instead of
    # repeating the section word. Generated fresh each build; fail-open.
    try:
        (dist / "media").mkdir(parents=True, exist_ok=True)
        for _cv in sorted((ROOT / "originals" / "media")
                          .glob("times-of-palestine-cover-*.svg")):
            if _cv.stem.endswith("-hero"):
                continue
            _svg = re.sub(r"<text\b.*?</text>", "",
                          _cv.read_text(encoding="utf-8"), flags=re.S)
            (dist / "media" / f"{_cv.stem}-hero.svg").write_text(
                _svg, encoding="utf-8")
    except Exception as exc:
        print(f"  ⚠ hero plates failed open: {type(exc).__name__}: {exc}")
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

    save_remote_image_cache()   # image overrides and covers verify late in the run
    # Section-freshness ledger (owner order 2026-08-11): every section, both
    # editions, updates at least daily. The ledger is written for the desks
    # and the daily editor, and stale sections are announced loudly on every
    # build. Fail-open — the monitor never stops the paper.
    try:
        _sf = __import__("section_freshness")
        _fresh = _sf.report()
        # Photo-led ratio (site audit 2026-08-16): the charter says covers
        # are photographs; branded category art is the stopgap. Measure the
        # front's reality on every build so the daily editor works the
        # photo-conversion queue against a number, not an impression.
        _orig = [i for i in en_items + ar_items
                 if i.get("source_id") == "top-original"]
        _cover_led = [i for i in _orig if str(i.get("image") or "").startswith(
            "/media/times-of-palestine-cover-")]
        if _orig:
            _fresh["photoLed"] = {
                "originals": len(_orig), "coverLed": len(_cover_led),
                "photoLedShare": round(1 - len(_cover_led) / len(_orig), 3),
                "coverLedPids": sorted({i["pid"] for i in _cover_led})[:40]}
            print(f"  photo-led originals: {len(_orig) - len(_cover_led)}"
                  f"/{len(_orig)} — {len(_cover_led)} still on category "
                  "covers (photo-conversion queue)")
        (dist / "section-freshness.json").write_text(
            json.dumps(_fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        # Queue-depth check (owner order 2026-08-16, "keep the machinery
        # fresh permanently"): the desk can only steer to a stale section
        # if topics.json still holds an unwritten topic for it — a dry
        # queue is the failure mode that starved humans at 45h. Count the
        # unwritten queue per category so starvation warns with its cause.
        _queue = None
        try:
            _tp = json.loads((ROOT / "topics.json").read_text(encoding="utf-8"))
            _done = json.loads((ROOT / "originals" / "_state.json")
                               .read_text(encoding="utf-8")).get("done", {})
            _queue = {}
            for _t in _tp.get("topics", []):
                if _t.get("id") not in _done:
                    _queue[_t.get("cat")] = _queue.get(_t.get("cat"), 0) + 1
        except Exception:
            pass
        for s in _fresh["stale"]:
            age = "no story yet" if s["ageHours"] is None else f"newest {s['ageHours']:.0f}h old"
            print(f"  ⚠ stale section {s['lang']}/{s['cat']}: {age} "
                  f"(target {s['staleAfterHours']}h) — assign coverage")
            print(f"::warning::stale section {s['lang']}/{s['cat']}: {age} "
                  f"(target {s['staleAfterHours']}h) — assign coverage")
            if _queue is not None and not _queue.get(s["cat"]):
                print(f"::warning::topics.json holds no unwritten topic for "
                      f"'{s['cat']}' — the desk cannot steer there beyond its "
                      "48h recycle fallback; queue new topics")
    except Exception as e:
        print(f"  ⚠ section freshness ledger failed open: {type(e).__name__}: {e}")
    print(f"\nBuilt dist/ — EN {len(en_items)} stories, AR {len(ar_items)} stories.")
    if not en_items and not ar_items:
        print("No items fetched from any feed — failing so the last good deploy stays live.")
        sys.exit(1)

if __name__ == "__main__":
    main()
