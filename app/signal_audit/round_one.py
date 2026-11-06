"""
Round one's candidates (FDS-SIG-002 section 3), copied verbatim into its registration.

* **SIG-A**, the Chaikin Money Flow sign over 20 bars, on the coin's own high, low, close
  and base-asset volume, same timeframe. MFM_i = ((C_i - L_i) - (H_i - C_i)) / (H_i - L_i),
  0 when H_i = L_i; CMF_t = sum(MFM_i V_i) / sum(V_i) over the 20 bars t - 19 .. t. Up if
  CMF_t > 0, down if CMF_t < 0; abstain if CMF_t = 0, if sum(V_i) = 0, or if any of the 20
  bars is missing. Two-sided; warm-up 19 bars; all audited coins.
* **SIG-B**, the BTC one-bar lead, on BTC's close, same timeframe (BTC is an input
  coin). Up if BTC close[t] > BTC close[t - 1], down if lower; abstain if equal, or if
  BTC's bar t or t - 1 is missing. Two-sided; warm-up 1 bar; every audited coin except
  BTC, on which it would be BTC's own one-bar momentum, a different candidate.

Both call at the close of bar t from closed bars only, and read only the eligible inputs
of FDS-SIG-001 section 4: the OHLCV and base-asset volume of coins the round fetches and
hashes. Neither is wired to any strategy or trade (FDS-SIG-001 section 14).
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

import numpy as np

from signal_audit.candidates import Bars, Candidate, run_ending_at
from signal_audit.stats import ABSTAIN, DOWN, TWO_SIDED, UP

INPUT_COIN = "BTC"  # SIG-B's input coin (FDS-SIG-002 section 3.2)


class ChaikinMoneyFlowSign(Candidate):
    key = "SIG-A"
    name = "Chaikin Money Flow sign, 20 bars"
    kind = TWO_SIDED
    inputs = (
        "the coin's own high H, low L, close C and base-asset volume V, on the same "
        "timeframe"
    )

    def __init__(self, length: int = 20):
        self.length = int(length)
        self.warmup = self.length - 1
        self.parameters = {"length": self.length}
        self.rule = (
            "MFM_i = ((C_i - L_i) - (H_i - C_i)) / (H_i - L_i), with MFM_i = 0 when "
            f"H_i = L_i; CMF_t = sum(MFM_i x V_i) / sum(V_i), both sums over the "
            f"{self.length} bars i = t - {self.length - 1} .. t. Up if CMF_t > 0; down if "
            f"CMF_t < 0; abstain if CMF_t = 0, if sum(V_i) = 0, or if any of the "
            f"{self.length} bars is missing"
        )

    @staticmethod
    def multiplier(high: float, low: float, close: float) -> float:
        """MFM = ((C - L) - (H - C)) / (H - L), 0 when H = L."""
        if high == low:
            return 0.0
        return ((close - low) - (high - close)) / (high - low)

    def value_at(self, bars: Bars, t: int) -> Optional[float]:
        """CMF_t from the bars up to t only, or None where the rule abstains for want
        of data (a bar of the 20 missing, or their volumes summing to 0). The sums are
        exactly rounded (``math.fsum``), so CMF_t = 0 is decided the same way
        whatever order the bars are added in."""
        import math

        if not run_ending_at(bars, t, self.length):
            return None
        lo = t - self.length + 1
        flows = []
        volumes = []
        for i in range(lo, t + 1):
            h, l, c, v = (
                float(bars.high[i]),
                float(bars.low[i]),
                float(bars.close[i]),
                float(bars.volume[i]),
            )
            flows.append(self.multiplier(h, l, c) * v)
            volumes.append(v)
        total_v = math.fsum(volumes)
        if total_v == 0.0:
            return None
        return math.fsum(flows) / total_v

    def cmf(self, bars: Bars) -> np.ndarray:
        """CMF_t at every bar (NaN where the rule abstains for want of data)."""
        out = np.full(len(bars), np.nan)
        for t in range(len(bars)):
            v = self.value_at(bars, t)
            if v is not None:
                out[t] = v
        return out

    def call_at(self, bars: Bars, inputs: Mapping[str, Bars], t: int) -> int:
        value = self.value_at(bars, t)
        if value is None:
            return ABSTAIN
        return UP if value > 0 else DOWN if value < 0 else ABSTAIN


class BtcOneBarLead(Candidate):
    key = "SIG-B"
    name = "BTC one-bar lead"
    kind = TWO_SIDED
    warmup = 1
    input_coins = (INPUT_COIN,)
    inputs = (
        "BTC's close on the same timeframe (BTC is an input coin, fetched and hashed "
        "whether or not it is audited)"
    )
    parameters: Mapping[str, Any] = {"lag_bars": 1}
    rule = (
        "for an audited coin other than BTC: up if BTC close[t] > BTC close[t - 1]; down "
        "if BTC close[t] < BTC close[t - 1]; abstain if they are equal, or if BTC's bar t "
        "or t - 1 is missing. BTC's bar t closes at the same moment as the coin's bar t"
    )
    coins_text = "every audited coin except BTC"

    def runs_on(self, coin: str) -> bool:
        return coin.upper() != INPUT_COIN

    def _btc(self, bars: Bars, inputs: Mapping[str, Bars]) -> Bars:
        if not self.runs_on(bars.coin):
            raise ValueError("SIG-B is never computed for BTC itself")
        btc = inputs.get(INPUT_COIN)
        if btc is None or btc.timeframe != bars.timeframe:
            raise ValueError("SIG-B needs BTC's bars on the same timeframe")
        return btc

    def calls(self, bars: Bars, inputs: Mapping[str, Bars]) -> np.ndarray:
        btc = self._btc(bars, inputs)
        step = bars.step
        k = np.searchsorted(btc.open_s, bars.open_s)
        k_prev = np.searchsorted(btc.open_s, bars.open_s - step)
        n = len(btc)
        have = (
            (k < n) & (btc.open_s[np.minimum(k, n - 1)] == bars.open_s)
            if n
            else (np.zeros(len(bars), dtype=bool))
        )
        have_prev = (
            (k_prev < n) & (btc.open_s[np.minimum(k_prev, n - 1)] == bars.open_s - step)
            if n
            else np.zeros(len(bars), dtype=bool)
        )
        out = np.full(len(bars), ABSTAIN, dtype=np.int8)
        ok = have & have_prev
        now = btc.close[np.minimum(k, n - 1)] if n else np.zeros(len(bars))
        before = btc.close[np.minimum(k_prev, n - 1)] if n else np.zeros(len(bars))
        out[ok & (now > before)] = UP
        out[ok & (now < before)] = DOWN
        return out

    def call_at(self, bars: Bars, inputs: Mapping[str, Bars], t: int) -> int:
        btc = self._btc(bars, inputs)
        at = int(bars.open_s[t])
        i = btc.index_at(at)
        j = btc.index_at(at - bars.step)
        if i < 0 or j < 0:
            return ABSTAIN
        now, before = float(btc.close[i]), float(btc.close[j])
        return UP if now > before else DOWN if now < before else ABSTAIN


def candidates() -> List[Candidate]:
    """FDS-SIG-002 section 3's candidates, in its order."""
    return [ChaikinMoneyFlowSign(20), BtcOneBarLead()]


def by_key() -> dict:
    return {c.key: c for c in candidates()}
