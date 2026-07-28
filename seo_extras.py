"""SEO extras for Times of Palestine: Google News sitemap, IndexNow, About pages,
and the Telegram channel auto-poster.

Kept in a separate module so build.py needs only a one-line hook. Everything
here is fail-open — discoverability plumbing must never block publication.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Public Telegram channel; posts go out via a bot the founder controls.
# The bot token lives ONLY in the TELEGRAM_BOT_TOKEN repo secret — never here,
# never in logs. Without the secret this feature silently does nothing.
TELEGRAM_CHANNEL = "@timesofpalestin"
TELEGRAM_MAX_PER_BUILD = 8  # stay far below Telegram's per-chat rate limits

# IndexNow (indexnow.org): instant URL submission to Bing/Yandex/Seznam/naver.
# No account needed — the key is proven by hosting <key>.txt at the site root.
INDEXNOW_KEY = "b66aee352627fb0ff61f3794e4c00253"

SITE_NAMES = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}

# About & Contact — Google News accountability requirements: who we are, how we
# work, editorial standards, corrections, and a way to reach the newsroom.
ABOUT = {
    "en": {
        "title": "About & Contact",
        "sections": [
            ("Who we are",
             "Times of Palestine is an independent digital newsroom covering Palestine "
             "in English and Arabic, around the clock. We answer to no government, "
             "party or faction. Our only allegiance is to verified truth, and to the "
             "people of Palestine and their God-given human rights."),
            ("How the newsroom works",
             "Our desk continuously gathers reporting from dozens of Palestinian, "
             "regional and international outlets, research institutes and primary "
             "sources. Every aggregated story names its original publisher and links "
             "directly to it; publishers retain all rights to their work. Alongside "
             "aggregation we publish original reporting and concise news briefs "
             "written by the TOP Newsdesk, clearly bylined as such."),
            ("Field reports",
             "Citizen journalists and witnesses send reports from the ground through "
             "our encrypted tip line. Before publication, every field report passes an "
             "automated triage adapted from open-source newsroom tooling: reports are "
             "screened for internal consistency and concrete, checkable detail, and "
             "held back when they rely on inflammatory rhetoric instead of facts. "
             "Field reports are published in a clearly separated section."),
            ("Editorial standards & corrections",
             "We report without censorship and without favor, we hold power to "
             "account wherever it sits, and we criticize through journalism, never "
             "personal attacks. When we get something wrong we correct it promptly. "
             "To request a correction, contact the newsroom on the channel below with "
             "the story link and the error."),
            ("Contact the newsroom",
             "Reach us on Signal — encrypted, and anonymous if you choose: "
             "message @TOP.972 or use the button below. For your safety, use Signal "
             "on a personal device and share nothing that identifies you unless you "
             "choose to."),
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
             "وهبها الله له."),
            ("كيف تعمل غرفة الأخبار",
             "يجمع مكتبنا الأخبار باستمرار من عشرات المصادر الفلسطينية والإقليمية "
             "والدولية ومراكز الأبحاث والمصادر الأولية. كل خبر مجمّع يُنسب إلى "
             "ناشره الأصلي ويُحيل إليه مباشرة، ويحتفظ الناشرون بكامل حقوقهم. وإلى "
             "جانب التجميع ننشر تقارير أصلية وملخصات إخبارية موجزة يعدّها فريق "
             "التحرير وتُنسب إليه بوضوح."),
            ("التقارير الميدانية",
             "يرسل الصحفيون المواطنون والشهود تقاريرهم من الميدان عبر خطنا الآمن "
             "المشفّر. قبل النشر، يمر كل تقرير ميداني بفرزٍ آلي مقتبس من أدوات "
             "مفتوحة المصدر لغرف الأخبار: تُفحص التقارير من حيث التماسك الداخلي "
             "والتفاصيل القابلة للتحقق، وتُحجب حين تعتمد على الخطاب التحريضي بدل "
             "الوقائع. وتُنشر التقارير الميدانية في قسم مستقل واضح."),
            ("المعايير التحريرية والتصويبات",
             "ننقل الخبر بلا رقابة وبلا محاباة، ونحاسب السلطة أينما كانت، وننتقد "
             "بالصحافة المهنية لا بالإساءات الشخصية. وحين نخطئ نصحح فوراً. لطلب "
             "تصويب، راسل غرفة الأخبار عبر القناة أدناه مع رابط المادة وبيان الخطأ."),
            ("اتصل بغرفة الأخبار",
             "راسلنا على «سيغنال» — مشفّر، ومجهول الهوية إن اخترت: "
             "@TOP.972 أو عبر الزر أدناه. لسلامتك، استخدم «سيغنال» من جهازك "
             "الشخصي ولا تشارك أي تفاصيل تكشف هويتك إلا إذا اخترت ذلك."),
        ],
        "cta": "راسلنا على سيغنال",
        "back": "كل الأخبار ←",
    },
}


def render_about(lang, built_at):
    b = __import__("build")
    t, a = b.STR[lang], ABOUT[lang]
    body = "".join(
        f'<h2 style="font-family:var(--serif);font-size:1.25rem;margin-top:1.6rem">{h}</h2>'
        f'<p class="summary">{p}</p>' for h, p in a["sections"])
    return f"""<!DOCTYPE html>
<html lang="{t['lang']}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0b0c"><link rel="manifest" href="/manifest.json">
<title>{a['title']} — {t['site_name']}</title>
<meta name="description" content="{a['sections'][0][1][:155]}">
<link rel="canonical" href="{b.BASE_URL}/{lang}/about.html">
<link rel="alternate" hreflang="en" href="{b.BASE_URL}/en/about.html">
<link rel="alternate" hreflang="ar" href="{b.BASE_URL}/ar/about.html">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{b.FONTS}" rel="stylesheet">
<style>{b.CSS}</style>
</head>
<body>
<div class="backbar"><a href="./">{a['back']}</a></div>
<header class="masthead compact"><div class="wrap">
  <a class="logotype" href="./"><h1><span class="l1">{t['masthead_top']}</span> <span class="l2">{t['masthead_bottom']}</span></h1></a>
</div></header>
<main>
  <article class="story">
    <p class="kick">{t['site_name']}</p>
    <h1>{a['title']}</h1>
    {body}
    <div class="cta"><a href="{b.SIGNAL_URL}" target="_blank" rel="noopener">🔒 {a['cta']} — @TOP.972</a></div>
  </article>
</main>
<footer><div class="wrap">
  <div class="flagline"></div>
  <div class="legal">
    <span>© {built_at.year} {t['site_name']} · timesofpalestine.com</span>
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
                f"<url><loc>{base_url}/{lang}/story/{it['pid']}.html</loc>"
                f"<news:news><news:publication>"
                f"<news:name>{SITE_NAMES[lang]}</news:name>"
                f"<news:language>{lang}</news:language>"
                f"</news:publication>"
                f"<news:publication_date>{it['date'].isoformat()}</news:publication_date>"
                f"<news:title>{title}</news:title>"
                f"</news:news></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + "".join(urls) + "</urlset>")


def ping_indexnow(langs_items, base_url):
    """Submit the freshest story URLs (last 24h) so search engines index them now."""
    now = datetime.now(timezone.utc)
    fresh = [f"{base_url}/{lang}/story/{it['pid']}.html"
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


def post_telegram(dist, langs_items, base_url):
    """Post new stories to the TOP Telegram channel, once each, newest first.

    Posted-story markers ride in briefs-cache.json (already persisted between
    builds by the workflow cache). The very first run with a token seeds the
    cache silently so the channel is not flooded with the whole backlog."""
    token = "".join(os.environ.get("TELEGRAM_BOT_TOKEN", "").split())
    if not token:
        return
    cache_path = dist.parent / "briefs-cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    except Exception:
        cache = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    items = sorted((it for _, lang_items in langs_items for it in lang_items),
                   key=lambda i: i["date"], reverse=True)
    fresh = [i for i in items if f"tg:{i['lang']}:{i['pid']}" not in cache]
    if not any(k.startswith("tg:") for k in cache):  # first run: seed, don't flood
        for it in fresh:
            cache[f"tg:{it['lang']}:{it['pid']}"] = {"ts": now_ts}
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"  → Telegram: first run — seeded {len(fresh)} stories, posting starts next build")
        return
    posted = 0
    for it in fresh[:TELEGRAM_MAX_PER_BUILD]:
        text = f"{it['title']}\n\n{base_url}/{it['lang']}/story/{it['pid']}.html"
        body = urllib.parse.urlencode({"chat_id": TELEGRAM_CHANNEL, "text": text}).encode()
        try:
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    cache[f"tg:{it['lang']}:{it['pid']}"] = {"ts": now_ts}
                    posted += 1
        except Exception:
            break  # rate limit or outage — try again next build
        time.sleep(3)
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    print(f"  → Telegram: posted {posted} new stories to {TELEGRAM_CHANNEL}")


def write_extras(dist, langs_items, built_at, base_url):
    """Hook called from build.py main() after the standard sitemap/robots write."""
    try:
        (dist / "news-sitemap.xml").write_text(
            render_news_sitemap(langs_items, built_at, base_url), encoding="utf-8")
        (dist / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8"); [(dist / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8") for f in dist.parent.glob("google*.html")]; [(dist / n).write_bytes((dist.parent / n).read_bytes()) for n in ("manifest.json", "sw.js", "icon-512.png") if (dist.parent / n).exists()]
        robots = dist / "robots.txt"
        robots.write_text(robots.read_text(encoding="utf-8")
                          + f"Sitemap: {base_url}/news-sitemap.xml\n", encoding="utf-8")
        for lang, _ in langs_items:  # About & Contact (Google News accountability)
            (dist / lang / "about.html").write_text(
                render_about(lang, built_at), encoding="utf-8")
        sm = dist / "sitemap.xml"  # about pages join the regular sitemap
        about_urls = "".join(f"<url><loc>{base_url}/{lang}/about.html</loc></url>"
                             for lang, _ in langs_items)
        sm.write_text(sm.read_text(encoding="utf-8")
                      .replace("</urlset>", about_urls + "</urlset>"), encoding="utf-8")
    except Exception as e:
        print(f"  ✗ seo extras (files): {type(e).__name__}")
        return
    try:
        status, n = ping_indexnow(langs_items, base_url)
        print(f"  → IndexNow: submitted {n} fresh URLs (HTTP {status})")
    except Exception as e:  # network hiccups must not fail the build
        print(f"  → IndexNow ping skipped ({type(e).__name__})")
    try:
        post_telegram(dist, langs_items, base_url)
    except Exception as e:  # the channel must never block the site
        print(f"  → Telegram posting skipped ({type(e).__name__})")
