"""One-off diagnostic: find which feed produces a given story pid."""
import json, sys
sys.path.insert(0, ".")
import build

target = sys.argv[1] if len(sys.argv) > 1 else "23ffbc910f"
feeds = json.load(open("feeds.json", encoding="utf-8"))
for lang, roster in feeds.items():
    for feed in roster:
        try:
            items = build.fetch_feed(feed, lang) or []
        except Exception as exc:
            print(f"  skip {feed.get('name')}: {type(exc).__name__}: {exc}")
            continue
        for it in items:
            if it.get("pid") == target:
                print("FOUND")
                print("lang:", lang)
                print("feed id:", feed.get("id"))
                print("feed name:", feed.get("name"))
                print("feed url:", feed.get("url"))
                print("title:", it.get("title"))
                print("link:", it.get("link"))
                print("source:", it.get("source"))
                print("date:", it.get("date"))
print("scan complete")
