"""FDS-SR-001 milestone M4a: the strategy lab's portfolio simulation (sections 5.4.1,
5.10 and 12).

* With one coin at 100% and no costs, the replay of a strategy's candidate trades makes
  exactly ``run_backtest``'s trades: STRAT-001, -002, -004 and -005, with stops, with the
  cooldown (applied by the replay) and with the regime gate's context.
* One load of candles serves every account: the candle loader is called once per series,
  whatever the number of accounts, and the candidate trades are the same for each.
* Small accounts: entries are raised to the minimum entry; a sell is rounded down to the
  coin's step, and the remainder is reported; the halt's exposure is reported.
* The baselines: buy-and-hold per coin; random entries replayed through the strategy's
  own exits, matched to its entries and waits, reproducible for a seed, and the same
  whether replayed alone or in a batch.
* The exchange layer reads the sell step, primary exchange first.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import unittest
import unittest.mock

import numpy as np
import pytest
from helpers import make_candles
from test_position_budget import _Json, connector, exchange_manager

from backtest.engine import CostModel, run_backtest
from signal_fusion.evaluation.replay import Account, Costs, replay
from strategy_lab import baselines as bl
from strategy_lab.candidates import RunnerSpec
from strategy_lab.simulate import (
    ACCOUNTS_GBP,
    after_long_gaps,
    Simulation,
    Universe,
    load_universe,
    usd_accounts,
)

DAY, HOUR = 86_400, 3_600
ZERO = CostModel(0, 0)
FREE = Costs(fee=0.0, allowance=0.0)


def waves(n, period=12.0, drift=0.15, amp=30.0, phase=0.0, seed=None):
    i = np.arange(n)
    x = 100 + amp * np.sin(i / period + phase) + drift * i
    if seed is not None:
        x = x + np.random.default_rng(seed).normal(0, 1.5, n)
    return list(np.maximum(x, 5.0))


def frame_for(tf, n, **kw):
    seconds = {"1h": HOUR, "4h": 4 * HOUR, "1d": DAY}[tf]
    return make_candles(waves(n, **kw), start="2023-01-02", tf_seconds=seconds)


def one_coin(frame, spec, context=None):
    universe = Universe(spec.timeframe, {"X": frame}, own={"X": context or {}})
    return Simulation(universe, spec)


def bt_times(trades, tf):
    """The backtester's (entry, exit) times; a forced exit is at the last close."""
    step = {"1h": HOUR, "4h": 4 * HOUR, "1d": DAY}[tf]
    return [
        (
            int(w.entry_time.timestamp()),
            int(w.exit_time.timestamp()) + (step if w.forced_close else 0),
        )
        for w in trades
    ]


def replayed_trades(sim):
    trades = sim.candidates()
    paths = sim.replay(
        trades, FREE, Account(start=10_000.0), size_fraction=1.0, detail=True
    )
    return [(trades[i], amount, net) for i, amount, net, _days in paths.detail]


CASES = [
    ("STRAT-001 1h", RunnerSpec("STRAT-001", timeframe="1h"), ("1h", 2400, {})),
    (
        "STRAT-002 4h + ATR stop",
        RunnerSpec(
            "STRAT-002",
            overlays=({"id": "OVL-ATR", "params": {"mult": 1.5}},),
            timeframe="4h",
        ),
        ("4h", 900, {"seed": 3}),
    ),
    (
        "STRAT-004 1d + ratchet",
        RunnerSpec(
            "STRAT-004",
            {"entry_days": 20, "exit_days": 10},
            ({"id": "OVL-RATCHET"},),
            "1d",
        ),
        ("1d", 500, {"seed": 4}),
    ),
    (
        "STRAT-005 1d",
        RunnerSpec("STRAT-005", timeframe="1d"),
        ("1d", 700, {"period": 20.0}),
    ),
    (
        "STRAT-001 1h + cooldown",
        RunnerSpec(
            "STRAT-001",
            overlays=(
                {
                    "id": "OVL-COOLDOWN",
                    "params": {"bars_after_exit": 30, "bars_after_loss": 60},
                },
            ),
            timeframe="1h",
        ),
        ("1h", 2400, {"seed": 5, "period": 6.0}),
    ),
]


@pytest.mark.parametrize("name, spec, data", CASES, ids=[c[0] for c in CASES])
def test_the_replay_makes_exactly_the_backtesters_trades(name, spec, data):
    tf, n, kw = data
    frame = frame_for(tf, n, **kw)
    sim = one_coin(frame, spec)
    got = replayed_trades(sim)
    want = run_backtest(frame, spec.build(), "X", tf, cost=ZERO).trades
    assert len(want) >= 3, name
    assert [(t.entry_s, t.exit_s) for t, _, _ in got] == bt_times(want, tf)
    for (t, amount, net), w in zip(got, want):
        assert t.entry_price == pytest.approx(w.entry_price)
        assert t.exit_price == pytest.approx(w.exit_price)
        assert net / amount * 100.0 == pytest.approx(w.pnl_pct, rel=1e-9, abs=1e-9)
        assert t.forced == w.forced_close


def test_the_cooldown_is_what_skips_entries_in_that_case():
    _, spec, (tf, n, kw) = CASES[-1]
    frame = frame_for(tf, n, **kw)
    sim = one_coin(frame, spec)
    paths = sim.replay(
        sim.candidates(), FREE, Account(start=10_000.0), size_fraction=1.0
    )
    assert int(paths.skipped_cooldown[0]) > 0
    plain = one_coin(frame, RunnerSpec("STRAT-001", timeframe="1h"))
    assert len(replayed_trades(plain)) > len(replayed_trades(sim))


def test_the_regime_gates_context_reaches_the_candidates():
    frame = frame_for("1d", 500, seed=6)
    spec = RunnerSpec(
        "STRAT-004",
        {"entry_days": 20, "exit_days": 10},
        ({"id": "OVL-REGIME", "params": {"reference": "self", "sma_days": 50}},),
        "1d",
    )
    context = {("self", "1d"): frame}
    sim = one_coin(frame, spec, context)
    got = replayed_trades(sim)
    want = run_backtest(
        frame, spec.build(), "X", "1d", cost=ZERO, context_frames=context
    ).trades
    assert [t.entry_s for t, _, _ in got] == [
        int(w.entry_time.timestamp()) for w in want
    ]
    ungated = one_coin(
        frame, RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d")
    )
    assert len(sim.candidates()) < len(ungated.candidates())


def test_an_entry_filling_at_its_coins_own_exit_is_not_taken():
    """STRAT-005 says ENTER on every decision day its vote holds; after a stop's exit,
    the entry decided on the same close is the backtester's ignored ENTER."""
    frame = frame_for("1d", 700, period=20.0, seed=8)
    spec = RunnerSpec(
        "STRAT-005",
        {"rebalance_days": 1},  # decides every day, so the vote holds while stops fire
        ({"id": "OVL-ATR", "params": {"mult": 0.5}},),
        "1d",
    )
    sim = one_coin(frame, spec)
    got = replayed_trades(sim)
    # the case occurs: a candidate fills at the open where a taken trade exits
    exits = {t.exit_s for t, _, _ in got}
    assert any(c.entry_s in exits for c in sim.candidates())
    want = run_backtest(frame, spec.build(), "X", "1d", cost=ZERO).trades
    assert [(t.entry_s, t.exit_s) for t, _, _ in got] == bt_times(want, "1d")


class LongGapTests(unittest.TestCase):
    """A series with a gap longer than a day is used from after its last such gap
    (A2 N17: compare-9's XRP trades ran across Coinbase's 2.5-year halt)."""

    SPEC = RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d")

    def loader_for(self, frames):
        def loader(symbol, tf, start, end, **kw):
            out = frames[symbol].copy()
            out.attrs.update(exchange="fake", pair=symbol)
            return out

        return loader

    def holed(self, frame, first, bars):
        """``frame`` without ``bars`` daily bars from bar ``first`` on."""
        keep = np.r_[0:first, first + bars : len(frame)]
        return frame.iloc[keep].reset_index(drop=True)

    def test_without_the_rule_a_trade_spans_the_hole_and_with_it_none_does(self):
        full = frame_for("1d", 500, seed=11)
        held = [
            t
            for t in Simulation(Universe("1d", {"X": full}), self.SPEC).candidates()
            if t.exit_i - t.entry_i >= 6 and t.entry_i > 60
        ]
        first = held[0].entry_i + 2  # a hole opening inside a held trade
        holed = self.holed(full, first, 30)
        hole_from = int(full["open_time"].iloc[first - 1].timestamp())
        hole_to = int(holed["open_time"].iloc[first].timestamp())

        def spans(trades):
            return [t for t in trades if t.entry_s <= hole_from and t.exit_s >= hole_to]

        joined = Simulation(Universe("1d", {"X": holed}), self.SPEC).candidates()
        self.assertTrue(spans(joined))  # the defect: a trade runs across 30 days
        universe = load_universe(
            ["X"],
            self.SPEC,
            "2023-01-02",
            "2025-01-01",
            loader=self.loader_for({"X-USD": holed}),
        )
        cut = Simulation(universe, self.SPEC).candidates()
        self.assertEqual(spans(cut), [])
        self.assertTrue(all(t.entry_s >= hole_to for t in cut))
        record = universe.sources["X:1d"]["cut_at_long_gap"]
        self.assertEqual(record["bars_dropped"], first)
        self.assertEqual(
            record["kept_from"], holed["open_time"].iloc[first].isoformat()
        )
        self.assertEqual(universe.sources["X:1d"]["exchange"], "fake")

    def test_a_gap_of_up_to_a_day_is_kept(self):
        frame = frame_for("1d", 300, seed=12)
        one_missing = self.holed(frame, 100, 1)  # 2 days between bars: 1 day missing
        two_missing = self.holed(frame, 100, 2)
        loader = self.loader_for({"A-USD": one_missing, "B-USD": two_missing})
        universe = load_universe(
            ["A", "B"], self.SPEC, "2023-01-02", "2024-06-01", loader=loader
        )
        self.assertEqual(len(universe.frames["A"]), 299)
        self.assertNotIn("cut_at_long_gap", universe.sources["A:1d"])
        self.assertEqual(len(universe.frames["B"]), 298 - 100)
        self.assertIn("cut_at_long_gap", universe.sources["B:1d"])

    def test_hourly_bars_keep_a_gap_of_a_day_and_end_at_a_longer_one(self):
        frame = frame_for("1h", 400, seed=13)
        self.assertEqual(len(after_long_gaps(self.holed(frame, 50, 24), HOUR)[0]), 376)
        kept, cut = after_long_gaps(self.holed(frame, 50, 25), HOUR)
        self.assertEqual(len(kept), 400 - 25 - 50)
        self.assertEqual(cut["bars_dropped"], 50)

    def test_the_regime_gates_reference_series_is_cut_too(self):
        spec = RunnerSpec(
            "STRAT-004",
            {"entry_days": 20, "exit_days": 10},
            ({"id": "OVL-REGIME", "params": {"sma_days": 50}},),
            "1d",
        )
        frames = {
            "AAA-USD": frame_for("1d", 400, seed=1),
            "BTC-USD": self.holed(frame_for("1d", 460, seed=3), 200, 10),
        }
        universe = load_universe(
            ["AAA"], spec, "2023-01-02", "2024-02-06", loader=self.loader_for(frames)
        )
        self.assertEqual(len(universe.shared[("BTC", "1d")]), 460 - 10 - 200)
        self.assertIn("cut_at_long_gap", universe.sources["BTC:1d"])


class LoaderTests(unittest.TestCase):
    def test_one_load_serves_every_account(self):
        calls = []
        frames = {
            "AAA-USD": frame_for("1d", 400, seed=1),
            "BBB-USD": frame_for("1d", 400, seed=2, phase=1.0),
            "BTC-USD": frame_for("1d", 460, seed=3),
        }

        def loader(symbol, tf, start, end, **kw):
            calls.append((symbol, tf))
            out = frames[symbol].copy()
            out.attrs.update(exchange="fake", pair=symbol)
            return out

        spec = RunnerSpec(
            "STRAT-004",
            {"entry_days": 20, "exit_days": 10},
            ({"id": "OVL-REGIME", "params": {"sma_days": 50}},),
            "1d",
        )
        universe = load_universe(
            ["AAA", "BBB"], spec, "2023-01-02", "2024-02-06", loader=loader
        )
        self.assertEqual(
            sorted(calls), [("AAA-USD", "1d"), ("BBB-USD", "1d"), ("BTC-USD", "1d")]
        )
        sim = Simulation(universe, spec)
        sizes = usd_accounts(ACCOUNTS_GBP, 1.25)
        self.assertEqual(sizes, {50.0: 62.5, 500.0: 625.0, 10_000.0: 12_500.0})
        costs = Costs(fee=0.005, allowance=0.0005, minimum_usd={"AAA": 1.0, "BBB": 1.0})
        results = sim.accounts(sizes, costs)
        self.assertEqual(len(calls), 3)  # no further loads for the accounts
        self.assertEqual(set(results), set(sizes))
        for paths in results.values():
            self.assertEqual(paths.start in sizes.values(), True)
        self.assertIn("BTC:1d", universe.sources)

    def test_the_rate_must_be_stated(self):
        for bad in (0, -1.2, float("nan")):
            with self.assertRaises(ValueError):
                usd_accounts(ACCOUNTS_GBP, bad)


class SmallAccountTests(unittest.TestCase):
    def setUp(self):
        frame = make_candles(
            [x / 1000.0 for x in waves(500, seed=9)], start="2023-01-02", tf_seconds=DAY
        )
        self.sim = one_coin(
            frame,
            RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d"),
        )

    def test_entries_are_raised_to_the_minimum_entry(self):
        costs = Costs(fee=0.005, allowance=0.0005, minimum_usd={"X": 1.0})
        paths = self.sim.replay(
            self.sim.candidates(), costs, Account(start=62.5), detail=True
        )
        floor = costs.floor("X", Account().margin_pct)
        amounts = [amount for _, amount, _, _ in paths.detail]
        self.assertTrue(amounts)
        self.assertTrue(all(a == pytest.approx(floor) for a in amounts))  # 1% is 0.63

    def test_a_sell_is_rounded_down_to_the_step_and_the_rest_reported(self):
        plain = Costs(fee=0.005, allowance=0.0005, minimum_usd={"X": 1.0})
        stepped = Costs(
            fee=0.005,
            allowance=0.0005,
            minimum_usd={"X": 1.0},
            base_increment={"X": 10.0},
        )
        a = self.sim.replay(self.sim.candidates(), plain, Account(start=62.5))
        b = self.sim.replay(self.sim.candidates(), stepped, Account(start=62.5))
        self.assertEqual(float(a.dust_usd[0]), 0.0)
        self.assertGreater(float(b.dust_usd[0]), 0.0)
        self.assertLess(float(b.net[0]), float(a.net[0]))  # the remainder is never sold
        self.assertEqual(int(a.trades[0]), int(b.trades[0]))


class HaltTests(unittest.TestCase):
    def test_the_exposure_at_the_halt_and_its_further_fall_are_reported(self):
        closes = [100.0] * 60 + [120.0] + list(np.linspace(118, 60, 40))
        frame = make_candles(closes, start="2023-01-02", tf_seconds=DAY)
        sim = one_coin(
            frame,
            RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d"),
        )
        paths = sim.replay(
            sim.candidates(), FREE, Account(start=10_000.0), size_fraction=1.0
        )
        self.assertGreater(int(paths.halt_s[0]), 0)
        self.assertGreater(float(paths.halt_exposure[0]), 0.0)
        self.assertGreater(float(paths.halt_further_loss[0]), 0.0)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.frames = {
            "AAA": frame_for("1d", 600, seed=11),
            "BBB": frame_for("1d", 600, seed=12, phase=2.0),
        }
        self.spec = RunnerSpec(
            "STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d"
        )
        self.sim = Simulation(Universe("1d", self.frames), self.spec)
        paths = self.sim.replay(self.sim.candidates(), FREE, Account(), detail=True)
        cands = self.sim.candidates()
        self.taken = [cands[i] for i, *_ in paths.detail]

    def test_buy_and_hold_is_one_trade_per_coin_to_the_last_close(self):
        trades = bl.hold_trades(self.sim)
        self.assertEqual(sorted(t.coin for t in trades), ["AAA", "BBB"])
        for t in trades:
            table = self.sim.tables[t.coin]
            self.assertEqual(t.decided, table.first_decision)
            self.assertTrue(t.forced)
            self.assertEqual(t.exit_i, table.n - 1)

    def test_random_entries_use_the_strategys_own_exits(self):
        draws = bl.random_draws(self.sim, self.taken, seed=300_000, count=20)
        for trades in draws.draws:
            for t in trades:
                self.assertEqual(t, self.sim.tables[t.coin].trade_from(t.decided))

    def test_random_entries_match_the_count_and_the_waits(self):
        draws = bl.random_draws(self.sim, self.taken, seed=300_000, count=20)
        self.assertEqual(draws.wanted, len(self.taken))
        self.assertTrue(all(r <= draws.wanted for r in draws.reached))
        self.assertTrue(any(r == draws.wanted for r in draws.reached))
        gaps = bl.waits(self.sim, self.taken)
        full = [d for d, r in zip(draws.draws, draws.reached) if r == draws.wanted]
        for trades in full[:5]:
            for coin, table in self.sim.tables.items():
                mine = [t for t in trades if t.coin == coin]
                free, got = table.first_decision, []
                for t in mine:
                    got.append(t.decided - free)
                    free = t.exit_i
                self.assertEqual(sorted(got), sorted(gaps[coin]))

    def test_draws_repeat_for_a_seed_and_differ_between_seeds(self):
        a = bl.random_draws(self.sim, self.taken, seed=300_000, count=5).draws
        b = bl.random_draws(self.sim, self.taken, seed=300_000, count=5).draws
        c = bl.random_draws(self.sim, self.taken, seed=400_000, count=5).draws
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_a_batch_of_draws_replays_as_each_draw_alone(self):
        draws = bl.random_draws(self.sim, self.taken, seed=300_000, count=7).draws
        costs = Costs(fee=0.005, allowance=0.0005)
        batch = bl.replay_draws(self.sim, draws, costs, Account(), chunk=3)
        self.assertEqual(len(batch.net), 7)
        for p, trades in enumerate(draws):
            alone = self.sim.replay(trades, costs, Account())
            self.assertAlmostEqual(float(batch.net[p]), float(alone.net[0]), places=9)
            self.assertAlmostEqual(
                float(batch.capital_days[p]), float(alone.capital_days[0]), places=9
            )


class ReplayCompatibilityTests(unittest.TestCase):
    def test_the_defaults_replay_as_before(self):
        sim = one_coin(frame_for("1h", 2400), RunnerSpec("STRAT-001", timeframe="1h"))
        opps = [t.opportunity() for t in sim.candidates()]
        costs = Costs(fee=0.005)
        before = replay(opps, sim.prices(), costs, Account())
        again = replay(opps, sim.prices(), costs, Account(), mark_s=HOUR, cooldown=None)
        for name in ("net", "capital_days", "trades", "max_drawdown", "final_equity"):
            np.testing.assert_array_equal(getattr(before, name), getattr(again, name))
        self.assertEqual(float(before.dust_usd[0]), 0.0)


class VenueStepTests(unittest.TestCase):
    def test_coinbase_states_its_sell_step(self):
        import pt_exchanges

        urls = []

        def get(url, timeout=None):
            urls.append(url)
            return _Json(
                {"id": "DOGE-USD", "base_increment": "0.1", "min_market_funds": "1"}
            )

        with unittest.mock.patch.object(pt_exchanges.requests, "get", get):
            self.assertEqual(
                connector("CoinbaseExchange").lot_increment("DOGE-USD"), 0.1
            )
        self.assertEqual(urls, ["https://api.exchange.coinbase.com/products/DOGE-USD"])

    def test_the_primary_exchange_is_asked_first(self):
        class Step:
            def __init__(self, step):
                self.step, self.asked = step, 0

            def lot_increment(self, symbol):
                self.asked += 1
                if isinstance(self.step, Exception):
                    raise self.step
                return self.step

        kraken, coinbase = Step(0.5), Step(ConnectionError("offline"))
        manager = exchange_manager("coinbase", kraken=kraken, coinbase=coinbase)
        self.assertEqual(manager.lot_increment("BTC-USD"), 0.5)
        self.assertEqual((coinbase.asked, kraken.asked), (1, 1))


if __name__ == "__main__":
    unittest.main()
