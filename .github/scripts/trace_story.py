import json, sys
sys.path.insert(0, ".")
import build
target = sys.argv[1] if len(sys.argv) > 1 else "7b5ecb12e4"
feeds = json.load(open("feeds.json", encoding="utf-8"))
for lang, roster in feeds.items():
    for feed in roster:
        try:
            items = build.fetch_feed(feed, lang) or []
        except Exception as exc:
            continue
        for it in items:
            if it.get("pid") == target:
                print("FOUND", lang, "|", feed.get("id"), "|", feed.get("name"), "|", it.get("title"), "|", it.get("link"), "|", it.get("date"))
print("scan complete")
