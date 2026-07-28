"""SEO extras for Times of Palestine: Google News sitemap + IndexNow pings.

Kept in a separate module so build.py needs only a one-line hook. Everything
here is fail-open — discoverability plumbing must never block publication.
"""
import json
import urllib.request
from datetime import datetime, timezone

# IndexNow (indexnow.org): instant URL submission to Bing/Yandex/Seznam/naver.
# No account needed — the key is proven by hosting <key>.txt at the site root.
INDEXNOW_KEY = "b66aee352627fb0ff61f3794e4c00253"

SITE_NAMES = {"en": "Times of Palestine", "ar": "تايمز أوف فلسطين"}


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


def write_extras(dist, langs_items, built_at, base_url):
    """Hook called from build.py main() after the standard sitemap/robots write."""
    try:
        (dist / "news-sitemap.xml").write_text(
            render_news_sitemap(langs_items, built_at, base_url), encoding="utf-8")
        (dist / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
        robots = dist / "robots.txt"
        robots.write_text(robots.read_text(encoding="utf-8")
                          + f"Sitemap: {base_url}/news-sitemap.xml\n", encoding="utf-8")
    except Exception as e:
        print(f"  ✗ seo extras (files): {type(e).__name__}")
        return
    try:
        status, n = ping_indexnow(langs_items, base_url)
        print(f"  → IndexNow: submitted {n} fresh URLs (HTTP {status})")
    except Exception as e:  # network hiccups must not fail the build
        print(f"  → IndexNow ping skipped ({type(e).__name__})")

