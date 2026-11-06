"""FDS-SIG-002 section 7 (and FDS-SIG-001 section 16 item 3): round one's candidates.

* CMF matches hand-worked values and an independent scalar reference at 1e-6, including
  H = L, a zero volume sum and a missing bar.
* The BTC lead abstains on a tie and on a missing BTC bar, and is never computed for BTC.
* No look-ahead: neither rule's call at t changes when bars after t are poisoned, and
  SIG-B reads BTC only from bars closed by t.
* The calls are deterministic, and the registration copies FDS-SIG-002 section 3's rules
  (inputs, parameters, thresholds, kind, warm-up, coins, BTC as the input coin).
* A row's pairs: the window's edges, gaps skipped and counted, ties counted.
"""

import os
import sys

import numpy as np
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from signal_audit import candidates as cd  # noqa: E402
from signal_audit import round_one as r1  # noqa: E402
from signal_audit import registration as reg  # noqa: E402
from signal_audit.pairs import row_pairs  # noqa: E402
from signal_audit.stats import ABSTAIN, DOWN, TWO_SIDED, UP  # noqa: E402

TOL = 1e-6
T0 = 1_767_225_600  # 2026-01-01 00:00 UTC


def bars(coin="ETH", tf="1h", n=200, seed=0, drop=(), start=T0):
    rng = np.random.default_rng(seed)
    step = cd.TIMEFRAME_SECONDS[tf]
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    vol = rng.uniform(1, 100, n)
    keep = np.array([i not in set(drop) for i in range(n)])
    return cd.Bars(
        coin,
        tf,
        (start + step * np.arange(n, dtype=np.int64))[keep],
        high[keep],
        low[keep],
        close[keep],
        vol[keep],
    )


def ref_cmf(h, lows, c, v):
    """The textbook Chaikin Money Flow over the given bars, written out."""
    num = 0.0
    den = 0.0
    for hi, lo, cl, vo in zip(h, lows, c, v):
        mfm = 0.0 if hi == lo else ((cl - lo) - (hi - cl)) / (hi - lo)
        num += mfm * vo
        den += vo
    return None if den == 0 else num / den


# --- SIG-A ----------------------------------------------------------------------------


def test_cmf_hand_worked():
    """20 bars, H = 10, L = 0: MFM = (2C - 10) / 10. Ten bars close at 8 (MFM 0.6) with
    volume 2, ten at 3 (MFM -0.4) with volume 1: CMF = (10 x 0.6 x 2 + 10 x -0.4 x 1) /
    (10 x 2 + 10 x 1) = (12 - 4) / 30 = 0.2666..."""
    n = 20
    b = cd.Bars(
        "ETH",
        "1h",
        T0 + 3600 * np.arange(n, dtype=np.int64),
        np.full(n, 10.0),
        np.zeros(n),
        np.array([8.0, 3.0] * 10),
        np.array([2.0, 1.0] * 10),
    )
    sig = r1.ChaikinMoneyFlowSign(20)
    assert abs(sig.value_at(b, 19) - 8.0 / 30.0) < TOL
    assert sig.call_at(b, {}, 19) == UP
    # the warm-up: no call before 19 earlier bars exist
    assert all(sig.call_at(b, {}, t) == ABSTAIN for t in range(19))
    # all closes at 3 instead: CMF = -0.4
    b2 = cd.Bars("ETH", "1h", b.open_s, b.high, b.low, np.full(n, 3.0), b.volume)
    assert abs(sig.value_at(b2, 19) + 0.4) < TOL and sig.call_at(b2, {}, 19) == DOWN


def test_cmf_matches_an_independent_reference():
    sig = r1.ChaikinMoneyFlowSign(20)
    for seed in range(5):
        b = bars(n=300, seed=seed)
        values = sig.cmf(b)
        for t in range(19, 300):
            want = ref_cmf(
                b.high[t - 19 : t + 1],
                b.low[t - 19 : t + 1],
                b.close[t - 19 : t + 1],
                b.volume[t - 19 : t + 1],
            )
            assert abs(values[t] - want) < TOL
            assert sig.call_at(b, {}, t) == (
                UP if want > 0 else DOWN if want < 0 else ABSTAIN
            )
        assert np.isnan(values[:19]).all()


def test_cmf_with_a_bar_whose_high_equals_its_low():
    b = bars(n=40, seed=3)
    b.high[25] = b.low[25] = b.close[25] = 100.0  # H = L: its MFM is 0
    sig = r1.ChaikinMoneyFlowSign(20)
    want = ref_cmf(b.high[11:31], b.low[11:31], b.close[11:31], b.volume[11:31])
    assert abs(sig.value_at(b, 30) - want) < TOL
    assert r1.ChaikinMoneyFlowSign.multiplier(5.0, 5.0, 5.0) == 0.0


def test_cmf_abstains_when_the_volume_sums_to_zero():
    b = bars(n=40, seed=4)
    b.volume[10:30] = 0.0
    sig = r1.ChaikinMoneyFlowSign(20)
    assert sig.value_at(b, 29) is None and sig.call_at(b, {}, 29) == ABSTAIN
    assert sig.call_at(b, {}, 30) != ABSTAIN  # bar 30 has volume again


def test_cmf_abstains_when_any_of_the_20_bars_is_missing():
    b = bars(n=60, seed=5, drop=(30,))  # the bar opening 30 hours in is missing
    sig = r1.ChaikinMoneyFlowSign(20)
    calls = sig.calls(b, {})
    opens = (b.open_s - T0) // 3600
    for t in range(len(b)):
        hour = int(opens[t])
        if 30 <= hour <= 30 + 19:  # any 20-bar window that would include hour 30
            assert calls[t] == ABSTAIN
        elif hour >= 19:
            assert calls[t] != ABSTAIN


def test_cmf_abstains_when_it_is_exactly_zero():
    n = 20
    b = cd.Bars(
        "ETH",
        "1h",
        T0 + 3600 * np.arange(n, dtype=np.int64),
        np.full(n, 10.0),
        np.zeros(n),
        np.full(n, 5.0),
        np.full(n, 7.0),
    )  # every close mid-range
    sig = r1.ChaikinMoneyFlowSign(20)
    assert sig.value_at(b, 19) == 0.0 and sig.call_at(b, {}, 19) == ABSTAIN


# --- SIG-B ----------------------------------------------------------------------------


def test_the_btc_lead_by_hand_and_its_abstentions():
    btc = cd.Bars(
        "BTC",
        "1h",
        T0 + 3600 * np.arange(6, dtype=np.int64),
        np.ones(6),
        np.ones(6),
        np.array([100, 101, 101, 99, 100, 100.5]),
        np.ones(6),
    )
    eth = bars(n=6, seed=6)
    lead = r1.BtcOneBarLead()
    calls = lead.calls(eth, {"BTC": btc})
    # t=0: no BTC bar t-1; t=1: up; t=2: equal (tie); t=3: down; t=4: up; t=5: up
    assert calls.tolist() == [ABSTAIN, UP, ABSTAIN, DOWN, UP, UP]
    assert [lead.call_at(eth, {"BTC": btc}, t) for t in range(6)] == calls.tolist()


def test_the_btc_lead_abstains_on_a_missing_btc_bar():
    btc = bars("BTC", n=50, seed=7, drop=(20,))
    eth = bars(n=50, seed=8)
    lead = r1.BtcOneBarLead()
    calls = lead.calls(eth, {"BTC": btc})
    assert calls[20] == ABSTAIN  # BTC's bar t is missing
    assert calls[21] == ABSTAIN  # BTC's bar t - 1 is missing
    assert calls[19] != ABSTAIN and calls[22] != ABSTAIN


def test_the_btc_lead_is_never_computed_for_btc():
    lead = r1.BtcOneBarLead()
    assert not lead.runs_on("BTC") and lead.runs_on("ETH")
    btc = bars("BTC", n=10)
    with pytest.raises(ValueError, match="never computed for BTC"):
        lead.calls(btc, {"BTC": btc})
    rows = reg.family_rows(r1.candidates(), ["BTC", "ETH", "SOL"], ("1h", "4h"), "x")
    assert not [r for r in rows if r.candidate == "SIG-B" and r.coin == "BTC"]


# --- no look-ahead (FDS-SIG-001 section 16 item 3) -------------------------------------


def _poisoned(b: cd.Bars, after: int) -> cd.Bars:
    """``b`` with every bar after position ``after`` replaced by nonsense."""
    h, l, c, v = b.high.copy(), b.low.copy(), b.close.copy(), b.volume.copy()
    h[after + 1 :] = 1e12
    l[after + 1 :] = -1e12
    c[after + 1 :] = 7e11
    v[after + 1 :] = 1e15
    return cd.Bars(b.coin, b.timeframe, b.open_s, h, l, c, v)


@pytest.mark.parametrize("tf", ["1h", "4h"])
def test_no_rule_reads_a_bar_after_t(tf):
    eth = bars("ETH", tf, n=120, seed=9)
    btc = bars("BTC", tf, n=120, seed=10)
    for cand in r1.candidates():
        full = cand.calls(eth, {"BTC": btc})
        for t in range(0, 120, 7):
            poisoned = cand.calls(_poisoned(eth, t), {"BTC": _poisoned(btc, t)})
            assert poisoned[t] == full[t], (cand.key, t)
            # and with nothing after t at all
            cut = cand.calls(eth.upto(t), {"BTC": btc.upto(t)})
            assert cut[t] == full[t], (cand.key, t)


def test_sig_b_reads_btc_only_from_bars_closed_by_t():
    """BTC's bar t closes when the coin's bar t does: a BTC bar opening after it never
    changes the call."""
    eth = bars("ETH", n=50, seed=11)
    btc = bars("BTC", n=50, seed=12)
    lead = r1.BtcOneBarLead()
    base = lead.calls(eth, {"BTC": btc})
    for t in range(1, 49):
        later = cd.Bars(
            "BTC", "1h", btc.open_s, btc.high, btc.low, btc.close.copy(), btc.volume
        )
        later.close[t + 1 :] = later.close[t + 1 :] * 3.7
        assert lead.calls(eth, {"BTC": later})[t] == base[t]


def test_the_calls_are_deterministic():
    eth = bars(n=300, seed=13)
    btc = bars("BTC", n=300, seed=14)
    for cand in r1.candidates():
        a = cand.calls(eth, {"BTC": btc})
        b = cand.calls(eth, {"BTC": btc})
        assert np.array_equal(a, b)


# --- the registration -------------------------------------------------------------------


def test_the_registration_copies_fds_sig_002_section_3():
    a, b = r1.candidates()
    ra, rb = a.registration(), b.registration()
    assert ra["key"] == "SIG-A" and ra["kind"] == TWO_SIDED and ra["warmup_bars"] == 19
    assert ra["parameters"] == {"length": 20}
    for text in (
        "MFM_i = ((C_i - L_i) - (H_i - C_i)) / (H_i - L_i)",
        "MFM_i = 0 when H_i = L_i",
        "Up if CMF_t > 0",
        "down if CMF_t < 0",
        "abstain if CMF_t = 0",
        "if sum(V_i) = 0",
        "if any of the 20 bars is missing",
    ):
        assert text in ra["rule"]
    assert "high H, low L, close C and base-asset volume V" in ra["inputs"]
    assert ra["coins"] == "all audited coins"
    assert rb["key"] == "SIG-B" and rb["kind"] == TWO_SIDED and rb["warmup_bars"] == 1
    assert (
        rb["input_coins"] == ["BTC"] and rb["coins"] == "every audited coin except BTC"
    )
    for text in (
        "up if BTC close[t] > BTC close[t - 1]",
        "down if BTC close[t] < BTC close[t - 1]",
        "abstain if they are equal",
        "if BTC's bar t or t - 1 is missing",
    ):
        assert text in rb["rule"]


def test_the_family_size_as_fds_sig_002_section_3_3():
    ten = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "LINK", "AVAX"]
    rows = reg.family_rows(r1.candidates(), ten, ("1h", "4h"), "x")
    assert reg.family_size(rows) == 76  # (10 + 9) x 2 x 2
    no_btc = [c for c in ten if c != "BTC"] + ["LTC"]
    assert (
        reg.family_size(reg.family_rows(r1.candidates(), no_btc, ("1h", "4h"), "x"))
        == 80
    )


# --- pairs ------------------------------------------------------------------------------


def test_a_rows_pairs_counts_gaps_and_ties():
    n = 60
    b = bars(n=n, seed=15, drop=(30,))
    b.close[b.open_s == T0 + 3600 * 40] = b.close[b.open_s == T0 + 3600 * 39]  # a tie
    start = T0 + 3600 * 20
    end = T0 + 3600 * 50  # the close time of the last outcome bar (opening at 49)
    rp = row_pairs(cd.Constant(UP), b, {}, start, end)
    # pairs (t, t+1) with t opening at 20 .. 48: 29 pairs on the grid
    assert rp.window_pairs == 29
    # bar 30 missing: pairs (29, 30) and (30, 31) are skipped
    assert rp.skipped == 2 and rp.missing_bars == 1
    assert rp.ties == 1
    assert rp.eligible == 29 - 2 - 1
    assert rp.open_s[0] == start and rp.open_s[-1] == T0 + 3600 * 48
    i = list(rp.open_s).index(T0 + 3600 * 25)
    c0 = b.close[b.open_s == T0 + 3600 * 25][0]
    c1 = b.close[b.open_s == T0 + 3600 * 26][0]
    assert abs(rp.pairs.ret[i] - (c1 / c0 - 1)) < 1e-15 and rp.pairs.up[i] == int(
        c1 > c0
    )
