"""Fetch the text of public X/Twitter posts — and, since 2026-09-05, any
other public page (a Facebook event, an announcement) — the newsroom's
link-resolver.

The editorial sandbox that Claude works in cannot reach x.com (egress
proxy), while the CI runners can. This script runs in the `x-fetch`
workflow (workflow_dispatch): given post URLs or bare status IDs it prints
each post's author, timestamp, full text and media links into the job log,
where the newsroom session reads them back. Stdlib only; fail-open per
post so one dead ID never hides the others.

Resolution order per post: the fxtwitter JSON API, then vxtwitter, then
Twitter's official oEmbed endpoint (text only). All three serve public
posts without credentials.
"""
import html
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; TimesOfPalestine-newsroom/1.0)"}


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _via_fx_style(host, sid):
    data = _get_json(f"https://{host}/status/{sid}")
    tweet = data.get("tweet") or data
    if not tweet.get("text"):
        raise ValueError("no text in response")
    author = tweet.get("author") or {}
    media = tweet.get("media") or {}
    photos = [m.get("url") for m in (media.get("photos") or []) if m.get("url")]
    videos = [m.get("url") for m in (media.get("videos") or []) if m.get("url")]
    quoted = tweet.get("quote") or {}
    return {
        "author": f'{author.get("name", "?")} (@{author.get("screen_name", "?")})',
        "date": tweet.get("created_at", "?"),
        "text": tweet.get("text", ""),
        "photos": photos,
        "videos": videos,
        "quoted": (f'@{(quoted.get("author") or {}).get("screen_name", "?")}: '
                   f'{quoted.get("text", "")}') if quoted else "",
        "via": host,
    }


def _via_oembed(sid):
    data = _get_json("https://publish.twitter.com/oembed?omit_script=1&url="
                     f"https://twitter.com/i/status/{sid}")
    text = re.sub(r"<[^>]+>", " ", data.get("html", ""))
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if not text:
        raise ValueError("empty oembed html")
    return {"author": data.get("author_name", "?"), "date": "?",
            "text": text, "photos": [], "videos": [], "quoted": "",
            "via": "publish.twitter.com/oembed"}


def fetch(sid):
    errors = []
    for attempt in (lambda: _via_fx_style("api.fxtwitter.com", sid),
                    lambda: _via_fx_style("api.vxtwitter.com", sid),
                    lambda: _via_oembed(sid)):
        try:
            return attempt()
        except Exception as exc:   # noqa: BLE001 — try the next mirror
            errors.append(f"{type(exc).__name__}: {exc}")
    return {"error": " | ".join(errors)}


# ---- any other public page (owner request 2026-09-05: a Facebook event) ----
# The same egress wall hides every social page from the sandbox. For a
# non-X URL the resolver fetches the page from the runner with a browser
# UA and prints what a reader would see: <title>, the Open Graph title and
# description (Facebook serves these to logged-out fetches even when the
# body is a login wall), then the visible text, capped. Facebook URLs are
# also tried through the m./mbasic. hosts, which render events without a
# session more often than www does. Fail-open per URL.
_TAG_RX = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_META_RX = re.compile(
    r'<meta\s+(?:[^>]*?)(?:property|name)=["\'](og:title|og:description|description|'
    r'twitter:title|twitter:description)["\'][^>]*?content=["\']([^"\']*)["\']', re.I)
_META_RX2 = re.compile(
    r'<meta\s+(?:[^>]*?)content=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\'](og:title|'
    r'og:description|description|twitter:title|twitter:description)["\']', re.I)
BROWSER_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
              "Accept-Language": "en-US,en;q=0.8,ar;q=0.6"}


def page_text(url, timeout=25):
    req = urllib.request.Request(url, headers=BROWSER_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1_500_000)
        final = r.geturl()
    doc = raw.decode("utf-8", "replace")
    meta = {}
    for m in _META_RX.finditer(doc):
        meta.setdefault(m.group(1).lower(), html.unescape(m.group(2)))
    for m in _META_RX2.finditer(doc):
        meta.setdefault(m.group(2).lower(), html.unescape(m.group(1)))
    title = re.search(r"<title[^>]*>(.*?)</title>", doc, re.S | re.I)
    body = _TAG_RX.sub(" ", doc)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", body, flags=re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    body = re.sub(r"[ \t\xa0]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body).strip()
    return {"final_url": final,
            "title": html.unescape(title.group(1)).strip() if title else "",
            "meta": meta, "text": body[:6000]}


def _page_variants(url):
    yield url
    m = re.match(r"https?://(?:www\.|web\.)?facebook\.com/(.*)$", url)
    if m:
        path = m.group(1)
        ev = re.search(r"/(\d{10,20})/?", "/" + path)
        if ev and "/events/" in "/" + path:
            path_ev = f"events/{ev.group(1)}/"
            yield f"https://m.facebook.com/{path_ev}"
            yield f"https://mbasic.facebook.com/{path_ev}"
            yield f"https://www.facebook.com/{path_ev}"
        else:
            yield f"https://m.facebook.com/{path}"
            yield f"https://mbasic.facebook.com/{path}"


def fetch_pages(urls):
    ok = 0
    for url in urls:
        print(f"\n=== PAGE {url} ===")
        got = None
        errors = []
        for variant in _page_variants(url):
            try:
                got = page_text(variant)
            except Exception as exc:   # noqa: BLE001 — try the next host
                errors.append(f"{variant}: {type(exc).__name__}: {exc}")
                continue
            if got["meta"].get("og:description") or len(got["text"]) > 400:
                break
        if not got:
            print("ERROR: could not fetch: " + " | ".join(errors))
            continue
        ok += 1
        print(f"final:  {got['final_url']}")
        print(f"title:  {got['title']}")
        for k in ("og:title", "og:description", "description", "twitter:title", "twitter:description"):
            if got["meta"].get(k):
                print(f"{k}: {got['meta'][k]}")
        print("text:")
        print(got["text"])
    print(f"\n=== {ok}/{len(urls)} page(s) fetched ===")
    return 0 if ok else 1


def main(argv):
    joined = " ".join(argv)
    pages = [u for u in re.findall(r"https?://\S+", joined)
             if not re.match(r"https?://(?:[\w-]+\.)*(?:x|twitter)\.com/", u)]
    ids = re.findall(r"\b(\d{15,25})\b", re.sub(r"https?://\S+", lambda m: "" if m.group(0) in pages else m.group(0), joined))
    if pages and not ids:
        return fetch_pages([u.rstrip(",") for u in pages])
    if pages:
        fetch_pages([u.rstrip(",") for u in pages])
    if not ids:
        print("x_fetch: no status IDs found in input", file=sys.stderr)
        return 1
    ok = 0
    for sid in dict.fromkeys(ids):
        post = fetch(sid)
        print(f"\n=== X POST {sid} ===")
        if "error" in post:
            print(f"ERROR: could not fetch: {post['error']}")
            continue
        ok += 1
        print(f"author: {post['author']}")
        print(f"date:   {post['date']}  (via {post['via']})")
        print("text:")
        print(post["text"])
        if post["quoted"]:
            print(f"quoted: {post['quoted']}")
        for url in post["photos"]:
            print(f"photo:  {url}")
        for url in post["videos"]:
            print(f"video:  {url}")
    print(f"\n=== {ok}/{len(dict.fromkeys(ids))} post(s) fetched ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
