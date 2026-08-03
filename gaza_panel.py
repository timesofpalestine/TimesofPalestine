"""GazaIndex humanitarian figures for the Times of Palestine homepage.

gazaindex.org (a program of the Gaza Genocide Center) keeps a sourced,
continuously updated record of the humanitarian situation in Gaza. Its public
API carries the underlying providers — WHO, UNICEF, UNFPA, UNESCO, OCHA, the
Ministry of Health — so every figure here is attributed to the body that
measured it. Fail-open: if the data is unreachable the panel simply omits.
"""
import json
import os
import urllib.request

GAZA_INDEX_URL = "https://www.gazaindex.org/api/v1/public/indicators"

# Curated because a homepage needs the few numbers that carry the whole story,
# not all fifty. Labels are written here so the panel reads naturally in Arabic.
GAZA_INDEX_KEYS = [
    ("children.orphaned_cumulative", "Children orphaned", "أطفال فقدوا ذويهم"),
    ("children.injured_cumulative", "Children injured", "أطفال جرحى"),
    ("referral.awaiting_total", "Awaiting medical referral abroad", "بانتظار تحويل طبي للخارج"),
    ("education.students_out_of_school", "Children out of school", "أطفال خارج المدارس"),
    ("health.hospitals_damaged_pct", "Hospitals damaged or out of service", "مستشفيات متضررة أو خارج الخدمة"),
    ("maternal.unassisted_births_per_day", "Daily births without skilled care", "ولادات يومياً دون رعاية مؤهلة"),
]

# Styles travel with the panel. The figures declare no colour of their own so
# they inherit the page ink and stay readable in both the light and dark themes.
PANEL_CSS = "section.gaza-index{padding-block:1.6rem;border-top:1px solid var(--line-dark)}.gi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:1.2rem}.gi-cell{border-inline-start:3px solid var(--red);padding-inline-start:.8rem}.gi-num{display:block;font-family:var(--serif);font-weight:900;font-size:1.75rem;line-height:1.1}[lang=ar] .gi-num{font-weight:700}.gi-lab{display:block;margin-top:.3rem;font-size:.78rem;font-weight:600;color:var(--muted);line-height:1.35}.gi-bar{display:block;margin-top:.42rem;block-size:4px;border-radius:2px;background:rgba(200,16,46,.18);overflow:hidden}.gi-bar>span{display:block;block-size:100%;background:var(--red);border-radius:2px}.gi-src{margin-top:1rem;font-size:.72rem;color:var(--muted)}.gi-src a{color:var(--green);font-weight:700}@media(max-width:960px){.gi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:560px){.gi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}"

_gaza_cache = {}


def _fmt(value, unit, lang):
    if unit == "percent":
        n = f"{value:g}%"
    elif value >= 1000:
        n = f"{int(round(value)):,}"
    else:
        n = f"{value:g}"
    return n.translate(str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩،")) if lang == "ar" else n


def panel(lang):
    """A strip of sourced humanitarian figures. Silent if the data is unreachable."""
    if os.environ.get("TOP_OFFLINE") == "1":
        return ""
    if "rows" not in _gaza_cache:
        try:
            req = urllib.request.Request(GAZA_INDEX_URL, headers={"User-Agent": "TimesOfPalestine/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                _gaza_cache["rows"] = {x["key"]: x for x in json.loads(r.read())["data"]}
            print(f"  → GazaIndex: {len(_gaza_cache['rows'])} indicators fetched")
        except Exception as e:
            _gaza_cache["rows"] = {}
            print(f"  → GazaIndex unavailable ({type(e).__name__}) — panel omitted")
    rows = _gaza_cache["rows"]
    cells, providers, latest = [], [], ""
    for key, en, ar in GAZA_INDEX_KEYS:
        row = rows.get(key)
        if not row or row.get("value_numeric") is None:
            continue
        pct_bar = ""
        if row.get("unit_code") == "percent":
            pct = max(0, min(100, float(row["value_numeric"])))
            pct_bar = (f'<span class="gi-bar" role="presentation">'
                       f'<span style="inline-size:{pct:g}%"></span></span>')
        cells.append(f'<div class="gi-cell"><span class="gi-num">'
                     f'{_fmt(row["value_numeric"], row.get("unit_code"), lang)}</span>'
                     f'{pct_bar}'
                     f'<span class="gi-lab">{ar if lang == "ar" else en}</span></div>')
        if row.get("provider_label"):
            providers.append(row["provider_label"])
        latest = max(latest, str(row.get("as_of") or "")[:10])
    if not cells:
        return ""
    seen, srcs = set(), []
    for pr in providers:
        if pr not in seen:
            seen.add(pr)
            srcs.append(pr)
    title = "غزة بالأرقام" if lang == "ar" else "Gaza by the Numbers"
    note = ("المصادر: " if lang == "ar" else "Sources: ") + " · ".join(srcs[:5])
    via = ("عبر " if lang == "ar" else "via ")
    asof = (f' — {latest}' if latest else "")
    return (f'<section class="gaza-index"><div class="wrap">'
            f'<div class="sec-head focus"><h2>{title}</h2><span class="rule"></span></div>'
            f'<div class="gi-grid">{"".join(cells)}</div>'
            f'<p class="gi-src">{note} {via}'
            f'<a href="https://www.gazaindex.org" target="_blank" rel="noopener">GazaIndex</a>{asof}</p>'
            f'</div></section>')
