"""
FDS-SIG-001 section 10.1 (owner decision D10): what each supported exchange's public
data states about when a market's trading began or ended, which the ranking may use
in place of a missing daily bar. Verification only: public market data, no keys, the
standard library alone (none of the code under audit), nothing ranked or registered.

    python docs/dev/sig_listing_evidence_probe.py [--ranking-date YYYY-MM-DD]

For each exchange whose connector lists markets (Binance, KuCoin, Kraken, Coinbase):
its public market list's fields, any that name or hold a time, and its statuses. Then
the checks the ranking rule rests on:

* **KuCoin's ``tradingStartTime``** against KuCoin's own daily candles: every USDT
  symbol whose stated start is within 40 days of the probe's 30-day span, and a sample
  of older ones (the first candle's day, and any candle before the stated day); and the
  symbols with no stated start (how many have fewer than 30 daily candles in the span).
* **Binance**, which states no time: each TRADING USDT symbol's first-ever daily kline
  (how many began within the span), each BREAK symbol's klines in the span, and
  whether its delisting-schedule endpoint answers without a key.

Writes ``docs/dev/sig-audit/verification/listing-evidence-probe.json`` (the answers'
SHA-256, not the answers).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAY = 86_400_000
DATEISH = re.compile(
    r"time|date|list|start|onboard|launch|creat|delist|since|_at$", re.I
)
LISTINGS = {
    "binance": ("https://api.binance.com/api/v3/exchangeInfo", "USDT"),
    "kucoin": ("https://api.kucoin.com/api/v2/symbols", "USDT"),
    "kraken": ("https://api.kraken.com/0/public/AssetPairs", "USD"),
    "coinbase": ("https://api.exchange.coinbase.com/products", "USD"),
}


def day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def get(url):
    """(HTTP status, parsed JSON or text, raw bytes)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "PowerTraderAI-audit-probe"}
    )
    err = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw.decode("utf-8")), raw
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw.decode("utf-8")), raw
            except ValueError:
                return e.code, raw.decode("utf-8", "replace"), raw
        except Exception as e:  # network trouble: try again, then report
            err = f"{type(e).__name__}: {e}"
            time.sleep(1 + attempt)
    return None, err, b""


def records(name, data, quote):
    if name == "binance":
        return [s for s in data["symbols"] if s.get("quoteAsset") == quote]
    if name == "kucoin":
        return [s for s in data["data"] if s.get("quoteCurrency") == quote]
    if name == "kraken":
        return [
            v
            for v in data["result"].values()
            if str(v.get("wsname", "")).endswith("/" + quote)
        ]
    return [p for p in data if p.get("quote_currency") == quote]


def timelike(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)) and 1_000_000_000 <= v <= 2_000_000_000_000:
        return True
    return isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", v))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    parser.add_argument("--ranking-date", default=yesterday)
    parser.add_argument(
        "--out",
        default=os.path.join(
            REPO,
            "docs",
            "dev",
            "sig-audit",
            "verification",
            "listing-evidence-probe.json",
        ),
    )
    args = parser.parse_args(argv)
    last = int(
        datetime.strptime(args.ranking_date, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    first = last - 29 * DAY
    out = {
        "what": "FDS-SIG-001 section 10.1, D10: the listing and cessation times each exchange states "
        "(verification; public market data; nothing ranked)",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ranking_date": args.ranking_date,
        "span": [day(first), day(last)],
        "exchanges": {},
    }
    lists = {}
    for name, (url, quote) in LISTINGS.items():
        status, data, raw = get(url)
        recs = records(name, data, quote) if status == 200 else []
        lists[name] = recs
        keys = collections.Counter(k for r in recs for k in r)
        held = collections.Counter(k for r in recs for k, v in r.items() if timelike(v))
        status_key = "enableTrading" if name == "kucoin" else "status"
        out["exchanges"][name] = {
            "endpoint": url,
            "http_status": status,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "markets": len(recs),
            "quote": quote,
            "fields": sorted(keys),
            "fields_named_for_a_time": sorted(k for k in keys if DATEISH.search(k)),
            "fields_holding_times": dict(sorted(held.items())),
            "statuses": dict(
                collections.Counter(str(r.get(status_key)) for r in recs).most_common()
            ),
        }
        print(
            f"{name}: {len(recs)} markets; time fields {out['exchanges'][name]['fields_holding_times']}",
            flush=True,
        )

    # KuCoin: the stated start against its own candles
    ku = lists["kucoin"]

    def kucoin_days(symbol, start_ms, end_ms):
        status, d, _raw = get(
            f"https://api.kucoin.com/api/v1/market/candles?type=1day&symbol={urllib.parse.quote(symbol)}"
            f"&startAt={start_ms // 1000}&endAt={end_ms // 1000 + 86399}"
        )
        time.sleep(0.12)
        if status != 200 or str(d.get("code")) != "200000":
            return None, f"{status} {str(d)[:120]}"
        return sorted(int(r[0]) * 1000 for r in d.get("data") or []), ""

    recent = [
        s
        for s in ku
        if s.get("tradingStartTime") and s["tradingStartTime"] >= first - 10 * DAY
    ]
    older = sorted(
        (
            s
            for s in ku
            if s.get("tradingStartTime") and s["tradingStartTime"] < first - 10 * DAY
        ),
        key=lambda s: s["tradingStartTime"],
    )
    checks = []
    for s in recent + older[:: max(1, len(older) // 25)][:25]:
        st = int(s["tradingStartTime"])
        days, err = kucoin_days(s["symbol"], min(st, first) - 40 * DAY, last + DAY)
        checks.append(
            {
                "symbol": s["symbol"],
                "stated_day": day(st),
                "first_candle_day": day(days[0]) if days else None,
                "candles_before_stated_day": sum(
                    1 for t in (days or []) if t < st // DAY * DAY
                ),
                "candles_in_span": sum(1 for t in (days or []) if first <= t <= last),
                "recent": s in recent,
                "error": err,
            }
        )
    rec = [c for c in checks if c["recent"]]
    old = [c for c in checks if not c["recent"]]
    unstated = []
    for s in ku:
        if s.get("tradingStartTime"):
            continue
        days, err = kucoin_days(s["symbol"], first, last)
        unstated.append(
            {"symbol": s["symbol"], "candles_in_span": len(days or []), "error": err}
        )
    out["kucoin"] = {
        "stated_start": sum(1 for s in ku if s.get("tradingStartTime")),
        "no_stated_start": len(unstated),
        "recent_listings_checked": len(rec),
        "recent_first_candle_on_stated_day": sum(
            1 for c in rec if c["first_candle_day"] == c["stated_day"]
        ),
        "older_checked": len(old),
        "older_first_candle_on_stated_day": sum(
            1 for c in old if c["first_candle_day"] == c["stated_day"]
        ),
        "any_candle_before_a_stated_day": sum(
            1 for c in checks if c["candles_before_stated_day"]
        ),
        "no_stated_start_with_fewer_than_30_days": sum(
            1 for u in unstated if u["candles_in_span"] < 30
        ),
        "errors": sum(1 for c in checks + unstated if c["error"]),
        "checks": checks,
    }
    print(
        "kucoin:", {k: v for k, v in out["kucoin"].items() if k != "checks"}, flush=True
    )

    # Binance: no stated times; what its klines show
    bn = lists["binance"]
    began, never, partial, empty, errors = [], [], [], [], 0
    for s in bn:
        sym = s["symbol"]
        if s.get("status") == "TRADING":
            status, d, _raw = get(
                f"https://api.binance.com/api/v3/klines?symbol={urllib.parse.quote(sym)}&interval=1d&startTime=0&limit=1"
            )
            if status == 200 and isinstance(d, list) and d:
                if int(d[0][0]) >= first:
                    began.append({"symbol": sym, "first_ever_day": day(int(d[0][0]))})
            elif status == 200 and isinstance(d, list):
                never.append(sym)  # listed as trading, no kline yet
            else:
                errors += 1
        else:
            status, d, _raw = get(
                f"https://api.binance.com/api/v3/klines?symbol={urllib.parse.quote(sym)}&interval=1d&startTime={first}&endTime={last}&limit=60"
            )
            if status == 200 and isinstance(d, list):
                (empty if not d else partial if len(d) < 30 else []).append(sym)
            else:
                errors += 1
        time.sleep(0.08)
    status, d, _raw = get("https://api.binance.com/sapi/v1/spot/delist-schedule")
    out["binance"] = {
        "trading": sum(1 for s in bn if s.get("status") == "TRADING"),
        "trading_first_ever_bar_within_span": began,
        "trading_without_any_bar": never,
        "not_trading": sum(1 for s in bn if s.get("status") != "TRADING"),
        "not_trading_without_a_bar_in_span": len(empty),
        "not_trading_with_part_of_span": partial,
        "errors": errors,
        "delist_schedule_without_a_key": {
            "http_status": status,
            "answer": str(d)[:200],
        },
    }
    print(
        "binance:",
        {k: (len(v) if isinstance(v, list) else v) for k, v in out["binance"].items()},
        flush=True,
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
