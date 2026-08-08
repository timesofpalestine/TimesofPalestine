"""SEO extras for Times of Palestine: Google News sitemap, IndexNow, About pages,
and the post-deploy Telegram delivery outbox.

Kept in a separate module so build.py needs only a one-line hook. Everything
here is fail-open — discoverability plumbing must never block publication.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile

from publishing import (
    canonicalize_url, is_http_url, is_public_http_url, safe_urlopen,
    story_short_path, story_url_path, utc_iso,
)

# Public Telegram channel; posts go out via a bot the founder controls.
# The bot token lives ONLY in the TELEGRAM_BOT_TOKEN repo secret — never here
# and never in logs. Without the secret the publisher reports itself disabled.
TELEGRAM_CHANNEL = "@timesofpalestin"
TELEGRAM_MAX_AGE_H = 6
TELEGRAM_OUTBOX = "telegram-outbox.json"
WEBHOOK_LEDGER = "webhook-delivery.json"

# IndexNow (indexnow.org): instant URL submission to Bing/Yandex/Seznam/naver.
# No account needed — the key is proven by hosting <key>.txt at the site root.
INDEXNOW_KEY = "b66aee352627fb0ff61f3794e4c00253"

SITE_NAMES = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}

# About & Contact — Google News accountability requirements: who we are, how we
# work, editorial standards, corrections, and a way to reach the newsroom.
# Rewritten 2026-08-05 (owner request): the page now tells the whole story —
# the living front page, the automated newsroom and its binding rules, the
# standing beats and reader services, the two-editions standard, the Palestine
# Times inheritance — in a register worthy of the masthead.
ABOUT = {
    "en": {
        "title": "About & Contact",
        "sections": [
            ("Who we are",
             "Times of Palestine is an independent digital newsroom covering Palestine "
             "in English and Arabic, around the clock. We answer to no government, "
             "party or faction. Our only allegiance is to verified truth, and to the "
             "people of Palestine and their God-given human rights. The name carries "
             "an inheritance: our publisher holds the title and archive of the "
             "Palestine Times, the English-language daily launched in Ramallah in "
             "2006, and this newsroom is its revival — the same duty, rebuilt for a "
             "new era."),
            ("Ownership &amp; funding",
             "Times of Palestine is privately owned and funded by its publisher, "
             "who also holds the title and archive of the Palestine Times. The "
             "site carries no advertising and no sponsored content, and accepts "
             "no funding from any government, party or faction. The publisher "
             "pays the newsroom's operating costs directly, and no funder — the "
             "publisher included — directs the coverage of any story: reporting "
             "decisions are made under the house editorial charter alone."),
            ("A living front page",
             "News here is never parked. The site rebuilds and republishes "
             "continuously, day and night: the lead story follows the news cycle, "
             "the freshest reporting carries a pulsing NEW mark, the breaking ticker "
             "runs in strict chronological order, and every timestamp is honest to "
             "the minute. When the story moves, the page moves with it."),
            ("How our journalism is made",
             "Our desk gathers reporting continuously from dozens of Palestinian, "
             "regional and international outlets, research institutes and primary "
             "sources, and rewrites every wire item in-house before it publishes — "
             "no story runs until its rewrite is complete. Each story names the "
             "outlet whose reporting it draws on inline in the text; the page's "
             "machine-readable record preserves the full source trail, publishers "
             "retain all rights to their work, and pages that carry a source's own "
             "summary link to it directly. Alongside the wire, our investigations "
             "desk researches and files original in-depth reports in both languages."),
            ("An automated newsroom, under binding rules",
             "Much of this newsroom runs on purpose-built editorial systems working "
             "under a binding house charter, supervised by the publisher. The rules "
             "are enforced in the publishing pipeline itself: one incident becomes "
             "one article, incomplete copy never runs, a headline must say who did "
             "what, and every correction or update is stamped, dated, on the "
             "story itself. Automation sets our pace; the charter sets our "
             "standards."),
            ("What we cover",
             "Beyond the day's news we keep standing files. Transparency & "
             "Accountability follows public money and unaccountable power, at "
             "volume, in both languages. Her Story reports what Palestinian women "
             "survive and carry, on their own terms. Arab Support tracks what Arab "
             "states actually deliver for Palestinians — promised, funded, underway "
             "or still needed. Health & Healing covers the war's toll on bodies and "
             "minds with a solutions lens, and Financial Freedom examines money "
             "that cannot be frozen at a border. The culture, sport and diaspora "
             "pages celebrate Palestinian lives and work worldwide — from the "
             "annual TOP 100 of the most influential Palestinians to the weekly "
             "Palestinian Table — and From the Archive republishes the Palestine "
             "Times under its original dates."),
            ("Data and reader services",
             "Palestine by the Numbers is our live data ledger on the front page: "
             "sourced, dated figures, downloadable as JSON and CSV. The scholarship "
             "guide maps funded study for Palestinian students worldwide and is "
             "kept current, and the Washington Brief reads the American capital "
             "with Palestinian eyes. To follow us: on-site search, RSS and JSON "
             "feeds for each edition, and the newsroom's Telegram channel."),
            ("Two editions, one newsroom",
             "English and Arabic are both first editions — neither translates the "
             "other. The facts and evidence are locked first; then each edition is "
             "written fresh, with its own headlines and its own line edit, the way "
             "great journalism sounds in that language."),
            ("Built for Palestine's connections",
             "Readers on damaged, throttled or vanishing networks come first. Pages "
             "are light by design, a text-only lite mode is one tap away, and a "
             "page you have opened stays readable offline in your browser. News "
             "about Palestine must remain reachable inside Palestine."),
            ("Field reports",
             "Citizen journalists and witnesses send dispatches from the ground through "
             "our encrypted tip line. Field reports go through an editorial check and "
             "appear in their own clearly labelled section of the site, so readers "
             "always know the source and nature of what they are reading."),
            ("Editorial standards &amp; corrections",
             "We report without censorship and without favor, we hold power to "
             "account wherever it sits, and we criticize through journalism, never "
             "personal attacks. We report the issue, never the individual, and we "
             "credit good-faith work precisely: what is promised, funded, underway, "
             "completed and still needed. When we get something wrong we correct it "
             "promptly and note the change, dated, on the story itself. "
             "To request a correction, contact the newsroom "
             "on the channel below with the story link and the error."),
            ("Contact the newsroom",
             "Reach us on Signal — encrypted, and anonymous if you choose: "
             "message @TOP.972 or use the button below. You can also message the "
             "newsroom bot on Telegram at @TOPnewsdeskbot; Telegram is easier, but "
             "Signal is the safer choice for sensitive material. For your safety, use "
             "either on a personal device and share nothing that identifies you unless "
             "you choose to."),
        ],
        "cta": "Message us on Signal",
        "back": "← All the news",
    },
    "ar": {
        "title": "من نحن — اتصل بنا",
        "sections": [
            ("من نحن",
             "«تايمز أوف فلسطين» غرفة أخبار رقمية مستقلة تغطي فلسطين بالعربية "
             "والإنجليزية على مدار الساعة. لا نتبع حكومة ولا حزباً ولا فصيلاً؛ "
             "ولاؤنا الوحيد للحقيقة الموثّقة، ولشعب فلسطين وحقوقه الإنسانية التي "
             "وهبها الله له. ويحمل الاسم إرثاً صحفياً: يملك ناشرنا حقوق صحيفة "
             "«فلسطين تايمز» وأرشيفها — اليومية الصادرة بالإنجليزية من رام الله "
             "عام 2006 — وهذه الغرفة إحياءٌ لها: الرسالة نفسها بعُدّة عصر جديد."),
            ("الملكية والتمويل",
             "«تايمز أوف فلسطين» ملكية خاصة يموّلها ناشرها مباشرة، وهو نفسه "
             "مالك حقوق صحيفة «فلسطين تايمز» وأرشيفها. لا يعرض الموقع أي "
             "إعلانات ولا محتوى مموّلاً، ولا يقبل تمويلاً من أي حكومة أو حزب "
             "أو فصيل. يتحمّل الناشر تكاليف تشغيل غرفة الأخبار بنفسه، ولا "
             "يوجّه أي مموّل — بمن في ذلك الناشر — تغطية أي مادة: القرار "
             "التحريري يخضع للميثاق التحريري وحده."),
            ("صفحة أولى حيّة",
             "الخبر عندنا لا يُركن. يُعاد بناء الموقع ونشره باستمرار ليل نهار: "
             "الخبر الأول يتبع دورة الأخبار، والتغطية الأحدث تحمل علامة «جديد» "
             "النابضة، وشريط العاجل يلتزم التسلسل الزمني، وكل توقيت صادق حتى "
             "الدقيقة. حين يتحرك الحدث تتحرك الصفحة معه."),
            ("كيف نصنع صحافتنا",
             "يجمع مكتبنا التغطيات باستمرار من عشرات المصادر الفلسطينية "
             "والإقليمية والدولية ومراكز الأبحاث والمصادر الأولية، ويعيد صياغة "
             "كل خبر داخل غرفة التحرير قبل نشره — فلا يُنشر خبر قبل اكتمال "
             "صياغته. يسمّي كل تقرير الوسيلةَ التي استند إلى تغطيتها داخل النص، "
             "وتحفظ البيانات الوصفية لكل صفحة سجلَّ المصدر كاملاً، ويحتفظ "
             "الناشرون بكامل حقوقهم؛ أما الصفحات التي تنقل ملخص المصدر نفسه "
             "فتُحيل إليه مباشرة. وإلى جانب أخبار الوكالات ينشر مكتب التحقيقات "
             "تقارير أصلية معمّقة باللغتين."),
            ("غرفة أخبار مؤتمتة بقواعد ملزمة",
             "تؤدي أنظمةُ تحرير مبنية خصيصاً جانباً كبيراً من عمل هذه الغرفة، "
             "بإشراف الناشر ووفق ميثاق تحريري ملزم تفرضه منظومة النشر نفسها: "
             "الحادثة الواحدة تقريرٌ واحد، والنص الناقص لا يُنشر، والعنوان "
             "يسمّي مَن فعل ماذا، وكل تصويب أو تحديث يُثبَّت بتاريخه على "
             "المادة نفسها. الأتمتة تضبط إيقاعنا، والميثاق يضبط معاييرنا."),
            ("ما نغطيه",
             "إلى جانب أخبار اليوم نُمسك ملفات دائمة: «شفافية ومساءلة» يتتبع "
             "المال العام والسلطة التي لا رقيب عليها باللغتين؛ و«حكايتها» يروي "
             "ما تعيشه المرأة الفلسطينية وما تحمله بشروطها هي؛ و«الإسناد "
             "العربي» يرصد ما تقدّمه الدول العربية فعلاً لفلسطين — ما وُعد به "
             "وما مُوّل وما يجري وما ينتظر؛ و«الصحة والتعافي» يغطي أثر الحرب في "
             "الأجساد والنفوس بعين الحلول؛ و«الحرية المالية» يتناول مالاً لا "
             "يُجمَّد على معبر. وتحتفي صفحات الثقافة والرياضة والشتات "
             "بالفلسطينيين وأعمالهم حول العالم — من قائمة المئة السنوية لأكثر "
             "فلسطينيي العالم تأثيراً إلى «المائدة الفلسطينية» الأسبوعية — "
             "ويعيد قسم «من الأرشيف» نشر مواد «فلسطين تايمز» بتواريخها الأصلية."),
            ("البيانات وخدمات القراء",
             "«فلسطين بالأرقام» سجلُّنا الحي على الصفحة الأولى: أرقام موثّقة "
             "منسوبة إلى مصادرها بتواريخها، قابلة للتنزيل بصيغتي JSON وCSV. "
             "ودليل المنح الدراسية يجمع فرص الدراسة الممولة للطلبة الفلسطينيين "
             "حول العالم ويُحدَّث باستمرار، و«موجز واشنطن» يقرأ عاصمة القرار "
             "الأميركي بعين فلسطينية. وللمتابعة: بحث داخل الموقع، وخلاصات RSS "
             "وJSON لكل نسخة، وقناة غرفة الأخبار على تيليغرام."),
            ("نسختان بمعيار واحد",
             "العربية والإنجليزية طبعتان أوليان — لا تترجم إحداهما الأخرى. "
             "تُثبَّت الوقائع والأدلة أولاً، ثم تُكتب كل نسخة كتابةً أصيلة "
             "بعناوينها وتحريرها الخاص، كما يليق بالصحافة الكبرى في لغتها."),
            ("مبنيّ لاتصالات فلسطين",
             "القارئ على شبكة مقطوعة أو مخنوقة أو زائلة أولويتنا الأولى. "
             "الصفحات خفيفة بالتصميم، والوضع النصي الخفيف على بُعد لمسة، "
             "والصفحة التي فتحتها مرة تبقى مقروءة دون اتصال من متصفحك. أخبار "
             "فلسطين يجب أن تبقى في متناول أهلها داخل فلسطين."),
            ("التقارير الميدانية",
             "يرسل الصحفيون المواطنون والشهود تقاريرهم من الميدان عبر خطنا الآمن "
             "المشفّر. تخضع التقارير الميدانية لمراجعة تحريرية وتُنشر في قسم خاص "
             "بها معرَّف بوضوح، حتى يعرف القراء دائماً مصدر ما يقرؤونه وطبيعته."),
            ("المعايير التحريرية والتصويبات",
             "ننقل الخبر بلا رقابة وبلا محاباة، ونحاسب السلطة أينما كانت، وننتقد "
             "بالصحافة المهنية لا بالإساءات الشخصية. نتناول القضية لا الشخص، "
             "ونمنح العمل الجاد حقّه بدقة: ما وُعد به، وما مُوّل، وما يجري، وما "
             "اكتمل، وما ينتظر. وحين نخطئ نصحح فوراً ونثبّت التعديل بتاريخه على "
             "المادة نفسها. لطلب تصويب، راسل غرفة الأخبار عبر القناة أدناه مع "
             "رابط المادة وبيان الخطأ."),
            ("اتصل بغرفة الأخبار",
             "راسلنا على «سيغنال» — مشفّر، ومجهول الهوية إن اخترت: "
             "@TOP.972 أو عبر الزر أدناه. ويمكنك أيضاً مراسلة بوت غرفة الأخبار على "
             "تيليغرام: @TOPnewsdeskbot — تيليغرام أسهل، لكن «سيغنال» أكثر أماناً "
             "للمواد الحساسة. لسلامتك، استخدم أياً منهما من جهازك الشخصي ولا تشارك "
             "أي تفاصيل تكشف هويتك إلا إذا اخترت ذلك."),
        ],
        "cta": "راسلنا على سيغنال",
        "back": "كل الأخبار ←",
    },
}


def render_about(lang, built_at):
    b = __import__("build")
    t, a = b.STR[lang], ABOUT[lang]
    esc = b.esc
    body = "".join(
        f'<h2 class="about-section">{h}</h2>'
        f'<p class="summary">{p}</p>' for h, p in a["sections"])
    # meta_desc strips no HTML — the intro section is plain text by contract.
    desc = esc(b.meta_desc(a["sections"][0][1]))
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/icon-192.png"><link rel="manifest" href="/manifest.json">
<title>{esc(a['title'])} — {t['site_name']}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{b.BASE_URL}/{lang}/about.html">
<link rel="alternate" hreflang="en" href="{b.BASE_URL}/en/about.html">
<link rel="alternate" hreflang="ar" href="{b.BASE_URL}/ar/about.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{t['site_name']}">
<meta property="og:title" content="{esc(a['title'])} — {t['site_name']}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{b.BASE_URL}/{lang}/about.html">
<meta property="og:image" content="{b.BASE_URL}/og-banner.png">
<link href="/assets/site.css" rel="stylesheet">
{b._THEME_JS}
</head>
<body>
<a class="skiplink" href="#top">{"تخطَّ إلى المحتوى" if lang == "ar" else "Skip to content"}</a><div class="backbar"><a href="./">{a['back']}</a><span class="bb-tools">{b.theme_btn(lang)}{b.lite_btn(lang)}</span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></p></a>
</div></header>
<main>
  <article class="story">
    <p class="kick">{t['site_name']}</p>
    <h1>{esc(a['title'])}</h1>
    {body}
    <div class="cta"><a href="{b.SIGNAL_URL}" target="_blank" rel="noopener">🔒 {a['cta']} — @TOP.972</a>
    <p class="about-telegram"><a href="{b.TELEGRAM_BOT_URL}" target="_blank" rel="noopener">{t['tips_tg']} → {b.TELEGRAM_BOT_NAME}</a></p></div>
  </article>
</main>
<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span>
    <a href="status.html">{"حالة النشر" if lang == "ar" else "Publishing status"}</a>
    <a href="./">{a['back']}</a>
  </div>
</div></footer>
</body>
</html>"""


def render_news_sitemap(langs_items, built_at, base_url):
    """Google News sitemap: stories from the last 48h with <news:news> metadata."""
    urls = []
    now = datetime.now(timezone.utc)
    for lang, items in langs_items:
        for it in items:
            if (now - it["date"]).total_seconds() > 48 * 3600 or it["cat"] == "social":
                continue
            title = (it["title"].replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;"))
            urls.append(
                f"<url><loc>{base_url}{story_url_path(it['title'], it['pid'], lang)}</loc>"
                f"<news:news><news:publication>"
                f"<news:name>{SITE_NAMES[lang]}</news:name>"
                f"<news:language>{lang}</news:language>"
                f"</news:publication>"
                f"<news:publication_date>{utc_iso(it['date'])}</news:publication_date>"
                f"<news:title>{title}</news:title>"
                f"</news:news></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + "".join(urls) + "</urlset>")


def ping_indexnow(langs_items, base_url):
    """Submit the freshest story URLs (last 24h) so search engines index them now."""
    now = datetime.now(timezone.utc)
    fresh = [f"{base_url}{story_url_path(it['title'], it['pid'], lang)}"
             for lang, items in langs_items for it in items
             if (now - it["date"]).total_seconds() <= 24 * 3600]
    fresh += [f"{base_url}/en/", f"{base_url}/ar/"]
    body = json.dumps({"host": base_url.split("//")[1], "key": INDEXNOW_KEY,
                       "keyLocation": f"{base_url}/{INDEXNOW_KEY}.txt",
                       "urlList": fresh[:2000]}).encode()
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, len(fresh)


def build_telegram_outbox(langs_items, base_url, now=None):
    """Return fresh published stories, grouping bilingual originals into one post."""
    now = now or datetime.now(timezone.utc)
    groups = {}
    for _, items in langs_items:
        for it in items:
            revision_time = it.get("modified") or it["date"]
            if (now - revision_time).total_seconds() > TELEGRAM_MAX_AGE_H * 3600:
                continue
            link = str(it.get("link", ""))
            original_slug = ""
            if it.get("source_id") == "top-original" and link.startswith("original:"):
                stem = link.split(":", 1)[1]
                suffix = f".{it['lang']}"
                if stem.endswith(suffix):
                    original_slug = stem[:-len(suffix)]
            group_key = (
                f"original:{original_slug}"
                if original_slug else f"story:{it['lang']}:{it['pid']}"
            )
            group = groups.setdefault(group_key, {
                "group_key": group_key,
                "published_at": revision_time.isoformat(),
                "parts": [],
            })
            if revision_time.isoformat() > group["published_at"]:
                group["published_at"] = revision_time.isoformat()
            base_key = f"story:{it['lang']}:{it['pid']}"
            revision = utc_iso(revision_time)
            group["parts"].append({
                "delivery_key": (
                    f"{base_key}:{revision}" if it.get("modified") else base_key),
                "legacy_key": (
                    "" if it.get("modified")
                    else f"tg:{it['lang']}:{it['pid']}"),
                "lang": it["lang"],
                "pid": it["pid"],
                "title": it["title"],
                "url": f"{base_url}{story_short_path(it['pid'], it['lang'])}",
                "revision": revision,
            })
    outbox = list(groups.values())
    for entry in outbox:
        entry["parts"].sort(key=lambda part: (part["lang"] != "en", part["lang"]))
    # Oldest first leaves the newest headline at the top of the Telegram channel.
    outbox.sort(key=lambda entry: (entry["published_at"], entry["group_key"]))
    return outbox


def write_telegram_outbox(dist, langs_items, base_url):
    outbox = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel": TELEGRAM_CHANNEL,
        "entries": build_telegram_outbox(langs_items, base_url),
    }
    (dist.parent / TELEGRAM_OUTBOX).write_text(
        json.dumps(outbox, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → Telegram outbox: {len(outbox['entries'])} fresh story groups")


def render_json_feed(lang, items, base_url):
    """Credential-free JSON Feed containing only publication-eligible stories."""
    title = SITE_NAMES[lang]
    rows = []
    for item in sorted(items, key=lambda row: row["date"], reverse=True):
        page_url = f"{base_url}{story_url_path(item['title'], item['pid'], lang)}"
        row = {
            "id": page_url,
            "url": page_url,
            "external_url": None if item.get("original") else item["link"],
            "title": item["title"],
            "summary": (item.get("brief") or item.get("dek") or "")[:1000],
            "date_published": utc_iso(item["date"]),
            "language": lang,
            # Wire attribution protocol: rewritten briefs are our copy — the
            # outlet credit rides only dek-fallback items (no brief).
            "authors": [
                {"name": title} if item.get("original") or item.get("brief")
                else {"name": item["source"],
                      **({"url": item["source_url"]}
                         if item.get("source_url") else {})}],
            "tags": [item["cat"]],
        }
        if item.get("modified"):
            row["date_modified"] = utc_iso(item["modified"])
        if item.get("image"):
            img = item["image"]
            row["image"] = img if img.startswith("http") else f"{base_url}{img}"
        rows.append(row)
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": title,
        "home_page_url": f"{base_url}/{lang}/",
        "feed_url": f"{base_url}/{lang}/feed.json",
        "language": lang,
        "items": rows,
    }


def render_distribution_outbox(langs_items, base_url, built_at):
    items = []
    for lang, rows in langs_items:
        for item in rows:
            items.append({
                "pid": item["pid"],
                "lang": lang,
                "title": item["title"],
                "date": utc_iso(item["date"]),
                "modified": utc_iso(item["modified"]) if item.get("modified") else None,
                "source": item["source"],
                "source_url": item.get("source_url", ""),
                "original": bool(item.get("original")),
                "link": item.get("link", ""),
            })
    return {
        "schemaVersion": 1,
        "generatedAt": utc_iso(built_at),
        "baseUrl": base_url,
        "items": items,
    }


def delivery_revision(item):
    return utc_iso(delivery_time(item))


def delivery_time(item):
    return item.get("modified") or item["date"]


def needs_revision_delivery(cache, marker, item):
    previous = cache.get(marker)
    if previous is None:
        return True
    if not item.get("modified"):
        return False
    return previous.get("revision") != delivery_revision(item)


def save_delivery_ledger(path, ledger):
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(ledger, handle, ensure_ascii=False)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def post_webhook(dist, langs_items, base_url):
    """Send a bounded outbox to an optional generic connector."""
    target = os.environ.get("DISTRIBUTION_WEBHOOK_URL", "").strip()
    if not target:
        return "disabled"
    if not is_public_http_url(target):
        raise ValueError("DISTRIBUTION_WEBHOOK_URL must be a public HTTP(S) URL")
    cache_path = dist.parent / WEBHOOK_LEDGER
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    items = sorted(
        (item for _, rows in langs_items for item in rows),
        key=lambda item: item["date"],
        reverse=True,
    )
    pending = [
        item for item in items
        if needs_revision_delivery(
            cache, f"webhook:{item['lang']}:{item['pid']}", item)
    ][:20]
    posted = 0
    for item in pending:
        page_url = f"{base_url}{story_short_path(item['pid'], item['lang'])}"
        revision = delivery_revision(item)
        key = f"top:{item['lang']}:{item['pid']}:{revision}"
        payload = json.dumps({
            "id": key,
            "title": item["title"],
            "url": page_url,
            "publishedAt": utc_iso(item["date"]),
            "modifiedAt": (
                utc_iso(item["modified"]) if item.get("modified") else None),
            "revision": revision,
            "language": item["lang"],
            "source": item["source"],
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            target,
            data=payload,
            headers={"Content-Type": "application/json", "Idempotency-Key": key},
        )
        with safe_urlopen(
            request, timeout=15, allow_redirects=False
        ) as response:
            if not 200 <= response.status < 300:
                raise OSError(f"webhook returned HTTP {response.status}")
        cache[f"webhook:{item['lang']}:{item['pid']}"] = {
            "ts": datetime.now(timezone.utc).timestamp(),
            "revision": revision,
        }
        save_delivery_ledger(cache_path, cache)
        posted += 1
    if not pending:
        save_delivery_ledger(cache_path, cache)
    print(f"  → webhook: delivered {posted} eligible stories")
    return "ok"


def render_status(lang):
    b = __import__("build")
    title = "حالة النشر" if lang == "ar" else "Publishing status"
    desc = ("حالة النشر الآلي لغرفة أخبار «تايمز أوف فلسطين»: آخر بناء وعدد القصص المنشورة."
            if lang == "ar" else
            "Live publishing health for the Times of Palestine newsroom: last build time and story counts.")
    loading = "جارٍ تحميل حالة آخر بناء…" if lang == "ar" else "Loading latest build health…"
    return f"""<!DOCTYPE html><html lang="{lang}" dir="{'rtl' if lang == 'ar' else 'ltr'}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="icon" href="/favicon.ico" sizes="48x48">
<title>{title} — {SITE_NAMES[lang]}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{b.BASE_URL}/{lang}/status.html">
<link rel="alternate" hreflang="en" href="{b.BASE_URL}/en/status.html">
<link rel="alternate" hreflang="ar" href="{b.BASE_URL}/ar/status.html">
<link rel="stylesheet" href="/assets/site.css">
{b._THEME_JS}
</head>
<body><div class="backbar"><a href="./">{"العودة إلى الأخبار" if lang == "ar" else "Back to the news"}</a><span class="bb-tools">{b.theme_btn(lang)}{b.lite_btn(lang)}</span></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><p class="wordmark"><span class="l1">{b.STR[lang]['masthead_top']}</span> <span class="l2">{b.STR[lang]['masthead_bottom']}</span></p></a>
</div></header>
<main><article class="story"><p class="kick">{SITE_NAMES[lang]}</p><h1>{title}</h1>
<p id="health" class="summary">{loading}</p><p><a href="./">{"العودة إلى الأخبار" if lang == "ar" else "Back to the news"}</a></p>
</article></main><script>
fetch("/health.json",{{cache:"no-store"}}).then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}})
.then(h=>{{const L={{"operational":{'"النشر منتظم"' if lang == "ar" else '"PUBLISHING NORMALLY"'},"degraded":{'"تدفق آلي مخفّض"' if lang == "ar" else '"REDUCED AUTOMATED FLOW"'},"down":{'"متوقف مؤقتاً"' if lang == "ar" else '"PAUSED"'}}};document.getElementById("health").textContent=`${{L[h.status]||h.status.toUpperCase()}} · ${{h.builtAt}} · EN ${{h.stories.en}} · AR ${{h.stories.ar}} · held ${{h.reviewHeld}}`;}})
.catch(()=>{{document.getElementById("health").textContent="Status unavailable";}});
</script></body></html>"""


def write_extras(dist, langs_items, built_at, base_url, health):
    """Hook called from build.py main() after the standard sitemap/robots write."""
    (dist / "news-sitemap.xml").write_text(
        render_news_sitemap(langs_items, built_at, base_url), encoding="utf-8")
    (dist / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    for source in dist.parent.glob("google*.html"):
        (dist / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    for name in ("manifest.json", "sw.js", "icon-512.png", "icon-512-maskable.png",
                 "icon-192.png", "favicon.ico"):
        source = dist.parent / name
        if source.exists():
            (dist / name).write_bytes(source.read_bytes())
    robots = dist / "robots.txt"
    robots.write_text(robots.read_text(encoding="utf-8")
                      + f"Sitemap: {base_url}/news-sitemap.xml\n", encoding="utf-8")
    for lang, items in langs_items:
        (dist / lang / "about.html").write_text(
            render_about(lang, built_at), encoding="utf-8")
        (dist / lang / "status.html").write_text(render_status(lang), encoding="utf-8")
        (dist / lang / "feed.json").write_text(
            json.dumps(render_json_feed(lang, items, base_url), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (dist / "distribution-outbox.json").write_text(
        json.dumps(
            render_distribution_outbox(langs_items, base_url, built_at),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_telegram_outbox(dist, langs_items, base_url)
    (dist / "404.html").write_text('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Page not found — Times of Palestine</title><meta name="robots" content="noindex"><link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/icon-192.png"><script>try{var t=localStorage.getItem("top-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}</script><style>*{margin:0;padding:0;box-sizing:border-box}:root{--paper:#f8f7f2;--ink:#141419;--muted:#595962;--red:#C8102E}@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#121417;--ink:#e8eaed;--muted:#a3a8b2;--red:#d43049}}:root[data-theme=dark]{--paper:#121417;--ink:#e8eaed;--muted:#a3a8b2;--red:#d43049}body{background:var(--paper);color:var(--ink);font-family:-apple-system,Helvetica,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:2rem}a{color:inherit}h1{font-family:Georgia,serif;font-size:clamp(1.6rem,4vw,2.4rem);font-weight:900;line-height:1.15}.flag{width:130px;height:5px;margin:0 auto 1.6rem;background:linear-gradient(90deg,#0b0b0c 0 34%,#C8102E 34% 67%,#00753A 67% 100%)}p{margin-top:.9rem;color:var(--muted);line-height:1.6}.links{margin-top:1.8rem;display:flex;gap:.8rem;justify-content:center;flex-wrap:wrap}.links a{background:var(--red);color:#fff;font-weight:800;padding:.8rem 1.6rem;border-radius:3px;text-decoration:none}</style></head><body><div><div class="flag"></div><h1>That page is no longer here.</h1><p>Stories rotate off the front page as the news moves. The newsroom is still publishing — pick an edition below.</p><p dir="rtl" lang="ar">تدور الأخبار وتُستبدل الصفحات باستمرار. اختر النسخة التي تريد قراءتها.</p><div class="links"><a href="/en/">English edition</a><a href="/ar/">النسخة العربية</a></div></div></body></html>', encoding="utf-8")
    sm = dist / "sitemap.xml"
    extra_urls = "".join(
        f"<url><loc>{base_url}/{lang}/{page}</loc></url>"
        for lang, _ in langs_items
        for page in (("about.html", "corrections.html", "status.html")
                     if __import__("build").CORRECTIONS_PAGE_LIVE
                     else ("about.html", "status.html")))
    sm.write_text(sm.read_text(encoding="utf-8")
                  .replace("</urlset>", extra_urls + "</urlset>"), encoding="utf-8")
    health.checks["discovery_files"] = "ok"
    connector_status = "disabled" if os.environ.get("TOP_OFFLINE") == "1" else "post_deploy"
    health.connectors.update({
        "indexnow": connector_status,
        "telegram": connector_status,
        "webhook": connector_status,
    })


def deliver(dist, langs_items, base_url, health):
    """Run external side effects only after the generated site has validated."""
    if os.environ.get("TOP_OFFLINE") == "1":
        health.connectors.update({
            "indexnow": "disabled", "telegram": "disabled", "webhook": "disabled"})
        return
    try:
        status, n = ping_indexnow(langs_items, base_url)
        print(f"  → IndexNow: submitted {n} fresh URLs (HTTP {status})")
        health.connectors["indexnow"] = "ok"
    except Exception as e:  # network hiccups must not fail the build
        print(f"  → IndexNow ping skipped ({type(e).__name__})")
        health.connectors["indexnow"] = "degraded"
    health.connectors["telegram"] = "external_outbox"
    try:
        health.connectors["webhook"] = post_webhook(dist, langs_items, base_url)
    except Exception as e:
        print(f"  → webhook posting skipped ({type(e).__name__})")
        health.connectors["webhook"] = "degraded"
