"""One incident, one story — shared event-similarity logic.

Two outlets covering one incident write two different headlines, so exact-title
dedupe misses them. This module normalizes headlines into token sets (number
words to digits, synonym folding, stopwords out) and decides whether two
headlines describe the same event. Used by build.py to publish one article per
event, and by telegram_publish.py so the channel never receives the same news
twice under different story IDs.

Deliberately conservative: different places or different casualty counts in
the headlines veto a match, and callers should only compare stories close in
time. Stdlib only.
"""
import difflib
import html
import re

_TAG_RX = re.compile(r"<[^>]+>")
_WORD_RX = re.compile(r"[\W_]+", re.UNICODE)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
              "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
              "twelve": "12"}  # "dozens" stays a word: too vague to use as a count
_EVENT_SYN = {}
for _canon, _words in (
    ("forces", "army force troop soldier military occupation idf"),
    ("strike", "strike airstrike attack raid shelling bombing bombardment assault"),
    ("kill", "kill killed martyr martyred slain dead death"),
    ("injure", "injure injured wound wounded hurt casualtie"),
    ("قوات", "قوات جيش جنود احتلال"),
    ("قصف", "قصف غارة غارات هجوم عدوان"),
    ("قتل", "قتل مقتل استشهاد استشهد شهداء شهيد قتلى"),
    ("جرحى", "جرحى إصابة إصابات أصيب مصابين مصابون"),
):
    for _w in _words.split():
        _EVENT_SYN[_w] = _canon
_EVENT_STOP = set(
    "the a an in on at of to for with by from and or as after amid over under near says say said "
    "reports report reported news update breaking least against during between about its his her "
    "their monday tuesday wednesday thursday friday saturday sunday today yesterday dozen dozens".split()
) | set("في على من إلى عن مع بعد خلال قرب ضد بين حتى نحو أكثر الأقل اليوم أمس "
        "الاثنين الثلاثاء الأربعاء الخميس الجمعة السبت الأحد".split())
_EVENT_PLACES = set(
    "gaza rafah khan younis jenin nablus hebron jerusalem ramallah tulkarem tulkarm bethlehem "
    "qalqilya jericho jabalia salfit tubas".split()
) | set("غزة رفح خان يونس جنين نابلس خليل قدس رام طولكرم لحم قلقيلية أريحا جباليا سلفيت طوباس".split())


def event_tokens(title):
    text = _WORD_RX.sub(" ", html.unescape(_TAG_RX.sub(" ", title or "")).lower())
    toks = set()
    for w in text.translate(_AR_DIGITS).split():
        w = _NUM_WORDS.get(w, w)
        if w in _EVENT_STOP or (len(w) <= 1 and not w.isdigit()):
            continue
        if w.isascii():
            w = w.rstrip("s")
        elif w.startswith("ال") and len(w) > 3:
            w = w[2:]
        toks.add(_EVENT_SYN.get(w, w))
    return toks


_NUM_RUN_RX = re.compile(r"\d+")


def _title_key(title):
    text = _WORD_RX.sub(" ", html.unescape(_TAG_RX.sub(" ", title or "")).lower())
    text = re.sub(r"\s+", " ", text.translate(_AR_DIGITS)).strip()
    # Collapse every count to one marker: a rolling story's updated toll
    # ("kills 12" → "kills 15") must not read as a new headline.
    return _NUM_RUN_RX.sub("#", text)


def near_identical(title_a, title_b):
    """True when two headlines are the same words give or take an updated
    number — the rolling-update case that the number veto in same_event
    deliberately keeps apart. Such pairs are one running story, not two
    events, no matter how far apart in time they were filed."""
    a, b = _title_key(title_a), _title_key(title_b)
    if not a or not b:
        return False
    if a == b:
        return True
    if 2 * min(len(a), len(b)) < 0.9 * (len(a) + len(b)):
        return False  # length gap alone caps the ratio below the bar
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.9


def _place_or_count_veto(toks_a, toks_b):
    places_a, places_b = toks_a & _EVENT_PLACES, toks_b & _EVENT_PLACES
    if places_a and places_b and not (places_a & places_b):
        return True  # different places → different events
    nums_a = {t for t in toks_a if t.isdigit()}
    nums_b = {t for t in toks_b if t.isdigit()}
    if nums_a and nums_b and not (nums_a & nums_b):
        return True  # different counts → different events
    return False


def same_event(toks_a, toks_b):
    """True when two token sets plausibly describe the same incident."""
    inter = toks_a & toks_b
    if len(inter) < 3:
        return False
    if len(inter) / len(toks_a | toks_b) < 0.42:
        return False
    return not _place_or_count_veto(toks_a, toks_b)


def same_story(title_toks, extended_toks):
    """True when one item's headline sits substantially inside another item's
    headline-plus-dek token set. This is the cross-desk case Jaccard misses:
    an original and a wire brief describe one event under unlike headlines
    ("Lebanon arrests envoy who accused Abbas's son…" vs "Lebanon detains
    ex-ambassador Dabbour for extradition") — the names each headline omits
    appear in the other's dek (owner call 2026-08-05, after a wire brief on
    the Dabbour arrest published beside the original covering it)."""
    if not title_toks or not extended_toks:
        return False
    inter = title_toks & extended_toks
    if len(inter) < 4:
        return False
    if len(inter) / len(title_toks) < 0.6:
        return False
    return not _place_or_count_veto(title_toks, extended_toks)
