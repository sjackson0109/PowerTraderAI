"""
The live entry assessment, log only (FDS-SIG-004 phase E, sections 5.8, 5.10 and 6.6).

**Where it runs.** The trader captures what an entry would be assessed on directly after
its own sizing (``capture``): the coin, the amount and minimum entry its sizing gave, and
the quote it priced the entry from. In this version every part is Off or Log only, so
nothing can change an order: the assessment is made and recorded after the order has been
placed (``log``), and an error in it is recorded, never raised into the trader.

**What it records** (section 5.8.2), one line per entry the strategy or the thinker wanted,
in ``<data dir>/signal_fusion/assessments.jsonl``:

* the predictive part: unavailable until a model is registered (``artifact``), with the
  reason;
* the volatility shrink: its scale needs the registered model's σ_ref, so it is
  unavailable until then too;
* the spread cap: the live spread of the entry's quote and its age, against s_max;
* the participation cap: the entry's share of the coin's median hourly approximate dollar
  volume over the 20 previous complete UTC days, from the candles of the venue the exchange
  layer reads (the primary exchange first), against π;
* what each part would have done, and the effect, which in this version is always none.

No record holds an outcome: not a fill's result, nor a trade's profit (section 6.6).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from signal_fusion import artifact
from signal_fusion import assessment as asm
from signal_fusion import liquidity as lq

DAY_S = 86400
RECORDS = "assessments.jsonl"


def records_path() -> str:
    import pt_paths

    return os.path.join(pt_paths.data_dir(), "signal_fusion", RECORDS)


def capture(
    settings: asm.Settings,
    coin: str,
    symbol: str,
    source: str,
    amount_usd: float,
    minimum_entry_usd: Optional[float],
    ask: Any,
    bid: Any,
    quotes_at: Optional[float],
    fees: Any = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """What the entry is assessed on, as it was at the hook."""
    now = time.time() if now is None else float(now)

    def number(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return v if v > 0 else None

    return {
        "settings": settings,
        "when_s": int(now),
        "coin": coin,
        "symbol": symbol,
        "source": source,
        "amount_usd": float(amount_usd),
        "minimum_entry_usd": number(minimum_entry_usd),
        "ask": number(ask),
        "bid": number(bid),
        "quote_age_s": (now - float(quotes_at)) if quotes_at else None,
        "fee": getattr(fees, "taker", None),
        "fee_source": getattr(fees, "source", None),
    }


def hourly_candles(coin: str, at_s: int):
    """The coin's 1-hour bars for the participation cap, through the exchange layer."""
    import pandas as pd

    from market_data.candles import exchange_candles

    end = pd.Timestamp((int(at_s) // 3600) * 3600, unit="s", tz="UTC")
    start = end - pd.Timedelta(days=lq.MEDIAN_DAYS + 1)
    df = exchange_candles(coin, "1h", start, end)
    venue = df.attrs.get("exchange", "")
    t = [int(x.timestamp()) for x in df["open_time"]]
    cols = [
        df[c].astype(float).to_numpy()
        for c in ("open", "high", "low", "close", "volume")
    ]
    return venue, t, cols


def evaluate(
    c: Dict[str, Any],
    candles: Optional[Callable[[str, int], Any]] = None,
    registered: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The record for one captured entry (the module docstring)."""
    s: asm.Settings = c["settings"]
    candles = candles or hourly_candles
    registered = registered or {}
    fields: Dict[str, Any] = {
        "amount_usd": c["amount_usd"],
        "minimum_entry_usd": c["minimum_entry_usd"],
        "fee": c["fee"],
        "fee_source": c["fee_source"],
        "quote_age_s": c["quote_age_s"],
    }
    venues = {"order": c["symbol"]}

    def model():
        data, why = artifact.load(registered.get("path"), registered.get("sha256"))
        if data is None:
            raise LookupError(why)
        return data

    def expected_value():
        model()  # no registered model: unavailable, with the reason
        raise LookupError("no expected value without a registered model")

    def shrink_scale():
        model()
        raise LookupError("no volatility reference without a registered model")

    def spread_check():
        check = lq.spread(c["bid"], c["ask"], c["quote_age_s"], s.spread_max)
        fields["spread"] = check.value
        return check.ok, check.value, check.reason

    def participation_check(amount):
        venue, t, (o, h, lo, cl, v) = candles(c["coin"], c["when_s"])
        venues["candles"] = venue
        median = lq.hourly_median(t, o, h, lo, cl, v, c["when_s"])
        fields["hourly_median_usd"] = median.value
        fields["eps_max"] = median.eps_max
        check = lq.participation(amount, median, s.participation_pi)
        fields["participation"] = check.value
        fields["participation_bound"] = check.bound
        return check.ok, check.value, check.reason

    pre = asm.predictive(s, expected_value)
    post = asm.protective(
        s,
        c["amount_usd"],
        c["minimum_entry_usd"],
        shrink_scale,
        spread_check,
        participation_check,
    )
    record = asm.record(c["when_s"], c["coin"], venues, c["source"], pre, post, fields)
    record["settings"] = {
        "entry_assessment": s.entry_assessment,
        "volatility_shrink": s.volatility_shrink,
        "participation_cap": s.participation_cap,
        "spread_cap": s.spread_cap,
        "participation_pi": s.participation_pi,
        "spread_max": s.spread_max,
    }
    return record


def log(c: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    """Evaluate and append the record; None when it could not be made (the failure is
    recorded instead). Never raises."""
    try:
        record = evaluate(c, **kwargs)
    except Exception as exc:
        record = {
            "when_s": c.get("when_s"),
            "coin": c.get("coin"),
            "effect": "allow",
            "error": f"{type(exc).__name__}: {exc}",
        }
    try:
        path = records_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except Exception:
        return None
    return record


def read_records(limit: int = 500) -> List[Dict[str, Any]]:
    """The latest records, newest first (the assessment table)."""
    try:
        with open(records_path(), "r", encoding="utf-8") as f:
            lines = f.readlines()[-int(limit) :]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
