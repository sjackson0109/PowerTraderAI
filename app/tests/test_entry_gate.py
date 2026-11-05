"""The entry gate (entry_gate, model_gate, llm_gate.evaluate, pt_pattern_trainer
deviation 13): a candidate passes only on what its entries earn after fees against
random entries with exactly the same trade rules, never on its hit rate.

* A candidate with no skill (random entries) fails, even with a hit rate above 90%.
* A candidate with a planted edge (entries placed before known rises) passes.
* Results are identical when re-run with the same seeds.
* Each rule (a-f) fails a candidate on its own; the hit rate never decides.
* The replay follows the trader's rules (checked by hand), and reads them as the
  trader does.
* The fee is the trader's: the taker rate (market orders), from the account first.
* The trainer publishes only a model that passes, puts the model in use back
  otherwise, and records the decision; ``--check-gate`` changes nothing.
* The LLM gate judges a provider/model/prompt version's signals the same way.

All prices are synthetic; nothing reaches an exchange or a provider.
"""

import json
import math
import os
import random
import sys
from datetime import timedelta

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entry_gate as eg  # noqa: E402
import llm_gate  # noqa: E402
import llm_signals  # noqa: E402
import model_gate as mg  # noqa: E402
import training_settings  # noqa: E402
from llm_store import LLMStore, SignalRecord  # noqa: E402
from pt_exchange_abstraction import TradingFees  # noqa: E402

FEES = eg.Fees(0.012, "taker", "coinbase", "default", 0.0005)
SETTINGS = eg.GateSettings()  # 20 entries, 0%, 1000 runs, 95th percentile
RULES = mg.trade_rules({})  # the trader's defaults
T0 = 1_700_000_000
HOUR = 3600


def hours_of(prices, entries=(), longs=None):
    """Held-out hours with the model's entry signal (3 timeframes long, none short)
    at ``entries``; ``longs`` sets every hour's long count instead."""
    n = len(prices)
    if longs is None:
        longs = [3 if i in set(entries) else 0 for i in range(n)]
    return mg.Hours(
        tuple(T0 + HOUR * (i + 1) for i in range(n)),
        tuple(float(p) for p in prices),
        tuple(longs),
        tuple(0 for _ in range(n)),
    )


def oscillating(n=3000, seed=7):
    """A price that swings 8% either way every two days: any entry is soon sold above
    its cost by the trailing profit margin, so almost every trade wins."""
    rng = random.Random(seed)
    return [
        100 * (1 + 0.08 * math.sin(2 * math.pi * i / 48)) * (1 + rng.gauss(0, 0.003))
        for i in range(n)
    ]


def sawtooth(n=3000, seed=3):
    """A price that falls 15% over 97 hours, then rises 10% in 3, again and again;
    returns the prices and the hour before each rise."""
    rng = random.Random(seed)
    p, prices, before_rise = 100.0, [], []
    for i in range(n):
        if i % 100 < 97:
            p *= (0.85 ** (1 / 97)) * (1 + rng.gauss(0, 0.002))
        else:
            if i % 100 == 97:
                before_rise.append(i - 1)
            p *= 1.10 ** (1 / 3)
        prices.append(p)
    return prices, before_rise


# --- the three tests the brief asks for ---------------------------------------------


def test_a_candidate_with_no_skill_fails_even_with_a_hit_rate_above_90_percent():
    prices = oscillating()
    entries = random.Random(1).sample(range(len(prices) - 200), 60)
    result = mg.evaluate(hours_of(prices, entries), RULES, FEES, SETTINGS, "SYN")
    d = result.decision
    assert d.candidate.hit_rate >= 0.9 and d.candidate.entries >= 20
    assert d.candidate.mean_return > 0  # it even makes money after fees...
    assert not d.passed  # ...but no more than random entries do
    assert any("95th percentile" in why for why in d.failed)
    assert not any("hit rate" in why for why in d.failed)
    assert 5 < d.baseline["rank"] < 95


def test_a_candidate_with_a_planted_edge_passes():
    prices, before_rise = sawtooth()
    result = mg.evaluate(hours_of(prices, before_rise), RULES, FEES, SETTINGS, "SYN")
    d = result.decision
    assert d.passed, d.failed
    assert d.candidate.entries == len(before_rise) >= 20
    assert d.candidate.mean_return > d.baseline["at_percentile"]
    assert d.candidate.drawdown >= d.baseline["median_drawdown"]
    assert d.baseline["rank"] == 100.0


def test_the_same_seeds_give_the_same_results():
    prices = oscillating()
    entries = random.Random(1).sample(range(len(prices) - 200), 60)
    hours = hours_of(prices, entries)
    first = mg.evaluate(hours, RULES, FEES, SETTINGS, "SYN", seed=11).to_dict()
    again = mg.evaluate(hours, RULES, FEES, SETTINGS, "SYN", seed=11).to_dict()
    assert first == again
    assert first["baseline"]["seed"] == 11 and first["baseline"]["runs"] == 1000
    other = mg.evaluate(hours, RULES, FEES, SETTINGS, "SYN", seed=12).to_dict()
    assert other["baseline"]["median"] != first["baseline"]["median"]
    # the draws rest on random() alone, which Python keeps for a seed: pinned here
    assert eg.draw(random.Random(0), 1000, 5) == [844, 758, 421, 261, 513]
    assert eg.draw(random.Random(0), 3, 5) == [2, 0, 1]  # all of them when short


# --- the pass rule --------------------------------------------------------------------


def flat_slots(ret=0.0, drawdown=-0.05, size=500):
    """Random entries that each return ``ret`` with ``drawdown``."""
    trade = eg.Trade(ret, 1.0, drawdown, ret > 0)
    return {"X": eg.Slots(size, lambda i: trade)}


def trades(n=25, ret=0.02, drawdown=-0.01, hit=True, committed=1.0):
    return [eg.Trade(ret * committed, committed, drawdown, hit) for _ in range(n)]


def test_each_rule_fails_a_candidate_on_its_own():
    counts = {"X": 25}
    ok = eg.decide(trades(), flat_slots(), counts, SETTINGS, FEES)
    assert ok.passed and ok.failed == []
    # a. too few entries
    d = eg.decide(trades(n=19), flat_slots(), {"X": 19}, SETTINGS, FEES)
    assert d.failed == ["19 entries, 20 needed"]
    # b. mean return not above the minimum set
    strict = eg.GateSettings(min_return=0.03)
    d = eg.decide(trades(), flat_slots(), counts, strict, FEES)
    assert d.failed == ["mean return after fees +2.00% is not above +3.00%"]
    # c. capital-weighted return not above 0: small winners, one large loser
    mixed = trades(n=24, ret=0.02) + [eg.Trade(-2.0, 10.0, -0.01, False)]
    d = eg.decide(mixed, flat_slots(), counts, SETTINGS, FEES)
    assert d.candidate.mean_return > 0 > d.candidate.capital_return
    assert d.failed == [
        f"capital-weighted return after fees {d.candidate.capital_return:+.2%} is not "
        "above 0%"
    ]
    # d. not above the random entries' 95th percentile
    d = eg.decide(trades(), flat_slots(ret=0.02), counts, SETTINGS, FEES)
    assert d.failed == [
        "mean return after fees +2.00% is not above the random entries' 95th "
        "percentile +2.00%"
    ]
    # e. worst drawdown worse than the random entries' median
    d = eg.decide(trades(drawdown=-0.2), flat_slots(), counts, SETTINGS, FEES)
    assert d.failed == [
        "worst drawdown -20.00% is worse than the random entries' median -5.00%"
    ]
    # f. below the current model's own mean return
    d = eg.decide(trades(), flat_slots(), counts, SETTINGS, FEES, current=0.03)
    assert d.failed == [
        "mean return after fees +2.00% is below the current model's +3.00%"
    ]
    # no fee rate: never judged at a rate nobody states
    d = eg.decide(trades(), flat_slots(), counts, SETTINGS, None)
    assert d.failed == ["no fee rate: no exchange states one"]


def test_the_hit_rate_never_decides():
    counts = {"X": 25}
    no_wins = eg.decide(trades(hit=False), flat_slots(), counts, SETTINGS, FEES)
    assert no_wins.passed and no_wins.candidate.hit_rate == 0.0
    all_wins = eg.decide(
        trades(ret=-0.01, hit=True), flat_slots(), counts, SETTINGS, FEES
    )
    assert not all_wins.passed and all_wins.candidate.hit_rate == 1.0


def test_every_decision_reports_what_the_brief_lists():
    prices, before_rise = sawtooth()
    lines = "\n".join(
        mg.evaluate(hours_of(prices, before_rise), RULES, FEES, SETTINGS, "SYN").lines()
    )
    for text in (
        "PASSED",
        "mean return after fees",
        "capital-weighted",
        "worst drawdown",
        "hit rate",
        "random entries (1000 runs of 30 entries, seeds 0..999)",
        "median",
        "95th percentile",
        "the candidate is at the 100th percentile",
        "fees: 1.20% a side (Coinbase taker rate, the exchange's published standard "
        "rate; the account's own could not be read) and 0.05% slippage a fill",
        "trade rules",
    ):
        assert text in lines, text


def test_percentiles_interpolate_as_numpy_does():
    np = pytest.importorskip("numpy")
    values = [random.Random(5).gauss(0, 1) for _ in range(101)]
    for p in (0, 5, 50, 95, 97.5, 100):
        assert eg.percentile(values, p) == pytest.approx(
            float(np.percentile(values, p))
        )
    assert eg.percentile_rank(2.0, [1.0, 2.0, 3.0, 4.0]) == 37.5


def test_draws_are_distinct_moments():
    for seed in range(50):
        drawn = eg.draw(random.Random(seed), 40, 25)
        assert len(set(drawn)) == 25 and all(0 <= i < 40 for i in drawn)


# --- the replay follows the trader's rules ----------------------------------------------


def test_one_trade_by_hand():
    """Entry at 100; down to 97 (a hard DCA at -2.5%); up to 106 (the trailing line
    starts at +2.5% after a DCA) and 110; sold when 109 falls below the line."""
    fees = eg.Fees(0.01, "taker", "coinbase", "default", 0.0)
    hours = hours_of([100, 97, 97, 106, 110, 109], longs=[0] * 6)
    t = mg.replay(0, hours, RULES, fees)
    qty = 1.0 * 0.99 / 100  # 1% of a 100-unit account, after the 1% fee
    dca = qty * 97 * 2.0  # the position's value times the multiplier
    qty += dca * 0.99 / 97
    committed = 1.0 + dca
    proceeds = qty * 109 * 0.99
    assert t.end == 5
    assert t.committed == pytest.approx(committed)
    assert t.net == pytest.approx(proceeds - committed)
    assert t.drawdown == pytest.approx((97 - 1.0 / (0.99 / 100)) / (1.0 / (0.99 / 100)))
    assert t.hit


def test_neural_dca_and_the_24_hour_cap():
    fees = eg.Fees(0.0, "taker", "coinbase", "default", 0.0)
    # a long count of 4 below cost buys at stage 0 (neural level 4)
    t = mg.replay(0, hours_of([100, 99, 99], longs=[3, 4, 0]), RULES, fees)
    assert t.committed == pytest.approx(1.0 + 0.01 * 99 * 2)
    # falling 10% every hour, with room in the budget: two DCA buys in 24 h, no third
    roomy = mg.trade_rules({"max_coin_allocation_pct": 100})
    hours = hours_of([100 * 0.9**i for i in range(6)], longs=[0] * 6)
    q1 = 0.01 + 0.01 * 2  # after the first DCA (at 90): 0.03 coins
    two = 1.0 + 0.01 * 90 * 2 + q1 * 81 * 2
    assert mg.replay(0, hours, roomy, fees).committed == pytest.approx(two)
    three = mg.trade_rules({"max_coin_allocation_pct": 100, "max_dca_buys_per_24h": 3})
    assert mg.replay(0, hours, three, fees).committed > two
    # a trade open at the end is sold at the last close; open over 7 days, not a win
    late = mg.replay(0, hours_of([100] * 191 + [101], longs=[0] * 192), RULES, fees)
    assert late.end == 191 and late.net > 0 and not late.hit
    soon = mg.replay(0, hours_of([100] * 10 + [101], longs=[0] * 11), RULES, fees)
    assert soon.net > 0 and soon.hit


def test_the_rules_are_read_as_the_trader_reads_them(tmp_path, monkeypatch):
    import pt_paths
    import pt_trader

    saved = {
        "trade_start_level": 9,  # bounded to 7
        "start_allocation_pct": 0.5,
        "max_coin_allocation_pct": 12.5,
        "dca_multiplier": 1.5,
        "dca_levels": [-3, -6],
        "max_dca_buys_per_24h": "3",
        "pm_start_pct_no_dca": 4.0,
        "pm_start_pct_with_dca": 1.0,
        "trailing_gap_pct": 0.75,
    }
    path = tmp_path / "gui_settings.json"
    # a file the trader's check refuses gives the trader's defaults
    path.write_text(json.dumps(dict(saved, start_allocation_pct=0)), encoding="utf-8")
    assert mg.read_trade_rules(str(path)) == mg.trade_rules({})
    path.write_text(json.dumps(saved), encoding="utf-8")
    rules = mg.read_trade_rules(str(path))
    monkeypatch.setattr(pt_trader, "_GUI_SETTINGS_PATH", str(path))
    monkeypatch.setitem(pt_trader._gui_settings_cache, "mtime", None)
    monkeypatch.setattr(pt_trader, "_last_settings_mtime", None)
    monkeypatch.setattr(pt_paths, "config_dir", lambda: str(tmp_path))
    for name in (
        "TRADE_START_LEVEL",
        "START_ALLOC_PCT",
        "MAX_COIN_PCT",
        "DCA_MULTIPLIER",
        "DCA_LEVELS",
        "MAX_DCA_BUYS_PER_24H",
        "PM_START_PCT_NO_DCA",
        "PM_START_PCT_WITH_DCA",
        "TRAILING_GAP_PCT",
        "crypto_symbols",
        "main_dir",
        "base_paths",
    ):
        monkeypatch.setattr(pt_trader, name, getattr(pt_trader, name))
    pt_trader._refresh_paths_and_symbols()
    assert rules == mg.TradeRules(
        trade_start_level=pt_trader.TRADE_START_LEVEL,
        start_allocation_pct=pt_trader.START_ALLOC_PCT,
        max_coin_allocation_pct=pt_trader.MAX_COIN_PCT,
        dca_multiplier=pt_trader.DCA_MULTIPLIER,
        dca_levels=tuple(float(x) for x in pt_trader.DCA_LEVELS),
        max_dca_buys_per_24h=pt_trader.MAX_DCA_BUYS_PER_24H,
        pm_start_pct_no_dca=pt_trader.PM_START_PCT_NO_DCA,
        pm_start_pct_with_dca=pt_trader.PM_START_PCT_WITH_DCA,
        trailing_gap_pct=pt_trader.TRAILING_GAP_PCT,
    )
    assert rules.trade_start_level == 7 and rules.dca_levels == (-3.0, -6.0)


# --- the fee --------------------------------------------------------------------------


def test_the_fee_is_the_taker_rate_from_the_account_first():
    account = TradingFees(0.004, 0.006, "coinbase", "exchange")
    standard = TradingFees(0.006, 0.012, "coinbase", "default")
    asked = []

    def from_account(symbol, names):
        asked.append((symbol, list(names)))
        return account

    fees = eg.trading_fees(
        "BTC", ["coinbase", "kraken"], account=from_account, public=lambda c: standard
    )
    assert asked == [("BTC-USD", ["coinbase", "kraken"])]  # primary first
    assert (fees.rate, fees.order_type, fees.exchange, fees.source) == (
        0.006,
        "taker",
        "coinbase",
        "exchange",
    )
    assert "read from the account" in fees.text()
    # no account rate: the published standard rate, said so
    fees = eg.trading_fees(
        "BTC", ["coinbase"], account=lambda s, n: None, public=lambda c: standard
    )
    assert (fees.rate, fees.source) == (0.012, "default")
    assert "the account's own could not be read" in fees.text()
    # no exchange at all: none (the gate then refuses to judge)
    assert eg.trading_fees("BTC", [], public=lambda c: None) is None


def test_llm_scoring_uses_the_traders_fee():
    found = eg.Fees(0.012, "taker", "coinbase", "default", 0.0005)
    costs = llm_signals.trade_costs(None, "ETH", fees=lambda c: found)
    assert (costs.fee_rate, costs.slippage_rate, costs.fees) == (0.012, 0.0005, found)
    assert costs.source.startswith("Coinbase taker rate")
    from backtest.engine import CostModel

    fallback = llm_signals.trade_costs(None, "ETH", fees=lambda c: None)
    assert fallback.fee_rate == CostModel().fee_bps / 1e4  # no exchange states one


# --- the settings ---------------------------------------------------------------------


def test_the_gate_settings_and_their_bounds():
    assert training_settings.normalise({}) == {
        "holdout_min_signals": 20,
        "gate_min_return_after_fees": 0.0,
        "gate_baseline_runs": 1000,
        "gate_baseline_percentile": 95.0,
    }
    # the old hit-rate minimum is kept as saved, and read by nothing
    kept = training_settings.normalise({"holdout_min_hit_rate": 0.55})
    assert kept["holdout_min_hit_rate"] == 0.55
    assert "holdout_min_hit_rate" not in training_settings.DEFAULTS
    problem = training_settings.problem
    assert problem("gate_baseline_runs", 50) == "outside 100 .. 100000"
    assert problem("gate_baseline_runs", 250.5) == "not a whole number"
    assert problem("gate_baseline_percentile", 100) == "outside 50 .. 99.9"
    assert problem("gate_min_return_after_fees", "x") == "not a number"
    assert problem("gate_min_return_after_fees", -0.01) == ""


def test_no_gate_reads_a_hit_rate_minimum():
    for name in (
        "entry_gate.py",
        "model_gate.py",
        "llm_gate.py",
        "training_settings.py",
    ):
        with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
            code = f.read()
        assert "min_hit_rate" not in code.replace("holdout_min_hit_rate``, which", "")


# --- the trainer publishes only what passes ---------------------------------------------


@pytest.fixture
def trainer(monkeypatch, tmp_path, isolated_user_dirs):
    import helpers_trainer as ht
    import pt_pattern_trainer as ppt

    monkeypatch.chdir(tmp_path)
    ht.guard_trainer_children(monkeypatch, tmp_path)
    monkeypatch.setattr(ppt, "ENFORCE_GATE", True)
    monkeypatch.setattr(ppt, "gate_fees", lambda coin: FEES)
    return ppt


def force_gate(monkeypatch, ppt, passed):
    """The real gate runs; its decision is then set to ``passed``."""
    real = ppt.check_gate
    seen = []

    def forced(*args, **kwargs):
        result = real(*args, **kwargs)
        seen.append(kwargs.get("current"))
        result.decision.passed = passed
        result.decision.failed = [] if passed else ["forced by the test"]
        return result

    monkeypatch.setattr(ppt, "check_gate", forced)
    return seen


def folder_files(folder):
    import model_store

    return model_store.folder_file_hashes(str(folder))


def test_a_model_that_fails_is_not_published_and_the_model_in_use_is_put_back(
    trainer, monkeypatch, tmp_path
):
    import model_store
    import test_model_provenance as tmp_

    tmp_.seed()
    folder = tmp_path / "coin"
    force_gate(monkeypatch, trainer, True)
    first = tmp_.train_main(str(folder))
    assert first["model_id"] and first["gate"]["fees"]["rate"] == 0.012
    in_use = folder_files(folder)
    assert tmp_.manifest_of(first)["gate"]["passed"] is True
    # retrain on a later window: the new model fails, so the first is put back
    for name in model_store.model_file_names():
        os.remove(folder / name)
    os.remove(folder / "trainer_last_training_time.txt")
    seen = force_gate(monkeypatch, trainer, False)
    later = tmp_.train_main(str(folder), start=tmp_.START + timedelta(hours=24))
    assert later["model_id"] is None and later["kept_model_id"] == first["model_id"]
    assert later["gate"]["passed"] is False
    assert seen[0]["model_id"] == first["model_id"]  # judged against the model in use
    assert folder_files(folder) == in_use
    record = json.loads((folder / "model_gate.json").read_text(encoding="utf-8"))
    assert (record["published"], record["kept_model_id"]) == (False, first["model_id"])
    published = [
        n for n in os.listdir(model_store.pt_paths.strategy_models_dir()) if n[0] != "."
    ]
    assert published == [first["model_id"]]


def test_a_first_model_that_fails_is_kept_unpublished(trainer, monkeypatch, tmp_path):
    import model_store
    import test_model_provenance as tmp_

    tmp_.seed()
    folder = tmp_path / "coin"
    force_gate(monkeypatch, trainer, False)
    summary = tmp_.train_main(str(folder))
    assert summary["model_id"] is None and summary["kept_model_id"] is None
    assert folder_files(folder) is not None  # the files stay...
    assert model_store.find_published(str(folder), coin="BTC") is None  # ...unused


def test_check_gate_judges_the_model_in_use_and_changes_nothing(
    trainer, monkeypatch, tmp_path
):
    import pt_paths
    import test_model_provenance as tmp_

    tmp_.seed()
    folder = tmp_path / "coin"
    force_gate(monkeypatch, trainer, True)
    first = tmp_.train_main(str(folder))
    before = {n: os.path.getmtime(folder / n) for n in os.listdir(folder)}
    assert tmp_.run_main(str(folder), extra=("--offline", "--check-gate")) == 0
    assert {n: os.path.getmtime(folder / n) for n in os.listdir(folder)} == before
    path = pt_paths.data_file("training_results", "btc_gate_check.json")
    with open(path, encoding="utf-8") as f:
        record = json.load(f)
    assert record["model_id"] == first["model_id"]
    assert record["refit_matches_record"] is True  # the same validation fit
    assert record["gate"]["fees"]["rate"] == 0.012
    assert "a check of the model in use" in record["gate"]["note"]


def test_the_check_window_lists_each_coins_result(monkeypatch):
    import time
    import tkinter as tk

    import gate_check_ui

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk cannot start: {exc}")
    root.withdraw()
    prices, before_rise = sawtooth()
    passed = mg.evaluate(hours_of(prices, before_rise), RULES, FEES, SETTINGS, "SYN")
    asked = []

    def run_check(coin):
        asked.append(coin)
        if coin == "BTC":
            record = {"model_id": "BTC-1", "gate": passed.to_dict()}
            return {"code": 0, "record": record, "output": ""}
        return {
            "code": 1,
            "record": None,
            "output": "ERROR: ETH has no published model",
        }

    try:
        win = gate_check_ui.GateCheckWindow(root, ["BTC", "ETH"], run_check)
        win.withdraw()
        deadline = time.time() + 20
        while len(win.results) < 2 and time.time() < deadline:
            root.update()
            time.sleep(0.02)
        assert asked == ["BTC", "ETH"]  # one at a time, in order
        tree = win.table.tree
        assert tree.item("BTC", "values")[:2] == ("BTC", "BTC-1")
        assert tree.item("BTC", "values")[2].endswith("(100th percentile)")
        assert tree.item("BTC", "values")[3] == "passed"
        assert tree.item("ETH", "values")[3] == "ERROR: ETH has no published model"
        assert win.status_var.get() == "Done: 2 of 2 checked."
        tree.selection_set("BTC")
        win._show_detail()
        assert "random entries (1000 runs" in win.detail.get("1.0", "end")
    finally:
        root.destroy()


# --- the LLM gate ---------------------------------------------------------------------


def bars_from(prices, start_ms=T0 * 1000):
    """Hourly bars of a price path (high and low 0.1% either side)."""
    return [
        [start_ms + i * HOUR * 1000, p, p * 1.001, p * 0.999, p, 1.0]
        for i, p in enumerate(prices)
    ]


def llm_signals_at(store, bars, moments, model):
    for k in moments:
        price = bars[k - 1][4]
        s = store.add_signal(
            SignalRecord(
                ts=bars[k][0] / 1000.0,
                coin="SYN",
                provider="ollama",
                model=model,
                prompt_version=1,
                direction="BUY",
                price=price,
                price_target=price * 1.05,
                stop_loss=price * 0.95,
                time_horizon="SHORT",
                trading_mode="paper",
            )
        )
        store.set_outcome(s.id, "scored", 0.0, True, price)


def judge(store, bars, model):
    now = bars[-1][0] / 1000.0 + HOUR
    return llm_gate.evaluate(
        store,
        "ollama",
        model,
        1,
        bars_for=lambda coin, a, b: [r for r in bars if a <= r[0] <= b],
        costs_for=lambda coin: llm_signals.Costs(0.012, 0.0005, "test", FEES),
        training=training_settings.normalise({}),
        now=now,
    )


def test_llm_signals_are_judged_against_random_signals(tmp_path):
    store = LLMStore(str(tmp_path / "llm.db"))
    prices, before_rise = sawtooth()
    bars = bars_from(prices)
    llm_signals_at(store, bars, [i + 1 for i in before_rise], "edge")
    edge = judge(store, bars, "edge")
    assert edge.passed, edge.failed
    assert edge.candidate.entries == len(before_rise)
    status = llm_gate.gate_status(
        store, "ollama", "edge", 1, training_settings.normalise({})
    )
    assert status.passed and status.headline().endswith("(100th percentile)")
    noise = random.Random(4).sample(range(1, len(bars) - 30), 30)
    llm_signals_at(store, bars, noise, "noise")
    luck = judge(store, bars, "noise")
    assert not luck.passed
    assert not llm_gate.gate_status(
        store, "ollama", "noise", 1, training_settings.normalise({})
    ).passed
    # the same seeds, the same decision
    assert judge(store, bars, "noise").to_dict() == luck.to_dict()
