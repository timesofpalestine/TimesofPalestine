"""Discover and fetch rights-cleared photo candidates for the Widow feature.
Sources: Wikimedia Commons API (license metadata included) and the Clinton
White House archive (US government works, public domain)."""
import json, re, ssl, urllib.request, urllib.parse
from pathlib import Path

OUT = Path("photo-candidates"); OUT.mkdir(exist_ok=True)
manifest = []
ctx = ssl.create_default_context()
UA = {"User-Agent": "TimesOfPalestine-newsroom/1.0 (rights-clearance research)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=45, context=ctx).read()

def commons_search(term, limit=12):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'filetype:bitmap "{term}"', "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size",
    })
    data = json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))
    out = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        for ii in page.get("imageinfo", []):
            md = ii.get("extmetadata", {})
            out.append({
                "title": page.get("title"),
                "url": ii.get("url"),
                "width": ii.get("width"), "height": ii.get("height"),
                "license": (md.get("LicenseShortName", {}) or {}).get("value"),
                "artist": re.sub(r"<[^>]+>", "", (md.get("Artist", {}) or {}).get("value") or ""),
                "descurl": ii.get("descriptionurl"),
            })
    return out

for term in ("Suha Arafat", "Yasser Arafat Oslo White House 1993", "Yasser Arafat Putin", "Yasser Arafat Davos"):
    try:
        hits = commons_search(term)
    except Exception as exc:
        print(f"commons search failed for {term!r}: {exc}"); continue
    print(f"\n=== Commons: {term} ({len(hits)} hits) ===")
    for h in hits:
        print(json.dumps(h, ensure_ascii=False))
        lic = (h.get("license") or "").lower()
        if any(k in lic for k in ("public domain", "pd", "cc by")) and h.get("url") and (h.get("width") or 0) >= 500:
            name = re.sub(r"[^A-Za-z0-9._-]", "_", h["title"].replace("File:", ""))[:80]
            try:
                (OUT / name).write_bytes(get(h["url"]))
                manifest.append(h | {"saved": name, "source": "wikimedia-commons"})
                print(f"  -> saved {name}")
            except Exception as exc:
                print(f"  -> download failed: {exc}")

# Clinton White House archive: December 1998 Middle East trip photo pages (PD-USGov)
for page_url in (
    "https://clintonwhitehouse3.archives.gov/WH/New/mideast/photos-1214.html",
    "https://clintonwhitehouse3.archives.gov/WH/New/mideast/photos-1215.html",
    "https://clintonwhitehouse3.archives.gov/WH/New/mideast/photos.html",
):
    try:
        html_text = get(page_url).decode("utf-8", "replace")
    except Exception as exc:
        print(f"archive page failed {page_url}: {exc}"); continue
    imgs = sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:jpg|jpeg|gif))"', html_text, re.I)))
    print(f"\n=== {page_url}: {len(imgs)} images ===")
    for rel in imgs:
        absu = urllib.parse.urljoin(page_url, rel)
        name = "wh-" + re.sub(r"[^A-Za-z0-9._-]", "_", rel.rsplit("/", 1)[-1])[:70]
        try:
            blob = get(absu)
            if len(blob) > 8000:
                (OUT / name).write_bytes(blob)
                manifest.append({"title": rel, "url": absu, "saved": name,
                                 "license": "PD-USGov (White House photo)",
                                 "source": "clintonwhitehouse.archives.gov"})
                print(f"  -> saved {name} ({len(blob)} bytes) from {absu}")
        except Exception as exc:
            print(f"  -> {absu}: {exc}")

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
print(f"\nTOTAL saved: {len(manifest)}")
