"""FDS-SR-001 milestone M5c: E1's declaration and the rules it runs by (sections 6.0 to
6.6, decisions E-D5, E-D6, E-D10 and E-D11).

* The declaration: three families of 4, 3 and 2 members, each corrected on its own; seed
  ranges that never overlap; no variant breaks a parameter rule; it freezes and verifies.
* The candles: nothing opening on or after 2025-05-06 is read; each coin starts at
  2020-01-01 or its first cached bar; each series is read once; a coin with no bars is
  left out with its reason.
* The rules: the block length (L = 28 x 2^k); the gate as a veto on the strategy's own
  trades, which keeps every trade it allows unchanged and replays like the gated runner;
  REF-RANDOM and R3 draws that repeat for a seed.
* The figures: per coin and per half they add up; a small account's entries are raised.
* The words: only an economic line says "profitable"; every line ends "Development only".

Synthetic candles only: no network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from helpers import make_candles

from signal_fusion.evaluation.replay import Account, Costs
from strategy_lab import e1
from strategy_lab import experiment as ex
from strategy_lab.candidates import RunnerSpec
from strategy_lab.simulate import Simulation, Universe
from strategy_lab.windows import ReservedPeriod

DAY, HOUR = 86_400, 3_600
ZERO = Costs(fee=0.0, allowance=0.0)
COSTS = Costs(fee=0.005, allowance=0.0005, minimum_usd={"X": 10.0, "Y": 10.0})


def waves(n, period=12.0, drift=0.15, amp=30.0, phase=0.0):
    i = np.arange(n)
    return list(np.maximum(100 + amp * np.sin(i / period + phase) + drift * i, 5.0))


def btc_daily():
    """Up for 300 days, down for 120 (below its 200-day average from about day 330),
    then up again: from 2020-01-01 to the development end."""
    n = (e1.DEV_END - pd.Timestamp("2020-01-01", tz="UTC")).days
    up = np.linspace(100, 300, 300)
    down = np.linspace(300, 150, 120)
    again = np.linspace(150, 600, n - 420)
    return make_candles(
        list(np.r_[up, down, again]), start="2020-01-01", tf_seconds=DAY
    )


def daily_universe(coins=("X", "Y")):
    n = (e1.DEV_END - pd.Timestamp("2020-01-01", tz="UTC")).days
    frames = {
        c: make_candles(
            waves(n, period=9.0 + k, phase=k), start="2020-01-01", tf_seconds=DAY
        )
        for k, c in enumerate(coins)
    }
    return Universe("1d", frames, shared={("BTC", "1d"): btc_daily()})


def gated(spec: RunnerSpec) -> RunnerSpec:
    return RunnerSpec(spec.strategy_id, dict(spec.params), (e1.GATE,), spec.timeframe)


class TestDeclaration:
    def test_three_families_of_four_three_and_two(self):
        e1.check_declaration()
        sizes = {f: sum(m.family == f for m in e1.MEMBERS) for f in "SGM"}
        assert sizes == {"S": 4, "G": 3, "M": 2}
        assert {f: k for f, (_n, k) in e1.FAMILIES.items()} == sizes
        assert [m.id for m in e1.MEMBERS] == [
            "S1", "S2", "S3", "S4", "G1", "G2", "G3", "M1", "M2",
        ]  # fmt: skip
        gate = {m.strategy for m in e1.MEMBERS if m.family == "G"}
        assert gate == {"STRAT-001", "STRAT-004", "STRAT-005"}
        assert {m.layer for m in e1.MEMBERS if m.family == "M"} == {e1.MODEL_PV}
        assert e1.STRATEGIES["STRAT-004"].timeframe == "1d"
        assert e1.STRATEGIES["STRAT-001"].timeframe == "1h"

    def test_overlapping_seed_ranges_are_refused(self, monkeypatch):
        spans = e1.seed_ranges()
        assert spans["S1"] == (910_000, 919_999)  # 10 runs of 1,000 draws
        assert spans["G1"] == (960_000, 960_009)  # 10 runs
        monkeypatch.setitem(e1.SHOWN_SEEDS, "random STRAT-000", 915_000)
        with pytest.raises(e1.E1Error, match="overlap"):
            e1.check_declaration()

    def test_it_freezes_and_verifies(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ex, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
        record = e1.declaration(
            rate={"gbp_usd": 1.3476, "source": "test"},
            venue={"minimum_usd": {"BTC": 1.0}, "base_increment": {"BTC": 1e-8}},
            series_sha256={"BTC:1d": "aa"},
            coins_kept=["BTC"],
            left_out={"BNB": "no bars"},
            exchange_order=["coinbase", "kraken"],
            listed_by_2021=["BTC"],
            probabilities_sha256=e1.MODEL_SHA256,
            served_by={"BTC:1d": "coinbase"},
        )
        assert record["market"]["served_by"] == {"BTC:1d": "coinbase"}
        frozen = ex.freeze(e1.EXPERIMENT_ID, record)
        assert (
            ex.verify(e1.EXPERIMENT_ID, {"BTC:1d": "aa"})["sha256"] == frozen["sha256"]
        )
        assert [frozen["family"][f]["k"] for f in "SGM"] == [4, 3, 2]
        assert frozen["accounts"]["usd"] == {
            "10000.0": 13476.0, "500.0": 673.8, "50.0": 67.38,
        }  # fmt: skip
        maker = frozen["costs"]["scenarios"][1]
        assert maker["fee"] == 0.006 and "market orders" in maker["note"]
        assert frozen["windows"]["lockbox_read"] is False
        with pytest.raises(ex.ExperimentError, match="candles changed"):
            ex.verify(e1.EXPERIMENT_ID, {"BTC:1d": "bb"})


class TestCandles:
    def setup_method(self):
        self.calls = []

        def base(symbol, tf, a, b, cache_dir=None, offline=True):
            self.calls.append((symbol, tf, a, b))
            n = int((b - a) / pd.Timedelta(days=1))
            return make_candles([100.0] * n, start=str(a.date()), tf_seconds=DAY)

        def first(symbol, tf):
            if symbol == "BNB-USD":
                return None
            if symbol == "ADA-USD":
                return pd.Timestamp("2021-03-19", tz="UTC")
            return pd.Timestamp("2020-01-01", tz="UTC")

        self.load = e1.development_loader(base, first)

    def test_nothing_from_the_reserved_months(self):
        with pytest.raises(ReservedPeriod):
            self.load("BTC-USD", "1d", "2020-01-01", "2025-05-07")

        def leaky(symbol, tf, a, b, **_kw):
            return make_candles([1.0, 1.0], start="2025-05-05", tf_seconds=DAY)

        with pytest.raises(ReservedPeriod, match="reserved months"):
            e1.development_loader(leaky, lambda s, tf: e1.HISTORY_START)(
                "BTC-USD", "1d", "2020-01-01", e1.DEV_END
            )

    def test_each_coin_from_its_first_bar_read_once(self):
        frame = self.load("ADA-USD", "1d", "2019-06-01", e1.DEV_END)
        assert self.calls[-1][2] == pd.Timestamp("2021-03-19", tz="UTC")
        assert frame["open_time"].max() < e1.DEV_END
        self.load("ADA-USD", "1d", "2019-06-01", e1.DEV_END)
        assert len(self.calls) == 1
        self.load("BTC-USD", "1d", "2019-06-01", e1.DEV_END)
        assert self.calls[-1][2] == pd.Timestamp("2020-01-01", tz="UTC")

    def test_the_exchanges_are_the_candle_loaders_in_settings_order(self, monkeypatch):
        import market_data.candles as candles

        class Manager:
            def exchange_names(self):
                return ["second", "first"]

        monkeypatch.setattr(candles, "_exchange_manager", lambda: Manager())
        e1.settings_exchanges.cache_clear()
        try:
            assert e1.settings_exchanges() == ("second", "first")
        finally:
            e1.settings_exchanges.cache_clear()

    def test_a_coin_without_bars_is_left_out_with_the_reason(self):
        u, left = e1.development_universe(["BTC", "ADA", "BNB"], "1d", self.load)
        assert sorted(u.frames) == ["ADA", "BTC"]
        assert "no cached bars" in left["BNB"]
        assert ("BTC", "1d") in u.shared  # the gate's context
        sha = e1.universe_sha256(u)
        assert set(sha) == {"ADA:1d", "BTC:1d"} and all(
            len(v) == 64 for v in sha.values()
        )


class TestRules:
    def test_the_block_length(self):
        assert e1.block_length([]) == 28
        assert e1.block_length([1.0] * 100) == 28
        assert e1.block_length([1.0] * 99 + [15.0]) == 28  # 1% may be longer than L/2
        assert e1.block_length([1.0] * 98 + [15.0] * 2) == 56
        assert e1.block_length([1.0] * 90 + [60.0] * 10) == 224

    def test_the_gate_vetoes_trades_and_keeps_the_rest_unchanged(self):
        u = daily_universe()
        spec = e1.STRATEGIES["STRAT-004"]
        sim, gsim = Simulation(u, spec), Simulation(u, gated(spec))
        plain = e1.scored(sim)
        filt = e1.gate_filter(plain, gsim)
        assert 0 < filt.veto.sum() < len(plain)
        acct = Account(start=10_000.0)
        a = sim.replay(plain, COSTS, acct, veto=filt.veto[None, :], detail=True)
        b = gsim.replay(e1.scored(gsim), COSTS, acct, detail=True)
        assert a.trades[0] == b.trades[0] > 0
        assert a.net[0] == pytest.approx(b.net[0])

    def test_the_gate_on_an_hourly_strategy(self):
        n = 4400  # 2020-12-01 to mid-2021: the reference falls below its average first
        frame = make_candles(waves(n, period=7.0), start="2020-12-01", tf_seconds=HOUR)
        u = Universe("1h", {"X": frame}, shared={("BTC", "1d"): btc_daily()})
        spec = e1.STRATEGIES["STRAT-001"]
        plain = e1.scored(Simulation(u, spec))
        filt = e1.gate_filter(plain, Simulation(u, gated(spec)))
        assert len(plain) > 0 and filt.veto.any()

    def test_the_draws_repeat_for_a_seed(self):
        u = daily_universe()
        spec = e1.STRATEGIES["STRAT-004"]
        sim = Simulation(u, spec)
        trades = e1.scored(sim)
        acct = Account(start=10_000.0)
        path = sim.replay(trades, COSTS, acct, detail=True)
        one = e1.random_test(sim, trades, path, COSTS, acct, 5_000, 5, 4)
        two = e1.random_test(sim, trades, path, COSTS, acct, 5_000, 5, 4)
        assert one["draws"] == e1.RUNS * 5 and len(one["runs"]) == e1.RUNS
        assert (one["p"], one["median"]) == (two["p"], two["median"])
        assert 0 < one["p"] <= 1
        filt = e1.gate_filter(trades, Simulation(u, gated(spec)))
        r, gpath = e1.r3_test(sim, trades, filt, COSTS, acct, 6_000, 5, 3)
        again, _ = e1.r3_test(sim, trades, filt, COSTS, acct, 6_000, 5, 3)
        assert r["assessable"] and r["vetoed"] > 0
        assert sum(r["veto_counts"].values()) == r["vetoed"]
        assert (r["p"], r["median"]) == (again["p"], again["median"])
        econ = e1.economic_test(path, trades, 7_000, 28, 4)
        assert set(econ["requirements"]) == {
            "trades", "profit", "stable", "not_one_coin", "within_halt",
        }  # fmt: skip
        assert np.isfinite(econ["smallest_detectable"])


class TestFigures:
    def test_they_add_up_and_a_small_account_is_raised(self):
        u = daily_universe()
        sim = Simulation(u, e1.STRATEGIES["STRAT-004"])
        trades = e1.scored(sim)
        small = Account(start=67.38)
        path = sim.replay(trades, COSTS, small, detail=True)
        regimes = e1.Regimes({**u.frames, "BTC": u.shared[("BTC", "1d")]})
        f = e1.figures(trades, path, COSTS, small, 1.3476, regimes)
        assert f["trades"] == sum(f["trades_by_half"]) > 0
        assert sum(c["net_usd"] for c in f["by_coin"].values()) == pytest.approx(
            f["net_usd"]
        )
        assert f["net_gbp"] == pytest.approx(f["net_usd"] / 1.3476)
        assert f["entries_raised_to_minimum"] > 0  # 1% of $67 is below the minimum
        trend = f["by_regime"]["btc_trend"]
        assert set(trend) <= {"above", "below", "unknown"}
        assert sum(c["trades"] for c in trend.values()) == f["trades"]

    def test_the_regime_tags(self):
        closes = [100.0] * 250 + [200.0] * 10
        btc = make_candles(closes, start="2020-01-01", tf_seconds=DAY)
        r = e1.Regimes({"BTC": btc})
        t = int(
            (pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=255)).timestamp()
        )
        trade = e1.Trade("BTC", 0, 1, 2, t, t + DAY, 200.0, 200.0, "strategy", False)
        tags = r.tags(trade)
        assert tags["btc_trend"] == "above" and tags["btc_average"] == "rising"
        assert tags["year"] == "2020"

    def test_auc(self):
        assert e1.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)
        assert e1.auc([0.5, 0.5], [1, 1]) is None


class TestWords:
    def member(self, mid):
        return next(m for m in e1.MEMBERS if m.id == mid)

    def trading(self, **kw):
        r = {
            "assessable": True, "value": 0.0004, "median": -0.0002, "p": 0.01,
            "draws": 10_000, "trades": 150, "too_few": False,
            "smallest_detectable": 0.0001, "net_usd": 120.0,
        }  # fmt: skip
        r.update(kw)
        return r

    def economic(self, trades=150, half=(70, 80)):
        return {
            "requirements": {"trades": trades >= 100 and min(half) >= 30},
            "test": {"p": 0.03},
            "report": {
                "net_usd": 250.0, "rpcd": 0.0003, "trades": trades,
                "trades_by_half": list(half), "max_drawdown": 0.02,
            },
            "smallest_detectable": 0.0002,
            "failed": "a profit in each half",
        }  # fmt: skip

    def test_only_an_economic_line_says_profitable(self):
        lines = [
            e1.member_line(self.member("S1"), self.trading(), True),
            e1.member_line(self.member("S1"), self.trading(p=0.4), False),
            e1.member_line(self.member("S1"), self.trading(p=0.4, too_few=True), False),
            e1.member_line(self.member("G1"), self.trading(net_usd=-50.0), True),
            e1.member_line(self.member("M1"), self.trading(p=0.6), False),
        ]
        assert lines[0].startswith("Beats random entries")
        assert lines[1].startswith("No better than random entries")
        assert lines[2].startswith("Too few trades to tell")
        assert lines[3].startswith("The gate adds value over random vetoes")
        assert "still loses money" in lines[3]
        assert lines[4].startswith("No better than random vetoes")
        for line in lines:
            assert "profitable" not in line.lower()
            assert line.endswith(e1.DEV_ONLY)
        win = e1.member_line(self.member("S3"), self.economic(), True)
        lose = e1.member_line(self.member("S3"), self.economic(), False)
        few = e1.member_line(self.member("S4"), self.economic(80, (50, 30)), False)
        assert win.startswith("Profitable after fees at £10,000")
        assert lose.startswith(
            "Not shown to be profitable after fees: a profit in each half"
        )
        assert few.startswith("Not assessable: 80 trades")
        assert all(x.endswith(e1.DEV_ONLY) for x in (win, lose, few))
