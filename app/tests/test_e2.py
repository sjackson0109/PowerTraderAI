"""SR1-E2: the registered development evaluation of the Donchian ensemble, as the owner
approved it on 2026-11-14 (decisions D1 to D5 of its registration draft).

* The declaration: one family, B, of 2 members (Holm at 5%); its hash is fixed, so a
  changed member, seed or rule is refused; seed ranges never overlap; it freezes with
  the code files it runs (the ensemble, STRAT-007, the sizing, the gap rule and the
  statistics) and the earlier exposures, and the evidence writer refuses once the code
  changes.
* The candles: nothing opening on or after 2025-05-06 is read; the second exchange's
  run reads that exchange's cache only; a coin with no bars is left out with its reason.
* F3 for a book: halves by entry day; the total without the most profitable coin sums
  every member's trades on that coin; the drawdown requirement (D1) compares the book's
  drawdown with the equal-weight hold's, both at the bars' lows from the earlier highs.
* The hold comparison: ten seeded runs of ``mean_test``, pooled (a stand-in here until
  ``research_stats.resampling.mean_test`` is in the tree).
* The words: only the economic line says "profitable"; every line ends "Development
  only"; the halt is reported, and the line says trading the book would need it changed.
* Each scored cell is logged in the strategy lab's trial log and the programme ledger.

Synthetic candles only: no network."""

from __future__ import annotations

import json
import os
from collections import namedtuple

import numpy as np
import pandas as pd
import pytest
from helpers import make_candles

from signal_fusion.evaluation.replay import Paths
from strategy_lab import e1, e2, ensemble
from strategy_lab import evidence as ev
from strategy_lab import experiment as ex
from strategy_lab.candidates import Trade
from strategy_lab.windows import ReservedPeriod

DAY = 86_400
FIRST_DAY = e2.DEV_START_S // DAY
LAST_DAY = e2.LAST_S // DAY
MIDDLE_DAY = FIRST_DAY + (LAST_DAY - FIRST_DAY + 1) // 2
REPO = os.path.join(os.path.dirname(__file__), "..", "..")
EXPOSURE_LOG = os.path.join(REPO, "docs", "dev", "compare-ensemble", "trials.jsonl")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
    return tmp_path / "strategy_lab"


def record_for_test():
    return e2.declaration(
        rate={"gbp_usd": 1.3476, "source": "test"},
        venue={"minimum_usd": {"BTC": 1.0}, "base_increment": {"BTC": 1e-8}},
        series_sha256={"BTC:1d": "aa"},
        coins_kept=["BTC"],
        left_out={"HYPE": "no bars"},
        exchange_order=["coinbase", "kraken", "kucoin"],
        listed_by_2021=["BTC"],
        served_by={"BTC:1d": "coinbase"},
        exposures=e2.exposures_record(EXPOSURE_LOG),
        second={"exchange": "kraken", "coins": [], "left_out": {"BTC": "no bars"}},
    )


# --- the declaration --------------------------------------------------------------------


class TestDeclaration:
    def test_one_family_of_two(self):
        e2.check_declaration()
        assert e2.EXPERIMENT_ID == "SR1-E2" and e2.APPROVED == "2026-11-14"
        assert [m.id for m in e2.MEMBERS] == ["B1", "B2"]
        assert [m.test for m in e2.MEMBERS] == ["random", "economic"]
        assert {m.family for m in e2.MEMBERS} == {"B"} and e2.K == 2
        assert e2.COINS == (
            "BTC", "ETH", "XRP", "BNB", "DOGE", "SOL", "ZEC", "DASH", "HYPE",
        )  # fmt: skip
        assert tuple(e2.design()["lookbacks"]) == ensemble.LOOKBACKS
        assert (e2.RUNS, e2.PER_RUN, e2.BOOTSTRAP_DRAWS) == (10, 200, 2000)
        assert e2.TARGETS == (0.25, 0.50, 0.75)

    def test_the_declarations_hash_is_fixed(self):
        assert e2.design_sha256() == e2.DESIGN_SHA256
        assert e2.DESIGN_SHA256 == (
            "7f7d4474d624ac59f7db5ca1193a1de475dafa0bb183c714b4f92b2447d46c9a"
        )

    def test_a_changed_member_is_refused(self, monkeypatch):
        b1, b2 = e2.MEMBERS
        changed = e2.Member(
            b1.id, b1.family, b1.test, b1.kind, b1.seed + 1, b1.question
        )
        monkeypatch.setattr(e2, "MEMBERS", (changed, b2))
        with pytest.raises(e2.E2Error, match="approved on 2026-11-14"):
            e2.check_declaration()

    def test_a_changed_lookback_or_test_rule_is_refused(self, monkeypatch):
        monkeypatch.setattr(ensemble, "LOOKBACKS", (20, 30, 60, 90, 150, 250))
        with pytest.raises(e2.E2Error, match="approved"):
            e2.check_declaration()
        monkeypatch.undo()
        from research_stats import resampling

        monkeypatch.setattr(resampling, "DEFAULT_BLOCK_SCALE", 1.0)
        with pytest.raises(e2.E2Error, match="approved"):
            e2.check_declaration()

    def test_overlapping_seed_ranges_are_refused(self, monkeypatch):
        spans = e2.seed_ranges()
        assert spans["B1"] == (2_000_000, 2_000_000 + 7 * 2_000 - 1)
        assert spans["B2"] == (2_100_000, 2_100_009)
        monkeypatch.setitem(e2.SHOWN_SEEDS, "hold comparison", 2_000_500)
        with pytest.raises(e2.E2Error, match="overlap"):
            e2.check_declaration()

    def test_the_earlier_exposures_are_counted_from_their_log(self, tmp_path):
        got = e2.exposures_record(EXPOSURE_LOG)
        assert (got["lines"], got["explorations"]) == (84, 38)
        assert len(got["sha256"]) == 64
        short = tmp_path / "trials.jsonl"
        short.write_text('{"trial": "x/run", "kind": "exploration"}\n', "utf-8")
        with pytest.raises(e2.E2Error, match="84 lines"):
            e2.exposures_record(str(short))

    def test_it_freezes_with_its_record(self, lab):
        record = record_for_test()
        frozen = ex.freeze(e2.EXPERIMENT_ID, record)
        assert (
            ex.verify(e2.EXPERIMENT_ID, {"BTC:1d": "aa"})["sha256"] == frozen["sha256"]
        )
        assert frozen["family"]["B"]["members"] == ["B1", "B2"]
        assert frozen["family"]["B"]["k"] == 2
        assert frozen["design_sha256"] == e2.DESIGN_SHA256
        assert frozen["accounts"]["usd"] == {
            "10000.0": 13476.0, "500.0": 673.8, "50.0": 67.38,
        }  # fmt: skip
        assert frozen["accounts"]["deciding_gbp"] == 10_000.0
        assert (
            frozen["costs"]["fee"] == 0.005 and frozen["costs"]["allowance"] == 0.0005
        )
        assert frozen["windows"]["lockbox_read"] is False
        assert frozen["windows"]["history_from"] == "2020-01-01"
        assert frozen["tests"]["seeds"] == {"B1": 2_000_000, "B2": 2_100_000}
        members = frozen["strategy"]["members"]
        assert sorted(int(k) for k in members) == list(ensemble.LOOKBACKS)
        assert members["90"]["overlays"][0]["params"] == {"days": 90}
        assert "below the equal-weight hold" in frozen["tests"]["economic"]["drawdown"]
        assert frozen["market"]["second_exchange"]["exchange"] == "kraken"
        # the earlier exposures are in the record before any result
        prs = [x.get("pr") for x in frozen["earlier_exposures"]["runs"]]
        assert prs == [291, 300, 257]
        log = frozen["earlier_exposures"]["trial_log"]
        assert (log["lines"], log["explorations"]) == (84, 38)
        with pytest.raises(ex.ExperimentError, match="candles changed"):
            ex.verify(e2.EXPERIMENT_ID, {"BTC:1d": "bb"})

    def test_the_record_lists_the_code_it_runs(self, lab):
        frozen = ex.freeze(e2.EXPERIMENT_ID, record_for_test())
        for name in (
            "strategies/donchian_midline.py",
            "strategy_lab/ensemble.py",
            "strategy_lab/sizing.py",
            "strategy_lab/e2.py",
            "strategy_lab/baselines.py",
            "market_data/gaps.py",
            "research_stats/resampling.py",
            "research_stats/power.py",
            "research_stats/multiple.py",
            "research_stats/overfitting.py",
            "research_engine/ledger.py",
            "feature_library/builtin.py",
        ):
            assert len(frozen["code"][name]) == 64, name
        assert frozen["code_extra"]["packages"] == ["research_stats", "feature_library"]

    def test_the_evidence_writer_refuses_once_the_code_changes(self, lab, monkeypatch):
        ex.freeze(e2.EXPERIMENT_ID, record_for_test())
        real = ex.code_hashes

        def changed(*a, **kw):
            out = real(*a, **kw)
            out["strategies/donchian_midline.py"] = "0" * 64
            return out

        line = ev.Line("STRAT-007", "x", "trading", "y", "z", "w")
        monkeypatch.setattr(ex, "code_hashes", changed)
        with pytest.raises(ex.ExperimentError, match="donchian_midline"):
            ev.write_results(e2.EXPERIMENT_ID, [line])
        monkeypatch.setattr(ex, "code_hashes", real)
        assert ev.write_results(e2.EXPERIMENT_ID, [line])["experiment"] == "SR1-E2"


# --- the candles -------------------------------------------------------------------------


class TestCandles:
    def test_nothing_from_the_lockbox(self):
        def base(symbol, tf, a, b, cache_dir=None, offline=True):
            n = int((b - a) / pd.Timedelta(days=1))
            return make_candles([100.0] * n, start=str(a.date()), tf_seconds=DAY)

        load = e2.development_loader(base, lambda s, tf: e2.HISTORY_START)
        with pytest.raises(ReservedPeriod):
            load("BTC-USD", "1d", "2020-01-01", "2025-05-07")

        def leaky(symbol, tf, a, b, **_kw):
            return make_candles([1.0, 1.0], start="2025-05-05", tf_seconds=DAY)

        with pytest.raises(ReservedPeriod, match="reserved months"):
            e2.development_loader(leaky, lambda s, tf: e2.HISTORY_START)(
                "BTC-USD", "1d", "2020-01-01", e2.DEV_END
            )
        frame = load("BTC-USD", "1d", "2019-01-01", e2.DEV_END)
        assert frame["open_time"].iloc[0] == e2.HISTORY_START
        assert frame["open_time"].max() < e2.DEV_END

    def test_the_second_exchange_reads_its_own_cache_only(self, monkeypatch):
        import market_data.candles as candles

        seen = []

        def fake(symbol, tf, a, b, cache_dir=None, offline=False, exchanges=None):
            seen.append(("candles", exchanges, offline))
            n = int((b - a) / pd.Timedelta(days=1))
            return make_candles([100.0] * n, start=str(a.date()), tf_seconds=DAY)

        def first(symbol, tf, cache_dir=None, exchanges=None):
            seen.append(("first", exchanges))
            return e2.HISTORY_START

        monkeypatch.setattr(candles, "exchange_candles", fake)
        monkeypatch.setattr(e1, "first_cached", first)
        e2.development_loader(exchanges=["kraken"])(
            "BTC-USD", "1d", e2.HISTORY_START, e2.DEV_END
        )
        assert seen == [("first", ["kraken"]), ("candles", ["kraken"], True)]

    def test_a_coin_without_bars_is_left_out_with_the_reason(self):
        def base(symbol, tf, a, b, cache_dir=None, offline=True):
            n = int((b - a) / pd.Timedelta(days=1))
            return make_candles(
                list(100 + np.sin(np.arange(n) / 9.0) * 20),
                start=str(a.date()),
                tf_seconds=DAY,
            )

        def first(symbol, tf):
            return None if symbol == "HYPE-USD" else e2.HISTORY_START

        load = e2.development_loader(base, first)
        u, left = e2.development_universe(["BTC", "HYPE"], load)
        assert sorted(u.frames) == ["BTC"] and "no cached bars" in left["HYPE"]
        assert set(e1.universe_sha256(u)) == {"BTC:1d"}


# --- F3 for a book ----------------------------------------------------------------------------


def trade(coin, entry_day, exit_day, price=100.0):
    return Trade(
        coin, entry_day - 1, entry_day, exit_day, entry_day * DAY, exit_day * DAY,
        price, price, "strategy", False,
    )  # fmt: skip


def fake_path(detail, mdd=0.10, intrabar=0.20, halt_s=-1, intrabar_halt=-1):
    one = lambda v: np.array([v])  # noqa: E731
    start = 13_476.0
    net = float(sum(r[2] for r in detail))
    days = float(sum(r[3] for r in detail))
    marks = np.arange(FIRST_DAY, LAST_DAY + 2) * DAY
    return Paths(
        net=one(net), capital_days=one(days), trades=one(len(detail)),
        skipped_cash=one(0), skipped_minimum=one(0), vetoed=one(0),
        max_drawdown=one(mdd), max_drawdown_usd=one(mdd * start), halt_s=one(halt_s),
        final_equity=one(start + net), time_in_market=one(0.5), mean_committed=one(0.2),
        peak_committed=one(0.5), start=start, detail=list(detail),
        curve=(marks, np.full(len(marks), start)), skipped_cooldown=one(0),
        dust_usd=one(0.0), halt_exposure=one(0.0), halt_further_loss=one(0.0),
        intrabar_max_drawdown=None if intrabar is None else one(intrabar),
        intrabar_max_drawdown_usd=None if intrabar is None else one(intrabar * start),
        intrabar_halt_s=None if intrabar is None else one(intrabar_halt),
    )  # fmt: skip


def flat_closes(coins=("AAA", "BBB")):
    return {c: {d: 100.0 for d in range(FIRST_DAY - 5, LAST_DAY + 5)} for c in coins}


class TestBookF3:
    def slices_and_path(self, nets, **kw):
        # (member, coin, entry day, exit day, net)
        rows, slices = [], []
        for i, (n, coin, a, b, net) in enumerate(nets):
            slices.append((n, trade(coin, a, b)))
            rows.append((i, 100.0, float(net), 100.0 * (b - a)))
        return slices, fake_path(rows, **kw)

    def test_halves_are_by_entry_day(self):
        slices, path = self.slices_and_path(
            [
                (20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0),
                # entered the day before the middle, exits after it: the first half
                (60, "AAA", MIDDLE_DAY - 1, MIDDLE_DAY + 40, 7.0),
                (20, "BBB", MIDDLE_DAY, MIDDLE_DAY + 5, -2.0),
                (90, "BBB", LAST_DAY - 20, LAST_DAY, 4.0),
            ]
        )
        hold = fake_path([], intrabar=0.5)
        r = e2.book_f3(path, slices, flat_closes(), hold, seed=3)
        assert r["report"]["trades_by_half"] == [2, 2]
        assert r["report"]["net_by_half"] == [12.0, 2.0]
        assert r["requirements"]["stable"] is True
        assert r["requirements"]["trades"] is False  # 4 trades: not assessable
        assert len(r["test"]["runs"]) == e2.RUNS
        # a resample with no capital in the market has no return per capital-day
        assert 0 < r["test"]["draws"] <= e2.RUNS * e2.BOOTSTRAP_DRAWS
        assert r["test"]["draws"] == sum(x["draws"] for x in r["test"]["runs"])

    def test_without_the_best_coin_sums_every_member_on_it(self):
        # by slice the best would be AAA~20 (+100), leaving -20; by coin the best is
        # BBB (+60), and AAA's members together leave +20
        slices, path = self.slices_and_path(
            [
                (20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 100.0),
                (60, "AAA", FIRST_DAY + 40, FIRST_DAY + 90, -80.0),
                (20, "BBB", MIDDLE_DAY + 10, MIDDLE_DAY + 20, 60.0),
            ]
        )
        r = e2.book_f3(path, slices, flat_closes(), fake_path([], intrabar=0.5), seed=3)
        assert r["report"]["net_by_coin"] == {"AAA": 20.0, "BBB": 60.0}
        assert r["report"]["best_coin"] == "BBB"
        assert r["report"]["without_best_coin"] == 20.0
        assert r["requirements"]["not_one_coin"] is True

    def test_the_drawdown_requirement_compares_with_the_hold_both_ways(self):
        slices, below = self.slices_and_path(
            [(20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0)], mdd=0.20, intrabar=0.30
        )
        hold = fake_path([], mdd=0.50, intrabar=0.40)
        r = e2.book_f3(below, slices, flat_closes(), hold, seed=3)
        assert r["requirements"]["below_hold"] is True
        assert r["report"]["intrabar_max_drawdown"] == 0.30
        assert r["report"]["hold_intrabar_max_drawdown"] == 0.40
        # measured at the lows, from the earlier highs: the closes would say otherwise
        _s, above = self.slices_and_path(
            [(20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0)], mdd=0.20, intrabar=0.45
        )
        r = e2.book_f3(above, slices, flat_closes(), hold, seed=3)
        assert r["requirements"]["below_hold"] is False
        _s, level = self.slices_and_path(
            [(20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0)], intrabar=0.40
        )
        assert (
            e2.book_f3(level, slices, flat_closes(), hold, seed=3)["requirements"][
                "below_hold"
            ]
            is False
        )  # not below: equal
        _s, none = self.slices_and_path(
            [(20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0)], intrabar=None
        )
        with pytest.raises(e2.E2Error, match="lows"):
            e2.book_f3(none, slices, flat_closes(), hold, seed=3)

    def test_the_halt_is_reported_not_modelled(self):
        t = (FIRST_DAY + 21) * DAY
        slices, path = self.slices_and_path(
            [(20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0)],
            halt_s=t + DAY, intrabar_halt=t,
        )  # fmt: skip
        r = e2.book_f3(path, slices, flat_closes(), fake_path([], intrabar=0.5), seed=3)
        assert r["report"]["intrabar_halt_reached_s"] == t
        assert r["report"]["halt_reached_s"] == t + DAY
        assert "within_halt" not in r["requirements"]

    def test_the_daily_marks_sum_to_each_trades_net(self):
        slices, path = self.slices_and_path(
            [
                (20, "AAA", FIRST_DAY + 10, FIRST_DAY + 30, 5.0),
                (60, "BBB", FIRST_DAY + 12, FIRST_DAY + 13, -1.5),
            ]
        )
        marks = e2.book_marks(path, slices, flat_closes())
        assert marks.first_day == FIRST_DAY and marks.days == LAST_DAY - FIRST_DAY + 1
        assert marks.pnl.sum() == pytest.approx(3.5)
        assert marks.capital[10] == 100.0 and marks.capital[12] == 200.0


# --- the hold comparison ---------------------------------------------------------------------


MR = namedtuple("MR", "mean p_value interval level mean_block draws days method")


def curves():
    t = np.arange(FIRST_DAY, FIRST_DAY + 400) * DAY
    rng = np.random.default_rng(4)
    book = 10_000 * np.exp(np.cumsum(rng.normal(0.001, 0.02, len(t))))
    hold = 10_000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, len(t))))
    return (t, book), (t[5:], hold[5:])  # the hold's first entry comes later


def test_the_hold_comparison_pools_ten_runs_of_mean_test(monkeypatch):
    """A stand-in for ``research_stats.resampling.mean_test`` (being added beside this
    work), with its interface: the comparison asks for 10 seeded runs of 2,000 and
    pools their counts."""
    from research_stats import resampling

    calls = []

    def stand_in(x, draws=2000, seed=0, mean_block=None, level=0.95,
                 method="studentised", block_scale=1.5):  # fmt: skip
        x = np.asarray(x)
        calls.append((len(x), draws, seed, method, block_scale))
        k = seed % 3  # this run's draws at or above
        return MR(float(x.mean()), (1 + k) / (draws + 1), (-0.001, 0.002), level, 7.5,
                  draws, len(x), method)  # fmt: skip

    monkeypatch.setattr(resampling, "mean_test", stand_in, raising=False)
    book, hold = curves()
    r = e2.hold_comparison(book, hold, seed=100)
    assert [c[2] for c in calls] == list(range(100, 110))
    assert {(c[1], c[3], c[4]) for c in calls} == {(2000, "studentised", 1.5)}
    common = book[0][5:]
    x = np.diff(np.log(book[1][5:])) - np.diff(np.log(hold[1]))
    assert calls[0][0] == len(common) - 1 == r["days"]
    assert r["annualised_mean"] == pytest.approx(365 * x.mean())
    counts = sum(s % 3 for s in range(100, 110))
    assert r["p"] == pytest.approx((1 + counts) / (10 * 2000 + 1))
    assert r["runs"][0]["interval"] == pytest.approx([-0.365, 0.73])
    assert r["draws"] == 20_000
    monkeypatch.delattr(resampling, "mean_test")
    with pytest.raises(e2.E2Error, match="mean_test"):
        e2.hold_comparison(book, hold, seed=100)


# --- the words ---------------------------------------------------------------------------------


class TestWords:
    def member(self, mid):
        return next(m for m in e2.MEMBERS if m.id == mid)

    def random(self, **kw):
        r = {
            "assessable": True, "value": 0.004, "median": 0.002, "p": 0.01,
            "draws": 2_000, "trades": 630, "too_few": False,
            "smallest_detectable": 0.001, "net_usd": 37_648.0,
        }  # fmt: skip
        r.update(kw)
        return r

    def economic(self, trades=630, half=(330, 300), p=0.01, halt=None, **met):
        req = {"stable": True, "not_one_coin": True, "below_hold": True, **met}
        req["trades"] = trades >= 100 and min(half) >= 30
        return {
            "requirements": req,
            "test": {"p": p},
            "report": {
                "net_usd": 37_648.0, "rpcd": 0.003, "trades": trades,
                "trades_by_half": list(half), "net_by_half": [20_000.0, 17_648.0],
                "net_by_coin": {"SOL": 20_000.0, "BTC": 17_648.0},
                "without_best_coin": 17_648.0, "best_coin": "SOL",
                "max_drawdown": 0.422, "hold_max_drawdown": 0.722,
                "intrabar_max_drawdown": 0.473, "hold_intrabar_max_drawdown": 0.754,
                "halt_reached_s": -1 if halt is None else halt,
                "intrabar_halt_reached_s": -1 if halt is None else halt,
                "halt_pct": 8.0,
            },
            "smallest_detectable": 0.0008,
        }  # fmt: skip

    def test_the_book_against_random_entries(self):
        b1 = self.member("B1")
        lines = [
            e2.member_line(b1, self.random(), True),
            e2.member_line(b1, self.random(p=0.4), False),
            e2.member_line(b1, self.random(p=0.4, too_few=True), False),
            e2.member_line(b1, self.random(net_usd=-50.0), True),
            e2.member_line(
                b1, {"assessable": False, "reason": "the book made no trades"}, False
            ),
        ]
        assert lines[0].startswith(
            "Beats random entries with each member's own exits (return per capital-day "
            "+0.4000% against a random median of +0.2000%, p = 0.0100 (Holm over 2, "
            "B = 2,000), 630 trades)"
        )
        assert lines[1].startswith(
            "No better than random entries with each member's own exits"
        )
        assert lines[2].startswith(
            "Too few trades to tell: this test could only see an edge"
        )
        assert "still loses money" in lines[3]
        assert lines[4].startswith("Not assessable: the book made no trades")
        for line in lines:
            assert "profitable" not in line.lower()
            assert line.endswith(e2.DEV_ONLY)

    def test_the_books_economics(self):
        b2 = self.member("B2")
        halt = int(pd.Timestamp("2021-01-22", tz="UTC").timestamp())
        win = e2.member_line(b2, self.economic(halt=halt), True)
        assert win.startswith(
            "Profitable after fees at £10,000 with 0.50% taker and 0.05% slippage a fill"
        )
        assert (
            "maximum drawdown 47.30% at the bars' lows, against the equal-weight hold's 75.40%"
            in win
        )
        assert (
            "The book reached the trader's 8% halt on 2021-01-22: trading it would need "
            "the halt changed." in win
        )
        never = e2.member_line(b2, self.economic(), True)
        assert "The book never reached the trader's 8% halt." in never
        worse = self.economic(below_hold=False, halt=halt)
        worse["report"]["intrabar_max_drawdown"] = 0.80
        lose = e2.member_line(b2, worse, False, holm_pass=True)
        assert lose.startswith(
            "Not shown to be profitable after fees. The book failed the requirement for "
            "a maximum drawdown below the equal-weight hold's (80.00% against 75.40%, "
            "each at the bars' lows from a peak at the earlier bars' highs). Its bootstrap "
            "test of return per capital-day passed Holm over 2 (p = 0.0100), but that is "
            "one of the five requirements, and a pass needs all five."
        )
        assert "trading it would need the halt changed" in lose
        unstable = e2.member_line(
            b2,
            self.economic(p=0.3, stable=False, not_one_coin=False),
            False,
            holm_pass=False,
        )
        assert unstable.startswith(
            "Not shown to be profitable after fees. The book failed the requirement that "
            "its bootstrap test of return per capital-day passes Holm (p = 0.3000), and "
            "failed the requirement for a positive net profit in both evaluation halves"
        )
        assert "without its most profitable coin ($+17,648.00 without SOL)" in unstable
        few = e2.member_line(b2, self.economic(80, (50, 30)), False)
        assert few.startswith("Not assessable: 80 trades (50 and 30 by half")
        for line in (win, never, lose, unstable, few):
            assert line.endswith(e2.DEV_ONLY)


# --- trials -----------------------------------------------------------------------------------


def test_each_scored_cell_is_logged_in_both_trial_logs(lab):
    from research_engine import ledger

    frozen = ex.freeze(e2.EXPERIMENT_ID, record_for_test())
    e2.log_trial(
        frozen, "B1", "strategy", ["BTC"], {"p": 0.01}, seeds=[2_000_000], family="B"
    )
    lines = ex.trials()
    assert [x["trial"] for x in lines] == ["SR1-E2/B1"]
    entries = ledger.entries()
    assert [e["trial_id"] for e in entries] == ["strategy_lab:SR1-E2/B1"]
    e = entries[0]
    assert (e["experiment_id"], e["member"], e["kind"], e["family"]) == (
        "SR1-E2", "B1", "declared", "B",
    )  # fmt: skip
    assert e["counted_in"] == "SR1-E2" and e["seeds"] == [2_000_000]
    assert e["code_hash"] == frozen["sha256"]
    assert any("291" in x for x in e["earlier_exposures"])
    assert e["candidates"][0]["id"] == "STRAT-007"
    # the strategy lab's line is the same trial: bringing it in adds nothing
    assert ledger.sync() == 0
    assert json.loads(json.dumps(e["outcome"])) == {"summary": {"p": 0.01}}


# --- the driver's checks ------------------------------------------------------------------------


def _driver():
    import importlib.util

    path = os.path.join(REPO, "docs", "dev", "run_sr1_e2.py")
    spec = importlib.util.spec_from_file_location("run_sr1_e2_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_driver_runs_only_in_a_sandbox():
    import tempfile

    drv = _driver()
    # a made-up profile outside the temp folder (only its name is used)
    drive = os.path.splitdrive(tempfile.gettempdir())[0]
    profile = os.path.join(drive + os.sep, "Users", "e2-test-profile")
    scratch = os.path.join(tempfile.gettempdir(), "e2-sandbox")
    good = {
        "USERPROFILE": profile,
        "POWERTRADER_HOME": os.path.join(scratch, "home"),
        "APPDATA": os.path.join(scratch, "roaming"),
        "LOCALAPPDATA": os.path.join(scratch, "local"),
        "PYTHON_KEYRING_BACKEND": "keyring.backends.fail.Keyring",
    }
    assert drv.sandbox_problem(good) is None
    for name, value, why in (
        ("APPDATA", os.path.join(profile, "AppData", "Roaming"), "real user folders"),
        (
            "LOCALAPPDATA",
            os.path.join(profile, "AppData", "Local"),
            "real user folders",
        ),
        ("POWERTRADER_HOME", "", "not set"),
        (
            "PYTHON_KEYRING_BACKEND",
            "keyring.backends.Windows.WinVaultKeyring",
            "keyring",
        ),
    ):
        env = {**good, name: value}
        assert why in (drv.sandbox_problem(env) or ""), name


def test_the_driver_refuses_a_rate_that_was_not_checked(tmp_path):
    drv = _driver()
    path = tmp_path / "rate.json"
    path.write_text(json.dumps({"gbp_usd": 1.3476}), "utf-8")
    with pytest.raises(SystemExit, match="second source"):
        drv.read_rate(str(path))
    path.write_text(
        json.dumps({"gbp_usd": 1.3476, "verification": {"agrees": True}}), "utf-8"
    )
    rate = drv.read_rate(str(path))
    assert rate["gbp_usd"] == 1.3476 and len(rate["file_sha256"]) == 64
