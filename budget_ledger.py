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
import statistics
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
    "claude-fable-5-1": {"in": 10.00, "out": 50.00, "cache_read": 0.25, "cache_write": 12.50},
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
        tiers = cfg.get("tiers") or {}
        if not isinstance(tiers, dict):
            tiers = {}
        return {"budget": budget, "hard_stop": hard_stop,
                "allocations": allocations, "tiers": tiers}
    except Exception as exc:
        # A broken config must not un-gate the discretionary desks: fall back
        # to the owner-approved floor rather than to "unlimited".
        print(f"  ⚠ budget: config unreadable ({type(exc).__name__}) — "
              "using $150 defaults", file=sys.stderr)
        return {"budget": 150.0, "hard_stop": 0.92,
                "allocations": {"briefs": 0.12, "investigations": 0.22,
                                "editor": 0.30, "washington": 0.24,
                                "maintenance": 0.04},
                "tiers": {}}


_LOCK = threading.RLock()          # in-process: the briefs desk records from a thread pool
_READ_RETRIES = 6                  # a transient partial read is retried before it counts
_READ_RETRY_DELAY = 0.05


def _parse_ledger(text):
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("desks"), dict):
        raise ValueError("ledger shape")
    data["desks"] = {k: float(v) for k, v in data["desks"].items()}
    data["tags"] = {k: float(v) for k, v in (data.get("tags") or {}).items()}
    runs = data.get("runs") or {}
    data["runs"] = {d: [r for r in (v or []) if isinstance(r, dict)]
                    for d, v in runs.items()} if isinstance(runs, dict) else {}
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
    return {"month": month, "desks": {}, "tags": {}, "runs": {}, "updated": None}


RUN_HISTORY = 30                   # per desk: enough to learn a tier's real price


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


def record(desk, model=None, usage=None, web_searches=0, usd=None, now=None,
           tag=None, tier=None):
    """Add one call's (or one run's) estimated spend. Never raises, and
    never replaces a ledger it could not read — losing one call's estimate
    is a rounding error; losing the month un-gates every desk.

    `tag` files the call under a sub-line of the desk (the wire's rewrite
    vs its duplicate judge) so the money can be attacked with evidence;
    `tier` marks a whole run (usd given) so the governor learns what each
    tier of a desk really costs."""
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
            if tag:
                key = f"{desk}:{tag}"
                ledger.setdefault("tags", {})[key] = round(
                    ledger["tags"].get(key, 0.0) + amount, 6)
            if usd is not None:
                runs = ledger.setdefault("runs", {}).setdefault(desk, [])
                runs.append({"ts": (now or datetime.now(timezone.utc)).isoformat(),
                             "usd": round(amount, 4), "tier": tier or "full"})
                del runs[:-RUN_HISTORY]
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

    def _sum_merge(field):
        base_map = (base or {}).get(field, {}) if _m(base) == month else {}
        merged = dict((upstream or {}).get(field, {}) or {})
        for key, value in ((ours or {}).get(field, {}) or {}).items():
            base_value = float(base_map.get(key, 0.0))
            # Spend only grows inside a month: an upstream entry below (or
            # missing against) the common base means upstream lost it — take
            # the base as the floor rather than propagating the loss.
            floor = max(float(merged.get(key, 0.0)), base_value)
            delta = float(value) - base_value
            merged[key] = round(floor + max(delta, 0.0), 6)
        return merged

    runs = {}
    for side in (upstream, ours):
        for desk, entries in ((side or {}).get("runs", {}) or {}).items():
            seen = {(r.get("ts"), r.get("usd")) for r in runs.get(desk, [])}
            for r in entries or []:
                if (r.get("ts"), r.get("usd")) not in seen:
                    runs.setdefault(desk, []).append(r)
                    seen.add((r.get("ts"), r.get("usd")))
    for desk in runs:
        runs[desk] = sorted(runs[desk], key=lambda r: r.get("ts") or "")[-RUN_HISTORY:]
    updated = max((ours or {}).get("updated") or "", (upstream or {}).get("updated") or "")
    return {"month": month, "desks": _sum_merge("desks"), "tags": _sum_merge("tags"),
            "runs": runs, "updated": updated or None}


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


def _days_in_month(now):
    return calendar.monthrange(now.year, now.month)[1]


def _elapsed_fraction(now):
    days = _days_in_month(now)
    day_progress = (now.day - 1 + (now.hour * 3600 + now.minute * 60) / 86400.0)
    return min(1.0, max(day_progress / days, 1.0 / days))  # day one gets a full day's pace


# ---------------------------------------------------------------------------
# The purse (owner question 2026-09-02: "come up with a creative solution").
#
# The first design paced five fixed silos, and reality broke it on day two:
# the wire alone runs near the whole budget, while the editor's silo could
# buy two Opus runs a month and then sit dark for four weeks. The redesign:
#
# 1. Silos became WEIGHTS. The wire's projected month (its trailing daily
#    rate) is reserved first — the wire IS the paper — and whatever the
#    ceiling leaves is the discretionary pool, shared by weight. The owner
#    still turns ONE knob (monthly_budget_usd); the desks re-balance
#    themselves as the wire's appetite moves.
# 2. Each desk keeps a PURSE: its cap accrues at a daily rate, every run
#    spends from it, and a run is allowed only when the purse can pay for
#    it. A big run empties the purse and the desk saves up again — no
#    monthly blackout, just a rhythm.
# 3. Desks can run in TIERS (editorial/budget.json "tiers"): the editor's
#    FULL edition (Opus, the whole mandate) and a LIGHT edition (Sonnet,
#    the non-negotiables). The governor picks the best tier the purse can
#    pay for on that weekday, learns each tier's real price from the runs
#    it records, and `--forecast` says what the month buys — and what a
#    bigger budget would.
# ---------------------------------------------------------------------------

def wire_projection(cfg, ledger, now):
    """What the protected desk will cost this month: trailing rate × month,
    never below its weight share (day one would otherwise read as free) and
    never below what it has already spent."""
    spent = ledger["desks"].get(PROTECTED_DESK, 0.0)
    elapsed = _elapsed_fraction(now)
    rate_based = spent / elapsed if elapsed > 0 else 0.0
    floor = cfg["budget"] * cfg["allocations"].get(PROTECTED_DESK, 0.0)
    return max(rate_based, floor, spent)


def desk_caps(cfg, ledger, now, budget=None):
    """(caps, pool): monthly cap per discretionary desk — the ceiling minus
    the wire's projected month, shared by allocation weight. `budget`
    overrides the configured number for what-if forecasts."""
    budget = cfg["budget"] if budget is None else budget
    ceiling = budget * cfg["hard_stop"]
    pool = max(0.0, ceiling - wire_projection(cfg, ledger, now))
    weights = {d: w for d, w in cfg["allocations"].items() if d != PROTECTED_DESK}
    total_w = sum(weights.values()) or 1.0
    return {d: pool * w / total_w for d, w in weights.items()}, pool


def purse(desk, cfg, ledger, now, budget=None):
    """Balance the desk may spend right now: accrued cap minus spent (None
    when the desk has no weight — ceiling only)."""
    caps, _ = desk_caps(cfg, ledger, now, budget)
    cap = caps.get(desk)
    if cap is None:
        return None
    return cap * _elapsed_fraction(now) - ledger["desks"].get(desk, 0.0)


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
    balance = purse(desk, cfg, ledger, now)
    if balance is None:
        return True, f"no allocation configured for '{desk}' — ceiling only"
    caps, pool = desk_caps(cfg, ledger, now)
    spent = ledger["desks"].get(desk, 0.0)
    if balance <= 0:
        return False, (f"{desk} purse empty: ${spent:.2f} spent against a "
                       f"${caps[desk]:.2f}/month cap (pool ${pool:.2f} after the "
                       f"wire's projected ${wire_projection(cfg, ledger, now):.2f})")
    return True, (f"{desk} purse ${balance:.2f}: ${spent:.2f} spent of a "
                  f"${caps[desk]:.2f}/month cap")


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def tier_prices(cfg, ledger, desk):
    """Configured price per tier, replaced by the median of the last five
    recorded runs of that tier once two or more exist."""
    prices = {}
    history = ledger.get("runs", {}).get(desk, [])
    for name, spec in (cfg.get("tiers", {}).get(desk) or {}).items():
        seen = [float(r.get("usd") or 0) for r in history if r.get("tier") == name]
        seen = [v for v in seen if v > 0][-5:]
        if len(seen) >= 2:
            prices[name] = statistics.median(seen)
        else:
            prices[name] = float(spec.get("usd") or 0)
    return prices


def _tier_eligible(spec, now):
    days = spec.get("days")
    return not days or _WEEKDAYS[now.weekday()] in [str(d).lower()[:3] for d in days]


def tier_shares(tiers):
    """Each edition saves from its own share of the desk's refill (config
    `share`, else an equal split) — so the light edition running most days
    never starves the full one of the money it is saving up."""
    raw = {name: float(spec.get("share") or 0) for name, spec in tiers.items()}
    if sum(raw.values()) <= 0:
        raw = {name: 1.0 for name in tiers}
    total = sum(raw.values())
    return {name: v / total for name, v in raw.items()}


def tier_balances(cfg, ledger, desk, now, budget=None):
    """Per-edition purses. Spend recorded with a tier is charged to it; spend
    with no tier (the wire-style running total, restored history) is charged
    to the first, most expensive tier so nothing is ever forgotten."""
    tiers = cfg.get("tiers", {}).get(desk) or {}
    caps, _ = desk_caps(cfg, ledger, now, budget)
    cap = caps.get(desk, 0.0)
    shares = tier_shares(tiers)
    elapsed = _elapsed_fraction(now)
    spent_by_tier = {name: 0.0 for name in tiers}
    for run in ledger.get("runs", {}).get(desk, []):
        t = run.get("tier")
        if t in spent_by_tier:
            spent_by_tier[t] += float(run.get("usd") or 0)
    first = next(iter(tiers), None)
    if first is not None:
        untracked = ledger["desks"].get(desk, 0.0) - sum(spent_by_tier.values())
        spent_by_tier[first] += max(untracked, 0.0)
    return {name: cap * shares[name] * elapsed - spent_by_tier[name] for name in tiers}


def _pick_tier(tiers, prices, balances, now):
    """Highest configured tier (file order) that is eligible today and whose
    own purse can pay for it; None when none can."""
    for name, spec in tiers.items():
        if _tier_eligible(spec, now) and balances.get(name, 0.0) >= prices.get(name, 0.0):
            return name
    return None


def choose_tier(desk, now=None):
    """(tier_or_None, spec, reason) — the edition the purse can pay for today."""
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    tiers = cfg.get("tiers", {}).get(desk) or {}
    allowed, reason = pace_allows(desk, now)
    if not tiers:  # an un-tiered desk runs whole or not at all
        return ("full" if allowed else None), {}, reason
    if not allowed and "ceiling" in reason:
        return None, {}, reason
    ledger = load_ledger(now)
    if purse(desk, cfg, ledger, now) is None:
        first = next(iter(tiers))
        return first, tiers[first], reason
    prices = tier_prices(cfg, ledger, desk)
    balances = tier_balances(cfg, ledger, desk, now)
    name = _pick_tier(tiers, prices, balances, now)
    caps, _ = desk_caps(cfg, ledger, now)
    shares = tier_shares(tiers)
    days = _days_in_month(now)
    purses = " ".join(f"{n}=${balances[n]:.2f}/${prices[n]:.2f}" for n in tiers)
    if name is None:
        waits = []
        for n in tiers:
            refill = caps.get(desk, 0.0) * shares[n] / days
            if refill > 0:
                waits.append((prices[n] - balances[n]) / refill)
        wait = min(waits) if waits else float("inf")
        return None, {}, (f"{desk} purses cannot pay any edition ({purses}) — "
                          + (f"next edition in ~{max(wait, 0):.0f} day(s)"
                             if wait != float("inf")
                             else "no discretionary pool at this budget"))
    return name, tiers[name], (f"{desk} {name.upper()} edition: purse {purses}; "
                              f"cap ${caps.get(desk, 0.0):.2f}/month")


def simulate_month(cfg, ledger, desk, now, budget=None, fresh=False):
    """Day-by-day rehearsal of a month at a budget: how many editions of
    each tier the purses would buy. `fresh` rehearses a normal month from
    day one with nothing spent — the number the knob should be judged on;
    otherwise the rest of THIS month, sunk spend included. Honest, not
    hopeful."""
    tiers = cfg.get("tiers", {}).get(desk) or {}
    if not tiers:
        return {}, desk_caps(cfg, ledger, now, budget)[0].get(desk, 0.0)
    caps, _ = desk_caps(cfg, ledger, now, budget)
    cap = caps.get(desk, 0.0)
    days = _days_in_month(now)
    shares = tier_shares(tiers)
    prices = tier_prices(cfg, ledger, desk)
    if fresh:
        start_day, balances = 1, {n: 0.0 for n in tiers}
    else:
        start_day = now.day
        balances = tier_balances(cfg, ledger, desk, now, budget)
    counts = {name: 0 for name in tiers}
    for offset in range(start_day, days + 1):
        day = now.replace(day=offset, hour=6, minute=30)
        if offset > start_day or fresh:
            for n in tiers:
                balances[n] += cap * shares[n] / days
        name = _pick_tier(tiers, prices, balances, day)
        if name:
            counts[name] += 1
            balances[name] -= prices.get(name, 0.0)
    return counts, cap


def _cadence(counts):
    return ", ".join(f"{n} {name}" for name, n in counts.items()) or "nothing"


def forecast(now=None, what_if=(200, 250, 300, 400)):
    """Owner-facing: where the month is going, what the purse buys, and
    what each bigger budget would buy — so the one knob is turned with
    eyes open, never guessed."""
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    ledger = load_ledger(now)
    total = month_total(ledger)
    wire = wire_projection(cfg, ledger, now)
    caps, pool = desk_caps(cfg, ledger, now)
    ceiling = cfg["budget"] * cfg["hard_stop"]
    days = _days_in_month(now)
    lines = [f"budget {ledger['month']} forecast — day {now.day} of {days}, "
             f"${total:.2f} spent, budget ${cfg['budget']:.0f} (ceiling ${ceiling:.2f})",
             f"  wire: ${ledger['desks'].get(PROTECTED_DESK, 0.0):.2f} so far → projects "
             f"${wire:.2f}/month; discretionary pool ${pool:.2f}"]
    tags = {k: v for k, v in ledger.get("tags", {}).items()
            if k.startswith(PROTECTED_DESK + ":")}
    if tags:
        lines.append("  wire breakdown: " + " ".join(
            f"{k.split(':', 1)[1]}=${v:.2f}" for k, v in sorted(tags.items())))
    for desk in DESKS:
        if desk == PROTECTED_DESK:
            continue
        spent = ledger["desks"].get(desk, 0.0)
        balance = purse(desk, cfg, ledger, now)
        if balance is None:
            continue
        cap = caps.get(desk, 0.0)
        if cfg.get("tiers", {}).get(desk):
            counts, _ = simulate_month(cfg, ledger, desk, now)
            lines.append(f"  {desk}: ${spent:.2f} spent, cap ${cap:.2f}, purse "
                         f"${balance:.2f} → rest of month buys {_cadence(counts)}")
        else:
            lines.append(f"  {desk}: ${spent:.2f} spent, cap ${cap:.2f}, purse "
                         f"${balance:.2f} (refills ${cap / days:.2f}/day)")
    tiered = [d for d in DESKS if cfg.get("tiers", {}).get(d)]
    if tiered and what_if:
        lines.append("  what the knob buys (a normal month at today's wire rate, "
                     "then the rest of this one):")
        for budget in what_if:
            if budget <= cfg["budget"]:
                continue
            parts = []
            for desk in tiered:
                normal, cap = simulate_month(cfg, ledger, desk, now, budget, fresh=True)
                rest, _ = simulate_month(cfg, ledger, desk, now, budget)
                parts.append(f"{desk} cap ${cap:.0f}: {_cadence(normal)} "
                             f"(this month {_cadence(rest)})")
            lines.append(f"    ${budget}: " + "; ".join(parts))
    return "\n".join(lines)


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
    if "--forecast" in argv:
        print(forecast())
        return 0
    if "--check" in argv:
        desk = argv[argv.index("--check") + 1]
        allowed, reason = pace_allows(desk)
        print(f"budget check {desk}: {'ALLOW' if allowed else 'SKIP'} — {reason}")
        return 0 if allowed else 3
    if "--record-usd" in argv:
        i = argv.index("--record-usd")
        desk, usd = argv[i + 1], float(argv[i + 2])
        tier = argv[argv.index("--tier") + 1] if "--tier" in argv else None
        recorded = record(desk, usd=usd, tier=tier)
        print(f"budget: recorded ${recorded:.2f} for {desk}"
              + (f" ({tier} tier)" if tier else ""))
        return 0
    if "--tier" in argv:
        # Workflow-facing: KEY=VALUE lines on stdout (append to $GITHUB_OUTPUT),
        # the human reason on stderr; exit 3 when the purse says skip.
        desk = argv[argv.index("--tier") + 1]
        name, spec, reason = choose_tier(desk)
        print(f"budget tier {desk}: {(name or 'SKIP').upper()} — {reason}", file=sys.stderr)
        if name is None:
            print("run=no\ntier=skip")
            return 3
        print(f"run=yes\ntier={name}")
        for key in ("model", "max_turns"):
            if spec.get(key) is not None:
                print(f"{key}={spec[key]}")
        return 0
    if "--resolve-conflict" in argv:
        return resolve_conflict()
    print("usage: budget_ledger.py --status | --forecast | --check DESK | --tier DESK"
          " | --record-usd DESK USD [--tier NAME] | --resolve-conflict")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
