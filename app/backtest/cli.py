"""
Backtest CLI::

    python -m app.backtest --strategy STRAT-000 --symbol BTCUSDT --tf 1h \\
        --start 2023-01-01 --end 2026-09-30 [--overlays OVL-ATR,OVL-COOLDOWN] \\
        [--out results.json]

Writes JSON KPIs (in-sample and out-of-sample, each with the buy-and-hold
benchmark) and a trades CSV next to it. ``--end`` is exclusive (bars with
``open_time < end``). Candles come from the cache / Binance public klines, or
from ``--candles-file`` (a cache-format CSV; no network).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.engine import CostModel, evaluate_split
from market_data.candles import (
    BinanceKlines,
    CandleDataError,
    cache_path,
    file_sha256,
    get_candles,
    load_candles_csv,
)
from market_data.timeframes import candle_timeframe_seconds, timeframe_seconds
from strategies.catalogue import CatalogueError, ParamError
from strategies.factory import build_runner, parse_overlay_ids

DISCLAIMER = (
    "Fills at the next bar open, with fees and slippage; indicator history for the "
    "out-of-sample window is taken from before the split but never traded."
)


def _trades_rows(result_by_sample: Dict[str, Any]) -> List[dict]:
    rows = []
    for sample, parts in result_by_sample.items():
        for kind in ("strategy", "buy_and_hold"):
            if kind not in parts:  # a window refused with LOOKAHEAD_MODEL
                continue
            for t in parts[kind].trades:
                row = asdict(t)
                row.update(sample=sample, series=kind)
                rows.append(row)
    return rows


def _section(parts: Dict[str, Any]) -> Dict[str, Any]:
    if "refused" in parts:
        bench = parts["buy_and_hold"]
        return {
            "bars": bench.bars,
            "from": bench.first_bar.isoformat(),
            "to": bench.last_bar.isoformat(),
            "refused": parts["refused"],
            "strategy": None,
            "buy_and_hold": bench.kpis,
        }
    strat, bench = parts["strategy"], parts["buy_and_hold"]
    return {
        "bars": strat.bars,
        "from": strat.first_bar.isoformat(),
        "to": strat.last_bar.isoformat(),
        "strategy": strat.kpis,
        "buy_and_hold": bench.kpis,
        "slippage_cost": {
            "strategy": strat.slippage_cost,
            "buy_and_hold": bench.slippage_cost,
        },
        "bars_missing": dict(strat.bars_missing),
    }


def _check_same_bars(candles: pd.DataFrame, cached, args) -> None:
    """With --candles-file the run trades the file's bars while a multi-timeframe
    strategy reads the cache: refuse unless the cache's bars of the run's timeframe are
    the file's bars wherever both exist (another symbol, venue or edit would mix two
    series without a word)."""
    if cached is None or cached.empty:
        return  # nothing to compare: those decisions are reported as missing bars
    cols = ["open", "high", "low", "close"]
    both = candles.merge(cached, on="open_time", suffixes=("", "_cache"))
    differ = sum(
        (both[c] != both[f"{c}_cache"]).sum() for c in cols  # exact: same source
    )
    if both.empty or differ:
        raise ValueError(
            f"the cache's {args.symbol} {args.tf} bars "
            f"({cache_path(args.symbol, args.tf, args.cache_dir)}) are not the bars of "
            f"{args.candles_file} (overlap {len(both)} bars, {differ} values differ): "
            "the strategy's other timeframes would come from a different series"
        )


def run(args: argparse.Namespace) -> Dict[str, Any]:
    overlay_specs = parse_overlay_ids(args.overlays)
    params = json.loads(args.params) if args.params else {}
    overlay_params = json.loads(args.overlay_params) if args.overlay_params else {}
    for spec in overlay_specs:
        spec["params"] = overlay_params.get(spec["id"], {})

    strategy_bars: Dict[str, pd.DataFrame] = {}

    def factory():
        runner = build_runner(args.strategy, params, overlay_specs)
        if strategy_bars:  # a strategy that reads other timeframes gets the run's own
            runner.strategy.use_bars(strategy_bars)
        return runner

    probe = factory()  # fail fast on unknown ids / bad params before touching data
    supported = getattr(probe.strategy, "supported_bar_seconds", None)
    if supported is not None and timeframe_seconds(args.tf) not in supported:
        raise ValueError(
            f"{args.strategy} cannot decide on {args.tf} bars "
            f"(it supports {sorted(supported)} s)"
        )
    model_symbol = getattr(probe.strategy, "model_symbol", None)
    if model_symbol is not None and model_symbol.upper() != args.symbol.upper():
        raise ValueError(
            f"the strategy's model was trained on {model_symbol}; this run is "
            f"{args.symbol} (use --symbol)"
        )
    # a strategy timeframe (the candle layer also accepts the candle-only "1w")
    timeframe_seconds(args.tf)

    source: Dict[str, Any]
    if args.candles_file:
        candles = load_candles_csv(args.candles_file, args.tf)
        source = {
            "kind": "file",
            "path": os.path.abspath(args.candles_file),
            "sha256": file_sha256(args.candles_file),
        }
        if args.start or args.end:
            mask = pd.Series(True, index=candles.index)
            if args.start:
                mask &= candles["open_time"] >= pd.Timestamp(args.start, tz="UTC")
            if args.end:
                mask &= candles["open_time"] < pd.Timestamp(args.end, tz="UTC")
            candles = candles[mask].reset_index(drop=True)
            candles.attrs["report"] = load_candles_csv(
                args.candles_file, args.tf
            ).attrs["report"]
    else:
        if not (args.start and args.end):
            raise SystemExit(
                "--start and --end are required unless --candles-file is given"
            )
        candles = get_candles(
            args.symbol,
            args.tf,
            args.start,
            args.end,
            cache_dir=args.cache_dir,
            fetcher=BinanceKlines(),
            offline=args.offline,
        )
        path = cache_path(args.symbol, args.tf, args.cache_dir)
        source = {
            "kind": "binance_klines_cache",
            "path": path,
            "sha256": file_sha256(path) if os.path.isfile(path) else None,
        }
    if len(candles) < 50:
        raise SystemExit(f"only {len(candles)} candles available; need at least 50")
    report = candles.attrs.get("report")
    extra_tfs = getattr(probe.strategy, "candle_timeframes", ())
    if extra_tfs:
        # the other timeframes come from the same place as the run's candles (the cache
        # or --cache-dir; offline with --candles-file), from far enough back that the
        # first bar has a closed bar in every timeframe
        first, last = candles["open_time"].iloc[0], candles["open_time"].iloc[-1]
        back = pd.Timedelta(
            seconds=2 * max(candle_timeframe_seconds(t) for t in extra_tfs)
        )
        end = last + pd.Timedelta(seconds=timeframe_seconds(args.tf))
        offline = bool(args.offline or args.candles_file)
        for tf in extra_tfs:
            if offline:  # what the cache holds; a shortfall is reported as missing bars
                frame = load_candles_csv(
                    cache_path(args.symbol, tf, args.cache_dir), tf
                )
                keep = (frame["open_time"] >= first - back) & (frame["open_time"] < end)
                frame = frame[keep].reset_index(drop=True)
            else:
                frame = get_candles(
                    args.symbol,
                    tf,
                    first - back,
                    end,
                    cache_dir=args.cache_dir,
                    fetcher=BinanceKlines(),
                )
            strategy_bars[tf] = frame
        if args.candles_file:
            _check_same_bars(candles, strategy_bars.get(args.tf), args)
        source["strategy_bars"] = {}
        for tf, frame in strategy_bars.items():
            path = cache_path(args.symbol, tf, args.cache_dir)
            source["strategy_bars"][tf] = {
                "bars": len(frame),
                "path": path,
                "sha256": file_sha256(path) if os.path.isfile(path) else None,
            }
        if source["kind"] == "binance_klines_cache":
            # online, loading the history before the window can extend the run's own
            # cache file: its hash is the one of the file as the run leaves it
            path = source["path"]
            source["sha256"] = file_sha256(path) if os.path.isfile(path) else None

    cost = CostModel(args.fee_bps, args.slippage_bps, args.size_fraction)
    split = evaluate_split(candles, factory, args.symbol, args.tf, cost, args.split)
    strategy = factory().strategy
    results = {
        "strategy_id": args.strategy,
        "params": strategy.params,
        "overlays": overlay_specs,
        "symbol": args.symbol,
        "timeframe": args.tf,
        "data": {
            "source": source,
            "candles": len(candles),
            "first": candles["open_time"].iloc[0].isoformat(),
            "last": candles["open_time"].iloc[-1].isoformat(),
            "gaps": report.to_dict() if report is not None else None,
        },
        "cost_model": {
            "fee_bps": cost.fee_bps,
            "slippage_bps": cost.slippage_bps,
            "size_fraction": cost.size_fraction,
        },
        "split": {
            "in_sample_fraction": args.split,
            "out_of_sample_starts": candles["open_time"]
            .iloc[split["out_of_sample"]["window"][0]]
            .isoformat(),
        },
        "in_sample": _section(split["in_sample"]),
        "out_of_sample": _section(split["out_of_sample"]),
        "note": DISCLAIMER,
    }
    if getattr(strategy, "model_id", None):  # a trained model (STRAT-003)
        results["model"] = {
            "model_id": strategy.model_id,
            "symbol": strategy.model_symbol,
            "train_start": strategy.model_window[0],
            "train_end": strategy.model_window[1],
        }
    results["_trades"] = _trades_rows(split)
    return results


def _fmt(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:,.2f}"


def print_summary(results: Dict[str, Any], out=print) -> None:
    out(
        f"{results['strategy_id']} {results['symbol']} {results['timeframe']}  "
        f"overlays={[o['id'] for o in results['overlays']] or 'none'}  "
        f"candles={results['data']['candles']}"
    )
    for name in ("in_sample", "out_of_sample"):
        sec = results[name]
        out(f"  {name}: {sec['from'][:10]} -> {sec['to'][:10]} ({sec['bars']} bars)")
        if sec.get("refused"):
            out(f"    REFUSED: {sec['refused']}")
        if sec.get("bars_missing"):
            out(
                f"    WARNING: decisions held for missing bars: {sec['bars_missing']} "
                "(not a signal; the data does not cover the window)"
            )
        for label in ("strategy", "buy_and_hold"):
            k = sec[label]
            if k is None:
                continue
            out(
                f"    {label:13s} ret {_fmt(k['total_return_pct'])}%  maxDD {_fmt(k['max_drawdown_pct'])}%  "
                f"sharpe {_fmt(k['sharpe'])}  trades {k['trade_count']}  fees ${_fmt(k['fees_paid'])}"
                + (
                    f"  vs B&H {_fmt(k['vs_buy_hold_pct'])}pp"
                    if label == "strategy"
                    else ""
                )
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.backtest", description=__doc__.split("\n\n")[0]
    )
    p.add_argument("--strategy", required=True, help="catalogue id, e.g. STRAT-000")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--tf", default="1h")
    p.add_argument("--start", help="YYYY-MM-DD (UTC)")
    p.add_argument("--end", help="YYYY-MM-DD (UTC, exclusive)")
    p.add_argument(
        "--overlays", help="comma separated overlay ids, e.g. OVL-ATR,OVL-COOLDOWN"
    )
    p.add_argument(
        "--params",
        help="strategy parameter overrides as JSON, e.g. '{\"fast_len\": 10}'",
    )
    p.add_argument("--overlay-params", help="overlay overrides as JSON keyed by id")
    p.add_argument("--fee-bps", type=float, default=10.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--size-fraction", type=float, default=1.0)
    p.add_argument(
        "--split", type=float, default=0.7, help="in-sample fraction (default 0.7)"
    )
    p.add_argument(
        "--candles-file", help="cache-format CSV to use instead of the cache/network"
    )
    p.add_argument(
        "--cache-dir", help="candle cache directory (default hub_data/candles)"
    )
    p.add_argument("--offline", action="store_true", help="never touch the network")
    p.add_argument("--out", help="write JSON results here (trades CSV alongside)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = run(args)
    except (CatalogueError, ParamError, CandleDataError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    trades = results.pop("_trades")
    print_summary(results)
    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        trades_path = os.path.splitext(out_path)[0] + "_trades.csv"
        pd.DataFrame(trades).to_csv(trades_path, index=False)
        print(f"wrote {out_path} and {trades_path}")
    return 0
