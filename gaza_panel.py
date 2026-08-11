"""Palestine by the Numbers — the live humanitarian ledger on the homepage.

Three data rows, each fail-open (a dead source omits its row, never breaks
the build):

1. GAZA: the Ministry of Health's cumulative toll, read from Tech for
   Palestine's Palestine Datasets (data.techforpalestine.org), which
   republishes the Ministry's daily reports as JSON. The build refetches it
   every cycle (the site rebuilds every 10 minutes), so the panel follows the
   Ministry's reports as they are issued (owner directive 2026-08-03). The
   figures are also written to /data/gaza-numbers.json so the page can update
   the numbers in place between visits (see PANEL_JS).
2. WEST BANK: killed, children, wounded and the settler-attack count from
   UN OCHA's record, republished in the same summary (owner directive
   2026-08-03: the ledger covers Palestine, not Gaza alone).
3. PRISONERS: Addameer's count arranged by age and gender (total, women,
   children, administrative detention, Gaza detainees held uncharged) —
   no API exists, so editorial/prisoners.json carries the figures and the
   daily editor cycle refreshes it when Addameer publishes.
4. gazaindex.org (Gaza Genocide Center) keeps the wider humanitarian
   indicators — orphans, out-of-school children, hospital damage — with each
   figure attributed to the body that measured it (WHO, UNICEF, UNFPA,
   UNESCO, OCHA, the Ministry of Health).
"""
import json
import os
import re
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
    ("women", ("gaza.killed.women",), "Women killed", "شهيدة"),
    ("injured", ("gaza.injured.total",), "Wounded", "جرحى"),
    ("press", ("gaza.killed.press", "known_press_killed_in_gaza.records"),
     "Journalists killed", "صحفيون شهداء"),
    ("famine", ("gaza.famine.total", "gaza.killed.famine"),
     "Killed by starvation", "شهداء التجويع"),
]

# West Bank row (owner directive 2026-08-03: the ledger covers Palestine, not
# Gaza alone — every death and settler attack in the West Bank counts here).
# Palestine Datasets republishes UN OCHA's West Bank casualty and settler-
# attack record alongside the Gaza MoH reports.
WB_KEYS = [
    ("wb_killed", ("west_bank.killed.total",), "Killed", "شهداء"),
    ("wb_children", ("west_bank.killed.children",), "Children killed", "شهداء أطفال"),
    ("wb_injured", ("west_bank.injured.total",), "Wounded", "جرحى"),
    ("wb_attacks", ("west_bank.settler_attacks", "west_bank.settler_attacks.total"),
     "Settler attacks", "اعتداءات المستوطنين"),
]

# Prisoners row (owner directive 2026-08-03: the ledger carries the prisoners,
# arranged by age and gender). Addameer publishes no API, so the figures live
# in editorial/prisoners.json, maintained by the newsroom from Addameer's
# periodic updates and refreshed by the daily editor cycle. The pr_total cell
# renders with a trailing "+" — Addameer reports "more than".
PR_KEYS = [
    ("pr_total", "Total held", "الإجمالي"),
    ("pr_admin", "Administrative detention", "اعتقال إداري"),
    ("pr_gaza", "From Gaza, uncharged", "من غزة دون تهمة"),
    ("pr_women", "Women", "أسيرات"),
    ("pr_children", "Children under 18", "أطفال دون ١٨"),
]
PR_PLUS = {"pr_total"}
PRISONERS_PATH = None  # resolved lazily so tests can inject via _pr_cache

# Methodology notes for the figures whose terms carry legal or statistical
# weight a lay reader can't be assumed to know. Rendered as a focusable "?"
# beside the label with a hover/focus tooltip — the note is the marker's
# aria-label, so screen readers hear it directly (owner-forwarded review,
# 2026-08-04: contextual tooltips for complex figures).
TERM_NOTES = {
    "pr_admin": (
        "Detention by Israeli military order without charge or trial, "
        "renewable indefinitely; the detainee never sees the evidence.",
        "اعتقال بأمر عسكري إسرائيلي دون تهمة أو محاكمة، قابل للتجديد "
        "إلى ما لا نهاية، ودون اطّلاع المعتقل على الأدلة."),
    "pr_gaza": (
        "Gazans held under Israel's Unlawful Combatants Law, which allows "
        "detention without charge or judicial review.",
        "غزّيون محتجزون بموجب قانون «المقاتلين غير الشرعيين» الإسرائيلي "
        "الذي يجيز الاحتجاز دون تهمة أو مراجعة قضائية."),
    "famine": (
        "Deaths from malnutrition and dehydration recorded by Gaza's "
        "Ministry of Health since October 2023.",
        "وفيات سوء التغذية والجفاف التي سجّلتها وزارة الصحة في غزة "
        "منذ أكتوبر/تشرين الأول 2023."),
    "wb_attacks": (
        "Settler incidents recorded by UN OCHA that caused Palestinian "
        "casualties or property damage.",
        "اعتداءات مستوطنين وثّقها مكتب أوتشا الأممي وأسفرت عن إصابات "
        "فلسطينية أو أضرار في الممتلكات."),
}

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
PANEL_CSS = "section.gaza-index{padding-block:1.6rem;border-top:1px solid var(--line-dark)}.gi-block{border:1px solid var(--line);background:var(--card);box-shadow:var(--sh);padding:1.05rem 1.15rem .95rem;margin-bottom:1rem}.gi-block:last-child{margin-bottom:0}.gi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.9rem}.gi-cell{background:var(--paper);border:1px solid var(--line);border-inline-start:3px solid var(--red);border-radius:6px;padding:.7rem .8rem .6rem;transition:background var(--tr)}.gi-num{display:block;font-family:var(--serif);font-weight:900;font-size:1.75rem;line-height:1.1;font-variant-numeric:tabular-nums}[lang=ar] .gi-num{font-weight:700}.gi-moh .gi-num{font-size:2.05rem}.gi-lab{display:block;margin-top:.3rem;font-size:.78rem;font-weight:600;color:var(--muted);line-height:1.35}.gi-bar{display:block;margin-top:.42rem;block-size:4px;border-radius:2px;background:rgba(200,16,46,.18);overflow:hidden}.gi-bar>span{display:block;block-size:100%;background:var(--red);border-radius:2px}.gi-src{margin-top:.85rem;font-size:.72rem;color:var(--muted)}.gi-src a{color:var(--green);font-weight:700}.gi-region{display:flex;align-items:center;gap:.5rem;font-size:.72rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--ink);margin:0 0 .8rem}.gi-region::before{content:\"\";width:4px;height:.95rem;background:var(--red);border-radius:2px;flex-shrink:0}[lang=ar] .gi-region{letter-spacing:0;font-size:.82rem}.gi-grid.gi-wb{grid-template-columns:repeat(4,minmax(0,1fr))}.gi-grid.gi-pr{grid-template-columns:repeat(5,minmax(0,1fr))}.gi-comp{display:flex;block-size:7px;border-radius:4px;overflow:hidden;background:var(--line);margin-top:.95rem}.gi-comp .seg{display:block;block-size:100%}.gi-legend{display:flex;flex-wrap:wrap;gap:.35rem 1.1rem;margin-top:.5rem;font-size:.7rem;font-weight:600;color:var(--muted)}.gi-legend .gi-lead{font-weight:800;color:var(--ink)}.gi-legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-inline-end:.35rem}.gi-live{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--red);animation:pulse 2s infinite;flex-shrink:0;margin-inline-end:.15rem;vertical-align:middle}.gi-flash{animation:giflash 1.8s ease}@keyframes giflash{0%{background:rgba(200,16,46,.16)}100%{background:transparent}}@media(prefers-reduced-motion:reduce){.gi-live{animation:none}.gi-flash{animation:none}}@media(max-width:960px){.gi-grid,.gi-grid.gi-wb,.gi-grid.gi-pr{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:560px){.gi-grid,.gi-grid.gi-wb,.gi-grid.gi-pr{grid-template-columns:repeat(2,minmax(0,1fr))}}.gi-help{position:relative;display:inline-block;margin-inline-start:.35rem;inline-size:15px;block-size:15px;border-radius:50%;background:var(--line);color:var(--muted);font-size:.62rem;font-weight:800;line-height:15px;text-align:center;cursor:help;vertical-align:middle}.gi-help:focus-visible{outline:2px solid var(--green);outline-offset:1px}.gi-help .gi-tip{position:absolute;inset-block-end:calc(100% + 8px);inset-inline-end:-8px;inline-size:min(240px,58vw);background:#0b0b0c;color:#f2eee8;font-size:.7rem;font-weight:500;line-height:1.55;padding:.55rem .7rem;border-radius:4px;box-shadow:0 4px 14px rgba(0,0,0,.35);opacity:0;visibility:hidden;transition:opacity .15s;z-index:30;text-align:start;pointer-events:none;cursor:auto}.gi-help:hover .gi-tip,.gi-help:focus .gi-tip{opacity:1;visibility:visible}@media(max-width:560px){.gi-help .gi-tip{position:fixed;inset-inline:12px;inset-block-end:calc(12px + env(safe-area-inset-bottom,0px));inset-block-start:auto;inline-size:auto;max-inline-size:none;z-index:80}}.gi-dl{margin-top:1rem;font-size:.72rem;color:var(--muted)}.gi-dl a{color:var(--green);font-weight:700}.toll-chart{margin:.9rem 0 0;padding-top:.9rem;border-top:1px solid var(--line)}.toll-chart figcaption{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin-bottom:.5rem}.tc-head{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}[lang=ar] .tc-head{letter-spacing:0;font-size:.8rem}.tc-now{font-family:var(--serif);font-weight:900;font-size:1.3rem;color:var(--red);font-variant-numeric:tabular-nums}[lang=ar] .tc-now{font-weight:700}.toll-chart svg{display:block;inline-size:100%;block-size:120px}.tc-area{fill:rgba(200,16,46,.14)}.tc-line{fill:none;stroke:var(--red);stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round}.tc-grid{stroke:var(--line);stroke-width:1;vector-effect:non-scaling-stroke}.tc-tick{fill:var(--muted);font-size:9px;font-weight:700}.tc-foot{margin:.35rem 0 0;font-size:.7rem;color:var(--muted);font-variant-numeric:tabular-nums}.gi-strip{background:var(--black);border-block-end:1px solid #26262c}.gi-strip .wrap{display:flex;align-items:baseline;gap:1.1rem;padding-block:.5rem;overflow-x:auto;scrollbar-width:none}@media(min-width:961px){.gi-strip .wrap{flex-wrap:wrap;overflow-x:visible;row-gap:.1rem}}.gi-strip .wrap::-webkit-scrollbar{display:none}.gs-kick{flex-shrink:0;font-size:.62rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#f93549;white-space:nowrap}[lang=ar] .gs-kick{letter-spacing:0;font-size:.74rem}.gs-cell{white-space:nowrap}.gs-num{font-family:var(--serif);font-weight:900;font-size:1rem;color:#f2eee8;font-variant-numeric:tabular-nums}[lang=ar] .gs-num{font-weight:700}.gs-lab{margin-inline-start:.35rem;font-size:.68rem;font-weight:600;color:#a3a8b2}[lang=ar] .gs-lab{font-size:.78rem}.gs-more{flex-shrink:0;margin-inline-start:auto;font-size:.68rem;font-weight:700;color:#3fd07c;white-space:nowrap}[lang=ar] .gs-more{font-size:.78rem}.gi-method{margin:-.3rem 0 1rem;font-size:.74rem;color:var(--muted)}[lang=ar] .gi-method{font-size:.84rem}.gi-method summary{cursor:pointer;font-weight:700;color:var(--green-deep)}.gi-method p{margin:.45rem 0 0;line-height:1.65;max-inline-size:60rem}"

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
function setNum(el,v){el.textContent=fmt(v)+(el.hasAttribute("data-gi-plus")?"+":"");el.setAttribute("data-gi-val",Math.round(v))}
function animate(el,from,to){if(RM||from===to){setNum(el,to);return}
 var t0=performance.now(),dur=800;
 function step(t){var p=Math.min(1,(t-t0)/dur);p=1-Math.pow(1-p,3);
  setNum(el,from+(to-from)*p);if(p<1)requestAnimationFrame(step);else setNum(el,to)}
 requestAnimationFrame(step)}
var nums=[].slice.call(document.querySelectorAll("[data-gi-key]"));
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
  function ard(s){return AR?String(s).replace(/[0-9]/g,function(c){return"\\u0660\\u0661\\u0662\\u0663\\u0664\\u0665\\u0666\\u0667\\u0668\\u0669"[+c]}):String(s)}
  [["gaza",d.asOf],["wb",d.wbAsOf],["pr",d.prAsOf]].forEach(function(p){
   if(!p[1])return;var a=g.querySelector('[data-gi-asof="'+p[0]+'"]');
   if(a)a.textContent=ard(p[1])})})
 .catch(function(){})}
setInterval(refresh,300000);
document.addEventListener("visibilitychange",function(){if(!document.hidden)refresh()});
})();
"""

_moh_cache = {}
_gaza_cache = {}
_pr_cache = {}


def _load_prisoners():
    """editorial/prisoners.json — newsroom-maintained, fail-open."""
    if "data" not in _pr_cache:
        try:
            import pathlib
            path = PRISONERS_PATH or (pathlib.Path(__file__).resolve().parent
                                      / "editorial" / "prisoners.json")
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            figs = data.get("figures") or {}
            if not isinstance(figs, dict):
                raise ValueError("figures must be an object")
            _pr_cache["data"] = data
        except Exception as e:
            _pr_cache["data"] = {}
            print(f"  → prisoners ledger unavailable ({type(e).__name__}) — row omitted")
    return _pr_cache["data"]


def prisoner_figures():
    """(figures dict keyed like PR_KEYS, as-of date) — empty on failure."""
    data = _load_prisoners()
    figs = {}
    for key, _en, _ar in PR_KEYS:
        v = (data.get("figures") or {}).get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            figs[key] = int(round(v))
    return figs, str(data.get("asOf") or "")[:10]


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


def _region_figures(data, keys):
    figs = {}
    for key, paths, _en, _ar in keys:
        for path in paths:
            v = _dig(data, path)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                figs[key] = int(round(v))
                break
    return figs


def live_figures():
    """(gaza figures, gaza as-of, west bank figures, wb as-of) — empty on failure."""
    data = _fetch_moh()
    if not data:
        return {}, "", {}, ""
    gaza = _region_figures(data, MOH_KEYS)
    wb = _region_figures(data, WB_KEYS)
    gaza_asof = str(_dig(data, "gaza.last_update") or "")[:10]
    wb_asof = str(_dig(data, "west_bank.last_update") or "")[:10]
    return gaza, gaza_asof, wb, wb_asof


def payload():
    """The /data/gaza-numbers.json body the live layer polls, or None."""
    gaza, gaza_asof, wb, wb_asof = live_figures()
    prisoners, pr_asof = prisoner_figures()
    figs = {**gaza, **wb, **prisoners}
    if not figs:
        return None
    return {"asOf": gaza_asof, "wbAsOf": wb_asof, "prAsOf": pr_asof,
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Gaza MoH & UN OCHA via Tech for Palestine; Addameer",
            "figures": figs}


def payload_csv(p):
    """/data/gaza-numbers.csv — the same ledger as the JSON, one row per
    indicator with bilingual labels and per-region sourcing, so journalists
    and researchers can cite or chart the figures without scraping the page."""
    import csv
    import io
    meta = {}
    for key, _paths, en, arl in MOH_KEYS:
        meta[key] = (en, arl, "gaza", p.get("asOf", ""),
                     "Gaza Ministry of Health via Tech for Palestine")
    for key, _paths, en, arl in WB_KEYS:
        meta[key] = (en, arl, "west_bank", p.get("wbAsOf", ""),
                     "UN OCHA via Tech for Palestine")
    for key, en, arl in PR_KEYS:
        meta[key] = (en, arl, "prisoners", p.get("prAsOf", ""),
                     "Addameer, with the Detainees Commission and the Prisoners' Society")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["region", "key", "indicator_en", "indicator_ar",
                "value", "as_of", "source", "fetched_at"])
    figures = p.get("figures", {})
    for key, (en, arl, region, asof, src) in meta.items():
        if key in figures:
            w.writerow([region, key, en, arl, figures[key], asof, src,
                        p.get("fetchedAt", "")])
    return out.getvalue()


def _fmt(value, unit, lang):
    if unit == "percent":
        n = f"{value:g}%"
    elif value >= 1000:
        n = f"{int(round(value)):,}"
    else:
        n = f"{value:g}"
    return n.translate(str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩،")) if lang == "ar" else n


_PD_LINK = ('<a href="https://data.techforpalestine.org" target="_blank" '
            'rel="noopener">Palestine Datasets</a>')


# Composition-strip accents come from the house SVG palette (design-system §2):
# gold for children, flag red for women, slate for detention categories.
_COMP_GOLD, _COMP_RED, _COMP_SLATE = "#c7a86b", "#C8102E", "#3d4f6b"


def _comp_strip(lang, total, parts, intro_en, intro_ar):
    """A quiet stacked bar: each part's share of the total, with a legend.
    parts: [(label_en, label_ar, value, color)] — the remainder stays neutral."""
    if not total or not parts:
        return ""
    ar = lang == "ar"
    segs, legend, described = [], [], []
    for en, arl, value, color in parts:
        if not value or value <= 0:
            continue
        pct = max(0.5, min(100, value / total * 100))
        label = arl if ar else en
        segs.append(f'<span class="seg" style="inline-size:{pct:.1f}%;'
                    f'background:{color}"></span>')
        legend.append(f'<span><i style="background:{color}"></i>{label} '
                      f'{_fmt_date(f"{pct:.0f}", lang)}%</span>')
        described.append(f"{label} {pct:.0f}%")
    if not segs:
        return ""
    intro = intro_ar if ar else intro_en
    aria = f'{intro}: {"، ".join(described) if ar else ", ".join(described)}'
    return (f'<div class="gi-comp" role="img" aria-label="{aria}">{"".join(segs)}</div>'
            f'<p class="gi-legend"><span class="gi-lead">{intro}</span>{"".join(legend)}</p>')


def _live_row(lang, cells_def, figs, region, src, asof, asof_key,
              extra_cls="", comp=""):
    """One region block: kicker, big-numeral grid with live hooks, optional
    composition strip, attribution line with its own as-of stamp."""
    if not figs:
        return ""
    ar = lang == "ar"
    cells = []
    for key, en, arl in cells_def:
        if key not in figs:
            continue
        plus = ' data-gi-plus=""' if key in PR_PLUS else ""
        shown = _fmt(figs[key], None, lang) + ("+" if key in PR_PLUS else "")
        help_html = ""
        if key in TERM_NOTES:
            note = TERM_NOTES[key][1 if ar else 0]
            help_html = (f'<span class="gi-help" tabindex="0" aria-label="{note}">'
                         f'{"؟" if ar else "?"}'
                         f'<span class="gi-tip" aria-hidden="true">{note}</span></span>')
        cells.append(f'<div class="gi-cell"><span class="gi-num" data-gi-key="{key}" '
                     f'data-gi-val="{figs[key]}"{plus}>{shown}</span>'
                     f'<span class="gi-lab">{arl if ar else en}{help_html}</span></div>')
    asof_html = ""
    if asof:
        asof_html = ((' · آخر تحديث ' if ar else ' · updated ')
                     + f'<span class="gi-asof" data-gi-asof="{asof_key}">'
                     + f'{_fmt_date(asof, lang)}</span>')
    return (f'<div class="gi-block"><h3 class="gi-region">{region}</h3>'
            f'<div class="gi-grid gi-moh{extra_cls}">{"".join(cells)}</div>'
            f'{comp}<p class="gi-src">{src}{asof_html}</p></div>')


def _fmt_date(iso_day, lang):
    return iso_day.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) if lang == "ar" else iso_day


DAILY_URL = "https://data.techforpalestine.org/api/v2/casualties_daily.min.json"
_chart_warned = False  # the panel renders twice per build (en, ar); warn once


def _num(n, lang):
    s = f"{n:,}"
    return s.translate(str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩،")) if lang == "ar" else s


def _daily_series():
    """(iso_day, cumulative killed) pairs from the Gaza MoH daily record.

    Same provenance as the toll above it — Tech for Palestine relaying the
    Ministry of Health — so the curve and the counter can never disagree.
    Silent on any failure: a chart is a bonus, never a reason to lose the panel.
    """
    global _chart_warned
    if os.environ.get("TOP_OFFLINE") == "1":
        return []
    try:
        rows = _get_json(DAILY_URL)
    except Exception as e:
        # Say so in the build log. The chart failing open is correct, but a
        # silent disappearance is how a dead upstream goes unnoticed for weeks.
        if not _chart_warned:
            _chart_warned = True
            print(f"  → toll chart: daily series unavailable ({type(e).__name__}) — curve omitted")
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        day, cum = r.get("report_date"), r.get("killed_cum")
        if isinstance(day, str) and isinstance(cum, (int, float)) and cum > 0:
            out.append((day[:10], int(cum)))
    if len(out) < 30:
        if not _chart_warned:
            _chart_warned = True
            print(f"  → toll chart: series too short ({len(out)} points) — curve omitted")
    return out


def _toll_chart(lang):
    """A cumulative-death curve for Gaza, drawn server-side as inline SVG.

    Deliberately no chart library and no client JS: the site ships almost none
    of either, and a static path renders instantly on a phone over a bad link.
    Colours come from currentColor and the site's own vars so it follows the
    reader's theme without a second stylesheet.
    """
    pts = _daily_series()
    if len(pts) < 30:
        return ""
    ar = lang == "ar"
    # One point per ~week keeps the path short without flattening the shape.
    step = max(1, len(pts) // 150)
    pts = pts[::step] + [pts[-1]]
    W, H, PAD_T, PAD_B = 720.0, 150.0, 12.0, 22.0
    peak = max(v for _d, v in pts)
    span = len(pts) - 1
    plot = H - PAD_T - PAD_B

    def xy(i, v):
        return (i / span * W, PAD_T + plot - (v / peak * plot))

    line = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
                    for i, (x, y) in enumerate(xy(i, v) for i, (_d, v) in enumerate(pts)))
    area = f"{line} L{W:.1f},{H - PAD_B:.1f} L0,{H - PAD_B:.1f} Z"
    first_day, last_day = pts[0][0], pts[-1][0]
    last_val = pts[-1][1]
    head = "الشهداء في غزة تراكمياً" if ar else "Gaza deaths, cumulative"
    note = (f"من {_fmt_date(first_day, lang)} إلى {_fmt_date(last_day, lang)}" if ar
            else f"{first_day} to {last_day}")
    # Marks every 20k so the eye gets a scale without a cluttered axis.
    grid = ""
    tick = 20000
    lvl = tick
    while lvl < peak:
        gy = PAD_T + plot - (lvl / peak * plot)
        grid += (f'<line x1="0" y1="{gy:.1f}" x2="{W:.0f}" y2="{gy:.1f}" class="tc-grid"/>'
                 f'<text x="4" y="{gy - 3:.1f}" class="tc-tick">{_num(lvl, lang)}</text>')
        lvl += tick
    return (
        f'<figure class="toll-chart" dir="ltr">'
        f'<figcaption><span class="tc-head">{head}</span>'
        f'<span class="tc-now">{_num(last_val, lang)}</span></figcaption>'
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" preserveAspectRatio="none" '
        f'aria-label="{head}: {_num(last_val, lang)} — {note}">'
        f'{grid}<path d="{area}" class="tc-area"/><path d="{line}" class="tc-line"/>'
        f'</svg><p class="tc-foot">{note}</p></figure>')


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
    """The Palestine by the Numbers section: the Gaza MoH toll, the West Bank
    toll and settler-attack count (UN OCHA), then the wider humanitarian
    indicators. Silent when no data layer is reachable."""
    if os.environ.get("TOP_OFFLINE") == "1":
        return ""
    ar = lang == "ar"
    gaza_figs, gaza_asof, wb_figs, wb_asof = live_figures()
    pr_figs, pr_asof = prisoner_figures()
    gaza_comp = _comp_strip(
        lang, gaza_figs.get("killed"),
        [("Children", "أطفال", gaza_figs.get("children"), _COMP_GOLD),
         ("Women", "نساء", gaza_figs.get("women"), _COMP_RED)],
        "Of those killed", "من الشهداء")
    gaza_html = _live_row(
        lang, [(k, en, arl) for k, _p, en, arl in MOH_KEYS], gaza_figs,
        "قطاع غزة" if ar else "Gaza",
        (f'المصدر: وزارة الصحة في غزة — عبر {_PD_LINK}' if ar
         else f'Source: Gaza Ministry of Health — via {_PD_LINK}'),
        gaza_asof, "gaza", comp=gaza_comp)
    wb_html = _live_row(
        lang, [(k, en, arl) for k, _p, en, arl in WB_KEYS], wb_figs,
        "الضفة الغربية" if ar else "West Bank",
        (f'المصدر: مكتب الأمم المتحدة لتنسيق الشؤون الإنسانية (أوتشا) — عبر {_PD_LINK}' if ar
         else f'Source: UN OCHA — via {_PD_LINK}'),
        wb_asof, "wb", extra_cls=" gi-wb")
    pr_link = ('<a href="https://addameer.ps" target="_blank" rel="noopener">'
               + ("مؤسسة الضمير" if ar else "Addameer Prisoner Support") + "</a>")
    pr_comp = _comp_strip(
        lang, pr_figs.get("pr_total"),
        [("Administrative detention", "اعتقال إداري", pr_figs.get("pr_admin"), _COMP_SLATE),
         ("From Gaza, uncharged", "من غزة دون تهمة", pr_figs.get("pr_gaza"), _COMP_GOLD)],
        "Held without charge or trial", "محتجزون دون تهمة أو محاكمة")
    pr_html = _live_row(
        lang, PR_KEYS, pr_figs,
        "الأسرى في سجون الاحتلال" if ar else "Prisoners in Israeli jails",
        (f'المصدر: {pr_link} وهيئة شؤون الأسرى ونادي الأسير' if ar
         else f'Source: {pr_link}, with the Detainees Commission and the Prisoners\' Society'),
        pr_asof, "pr", extra_cls=" gi-pr", comp=pr_comp)
    # The curve sits directly under the Gaza counters it is drawn from.
    chart_html = _toll_chart(lang) if gaza_html else ""
    gi_cells, gi_srcs, gi_latest = _gazaindex_rows(lang)
    if not gaza_html and not wb_html and not pr_html and not gi_cells:
        return ""
    gi_html = ""
    if gi_cells:
        head = "مؤشرات إنسانية" if ar else "Humanitarian indicators"
        note = ("المصادر: " if ar else "Sources: ") + " · ".join(gi_srcs[:5])
        via = ("عبر " if ar else "via ")
        asof = f' — {_fmt_date(gi_latest, lang)}' if gi_latest else ""
        gi_html = (f'<div class="gi-block"><h3 class="gi-region">{head}</h3>'
                   f'<div class="gi-grid">{"".join(gi_cells)}</div>'
                   f'<p class="gi-src">{note} {via}'
                   f'<a href="https://www.gazaindex.org" target="_blank" rel="noopener">'
                   f'GazaIndex</a>{asof}</p></div>')
    title = "فلسطين بالأرقام" if ar else "Palestine by the Numbers"
    live = ('<span class="gi-live" role="presentation"></span>'
            if (gaza_html or wb_html or pr_html) else "")
    # Inline methodology (owner-forwarded review, 2026-08-10): contested,
    # high-stakes figures carry their own how-we-compile note right on the
    # ledger — not only in the per-term tooltips and the About page.
    method = ""
    if gaza_html or wb_html or pr_html:
        if ar:
            m_sum = "كيف تُجمَع هذه الأرقام؟"
            m_body = ("حصيلة غزة هي العدّ التراكمي لوزارة الصحة في غزة كما تنشره "
                      "تقاريرها اليومية عبر «بيانات فلسطين»، ويُعاد جلبه مع كل دورة "
                      "بناء للموقع. أرقام الضفة الغربية واعتداءات المستوطنين سجلُّ "
                      "مكتب الأمم المتحدة لتنسيق الشؤون الإنسانية (أوتشا)، وأعداد "
                      "الأسرى أرقام مؤسسة الضمير المنشورة وتحدّثها غرفة الأخبار "
                      "يدوياً لغياب أي واجهة بيانات حية لديها. علامة «+» تعني أن "
                      "المصدر يقول «أكثر من»، وعلامة «؟» بجوار بعض البنود تشرح "
                      "مصطلحاتها القانونية، وتُراجع الصفحة الأرقام تلقائياً كل خمس "
                      "دقائق تقريباً. السجل كاملاً قابل للتنزيل أسفل هذا القسم، "
                      "وتُنسب كل الأرقام إلى مصادرها الأولية.")
        else:
            m_sum = "How these figures are compiled"
            m_body = ("The Gaza toll is the Ministry of Health's cumulative count, "
                      "read from its daily reports as republished by Palestine "
                      "Datasets and refetched on every build cycle. West Bank "
                      "casualties and settler attacks are UN OCHA's record; "
                      "prisoner counts are Addameer's published figures, maintained "
                      "by the newsroom because no live feed exists. A “+” "
                      "marks a figure its source reports as “more than”, "
                      "the “?” markers explain terms that carry legal "
                      "weight, and the page re-checks the numbers about every five "
                      "minutes. The full ledger is downloadable at the end of this "
                      "section, with every figure attributed to its primary source.")
        method = (f'<details class="gi-method"><summary>{m_sum}</summary>'
                  f'<p>{m_body}</p></details>')
    # Open data: the ledger's own JSON/CSV, for the journalists, academics and
    # NGOs who cite it. Only offered when the live rows rendered — the files
    # are written from the same payload, so they exist exactly then.
    dl = ""
    if gaza_html or wb_html or pr_html:
        dl = ('<p class="gi-dl">'
              + ("بيانات مفتوحة — حمّل هذا السجل: " if ar
                 else "Open data — download this ledger: ")
              + '<a href="/data/gaza-numbers.json" download>JSON</a> · '
              + '<a href="/data/gaza-numbers.csv" download>CSV</a>'
              + (" · تُنسب الأرقام إلى مصادرها الأولية المذكورة أعلاه" if ar
                 else " · cite the primary sources named above") + "</p>")
    # Machine-readable record of the ledger, emitted only when the download
    # links are — the JSON/CSV come from the same payload, so advertising a
    # dataset the build didn't write would be a lie to the crawler.
    # Dataset, not DataFeed: DataFeed describes a stream of items, while this
    # is a citable table with two distributions, and Dataset is what Google
    # Dataset Search actually indexes.
    ld = ""
    if dl:
        as_of = max([d for d in (gaza_asof, wb_asof, pr_asof, gi_latest) if d] or [""])
        ds = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": title,
            "description": (
                "السجل الإنساني الحي لتايمز أوف فلسطين: حصيلة وزارة الصحة في غزة، "
                "وأرقام مكتب الأمم المتحدة لتنسيق الشؤون الإنسانية عن الضفة الغربية "
                "واعتداءات المستوطنين، وأعداد الأسرى — منسوبة إلى مصادرها الأولية."
                if ar else
                "Times of Palestine's live humanitarian ledger: the Gaza Ministry of "
                "Health casualty toll, UN OCHA West Bank casualty and settler-attack "
                "figures, and Palestinian prisoner counts, each attributed to the "
                "primary source that published it."),
            "url": f"https://www.timesofpalestine.com/{lang}/",
            "inLanguage": lang,
            "isAccessibleForFree": True,
            "creator": {"@type": "NewsMediaOrganization",
                        "name": "Times of Palestine",
                        "url": "https://www.timesofpalestine.com/"},
            "distribution": [
                {"@type": "DataDownload", "encodingFormat": "application/json",
                 "contentUrl": "https://www.timesofpalestine.com/data/gaza-numbers.json"},
                {"@type": "DataDownload", "encodingFormat": "text/csv",
                 "contentUrl": "https://www.timesofpalestine.com/data/gaza-numbers.csv"}],
        }
        if as_of:
            ds["dateModified"] = as_of
        ld = ('<script type="application/ld+json">'
              + json.dumps(ds, ensure_ascii=False, separators=(",", ":"))
              + "</script>")
    return (f'<section class="gaza-index" id="numbers"><div class="wrap">'
            f'<div class="sec-head focus"><h2>{live}{title}</h2><span class="rule"></span></div>'
            f'{method}{gaza_html}{chart_html}{wb_html}{pr_html}{gi_html}{dl}'
            f'</div></section>{ld}<script>{PANEL_JS}</script>')


# The condensed key-figures strip at the top of the front page (owner-forwarded
# review, 2026-08-10): the ledger's three defining numbers — Gaza killed and
# wounded, prisoners held — surfaced before the first scroll, linking down to
# the full #numbers ledger. Same data, same live hooks: the cells carry
# data-gi-key, so PANEL_JS's five-minute poll revises the strip and the ledger
# together. Restraint binds here too — no pulsing, no motion of its own.
_RATES_CACHE = {}


def shekel_rates():
    """Shekel reference rates for the strip (owner directive 2026-08-11:
    the exchange rate is a daily-paper staple for readers paid in dollars
    or dinars and spending in shekels). USD/EUR→ILS come from the ECB
    daily reference via the keyless frankfurter API; JOD→ILS is derived
    from the dinar's fixed USD peg (1 USD = 0.709 JOD) and labelled as a
    reference. Fail-open: any error returns {} and the strip simply omits
    the rates. Cached per build."""
    if _RATES_CACHE:
        return _RATES_CACHE
    try:
        req = urllib.request.Request(
            "https://api.frankfurter.dev/v1/latest?base=USD&symbols=ILS,EUR",
            headers={"User-Agent": "TimesofPalestine/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        usd_ils = float(data["rates"]["ILS"])
        usd_eur = float(data["rates"]["EUR"])
        _RATES_CACHE.update({
            "usd": usd_ils, "eur": usd_ils / usd_eur, "jod": usd_ils / 0.709,
            "date": data.get("date", "")})
    except Exception as e:  # noqa: BLE001 — a rates outage never marks the paper
        print(f"  → shekel rates unavailable ({type(e).__name__}) — strip omits them")
    return _RATES_CACHE


_MARKETS_CACHE = {"done": False}


def market_figures():
    """Market watch (owner directive 2026-08-11): the Al-Quds index from the
    Palestine Exchange and TA-125 from Tel Aviv, for the strip and for the
    economy desk's same-day coverage of significant moves. TA-125 reads the
    keyless Yahoo Finance chart API; Al-Quds reads the Palestine Exchange's
    own page with a tolerant pattern (the exchange publishes no API).
    Fail-open per index: whatever cannot be fetched is simply omitted."""
    if _MARKETS_CACHE["done"]:
        return _MARKETS_CACHE
    _MARKETS_CACHE["done"] = True
    try:  # TA-125 — level and day change from the last two closes
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ETA125.TA"
            "?range=5d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0 (TimesofPalestine newsroom)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            chart = json.loads(r.read().decode("utf-8"))["chart"]["result"][0]
        closes = [c for c in chart["indicators"]["quote"][0]["close"] if c]
        if len(closes) >= 2:
            _MARKETS_CACHE["ta125"] = {
                "level": closes[-1],
                "pct": (closes[-1] - closes[-2]) / closes[-2] * 100}
    except Exception as e:  # noqa: BLE001
        print(f"  → TA-125 unavailable ({type(e).__name__}) — strip omits it")
    for url in ("https://www.pex.ps/en/al-quds-index/", "https://www.pex.ps/"):
        try:  # Al-Quds index — first decimal number near the index's name
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (TimesofPalestine newsroom)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8", errors="replace")
            m = re.search(r"(?:Al[- ]Quds|القدس)(?:(?!\d)[\s\S]){0,240}?(\d{3,4}\.\d{1,2})", html)
            if m:
                _MARKETS_CACHE["alquds"] = {"level": float(m.group(1))}
                break
        except Exception as e:  # noqa: BLE001
            print(f"  → Al-Quds fetch failed at {url} ({type(e).__name__})")
    if "alquds" not in _MARKETS_CACHE:
        # Editorial fallback (owner order 2026-08-11: the Ramallah ticker must
        # SHOW): the daily editor maintains the latest close in
        # editorial/markets.json; the strip renders it with its date.
        try:
            import pathlib
            data = json.loads((pathlib.Path(__file__).resolve().parent
                               / "editorial" / "markets.json").read_text(encoding="utf-8"))
            aq = data.get("alquds") or {}
            if aq.get("level"):
                _MARKETS_CACHE["alquds"] = {"level": float(aq["level"]),
                                            "asof": str(aq.get("date", ""))}
        except Exception as e:  # noqa: BLE001
            print(f"  → Al-Quds editorial fallback unavailable ({type(e).__name__}) — strip omits it")
    return _MARKETS_CACHE


def strip(lang):
    if os.environ.get("TOP_OFFLINE") == "1":
        return ""
    ar = lang == "ar"
    gaza_figs, _ga, _wb, _wba = live_figures()
    pr_figs, _pra = prisoner_figures()
    cells_def = [
        ("killed", gaza_figs.get("killed"), "killed in Gaza", "شهداء غزة"),
        ("injured", gaza_figs.get("injured"), "wounded", "الجرحى"),
        ("pr_total", pr_figs.get("pr_total"), "prisoners held", "الأسرى"),
    ]
    cells = []
    for key, val, en, arl in cells_def:
        if not val:
            continue
        plus = ' data-gi-plus=""' if key in PR_PLUS else ""
        shown = _fmt(val, None, lang) + ("+" if key in PR_PLUS else "")
        cells.append(f'<span class="gs-cell"><b class="gs-num" data-gi-key="{key}" '
                     f'data-gi-val="{val}"{plus}>{shown}</b>'
                     f'<span class="gs-lab">{arl if ar else en}</span></span>')
    if not cells:
        return ""
    # Money block, kept COMPACT (owner report 2026-08-11: the strip crowded
    # the markets off-screen): ONE combined dollar/dinar cell, then the two
    # indexes with short labels. The euro moved to the cell title — dollars
    # and dinars are what Palestinian households are paid in.
    rates = shekel_rates()
    if rates:
        note = ((f"سعر مرجعي {rates['date']} · اليورو ₪{rates['eur']:.2f} · "
                 "الدينار محتسب من ربطه بالدولار") if ar else
                (f"reference {rates['date']} · euro ₪{rates['eur']:.2f} · "
                 "dinar derived from its dollar peg"))
        jd = "د.أ" if ar else "JD"
        cells.append(
            f'<span class="gs-cell" title="{note}"><b class="gs-num">'
            f'₪{rates["usd"]:.2f}/$ · ₪{rates["jod"]:.2f}/{jd}</b></span>')
    mkt = market_figures()
    if mkt.get("alquds"):
        aq = mkt["alquds"]
        asof = f' · {aq["asof"]}' if aq.get("asof") else ""
        cells.append(
            '<span class="gs-cell" title="'
            + (f"مؤشر القدس — بورصة فلسطين{asof}" if ar
               else f"Al-Quds index — Palestine Exchange{asof}")
            + f'"><b class="gs-num">{aq["level"]:,.1f}</b>'
            f'<span class="gs-lab">{"القدس" if ar else "Al-Quds"}</span></span>')
    if mkt.get("ta125"):
        t = mkt["ta125"]
        arrow = "▲" if t.get("pct", 0) >= 0 else "▼"
        cells.append(
            '<span class="gs-cell" title="'
            + ("تل أبيب 125 — بورصة تل أبيب" if ar else "TA-125 — Tel Aviv Stock Exchange")
            + f'"><b class="gs-num">{t["level"]:,.0f} {arrow}{abs(t.get("pct", 0)):.1f}%</b>'
            f'<span class="gs-lab">{"تل أبيب" if ar else "TA-125"}</span></span>')
    kick = "فلسطين بالأرقام" if ar else "Palestine by the Numbers"
    more = "السجل الكامل ←" if ar else "Full ledger →"
    label = ("فلسطين بالأرقام — أبرز المؤشرات" if ar
             else "Palestine by the Numbers — key figures")
    return (f'<aside class="gi-strip" aria-label="{label}"><div class="wrap">'
            f'<a class="gs-kick" href="#numbers">{kick}</a>{"".join(cells)}'
            f'<a class="gs-more" href="#numbers">{more}</a></div></aside>')
