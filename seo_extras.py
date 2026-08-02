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
    canonicalize_url, is_http_url, is_public_http_url, safe_urlopen, utc_iso,
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
             "Citizen journalists and witnesses send dispatches from the ground through "
             "our encrypted tip line. Field reports go through an editorial check and "
             "appear in their own clearly labelled section of the site, so readers "
             "always know the source and nature of what they are reading."),
            ("Editorial standards & corrections",
             "We report without censorship and without favor, we hold power to "
             "account wherever it sits, and we criticize through journalism, never "
             "personal attacks. When we get something wrong we correct it promptly. "
             "To request a correction, contact the newsroom on the channel below with "
             "the story link and the error."),
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
             "وهبها الله له."),
            ("كيف تعمل غرفة الأخبار",
             "يجمع مكتبنا الأخبار باستمرار من عشرات المصادر الفلسطينية والإقليمية "
             "والدولية ومراكز الأبحاث والمصادر الأولية. كل خبر مجمّع يُنسب إلى "
             "ناشره الأصلي ويُحيل إليه مباشرة، ويحتفظ الناشرون بكامل حقوقهم. وإلى "
             "جانب التجميع ننشر تقارير أصلية وملخصات إخبارية موجزة يعدّها فريق "
             "التحرير وتُنسب إليه بوضوح."),
            ("التقارير الميدانية",
             "يرسل الصحفيون المواطنون والشهود تقاريرهم من الميدان عبر خطنا الآمن "
             "المشفّر. تخضع التقارير الميدانية لمراجعة تحريرية وتُنشر في قسم خاص "
             "بها معرَّف بوضوح، حتى يعرف القراء دائماً مصدر ما يقرؤونه وطبيعته."),
            ("المعايير التحريرية والتصويبات",
             "ننقل الخبر بلا رقابة وبلا محاباة، ونحاسب السلطة أينما كانت، وننتقد "
             "بالصحافة المهنية لا بالإساءات الشخصية. وحين نخطئ نصحح فوراً. لطلب "
             "تصويب، راسل غرفة الأخبار عبر القناة أدناه مع رابط المادة وبيان الخطأ."),
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
    body = "".join(
        f'<h2 class="about-section">{h}</h2>'
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
<link href="/assets/site.css" rel="stylesheet">
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
                f"<url><loc>{base_url}/{lang}/story/{it['pid']}.html</loc>"
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
                "url": f"{base_url}/{it['lang']}/story/{it['pid']}.html",
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
        page_url = f"{base_url}/{lang}/story/{item['pid']}.html"
        row = {
            "id": page_url,
            "url": page_url,
            "external_url": None if item.get("original") else item["link"],
            "title": item["title"],
            "summary": (item.get("brief") or item.get("dek") or "")[:1000],
            "date_published": utc_iso(item["date"]),
            "language": lang,
            "authors": [{"name": item["source"],
                         **({"url": item["source_url"]} if item.get("source_url") else {})}],
            "tags": [item["cat"]],
        }
        if item.get("modified"):
            row["date_modified"] = utc_iso(item["modified"])
        if item.get("image"):
            row["image"] = item["image"]
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
        page_url = f"{base_url}/{item['lang']}/story/{item['pid']}.html"
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
    title = "حالة النشر" if lang == "ar" else "Publishing status"
    loading = "جارٍ تحميل حالة آخر بناء…" if lang == "ar" else "Loading latest build health…"
    return f"""<!DOCTYPE html><html lang="{lang}" dir="{'rtl' if lang == 'ar' else 'ltr'}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — {SITE_NAMES[lang]}</title><link rel="stylesheet" href="/assets/site.css"></head>
<body><main><article class="story"><p class="kick">{SITE_NAMES[lang]}</p><h1>{title}</h1>
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
    for name in ("manifest.json", "sw.js", "icon-512.png", "icon-192.png", "favicon.ico"):
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
    (dist / "404.html").write_text('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Page not found — Times of Palestine</title><meta name="robots" content="noindex"><link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/icon-192.png"><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#faf9f4;color:#141419;font-family:-apple-system,Helvetica,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:2rem}a{color:inherit}h1{font-family:Georgia,serif;font-size:clamp(1.6rem,4vw,2.4rem);font-weight:900;line-height:1.15}.flag{width:130px;height:5px;margin:0 auto 1.6rem;background:linear-gradient(90deg,#0b0b0c 0 34%,#C8102E 34% 67%,#00753A 67% 100%)}p{margin-top:.9rem;color:#595962;line-height:1.6}.links{margin-top:1.8rem;display:flex;gap:.8rem;justify-content:center;flex-wrap:wrap}.links a{background:#C8102E;color:#fff;font-weight:800;padding:.8rem 1.6rem;border-radius:3px;text-decoration:none}@media (prefers-color-scheme:dark){body{background:#101013;color:#e9e9ef}p{color:#a0a0aa}.links a{background:#ff8896;color:#101013}}</style></head><body><div><div class="flag"></div><h1>That page is no longer here.</h1><p>Stories rotate off the front page as the news moves. The newsroom is still publishing — pick an edition below.</p><p dir="rtl" lang="ar">تدور الأخبار وتُستبدل الصفحات باستمرار. اختر النسخة التي تريد قراءتها.</p><div class="links"><a href="/en/">English edition</a><a href="/ar/">النسخة العربية</a></div></div></body></html>', encoding="utf-8")
    sm = dist / "sitemap.xml"
    extra_urls = "".join(
        f"<url><loc>{base_url}/{lang}/{page}</loc></url>"
        for lang, _ in langs_items for page in ("about.html", "status.html"))
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
