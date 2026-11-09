"""What strategy_lab.observation.reconcile reports for cases item 8 needs: a duplicated
entry, a trade still open, a row from another strategy, a late fill in the same candle,
an exit fee. Synthetic daily bars and trade rows; sandbox only, no network."""

import os

for var in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
    assert "p4-sbx" in os.environ.get(var, ""), var

import numpy as np
import pandas as pd

from strategy_lab import observation as obs
from strategy_lab.candidates import RunnerSpec

DAY = 86_400
rng = np.random.default_rng(5)
closes = list(100 * np.exp(np.cumsum(rng.normal(0.002, 0.03, 500))))
t0 = pd.Timestamp("2023-01-01", tz="UTC")
frame = pd.DataFrame(
    {
        "open_time": [t0 + pd.Timedelta(days=i) for i in range(len(closes))],
        "open": [closes[0]] + closes[:-1],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": 100.0,
    }
)
snap = obs.snapshot(
    {
        "trading": {"mode": "paper"},
        "strategy": {"active_id": "STRAT-004", "timeframe": "1d"},
    },
    {"coins": ["AAA"]},
)
start = int(frame.open_time.iloc[60].timestamp())
end = int((frame.open_time.iloc[-1]).timestamp())
spec = obs.spec_of(snap)
trades = obs.replay_trades(spec, {"AAA": frame}, start, end)["AAA"]
print("replay trades:", len(trades), "last forced:", trades[-1].forced)
a, b, c = trades[0], trades[1], trades[-1]


def row(side, tag, ts, price, qty=1.0, fee_rate=0.005, sid="STRAT-004"):
    return {
        "ts": ts,
        "side": side,
        "tag": tag,
        "symbol": "AAA-USD",
        "qty": qty,
        "price": price,
        "fees_usd": price * qty * fee_rate,
        "strategy_id": sid,
    }


cases = {
    "1 duplicated entry (two ENTRY buys, one EXIT sell)": [
        row("buy", "ENTRY", a.entry_s + 30, a.entry_price),
        row("buy", "ENTRY", a.entry_s + 90, a.entry_price),
        row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price, qty=2.0),
    ],
    "2 entry 20 hours late, in the same candle": [
        row("buy", "ENTRY", a.entry_s + 20 * 3600, a.entry_price * 1.03),
        row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price),
    ],
    "3 exit fee 1.20% against entry fee 0.50%": [
        row("buy", "ENTRY", a.entry_s + 30, a.entry_price),
        row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price, fee_rate=0.012),
    ],
    "4 trade still open at reconcile (replay closes it at the last close)": [
        row("buy", "ENTRY", c.entry_s + 30, c.entry_price),
    ],
    "5 a row placed by another strategy (STRAT-001) on the replay's bar": [
        row("buy", "ENTRY", a.entry_s + 30, a.entry_price, sid="STRAT-001"),
        row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price, sid="STRAT-001"),
    ],
}
for name, rows in cases.items():
    out = obs.reconcile(
        {"started_s": start, "snapshot": snap}, rows, {"AAA": frame}, end
    )
    shown = [r for r in out if r.result != "missed"]
    print(f"\n{name}: {obs.summary(out)}")
    for r in shown:
        print(
            "  ",
            r.result,
            "fill_vs_open",
            None if r.fill_vs_open is None else round(r.fill_vs_open, 4),
            "fee_rate_paid",
            r.fee_rate_paid,
        )
    print(
        "   paper_trades():",
        [
            (p.entry_s - start, p.exit_s and p.exit_s - start, p.exit_fee)
            for p in obs.paper_trades(rows, start, end)
        ],
    )
