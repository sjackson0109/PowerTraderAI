"""
FDS-SR-001 milestone M5c: experiment E1, registered and run in a sandbox, on the owner's
approval of 2026-11-08 (``strategy_lab/e1.py`` declares and evaluates it).

Run it only inside E1's sandbox: POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed at
scratch folders, a keyring that fails, no keys. The sandbox's candle cache was cut at
2025-05-06 00:00 UTC, so no bar of the reserved months exists there.

    python run_sr1_e1.py <app dir> <out dir> rate
    python run_sr1_e1.py <app dir> <out dir> freeze
    python run_sr1_e1.py <app dir> <out dir> run
    python run_sr1_e1.py <app dir> <out dir> rehearse

* ``rate``: the GBP-to-USD reference rate (E-D6), from the Bank of England's database
  (series XUDLUSS, the spot rate of US$ into sterling, its latest published day), checked
  against the ECB's euro reference rates on the same day (USD per EUR / GBP per EUR):
  they must agree within 0.25%. Both answers are saved as received, with their SHA-256s.
* ``freeze``: reads the candles once, offline; today's venue rules (Coinbase's public
  product data); checks batch PV-1's probabilities against their recorded SHA-256s; and
  freezes E1 (``strategy_lab.experiment.freeze``). Nothing is scored.
* ``run``: verifies the frozen record (its seal, the code, the libraries, the candles and
  the probabilities), runs ``strategy_lab.e1.evaluate``, and writes ``results.json``,
  the evidence lines and the report.
* ``rehearse``: the same pipeline on synthetic candles, probabilities, venue rules and
  rate, in a separate sandbox whose folder name holds "rehearsal": it reads no real data,
  and shows that every step runs and how long it takes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

BOE_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?"
    "csv.x=yes&Datefrom={start}&Dateto=now&SeriesCodes=XUDLUSS&CSVF=TN&UsingCodes=Y"
    "&VPD=Y&VFD=N"
)
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
TOLERANCE = 0.0025


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def _setup(app: str) -> None:
    if app not in sys.path:
        sys.path.insert(0, app)
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set: run this only inside a sandbox")


def _plain(x):
    """JSON-safe: arrays to lists, numpy numbers to Python ones, NaN to None."""
    import numpy as np

    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if not math.isfinite(v) else v
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(_plain(data), f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def _sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# --- the rate (E-D6) ---------------------------------------------------------------------------


def _get(url: str, agent: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (a fixed https URL)
        return r.read()


def parse_boe(text: str) -> List[Tuple[str, float]]:
    """(ISO date, US$ per £) rows of the Bank of England's XUDLUSS CSV."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{1,2} [A-Za-z]{3} \d{4})\s*,\s*([0-9.]+)\s*$", line)
        if m:
            day = datetime.strptime(m.group(1), "%d %b %Y").date().isoformat()
            out.append((day, float(m.group(2))))
    return sorted(out)


def parse_ecb(text: str) -> Dict[str, Dict[str, float]]:
    """{ISO date: {currency: units per euro}} of the ECB's reference-rate XML."""
    out: Dict[str, Dict[str, float]] = {}
    for day, body in re.findall(
        r"<Cube time=['\"](\d{4}-\d\d-\d\d)['\"]>(.*?)</Cube>", text, re.S
    ):
        rates = re.findall(
            r"currency=['\"]([A-Z]{3})['\"] rate=['\"]([0-9.]+)['\"]", body
        )
        out[day] = {c: float(r) for c, r in rates}
    return out


def rate(out: str) -> Dict[str, Any]:
    folder = os.path.join(out, "rate")
    os.makedirs(folder, exist_ok=True)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=30)).strftime("%d/%b/%Y")
    boe_url = BOE_URL.format(start=start)
    boe_raw = _get(boe_url, "Mozilla/5.0")
    ecb_raw = _get(ECB_URL, "PowerTraderAI-research/1.0")
    retrieved = datetime.now(timezone.utc).isoformat()
    paths = {
        "boe": os.path.join(folder, "boe-XUDLUSS.csv"),
        "ecb": os.path.join(folder, "ecb-eurofxref-hist-90d.xml"),
    }
    for key, raw in (("boe", boe_raw), ("ecb", ecb_raw)):
        with open(paths[key], "wb") as f:
            f.write(raw)
    boe = parse_boe(boe_raw.decode("utf-8", "replace"))
    ecb = parse_ecb(ecb_raw.decode("utf-8", "replace"))
    if not boe:
        raise SystemExit("the Bank of England's answer holds no XUDLUSS rows")
    day, value = boe[-1]
    if day not in ecb or "USD" not in ecb[day] or "GBP" not in ecb[day]:
        raise SystemExit(f"the ECB has no USD and GBP rates for {day}: not verified")
    cross = ecb[day]["USD"] / ecb[day]["GBP"]
    diff = abs(cross / value - 1.0)
    latest_ecb = max(ecb)
    record = {
        "gbp_usd": value,
        "source": "Bank of England Database, series XUDLUSS (spot exchange rate, US$ into sterling)",
        "url": boe_url,
        "rate_date": day,
        "retrieved_at": retrieved,
        "raw_sha256": _sha_file(paths["boe"]),
        "verification": {
            "source": "European Central Bank euro foreign exchange reference rates (USD per EUR / GBP per EUR)",
            "url": ECB_URL,
            "rate_date": day,
            "usd_per_eur": ecb[day]["USD"],
            "gbp_per_eur": ecb[day]["GBP"],
            "cross": cross,
            "relative_difference": diff,
            "tolerance": TOLERANCE,
            "agrees": diff <= TOLERANCE,
            "raw_sha256": _sha_file(paths["ecb"]),
        },
        "ecb_latest": {
            "rate_date": latest_ecb,
            "cross": ecb[latest_ecb]["USD"] / ecb[latest_ecb]["GBP"],
        },
        "note": (
            "the latest day both publish at retrieval; frozen in E1's record and applied "
            "to every account; never read during the replay"
        ),
    }
    if not record["verification"]["agrees"]:
        raise SystemExit(f"the two sources differ by {diff:.4%}: not verified")
    _write(os.path.join(out, "rate.json"), record)
    return record


# --- freezing ------------------------------------------------------------------------------------


def _probabilities_sha256() -> Dict[str, str]:
    from model_lab.batch import batch_dir
    from strategy_lab import e1

    out = {}
    for key in (e1.MODEL_PV, e1.MODEL_P):
        path = os.path.join(batch_dir(e1.MODEL_BATCH), "probabilities", f"{key}.npz")
        out[key] = _sha_file(path)
        if out[key] != e1.MODEL_SHA256[key]:
            raise SystemExit(f"{key}: its probabilities are not the recorded ones")
    return out


def _left_out(data) -> Dict[str, str]:
    return {f"{c}:{tf}": why for tf, d in data.left_out.items() for c, why in d.items()}


def freeze(out: str) -> Dict[str, Any]:
    from pt_multi_exchange import market_exchanges
    from strategy_lab import e1, experiment
    from strategy_lab.venue import venue_rules

    with open(os.path.join(out, "rate.json"), encoding="utf-8") as f:
        rate_record = json.load(f)
    log("candles")
    loader = e1.development_loader()
    data = e1.load_data(loader)
    series = data.series_sha256()
    kept = sorted(data.universes["1d"].frames)
    log(f"{len(series)} series; coins {kept}")
    log("venue rules")
    venue = venue_rules(kept).as_record()
    venue["read_at"] = datetime.now(timezone.utc).isoformat()
    order = list(market_exchanges().exchange_names())
    record = e1.declaration(
        rate_record,
        venue,
        series,
        kept,
        _left_out(data),
        order,
        e1.listed_by_2021(data),
        _probabilities_sha256(),
        e1.served_by(data),
    )
    if experiment.trials():
        raise SystemExit("the sandbox's trial log is not empty: E1 must be its first")
    frozen = experiment.freeze(e1.EXPERIMENT_ID, record)
    _write(os.path.join(out, "experiment.json"), frozen)
    log(f"frozen {e1.EXPERIMENT_ID} {frozen['sha256']} at {frozen['frozen_at']}")
    return frozen


# --- running ------------------------------------------------------------------------------------


def _finish(out: str, record, result, started: float) -> None:
    from strategy_lab import e1, evidence

    result["seconds"] = round(time.time() - started, 1)
    _write(os.path.join(out, "results.json"), result)
    from sr1_e1_report import report

    text = report(record, result)
    with open(
        os.path.join(out, "SR1-E1-REPORT-dev.md"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(text)
    lines = e1.evidence_lines(result, len(result["coins"]["1d"]))
    sealed = evidence.write_results(e1.EXPERIMENT_ID, lines)
    _write(os.path.join(out, "evidence.json"), sealed)
    log(f"done in {result['seconds']} s")


def run(out: str) -> None:
    from model_lab.batch import read_probabilities
    from strategy_lab import e1, experiment

    record = experiment.verify(e1.EXPERIMENT_ID)
    log(f"verified {e1.EXPERIMENT_ID} {record['sha256']}")
    if _probabilities_sha256() != record["models"]["sha256"]:
        raise SystemExit("the probabilities changed since the freeze")
    started = time.time()
    loader = e1.development_loader()
    data = e1.load_data(loader)
    experiment.verify(e1.EXPERIMENT_ID, data.series_sha256())
    log("candles verified")
    result = e1.evaluate(
        record,
        loader,
        lambda key: read_probabilities(e1.MODEL_BATCH, key),
        progress=log,
        data=data,
    )
    _finish(out, record, result, started)


# --- the rehearsal (synthetic) ------------------------------------------------------------------

_LISTED = {
    "BTC": "2020-01-01", "ETH": "2020-01-01", "DASH": "2020-01-01", "LINK": "2020-01-01",
    "LTC": "2020-01-01", "ZEC": "2020-12-09", "ADA": "2021-03-19", "DOGE": "2021-06-04",
    "SOL": "2021-06-18", "AVAX": "2021-10-01", "XRP": "2023-07-14",
}  # fmt: skip


def _synthetic():
    """Random-walk hourly bars per coin, and the 4h, 12h and daily bars built from them."""
    import numpy as np
    import pandas as pd

    from strategy_lab import e1

    frames = {}
    for k, (coin, listed) in enumerate(sorted(_LISTED.items())):
        start = pd.Timestamp(listed, tz="UTC")
        hours = int((e1.DEV_END - start) / pd.Timedelta(hours=1))
        rng = np.random.default_rng(1000 + k)
        r = rng.normal(0.00002, 0.008, hours)
        close = 50.0 * (k + 1) * np.exp(np.cumsum(r))
        open_ = np.r_[close[0], close[:-1]]
        wick = np.abs(rng.normal(0, 0.002, hours))
        h1 = pd.DataFrame(
            {
                "open_time": pd.date_range(start, periods=hours, freq="h"),
                "open": open_,
                "high": np.maximum(open_, close) * (1 + wick),
                "low": np.minimum(open_, close) * (1 - wick),
                "close": close,
                "volume": rng.uniform(10, 100, hours),
            }
        )
        frames[(coin, "1h")] = h1
        for tf, rule in (("4h", "4h"), ("12h", "12h"), ("1d", "1D")):
            g = h1.set_index("open_time").resample(rule, origin="epoch")
            agg = pd.DataFrame(
                {
                    "open": g["open"].first(),
                    "high": g["high"].max(),
                    "low": g["low"].min(),
                    "close": g["close"].last(),
                    "volume": g["volume"].sum(),
                }
            ).dropna()
            frames[(coin, tf)] = agg.reset_index()
    return frames


def rehearse(out: str) -> None:
    import numpy as np
    import pandas as pd

    from strategy_lab import e1, experiment

    if "rehearsal" not in os.environ["POWERTRADER_HOME"].lower():
        raise SystemExit(
            "rehearse only in a sandbox whose folder name holds 'rehearsal'"
        )
    frames = _synthetic()

    def base(symbol, tf, a, b, cache_dir=None, offline=True):
        f = frames[(symbol.split("-")[0], tf)]
        return f[(f["open_time"] >= a) & (f["open_time"] < b)].reset_index(drop=True)

    def first(symbol, tf):
        f = frames.get((symbol.split("-")[0], tf))
        return None if f is None else pd.Timestamp(f["open_time"].iloc[0])

    rng = np.random.default_rng(7)
    probs = {}
    for key in (e1.MODEL_PV, e1.MODEL_P):
        probs[key] = {}
        for coin in _LISTED:
            h = frames[(coin, "1h")]
            close_s = (
                (h["open_time"] - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
            ).to_numpy() + 3600
            keep = close_s >= int(pd.Timestamp("2022-01-01", tz="UTC").timestamp())
            probs[key][coin] = (close_s[keep], rng.uniform(0.1, 0.6, int(keep.sum())))
    started = time.time()
    loader = e1.development_loader(base, first)
    data = e1.load_data(loader)
    kept = sorted(data.universes["1d"].frames)
    record = e1.declaration(
        {"gbp_usd": 1.30, "source": "synthetic (rehearsal)"},
        {
            "minimum_usd": {c: 1.0 for c in kept},
            "base_increment": {c: 1e-8 for c in kept},
            "unknown": {},
            "read_at": "synthetic",
        },
        data.series_sha256(),
        kept,
        _left_out(data),
        ["coinbase", "kraken", "kucoin", "binance"],
        e1.listed_by_2021(data),
        {k: "synthetic" for k in probs},
        e1.served_by(data),
    )
    frozen = experiment.freeze(e1.EXPERIMENT_ID, record)
    log(f"rehearsal frozen in {time.time() - started:.0f} s")
    result = e1.evaluate(
        frozen, loader, lambda key: probs[key], progress=log, data=data
    )
    result["rehearsal"] = "synthetic candles, probabilities, venue rules and rate"
    _finish(out, frozen, result, started)


def main(argv: List[str]) -> int:
    app, out, step = argv[1], argv[2], argv[3]
    _setup(app)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out, exist_ok=True)
    if step == "rate":
        print(json.dumps(rate(out), indent=1))
    elif step == "freeze":
        freeze(out)
    elif step == "run":
        run(out)
    elif step == "rehearse":
        rehearse(out)
    else:
        raise SystemExit(f"unknown step {step!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
