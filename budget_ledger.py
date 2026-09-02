"""Budget governor for the AI newsroom (owner order 2026-09-01: the paper
never goes over its monthly API budget again).

August's lesson: the org-level Anthropic spend cap is a cliff — when the
newsroom hit it on the 25th, EVERYTHING stopped for six days, wire included.
This module replaces the cliff with pacing: every desk's estimated spend is
recorded in a committed ledger, and the discretionary desks (investigations,
daily editor, Washington Brief, weekly maintenance) skip a run when they are
ahead of their allocation's linear monthly pace. The briefs desk — the wire
IS the paper — is never paced; it stops only at the hard ceiling, which sits
below the real cap so the wire keeps its last-resort headroom.

Design rules:
- Estimates only, at list price with a safety factor — we would rather stop
  at 92% of a real 100% than sail past it. The provider cap stays as the
  outer backstop.
- Ledger IO is fail-open for READING (a corrupt ledger never crashes the
  build) but a read failure is LOUD, and the pacing gates keep working from
  an empty ledger — which under-counts, so the hard ceiling and the provider
  cap still bound the damage.
- WRITING never wipes history (site scan 2026-09-02). The first day in
  production the ledger lost every desk's month-to-date three times: the
  briefs desk records from a thread pool, and a reader that caught a
  half-written file "failed open" to an empty ledger and saved it over the
  month. So: one process-wide lock plus an advisory file lock around every
  record, atomic temp-file-then-rename writes so no reader ever sees a
  partial file, and a ledger that exists but cannot be parsed is NEVER
  overwritten by a record — that call's spend goes unrecorded with a loud
  warning instead of the whole month vanishing.
- The ledger lives at originals/_ledger.json so the build workflow's
  existing persist step commits it with no new wiring; the action-based
  workflows commit their own entries. Concurrent builds both change the
  file, so the persist step resolves a rebase conflict on it with
  `--resolve-conflict` (upstream + this run's delta) rather than dropping
  the run's commit.

Stdlib only (charter rule 6).
"""
import calendar
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:  # advisory cross-process lock; absent on Windows → in-process lock only
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "editorial" / "budget.json"
LEDGER_FILE = ROOT / "originals" / "_ledger.json"

# USD per million tokens, list price. Unknown models fall back to the most
# expensive row so a model switch can only over-count, never under-count.
PRICES = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "claude-opus-5": {"in": 5.00, "out": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-5": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}
_FALLBACK_PRICE = PRICES["claude-opus-5"]
WEB_SEARCH_USD = 0.01           # $10 per 1,000 searches
SAFETY_FACTOR = 1.10            # recorded estimates run 10% hot on purpose

DESKS = ("briefs", "investigations", "editor", "washington", "maintenance")
PROTECTED_DESK = "briefs"       # never paced; hard ceiling only


def _price_row(model):
    model = (model or "").lower()
    for key, row in PRICES.items():
        if model.startswith(key):
            return row
    return _FALLBACK_PRICE


def _u(usage, field):
    """Read a usage field from an SDK object or a plain dict; missing → 0."""
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(field, 0)
    else:
        value = getattr(usage, field, 0)
    return int(value or 0)


def estimate_usd(model, usage, web_searches=0):
    row = _price_row(model)
    tokens_usd = (
        _u(usage, "input_tokens") * row["in"]
        + _u(usage, "output_tokens") * row["out"]
        + _u(usage, "cache_read_input_tokens") * row["cache_read"]
        + _u(usage, "cache_creation_input_tokens") * row["cache_write"]
    ) / 1_000_000
    return tokens_usd + web_searches * WEB_SEARCH_USD


def _month_key(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        budget = float(cfg["monthly_budget_usd"])
        hard_stop = float(cfg.get("hard_stop_fraction", 0.92))
        allocations = {k: float(v) for k, v in cfg["allocations"].items()}
        if budget <= 0 or not 0 < hard_stop <= 1:
            raise ValueError("budget/hard_stop out of range")
        return {"budget": budget, "hard_stop": hard_stop, "allocations": allocations}
    except Exception as exc:
        # A broken config must not un-gate the discretionary desks: fall back
        # to the owner-approved floor rather than to "unlimited".
        print(f"  ⚠ budget: config unreadable ({type(exc).__name__}) — "
              "using $150 defaults", file=sys.stderr)
        return {"budget": 150.0, "hard_stop": 0.92,
                "allocations": {"briefs": 0.12, "investigations": 0.22,
                                "editor": 0.30, "washington": 0.24,
                                "maintenance": 0.04}}


_LOCK = threading.RLock()          # in-process: the briefs desk records from a thread pool
_READ_RETRIES = 6                  # a transient partial read is retried before it counts
_READ_RETRY_DELAY = 0.05


def _parse_ledger(text):
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("desks"), dict):
        raise ValueError("ledger shape")
    data["desks"] = {k: float(v) for k, v in data["desks"].items()}
    return data


def _read_ledger():
    """(ledger_or_None, state) with state in ok / missing / unreadable.

    Reads are retried briefly: writes are atomic renames now, but a ledger
    being rewritten by another process is still worth a second look before
    it is declared corrupt."""
    last = None
    for attempt in range(_READ_RETRIES):
        try:
            return _parse_ledger(LEDGER_FILE.read_text(encoding="utf-8")), "ok"
        except FileNotFoundError:
            return None, "missing"
        except Exception as exc:
            last = exc
            time.sleep(_READ_RETRY_DELAY * (attempt + 1))
    print(f"  ⚠ budget: ledger unreadable ({type(last).__name__})", file=sys.stderr)
    return None, "unreadable"


def _fresh(month):
    return {"month": month, "desks": {}, "updated": None}


def load_ledger(now=None):
    """Reader view: fail-open to an empty month-to-date. Loud on corruption."""
    month = _month_key(now)
    with _LOCK:
        data, state = _read_ledger()
    if state == "ok" and data.get("month") == month:
        return data
    if state == "unreadable":
        print("  ⚠ budget: pacing from an EMPTY estimate this run (under-counts; "
              "hard ceiling and the provider cap still apply) — the corrupt "
              "ledger is left untouched for repair", file=sys.stderr)
    return _fresh(month)


def _save_ledger(ledger, now=None):
    """Atomic: temp file in the same directory, then rename — no reader can
    ever see a truncated or half-written ledger."""
    tmp = None
    try:
        ledger["updated"] = (now or datetime.now(timezone.utc)).isoformat()
        LEDGER_FILE.parent.mkdir(exist_ok=True)
        tmp = LEDGER_FILE.with_name(f".{LEDGER_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        os.replace(tmp, LEDGER_FILE)
        tmp = None
    except OSError as exc:
        print(f"  ⚠ budget: ledger write failed ({exc}) — spend not recorded",
              file=sys.stderr)
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


class _FileLock:
    """Advisory lock beside the ledger (fcntl where available, else no-op)."""

    def __init__(self):
        self.path = LEDGER_FILE.with_name(f".{LEDGER_FILE.name}.lock")
        self.fh = None

    def __enter__(self):
        if fcntl is not None:
            try:
                self.path.parent.mkdir(exist_ok=True)
                self.fh = open(self.path, "a+")
                fcntl.flock(self.fh, fcntl.LOCK_EX)
            except OSError:
                self.fh = None
        return self

    def __exit__(self, *exc):
        if self.fh is not None:
            try:
                fcntl.flock(self.fh, fcntl.LOCK_UN)
            finally:
                self.fh.close()
                self.fh = None
        return False


def record(desk, model=None, usage=None, web_searches=0, usd=None, now=None):
    """Add one call's (or one run's) estimated spend. Never raises, and
    never replaces a ledger it could not read — losing one call's estimate
    is a rounding error; losing the month un-gates every desk."""
    try:
        amount = float(usd) if usd is not None else estimate_usd(
            model, usage, web_searches)
        amount *= SAFETY_FACTOR
        if amount <= 0:
            return 0.0
        month = _month_key(now)
        with _LOCK, _FileLock():
            ledger, state = _read_ledger()
            if state == "unreadable":
                print(f"  ⚠ budget: ${amount:.4f} for {desk} NOT recorded — the "
                      "ledger exists but cannot be parsed and is never overwritten",
                      file=sys.stderr)
                return 0.0
            if state == "missing" or ledger.get("month") != month:
                ledger = _fresh(month)  # first run, or the month rolled over
            ledger["desks"][desk] = round(ledger["desks"].get(desk, 0.0) + amount, 6)
            _save_ledger(ledger, now)
        return amount
    except Exception as exc:
        print(f"  ⚠ budget: record failed ({type(exc).__name__}) — "
              "spend not recorded", file=sys.stderr)
        return 0.0


def merge_ledgers(base, upstream, ours):
    """Three-way merge for the persist step: upstream + (ours − base) per desk.

    Two builds can start from the same commit and both record spend; a plain
    rebase then conflicts on the file. The right answer is never "pick a
    side" — it is the other run's ledger PLUS this run's own increments.
    A newer month wins outright (the month rolled over on one side); a
    missing/corrupt version counts as empty."""
    def _m(ledger):
        return (ledger or {}).get("month") or ""
    if _m(ours) > _m(upstream):
        return ours
    if _m(upstream) > _m(ours):
        return upstream
    month = _m(upstream)
    base_desks = (base or {}).get("desks", {}) if _m(base) == month else {}
    up_desks = dict((upstream or {}).get("desks", {}))
    for desk, value in ((ours or {}).get("desks", {}) or {}).items():
        base_value = float(base_desks.get(desk, 0.0))
        # Spend only grows inside a month: an upstream entry below (or
        # missing against) the common base means upstream lost it — take
        # the base as the floor rather than propagating the loss.
        floor = max(float(up_desks.get(desk, 0.0)), base_value)
        delta = float(value) - base_value
        up_desks[desk] = round(floor + max(delta, 0.0), 6)
    updated = max((ours or {}).get("updated") or "", (upstream or {}).get("updated") or "")
    return {"month": month, "desks": up_desks, "updated": updated or None}


def _git_stage(stage):
    """Read one index stage of the ledger during a stopped rebase (None if
    absent or unparseable)."""
    rel = LEDGER_FILE.relative_to(ROOT).as_posix()
    try:
        out = subprocess.run(["git", "show", f":{stage}:{rel}"], cwd=ROOT,
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        return _parse_ledger(out.stdout)
    except Exception:
        return None


def resolve_conflict():
    """CLI: in a stopped `git rebase origin/main`, stage 1 is the common
    base, stage 2 the upstream (origin/main) version and stage 3 this run's
    replayed commit. Writes the merged ledger; falls back to upstream so a
    resolution failure can only lose this run's delta, never the month."""
    base, upstream, ours = _git_stage(1), _git_stage(2), _git_stage(3)
    if upstream is None and ours is None:
        print("  ⚠ budget: no ledger stages to merge — leaving file as is",
              file=sys.stderr)
        return 1
    merged = merge_ledgers(base, upstream, ours)
    with _LOCK, _FileLock():
        _save_ledger(merged)
    desks = " ".join(f"{d}=${v:.2f}" for d, v in sorted(merged["desks"].items()))
    print(f"budget: ledger conflict merged → {merged['month']} {desks}")
    return 0


def month_total(ledger):
    return sum(ledger["desks"].values())


def _elapsed_fraction(now):
    days = calendar.monthrange(now.year, now.month)[1]
    day_progress = (now.day - 1 + (now.hour * 3600 + now.minute * 60) / 86400.0)
    return min(1.0, max(day_progress / days, 1.0 / days))  # day one gets a full day's pace


def pace_allows(desk, now=None):
    """(allowed, reason). The wire is exempt from pacing, ceiling only."""
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    ledger = load_ledger(now)
    total = month_total(ledger)
    ceiling = cfg["budget"] * cfg["hard_stop"]
    if total >= ceiling:
        return False, (f"hard ceiling: ${total:.2f} of ${ceiling:.2f} "
                       f"({cfg['hard_stop']:.0%} of ${cfg['budget']:.0f}) spent")
    if desk == PROTECTED_DESK:
        return True, f"protected desk, under ceiling (${total:.2f}/${ceiling:.2f})"
    alloc = cfg["allocations"].get(desk)
    if alloc is None:
        return True, f"no allocation configured for '{desk}' — ceiling only"
    pace = cfg["budget"] * alloc * _elapsed_fraction(now)
    spent = ledger["desks"].get(desk, 0.0)
    if spent >= pace:
        return False, (f"{desk} ahead of pace: ${spent:.2f} spent vs "
                       f"${pace:.2f} paced of ${cfg['budget'] * alloc:.2f}/month")
    return True, f"{desk} on pace: ${spent:.2f} of ${pace:.2f} paced"


def status_line(now=None):
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    ledger = load_ledger(now)
    total = month_total(ledger)
    parts = " ".join(f"{d}=${ledger['desks'].get(d, 0):.2f}" for d in DESKS)
    line = (f"budget {ledger['month']}: est ${total:.2f} of "
            f"${cfg['budget']:.0f} ({parts})")
    if total >= cfg["budget"] * 0.8:
        line += " ⚠ over 80% — discretionary desks will pace out"
    return line


def main(argv):
    if "--status" in argv:
        print(status_line())
        return 0
    if "--check" in argv:
        desk = argv[argv.index("--check") + 1]
        allowed, reason = pace_allows(desk)
        print(f"budget check {desk}: {'ALLOW' if allowed else 'SKIP'} — {reason}")
        return 0 if allowed else 3
    if "--record-usd" in argv:
        i = argv.index("--record-usd")
        desk, usd = argv[i + 1], float(argv[i + 2])
        recorded = record(desk, usd=usd)
        print(f"budget: recorded ${recorded:.2f} for {desk}")
        return 0
    if "--resolve-conflict" in argv:
        return resolve_conflict()
    print("usage: budget_ledger.py --status | --check DESK | --record-usd DESK USD"
          " | --resolve-conflict")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
