"""Outbreak watch — the newsroom's disease monitor feeding SANAD.

Owner directive 2026-08-04: keep an eye on the diseases spreading in Gaza
and the West Bank and post them to SANAD automatically, so the specialist
network can offer solutions.

How it works, end to end:
1. Every build scans the wire items already fetched (both languages) for
   disease/outbreak signals — epidemics, vaccine-preventable resurgence,
   and population-level supply emergencies (dialysis fluid, oxygen).
2. Each detected outbreak becomes an ordinary SANAD case event whose id is
   DETERMINISTIC (disease + ISO week): rebuilding the site regenerates the
   same event, and SANAD's idempotent merge means no device ever sees a
   duplicate. A continuing outbreak re-files weekly as a follow-up case.
3. The events are published at /sanad/watch.json. The SANAD page pulls the
   file whenever a device is online — and because the alerts are ordinary
   events, any device that has them relays them onward over the offline
   carriers (pasted text, share-sheet, bitchat) to devices that never see
   the internet at all.

Stdlib only, fail-open: a scan error must never break the news build.
"""
import hashlib
import re
from datetime import datetime, timezone

# (key, EN name, AR name, specialty, urgency, patterns)
# Patterns run over title+dek+brief in both languages, case-insensitive.
DISEASES = [
    ("cholera", "Cholera", "الكوليرا", "Infectious disease", "red",
     r"cholera|كوليرا"),
    ("polio", "Polio", "شلل الأطفال", "Paediatrics", "red",
     r"\bpolio|شلل الأطفال"),
    ("meningitis", "Meningitis", "التهاب السحايا", "Infectious disease", "red",
     r"meningitis|سحايا"),
    ("measles", "Measles", "الحصبة", "Paediatrics", "amber",
     r"measles|الحصبة"),
    ("hepatitis", "Hepatitis", "التهاب الكبد", "Infectious disease", "amber",
     r"hepatitis|التهاب الكبد"),
    ("typhoid", "Typhoid", "التيفوئيد", "Infectious disease", "amber",
     r"typhoid|تيفوئيد"),
    ("pertussis", "Whooping cough", "السعال الديكي", "Paediatrics", "amber",
     r"whooping cough|pertussis|سعال ديكي|السعال الديكي"),
    ("diarrhoea", "Acute watery diarrhoea", "الإسهال المائي الحاد",
     "Infectious disease", "amber",
     r"(?:watery|acute|bloody)\s+diarrh|إسهال (?:مائي|حاد|دموي)"),
    ("scabies", "Scabies and skin disease", "الجرب والأمراض الجلدية",
     "Infectious disease", "amber",
     r"scabies|\bجرب\b|أمراض جلدية"),
    ("lice", "Lice infestations", "القمل", "Infectious disease", "routine",
     r"\blice\b|\bقمل\b"),
    ("malnutrition", "Acute malnutrition", "سوء التغذية الحاد",
     "Nutrition", "red",
     r"acute malnutrition|severe malnutrition|سوء التغذية الحاد|سوء تغذية حاد"),
    ("dialysis", "Dialysis supply failure", "انقطاع مستلزمات الغسيل الكلوي",
     "Nephrology / dialysis", "red",
     r"dialysis|غسيل الكلى|غسيل كلوي|الغسيل الكلوي"),
]

# An item counts as an outbreak signal only when a spread/emergency word
# appears too — a feature about a survivor of hepatitis is not an alert.
CONTEXT_RX = re.compile(
    r"outbreak|spread|cases|epidemic|surge|infect|shortage|runs? out|ran out|"
    r"out of stock|halv|halt|crisis|record|rise|rising|soar|"
    r"تفش|انتشار|إصاب|حالات|وباء|نفاد|نفد|شحّ?|أزمة|ارتفاع|تسجيل|توقف|تعطّ?ل",
    re.I)

_WB_RX = re.compile(r"west bank|الضفة", re.I)


def _week(dt):
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def watch_events(items, now=None):
    """Scan wire items -> list of SANAD case-event dicts (SND1-compatible)."""
    now = now or datetime.now(timezone.utc)
    out, seen = [], set()
    for key, en, ar, specialty, urgency, pat in DISEASES:
        rx = re.compile(pat, re.I)
        for it in items:
            try:
                # A genuine outbreak story names the disease in its headline
                # or dek; a passing mention deep in a body is not an alert
                # (a prosthetics feature citing polio history must not file).
                head = " ".join(str(it.get(f) or "") for f in ("title", "dek"))
                text = head + " " + str(it.get("brief") or "")
                if not rx.search(head) or not CONTEXT_RX.search(text):
                    continue
                zone = "West Bank" if _WB_RX.search(text) else "Gaza City"
                week = _week(it.get("date") or now)
                dedupe = f"{key}:{zone}:{week}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                eid = "epi" + hashlib.md5(dedupe.encode()).hexdigest()[:9]
                ts = int((it.get("date") or now).timestamp() * 1000)
                pid, lang = it.get("pid"), it.get("lang", "en")
                url = (f"https://www.timesofpalestine.com/{lang}/story/{pid}.html"
                       if pid else "")
                headline = str(it.get("title") or "")
                dek = str(it.get("dek") or "")[:400]
                out.append({
                    "id": eid, "ty": "case", "ts": ts,
                    "by": {"n": "TOP Health Watch", "r": "field",
                           "c": "Times of Palestine newsroom"},
                    "ref": f"EPI-{week}-{key.upper()[:6]}",
                    "c": {
                        "specialty": specialty, "urgency": urgency,
                        "ageBand": "population", "sex": "all",
                        "zone": zone, "facility": "population-level alert",
                        "days": "",
                        "presentation": f"{en} · {ar} — {headline}"
                                        + (f" — {dek}" if dek else ""),
                        "findings": ("Automated newsroom watch from wire "
                                     "coverage; verify locally. التغطية: ")
                                    + (url or "timesofpalestine.com"),
                        "resources": "",
                        "question": (f"What is working in the field against "
                                     f"{en.lower()} under these conditions — "
                                     f"protocols, dosing with available stock, "
                                     f"isolation without space? "
                                     f"ما الذي ينجح ميدانياً ضد {ar} في هذه "
                                     f"الظروف — بروتوكولات وجرعات بما هو "
                                     f"متوفر؟ أجيبوا على هذه اللوحة."),
                        "contact": "Reply on this board · الرد على هذه اللوحة",
                    },
                })
            except Exception:
                continue   # one bad item never kills the watch
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out[:24]   # a board, not a firehose
