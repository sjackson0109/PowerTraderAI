"""SignalEngine with STRAT-004 at its defaults on synthetic daily bars, when the
exchange publishes the just-closed daily bar a few seconds late. Sandbox only, no
network: the candle provider is a function over a synthetic frame."""

import os

for var in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
    assert "p4-sbx" in os.environ.get(var, ""), var

import pandas as pd

from signal_engine import SignalEngine
from strategies.factory import build_runner

DAY = pd.Timedelta(days=1)
closes = (
    [100.0] * 70 + [101.0, 100.5] + [100.4] * 8
)  # bar 70: a new 55-day closing high
rows = []
t0 = pd.Timestamp("2024-01-01", tz="UTC")
for i, c in enumerate(closes):
    o = closes[i - 1] if i else c
    rows.append(
        {
            "open_time": t0 + i * DAY,
            "open": o,
            "high": max(o, c) * 1.001,
            "low": min(o, c) * 0.999,
            "close": c,
            "volume": 100.0,
        }
    )
frame = pd.DataFrame(rows)

replay = build_runner("STRAT-004")
replay.set_timeframe(86_400)
for k in (70, 71):
    d = replay.evaluate(replay.window(frame, k), None, "BTC")
    print(f"replay bar {k} ({frame.open_time[k].date()}): {d.action.value} {d.reason}")


class LateFeed:
    """Closed bars only; the bar that closed at the latest boundary is held back for
    the first ``late_s`` seconds after it closes (the exchange has not published it)."""

    def __init__(self, late_s):
        self.now = 0.0
        self.late_s = late_s
        self.calls = []

    def clock(self):
        return self.now

    def provider(self, symbol, tf, n, now):
        cutoff = now - pd.Timedelta(seconds=self.late_s)
        closed = frame[frame["open_time"] + DAY <= cutoff]
        self.calls.append((now, closed["open_time"].iloc[-1]))
        return closed.tail(n).reset_index(drop=True)


for late_s in (0, 5):
    feed = LateFeed(late_s)
    engine = SignalEngine(
        {"strategy": {"active_id": "STRAT-004", "timeframe": "1d"}},
        feed.provider,
        feed.clock,
    )
    close70 = (frame.open_time[70] + DAY).timestamp()
    seen = []
    # the trader asks every pass: 1 s after the close, then every 10 minutes for a day
    for offset in [1] + list(range(600, 86_400 + 1, 600)):
        feed.now = close70 + offset
        d = engine.decide("BTC", None)
        seen.append((offset, d.bar_time.date(), d.action.value, d.reason))
    first = seen[0]
    last = seen[-1]
    enters = [s for s in seen if s[2] == "ENTER_LONG"]
    print(
        f"\nexchange {late_s} s late: provider calls {len(feed.calls)}; "
        f"first decision {first}; last {last}; ENTER_LONG decisions {len(enters)}"
    )
    days = sorted({s[1] for s in seen})
    print("  bars decided on:", [str(x) for x in days])


class OnceLateFeed(LateFeed):
    """Late only for the bar that closed at ``late_boundary``; on time otherwise."""

    def __init__(self, late_s, late_boundary):
        super().__init__(late_s)
        self.late_boundary = late_boundary

    def provider(self, symbol, tf, n, now):
        late = (
            self.late_boundary
            <= now
            < self.late_boundary + pd.Timedelta(seconds=self.late_s)
        )
        cutoff = now - pd.Timedelta(seconds=self.late_s if late else 0)
        closed = frame[frame["open_time"] + DAY <= cutoff]
        self.calls.append((now, closed["open_time"].iloc[-1]))
        return closed.tail(n).reset_index(drop=True)


boundary = frame.open_time[70] + DAY
feed = OnceLateFeed(5, boundary)
engine = SignalEngine(
    {"strategy": {"active_id": "STRAT-004", "timeframe": "1d"}},
    feed.provider,
    feed.clock,
)
seen = []
for offset in [1] + list(range(600, 2 * 86_400 + 1, 600)):
    feed.now = boundary.timestamp() + offset
    d = engine.decide("BTC", None)
    seen.append((d.bar_time.date(), d.action.value))
print("\nlate once, at the close of bar 70 only:")
print("  bars decided on:", sorted({str(s[0]) for s in seen}))
print("  ENTER_LONG decisions:", sum(1 for s in seen if s[1] == "ENTER_LONG"))
