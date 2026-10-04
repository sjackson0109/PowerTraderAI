"""FDS-121 acceptance 8 + 9: the CLI runs on a cached fixture and writes JSON + CSV."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

from backtest import cli
from backtest.kpis import KPI_KEYS

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(APP_DIR)
FIXTURE = os.path.join(HERE, "fixtures", "BTCUSDT_1h.csv")


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "results.json")

    def base(self, *extra):
        return (
            "--strategy",
            "STRAT-000",
            "--symbol",
            "BTCUSDT",
            "--tf",
            "1h",
            "--candles-file",
            FIXTURE,
            "--out",
            self.out,
            *extra,
        )

    def test_runs_on_the_cached_fixture_and_writes_json_and_trades_csv(self):
        code, stdout, stderr = run_cli(*self.base())
        self.assertEqual(code, 0, stderr)
        self.assertTrue(os.path.isfile(self.out))
        trades_path = os.path.join(self.tmp.name, "results_trades.csv")
        self.assertTrue(os.path.isfile(trades_path))
        self.assertIn("in_sample", stdout)
        self.assertIn("out_of_sample", stdout)

        with open(self.out, encoding="utf-8") as f:
            res = json.load(f)
        self.assertEqual(
            (res["strategy_id"], res["symbol"], res["timeframe"]),
            ("STRAT-000", "BTCUSDT", "1h"),
        )
        for sample in ("in_sample", "out_of_sample"):
            for series in ("strategy", "buy_and_hold"):
                self.assertEqual(
                    set(res[sample][series]), set(KPI_KEYS), f"{sample}.{series}"
                )
        self.assertIsNotNone(res["in_sample"]["strategy"]["vs_buy_hold_pct"])
        self.assertIsNotNone(res["out_of_sample"]["strategy"]["vs_buy_hold_pct"])
        self.assertEqual(
            res["cost_model"],
            {"fee_bps": 10.0, "slippage_bps": 5.0, "size_fraction": 1.0},
        )

        trades = pd.read_csv(trades_path)
        self.assertTrue(
            {"sample", "series", "entry_time", "exit_time", "pnl", "exit_rule"}
            <= set(trades.columns)
        )
        self.assertEqual(set(trades["sample"]), {"in_sample", "out_of_sample"})
        self.assertEqual(set(trades["series"]), {"strategy", "buy_and_hold"})

    def test_results_record_the_data_provenance(self):
        run_cli(*self.base())
        with open(self.out, encoding="utf-8") as f:
            data = json.load(f)["data"]
        import hashlib

        self.assertEqual(
            data["source"]["sha256"],
            hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest(),
        )
        self.assertEqual(data["candles"], 1513)
        self.assertEqual(data["gaps"]["missing_bars"], 0)

    def test_split_is_seventy_thirty_by_time(self):
        run_cli(*self.base())
        with open(self.out, encoding="utf-8") as f:
            res = json.load(f)
        n = res["data"]["candles"]
        self.assertEqual(res["in_sample"]["bars"], int(n * 0.7))
        self.assertEqual(res["out_of_sample"]["bars"], n - int(n * 0.7))
        self.assertLess(res["in_sample"]["to"], res["out_of_sample"]["from"])

    def test_output_is_deterministic(self):
        run_cli(*self.base())
        first = open(self.out, encoding="utf-8").read()
        run_cli(*self.base())
        self.assertEqual(first, open(self.out, encoding="utf-8").read())

    def test_cost_and_param_options_are_applied(self):
        run_cli(*self.base("--fee-bps", "0", "--slippage-bps", "0"))
        free = json.load(open(self.out, encoding="utf-8"))
        run_cli(*self.base("--fee-bps", "50", "--slippage-bps", "25"))
        dear = json.load(open(self.out, encoding="utf-8"))
        self.assertEqual(free["in_sample"]["strategy"]["fees_paid"], 0.0)
        self.assertGreater(dear["in_sample"]["strategy"]["fees_paid"], 0.0)
        self.assertGreater(
            free["in_sample"]["strategy"]["total_return_pct"],
            dear["in_sample"]["strategy"]["total_return_pct"],
        )
        run_cli(*self.base("--params", '{"fast_len": 5, "slow_len": 20}'))
        tuned = json.load(open(self.out, encoding="utf-8"))
        self.assertEqual(tuned["params"], {"fast_len": 5, "slow_len": 20})

    def test_start_and_end_select_the_window(self):
        run_cli(*self.base("--start", "2026-06-20", "--end", "2026-07-20"))
        res = json.load(open(self.out, encoding="utf-8"))
        self.assertEqual(res["data"]["candles"], 30 * 24)
        self.assertTrue(res["data"]["first"].startswith("2026-06-20"))

    def test_unknown_strategy_overlay_or_bad_params_exit_2_with_a_message(self):
        for argv, needle in (
            (("--strategy", "STRAT-404", "--candles-file", FIXTURE), "STRAT-404"),
            (
                (
                    "--strategy",
                    "STRAT-000",
                    "--overlays",
                    "OVL-NOPE",
                    "--candles-file",
                    FIXTURE,
                ),
                "OVL-NOPE",
            ),
            (
                (
                    "--strategy",
                    "STRAT-000",
                    "--params",
                    '{"fast_len": 1}',
                    "--candles-file",
                    FIXTURE,
                ),
                "fast_len",
            ),
            (
                (
                    "--strategy",
                    "STRAT-000",
                    "--params",
                    '{"bogus": 1}',
                    "--candles-file",
                    FIXTURE,
                ),
                "bogus",
            ),
        ):
            with self.subTest(argv=argv):
                code, _, stderr = run_cli(*argv)
                self.assertEqual(code, 2)
                self.assertIn(needle, stderr)

    def test_a_main_strategy_cannot_be_used_as_an_overlay(self):
        code, _, stderr = run_cli(
            "--strategy",
            "STRAT-000",
            "--overlays",
            "STRAT-000",
            "--candles-file",
            FIXTURE,
        )
        self.assertEqual(code, 2)
        self.assertIn("not a risk overlay", stderr)

    def test_offline_uses_only_the_cache_and_never_the_network(self):
        cache = os.path.join(self.tmp.name, "cache")
        os.makedirs(cache)
        shutil.copy(FIXTURE, os.path.join(cache, "BTCUSDT_1h.csv"))
        code, _, stderr = run_cli(
            "--strategy",
            "STRAT-000",
            "--symbol",
            "BTCUSDT",
            "--tf",
            "1h",
            "--start",
            "2026-06-10",
            "--end",
            "2026-08-01",
            "--cache-dir",
            cache,
            "--offline",
            "--out",
            self.out,
        )
        self.assertEqual(code, 0, stderr)
        res = json.load(open(self.out, encoding="utf-8"))
        self.assertEqual(res["data"]["source"]["kind"], "binance_klines_cache")
        # a range the cache cannot satisfy is an error, not a download
        code, _, stderr = run_cli(
            "--strategy",
            "STRAT-000",
            "--symbol",
            "BTCUSDT",
            "--tf",
            "1h",
            "--start",
            "2025-01-01",
            "--end",
            "2026-08-01",
            "--cache-dir",
            cache,
            "--offline",
        )
        self.assertEqual(code, 2)
        self.assertIn("offline", stderr)

    def test_needs_start_and_end_without_a_candles_file(self):
        with self.assertRaises(SystemExit):
            run_cli("--strategy", "STRAT-000")

    def test_runs_as_python_dash_m_app_dot_backtest(self):
        env = dict(os.environ, POWERTRADER_ENV="test")
        proc = subprocess.run(
            [sys.executable, "-m", "app.backtest", *self.base()],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("out_of_sample", proc.stdout)
        self.assertTrue(os.path.isfile(self.out))


class SyntheticExampleIsLabelledTests(unittest.TestCase):
    def test_the_random_price_example_is_marked_demo_only(self):
        path = os.path.join(APP_DIR, "backtesting_engine.py")
        source = open(path, encoding="utf-8").read()
        main_block = source[source.index('if __name__ == "__main__":') :]
        self.assertIn("DEMO ONLY - SYNTHETIC DATA", source)
        self.assertIn("DEMO ONLY - SYNTHETIC DATA", main_block)  # printed when run
        self.assertIn("python -m app.backtest", source)

    def test_no_new_test_uses_the_random_price_example_to_judge_performance(self):
        this_file = os.path.basename(__file__)
        for name in os.listdir(HERE):
            if name.startswith("test_") and name.endswith(".py") and name != this_file:
                text = open(os.path.join(HERE, name), encoding="utf-8").read()
                self.assertFalse("from backtesting_engine" in text, name)
                self.assertFalse("import backtesting_engine" in text, name)


if __name__ == "__main__":
    unittest.main()
