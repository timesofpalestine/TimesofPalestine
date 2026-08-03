"""Gaza by the Numbers — the live humanitarian ledger on the homepage.

Two data layers, each fail-open (a dead source omits its row, never breaks
the build):

1. THE LEAD ROW is the Gaza Ministry of Health's cumulative toll, read from
   Tech for Palestine's Palestine Datasets (data.techforpalestine.org), which
   republishes the Ministry's daily reports as JSON. The build refetches it
   every cycle (the site rebuilds every 10 minutes), so the panel follows the
   Ministry's reports as they are issued (owner directive 2026-08-03). The
   figures are also written to /data/gaza-numbers.json so the page can update
   the numbers in place between visits (see PANEL_JS).
2. gazaindex.org (Gaza Genocide Center) keeps the wider humanitarian
   indicators — orphans, out-of-school children, hospital damage — with each
   figure attributed to the body that measured it (WHO, UNICEF, UNFPA,
   UNESCO, OCHA, the Ministry of Health).
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

MOH_SUMMARY_URL = "https://data.techforpalestine.org/api/v3/summary.json"
GAZA_INDEX_URL = "https://www.gazaindex.org/api/v1/public/indicators"

# The Ministry's headline figures. Each entry: stable key (used in the DOM and
# in gaza-numbers.json), candidate JSON paths in the summary (first hit wins,
# so a schema rename degrades to a missing cell instead of a crash), then the
# English and Arabic labels.
MOH_KEYS = [
    ("killed", ("gaza.killed.total",), "Killed", "شهداء"),
    ("children", ("gaza.killed.children",), "Children killed", "شهداء أطفال"),
    ("women", ("gaza.killed.women",), "Women killed", "شهيدات"),
    ("injured", ("gaza.injured.total",), "Wounded", "جرحى"),
    ("press", ("gaza.killed.press", "known_press_killed_in_gaza.records"),
     "Journalists killed", "صحفيون شهداء"),
    ("famine", ("gaza.famine.total", "gaza.killed.famine"),
     "Killed by starvation", "شهداء التجويع"),
]

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
PANEL_CSS = "section.gaza-index{padding-block:1.6rem;border-top:1px solid var(--line-dark)}.gi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:1.2rem}.gi-cell{border-inline-start:3px solid var(--red);padding-inline-start:.8rem;transition:background var(--tr)}.gi-num{display:block;font-family:var(--serif);font-weight:900;font-size:1.75rem;line-height:1.1;font-variant-numeric:tabular-nums}[lang=ar] .gi-num{font-weight:700}.gi-moh .gi-num{font-size:2.05rem}.gi-lab{display:block;margin-top:.3rem;font-size:.78rem;font-weight:600;color:var(--muted);line-height:1.35}.gi-bar{display:block;margin-top:.42rem;block-size:4px;border-radius:2px;background:rgba(200,16,46,.18);overflow:hidden}.gi-bar>span{display:block;block-size:100%;background:var(--red);border-radius:2px}.gi-src{margin-top:1rem;font-size:.72rem;color:var(--muted)}.gi-src a{color:var(--green);font-weight:700}.gi-moh+.gi-src{margin-bottom:1.4rem}.gi-live{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--red);animation:pulse 2s infinite;flex-shrink:0;margin-inline-end:.15rem;vertical-align:middle}.gi-flash{animation:giflash 1.8s ease}@keyframes giflash{0%{background:rgba(200,16,46,.16)}100%{background:transparent}}@media(prefers-reduced-motion:reduce){.gi-live{animation:none}.gi-flash{animation:none}}@media(max-width:960px){.gi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:560px){.gi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}"

# The live layer: a gentle roll-up when the panel first scrolls into view,
# then a refetch of /data/gaza-numbers.json every 5 minutes that animates any
# figure the Ministry has revised and briefly tints its cell. Restraint is
# deliberate — these are casualty figures, not a scoreboard: no count-up from
# zero, no confetti, a settle from 96.5% and a fading wash on change.
PANEL_JS = """
(function(){var g=document.querySelector("section.gaza-index");if(!g)return;
var AR=(document.documentElement.lang||"en")==="ar";
var RM=matchMedia("(prefers-reduced-motion: reduce)").matches;
function fmt(n){n=Math.round(n);var s=String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g,",");
 return AR?s.replace(/[0-9,]/g,function(c){return c===","?"\\u060c":"\\u0660\\u0661\\u0662\\u0663\\u0664\\u0665\\u0666\\u0667\\u0668\\u0669"[+c]}):s}
function setNum(el,v){el.textContent=fmt(v);el.setAttribute("data-gi-val",Math.round(v))}
function animate(el,from,to){if(RM||from===to){setNum(el,to);return}
 var t0=performance.now(),dur=800;
 function step(t){var p=Math.min(1,(t-t0)/dur);p=1-Math.pow(1-p,3);
  setNum(el,from+(to-from)*p);if(p<1)requestAnimationFrame(step);else setNum(el,to)}
 requestAnimationFrame(step)}
var nums=[].slice.call(g.querySelectorAll("[data-gi-key]"));
if("IntersectionObserver"in window&&!RM){
 var io=new IntersectionObserver(function(es){es.forEach(function(e){
  if(!e.isIntersecting)return;io.unobserve(e.target);
  var v=+e.target.getAttribute("data-gi-val")||0;
  animate(e.target,Math.floor(v*.965),v)})},{threshold:.4});
 nums.forEach(function(n){io.observe(n)})}
function refresh(){if(document.hidden||!nums.length)return;
 fetch("/data/gaza-numbers.json",{cache:"no-store"})
 .then(function(r){return r.ok?r.json():null})
 .then(function(d){if(!d||!d.figures)return;
  nums.forEach(function(el){var k=el.getAttribute("data-gi-key");
   if(!(k in d.figures))return;
   var nv=+d.figures[k],ov=+el.getAttribute("data-gi-val");
   if(nv&&nv!==ov){animate(el,ov,nv);
    var c=el.closest(".gi-cell");
    if(c){c.classList.remove("gi-flash");void c.offsetWidth;c.classList.add("gi-flash")}}});
  var a=g.querySelector(".gi-asof");
  if(a&&d.asOf)a.textContent=AR?String(d.asOf).replace(/[0-9]/g,function(c){return"\\u0660\\u0661\\u0662\\u0663\\u0664\\u0665\\u0666\\u0667\\u0668\\u0669"[+c]}):d.asOf})
 .catch(function(){})}
setInterval(refresh,300000);
document.addEventListener("visibilitychange",function(){if(!document.hidden)refresh()});
})();
"""

_moh_cache = {}
_gaza_cache = {}


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TimesOfPalestine/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _dig(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _fetch_moh():
    if os.environ.get("TOP_OFFLINE") == "1":
        return {}
    if "data" not in _moh_cache:
        try:
            _moh_cache["data"] = _get_json(MOH_SUMMARY_URL)
            print("  → MoH summary: fetched (Palestine Datasets)")
        except Exception as e:
            _moh_cache["data"] = {}
            print(f"  → MoH summary unavailable ({type(e).__name__}) — lead row omitted")
    return _moh_cache["data"]


def moh_figures():
    """(figures dict keyed like MOH_KEYS, as-of date string) — both empty on failure."""
    data = _fetch_moh()
    if not data:
        return {}, ""
    figs = {}
    for key, paths, _en, _ar in MOH_KEYS:
        for path in paths:
            v = _dig(data, path)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                figs[key] = int(round(v))
                break
    as_of = str(_dig(data, "gaza.last_update") or "")[:10]
    return figs, as_of


def payload():
    """The /data/gaza-numbers.json body the live layer polls, or None."""
    figs, as_of = moh_figures()
    if not figs:
        return None
    return {"asOf": as_of,
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Gaza Ministry of Health via Tech for Palestine",
            "figures": figs}


def _fmt(value, unit, lang):
    if unit == "percent":
        n = f"{value:g}%"
    elif value >= 1000:
        n = f"{int(round(value)):,}"
    else:
        n = f"{value:g}"
    return n.translate(str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩،")) if lang == "ar" else n


def _moh_row(lang):
    figs, as_of = moh_figures()
    if not figs:
        return ""
    ar = lang == "ar"
    cells = []
    for key, _paths, en, arl in MOH_KEYS:
        if key not in figs:
            continue
        cells.append(f'<div class="gi-cell"><span class="gi-num" data-gi-key="{key}" '
                     f'data-gi-val="{figs[key]}">{_fmt(figs[key], None, lang)}</span>'
                     f'<span class="gi-lab">{arl if ar else en}</span></div>')
    link = ('<a href="https://data.techforpalestine.org" target="_blank" '
            'rel="noopener">Palestine Datasets</a>')
    src = (f'المصدر: وزارة الصحة في غزة — عبر {link}' if ar
           else f'Source: Gaza Ministry of Health — via {link}')
    asof_html = ""
    if as_of:
        asof_txt = _fmt_date(as_of, lang)
        asof_html = ((' · آخر تحديث ' if ar else ' · updated ')
                     + f'<span class="gi-asof">{asof_txt}</span>')
    return (f'<div class="gi-grid gi-moh">{"".join(cells)}</div>'
            f'<p class="gi-src">{src}{asof_html}</p>')


def _fmt_date(iso_day, lang):
    return iso_day.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) if lang == "ar" else iso_day


def _gazaindex_rows(lang):
    """(cells html list, sources list, latest as-of) from gazaindex — all empty on failure."""
    if os.environ.get("TOP_OFFLINE") == "1":
        return [], [], ""
    if "rows" not in _gaza_cache:
        try:
            _gaza_cache["rows"] = {x["key"]: x for x in _get_json(GAZA_INDEX_URL)["data"]}
            print(f"  → GazaIndex: {len(_gaza_cache['rows'])} indicators fetched")
        except Exception as e:
            _gaza_cache["rows"] = {}
            print(f"  → GazaIndex unavailable ({type(e).__name__}) — indicator row omitted")
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
    seen, srcs = set(), []
    for pr in providers:
        if pr not in seen:
            seen.add(pr)
            srcs.append(pr)
    return cells, srcs, latest


def panel(lang):
    """The Gaza by the Numbers section: MoH lead row + wider indicators.
    Silent when no data layer is reachable."""
    if os.environ.get("TOP_OFFLINE") == "1":
        return ""
    moh_html = _moh_row(lang)
    gi_cells, gi_srcs, gi_latest = _gazaindex_rows(lang)
    if not moh_html and not gi_cells:
        return ""
    gi_html = ""
    if gi_cells:
        note = ("المصادر: " if lang == "ar" else "Sources: ") + " · ".join(gi_srcs[:5])
        via = ("عبر " if lang == "ar" else "via ")
        asof = f' — {_fmt_date(gi_latest, lang)}' if gi_latest else ""
        gi_html = (f'<div class="gi-grid">{"".join(gi_cells)}</div>'
                   f'<p class="gi-src">{note} {via}'
                   f'<a href="https://www.gazaindex.org" target="_blank" rel="noopener">'
                   f'GazaIndex</a>{asof}</p>')
    title = "غزة بالأرقام" if lang == "ar" else "Gaza by the Numbers"
    live = '<span class="gi-live" role="presentation"></span>' if moh_html else ""
    return (f'<section class="gaza-index"><div class="wrap">'
            f'<div class="sec-head focus"><h2>{live}{title}</h2><span class="rule"></span></div>'
            f'{moh_html}{gi_html}'
            f'</div></section><script>{PANEL_JS}</script>')
