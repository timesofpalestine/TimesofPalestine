"""Fetch the text of public X/Twitter posts — the newsroom's link-resolver.

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


def main(argv):
    ids = re.findall(r"\b(\d{15,25})\b", " ".join(argv))
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
