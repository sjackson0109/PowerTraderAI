"""
FDS-SIG-001: the signal-candidate audit script (section 12). Round N's files are in
``docs/dev/sig-audit/round-<N>/``; its report is ``docs/dev/SIG-AUDIT-REPORT-round-<N>.md``.

    python docs/dev/run_signal_audit.py rank --round 1 --ranking-date 2026-11-06
        step 0: on the round's exchange (the first in Settings, the primary first, that
        lists its markets, states daily quote volume and serves the round's history),
        rank its markets by 30-day quote volume, apply the exclusions and the history
        check, and write the ranking evidence (network: public market data only)
    python docs/dev/run_signal_audit.py draft --round 1 --window-end 2027-08-01T00:00:00Z
        a draft registration.json from round one's candidates (FDS-SIG-002) and step
        0's evidence, for the owner's review; committing it (in its own commit, before
        the window starts) is the registration
    python docs/dev/run_signal_audit.py freeze --round 1
        step 2: freeze.json, for its own commit (the code freeze)
    python docs/dev/run_signal_audit.py fetch --round 1
        step 3, after the window ends: every audited and input coin's candles from the
        registered exchange, each file's SHA-256 recorded (network: public data only)
    python docs/dev/run_signal_audit.py run --round 1 [--supersede "<what and why>"]
        steps 4 and 5: the refusals, every row, both Holm procedures, the verdicts
        (asserted and re-derived), the evidence series, results.json and the report

Every command needs ``POWERTRADER_HOME`` set to a scratch folder outside the repo (the
candle cache and every fetched file stay there). No API key is read, created or asked
for; the only network use is the exchanges' public market data, in ``rank`` and
``fetch``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(REPO, "app")
sys.path.insert(0, APP)

from signal_audit import candidates as cd  # noqa: E402
from signal_audit import round_one  # noqa: E402
from signal_audit import engine, ranking  # noqa: E402
from signal_audit import registration as reg  # noqa: E402
from signal_audit import report as rp  # noqa: E402
from signal_audit import stats as st  # noqa: E402

SEED = 20261106  # the registered seed of round one's draft (the owner may change it)
MDE_SIMS = 1000  # simulated rows per run of the two-sided minimum detectable effect
MDE_RUNS = 10  # independent runs (the owner, 2026-11-06: every simulation, ten times)


class Stop(RuntimeError):
    pass


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sandbox() -> str:
    raw = os.environ.get("POWERTRADER_HOME", "").strip()
    if not raw or not os.path.isabs(os.path.expanduser(raw)):
        raise Stop(
            "POWERTRADER_HOME must be set to an absolute scratch folder outside the "
            "repo, e.g. in PowerShell: $env:POWERTRADER_HOME = 'C:\\scratch\\sig-home'"
        )
    home = os.path.realpath(os.path.expanduser(raw))
    if os.path.commonpath([home, os.path.realpath(REPO)]) == os.path.realpath(REPO):
        raise Stop(f"POWERTRADER_HOME {raw} is inside the repo")
    return home


def _manager():
    from market_data import candles

    return candles._exchange_manager()


def _settings_order(manager) -> List[str]:
    return list(manager.exchange_names())


def _connector(manager, name):
    return ranking._connector(manager, name)


# --- step 0 ----------------------------------------------------------------------------


def rank(n: int, ranking_date: str, window_days: int) -> Dict[str, Any]:
    """Step 0 on the round's exchange: listing, 30-day quote volumes, ranking,
    exclusions, the history check and the replacements; the evidence is written to
    the round's folder (the candle files stay in the sandbox)."""
    import pandas as pd

    from market_data import candles

    sandbox()
    manager = _manager()
    names = _settings_order(manager)
    bars_needed = {
        "1h": window_days * 24 + 24 * 31,
        "4h": window_days * 6 + 6 * 31,
    }
    choice = ranking.choose_exchange(manager, names, bars_needed)
    if choice.exchange is None:
        raise Stop(
            f"no exchange in Settings can rank and serve the round: {choice.considered}"
        )
    conn = _connector(manager, choice.exchange)
    fetched_at = datetime.now(timezone.utc)
    day = datetime.strptime(ranking_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    problem = ranking.ranking_fetch_problem(ranking_date, fetched_at)
    if problem:
        raise Stop(problem)
    listing = conn.spot_markets()
    days = ranking.ranking_days(ranking_date)
    volumes = ranking.gather_volumes(
        conn, choice.exchange, listing, days, lambda t: print(t, flush=True)
    )
    answers = list(listing.answers)
    for v in volumes.values():
        if not isinstance(v, ranking.VolumeFailure):
            answers.extend(v.answers)
    exclusions = ranking.Exclusions()
    out = reg.round_dir(REPO, n)
    try:
        ranked = ranking.rank_markets(listing, volumes, ranking_date, exclusions)
    except ranking.RankingRefused as exc:
        # every market whose volume is not established, with its error or missing
        # days and the exchange, kept for diagnosis; nothing is ranked or registered
        _write_json(
            os.path.join(out, "ranking", "refused.json"),
            {
                "exchange": choice.exchange,
                "ranking_date": ranking_date,
                "fetched_at": reg.iso(fetched_at),
                "reason": str(exc),
                "markets": [e.to_dict() for e in exc.markets],
            },
        )
        raise Stop(f"ranking refused: {exc}")
    span_start = int(day.timestamp()) - ranking.RANKING_DAYS * 86400
    span_end = int(fetched_at.timestamp()) // 3600 * 3600
    files = {}

    def history_of(r: ranking.Ranked) -> ranking.History:
        try:
            df = candles.exchange_candles(
                r.coin,
                "1h",
                pd.Timestamp(span_start, unit="s", tz="UTC"),
                pd.Timestamp(span_end, unit="s", tz="UTC"),
                manager=manager,
                exchanges=[choice.exchange],
            )
        except Exception as exc:
            return ranking.History(False, 0, 0, 0, 1.0, 0, f"no 1h candles ({exc})")
        open_s = (df["open_time"].astype("int64") // 10**9).to_numpy()
        path = candles.cache_path(df.attrs["pair"], "1h", None, choice.exchange)
        files[r.coin] = {
            "pair": df.attrs["pair"],
            "file": os.path.relpath(path, sandbox()),
            "sha256": reg.file_sha256(path),
        }
        return ranking.check_history(open_s, span_start, span_end)

    selection = ranking.select_coins(ranked, history_of)
    os.makedirs(os.path.join(out, "ranking"), exist_ok=True)
    raw = ranking.write_raw_answers(
        os.path.join(out, "ranking", "raw.jsonl.gz"), answers
    )
    raw["file"] = os.path.relpath(raw["file"], REPO).replace("\\", "/")
    evidence = {
        "exchange": choice.exchange,
        "exchanges_considered": choice.considered,
        "ranking_date": ranking_date,
        "fetched_at": reg.iso(fetched_at),
        "quote": listing.quote,
        "measure": next(
            (
                v.measure
                for v in volumes.values()
                if not isinstance(v, ranking.VolumeFailure)
            ),
            None,
        ),
        "universe": f"every spot market {choice.exchange} lists against {listing.quote}, "
        "any status",
        "exclusions": exclusions.to_dict(),
        "ranked": [r.to_dict() for r in ranked],
        "coins": selection.coins,
        "replacements": selection.replacements,
        "considered_down_to_rank": selection.considered_down_to,
        "history": {
            "span": [
                reg.iso(datetime.fromtimestamp(span_start, timezone.utc)),
                reg.iso(datetime.fromtimestamp(span_end, timezone.utc)),
            ],
            "tolerance": {
                "max_missing_share": ranking.MAX_MISSING_SHARE,
                "max_gap_hours": ranking.MAX_GAP_HOURS,
            },
            "coins": selection.history,
            "files": files,
        },
        "raw_answers": raw,
    }
    _write_json(os.path.join(out, "ranking", "ranking.json"), evidence)
    print(
        f"round {n}: ranked on {choice.exchange}; coins {selection.coins}", flush=True
    )
    return evidence


# --- the draft registration -------------------------------------------------------------


def draft(
    n: int, window_end: str, window_start: Optional[str] = None
) -> Dict[str, Any]:
    """A draft registration from round one's candidates and step 0's evidence. Its
    window starts at the first 00:00 UTC after now (the registration is committed
    before then) unless given."""
    evidence = _read_json(
        os.path.join(reg.round_dir(REPO, n), "ranking", "ranking.json")
    )
    cands = round_one.candidates()
    coins = evidence["coins"]
    rows = reg.family_rows(cands, coins, reg.TIMEFRAMES, evidence["exchange"])
    F = reg.family_size(rows)
    start = window_start or reg.iso(reg.next_midnight(datetime.now(timezone.utc)))
    record = {
        "round": n,
        "spec": reg.SPEC,
        "candidates_spec": reg.CANDIDATES_SPEC,
        "kind": "round",
        "exchange": evidence["exchange"],
        "exchanges_considered": evidence["exchanges_considered"],
        "ranking": {
            "date": evidence["ranking_date"],
            "fetched_at": evidence["fetched_at"],
            "measure": evidence["measure"],
            "universe": evidence["universe"],
            "exclusions": evidence["exclusions"],
            "evidence": f"{reg.rel_round_dir(n)}/ranking/ranking.json",
            "raw_answers_sha256": evidence["raw_answers"]["file_sha256"],
        },
        "coins": coins,
        "input_coins": [round_one.INPUT_COIN],
        "replacements": evidence["replacements"],
        "timeframes": list(reg.TIMEFRAMES),
        "window": {"start": start, "end": window_end},
        "target": "the direction of the next bar: up if close[t+1] > close[t], down if "
        "lower; ties excluded and counted; a pair across a data gap skipped and counted",
        "candidates": [c.registration() for c in cands],
        "rows": [k.to_dict() for k in rows],
        "family": {
            "size": F,
            "error": st.FAMILY_ERROR,
            "statistics": list(st.STATISTICS),
            "either_statistic_qualifies": True,
        },
        "dependence": {
            "block_length": "max(one day of bars, ceil(2 tau)), tau the larger "
            "Bartlett-weighted autocorrelation time of the call indicators, lag "
            "M = min(one month of bars, floor(S/4))",
            "floors": {
                "calls": st.MIN_CALLS,
                "blocks": st.MIN_BLOCKS,
                "discordant": st.MIN_DISCORDANT,
                "abstained": st.MIN_ABSTAINED,
            },
            "bootstrap_draws": st.min_bootstrap_draws(F),
            "seed": SEED,
        },
        "power": {"mde_sims_per_run": MDE_SIMS, "mde_runs": MDE_RUNS},
        "previously_examined": [
            "BTC and ETH 1h and 4h bars 2023-01-01 to 2026-09-30 (PR #154 and batch 1)",
            "Coinbase 1h bars 2023-11-06 to 2026-11-05 of BTC, ETH, XRP, BNB, DOGE, SOL, "
            "ZEC, DASH, HYPE, ADA, AVAX, LINK, LTC (the gate diagnostic and the volume "
            "research)",
            "Coinbase 1h bars 2020-01-01 to 2025-05-06 of those coins (FDS-MH-001 phase B "
            "timing run)",
        ],
        "frozen_paths": list(reg.FROZEN_PATHS),
        "sandbox_home": os.environ.get("POWERTRADER_HOME"),
        "owner_decisions_pending": [],
    }
    path = os.path.join(reg.round_dir(REPO, n), "registration.json")
    _write_json(path, record)
    print(f"draft registration {path}: F = {F}, window {start} to {window_end}")
    return record


def freeze(n: int) -> None:
    path = os.path.join(reg.round_dir(REPO, n), "freeze.json")
    _write_json(path, {"round": n, "frozen_paths": list(reg.FROZEN_PATHS)})
    print(f"{path}: commit it on its own (the code freeze)")


# --- step 3 ----------------------------------------------------------------------------


def _bars_from_frame(coin: str, tf: str, df) -> cd.Bars:
    import numpy as np

    return cd.Bars(
        coin,
        tf,
        (df["open_time"].astype("int64") // 10**9).to_numpy(dtype=np.int64),
        df["high"].to_numpy(float),
        df["low"].to_numpy(float),
        df["close"].to_numpy(float),
        df["volume"].to_numpy(float),
    )


def _span(record: Mapping[str, Any], tf: str):
    start = reg.parse_time(record["window"]["start"])
    end = reg.parse_time(record["window"]["end"])
    warm = max(c["warmup_bars"] for c in record["candidates"])
    step = cd.TIMEFRAME_SECONDS[tf]
    return start - timedelta(seconds=(warm + 1) * step), end


def fetch(n: int) -> Dict[str, Any]:
    import pandas as pd

    from market_data import candles

    sandbox()
    folder = reg.round_dir(REPO, n)
    record = _read_json(os.path.join(folder, "registration.json"))
    if datetime.now(timezone.utc) < reg.parse_time(record["window"]["end"]):
        raise Stop("the window has not ended: no fetch before its end")
    manager = _manager()
    data_path = os.path.join(folder, "data.json")
    earlier = _read_json(data_path) if os.path.exists(data_path) else {}
    files = {}
    for coin in sorted(set(record["coins"]) | set(record["input_coins"])):
        for tf in record["timeframes"]:
            a, b = _span(record, tf)
            df = candles.exchange_candles(
                coin,
                tf,
                pd.Timestamp(a),
                pd.Timestamp(b),
                manager=manager,
                exchanges=[record["exchange"]],
            )
            path = candles.cache_path(df.attrs["pair"], tf, None, record["exchange"])
            sha = reg.file_sha256(path)
            key = f"{coin}/{tf}"
            if (
                key in earlier.get("files", {})
                and earlier["files"][key]["sha256"] != sha
            ):
                raise Stop(f"{key}: the candle file differs from its earlier record")
            files[key] = {
                "pair": df.attrs["pair"],
                "sha256": sha,
                "bars": int(len(df)),
                "file": os.path.relpath(path, sandbox()),
            }
    out = {
        "round": n,
        "exchange": record["exchange"],
        "files": files,
        "fetched_at": reg.iso(datetime.now(timezone.utc)),
    }
    _write_json(data_path, out)
    return out


# --- steps 4 and 5 ---------------------------------------------------------------------


def run(n: int, supersede: Optional[str] = None) -> Dict[str, Any]:
    import pandas as pd

    from market_data import candles

    sandbox()
    folder = reg.round_dir(REPO, n)
    state = reg.check_can_run(
        REPO,
        n,
        supersede=supersede,
        results_exist=os.path.exists(os.path.join(folder, "results.json")),
    )
    record = _read_json(os.path.join(folder, "registration.json"))
    data = _read_json(os.path.join(folder, "data.json"))
    for key, f in data["files"].items():
        path = os.path.join(sandbox(), f["file"])
        if reg.file_sha256(path) != f["sha256"]:
            raise Stop(f"{key}: the candle file differs from its fetch record")
    superseded = _supersede(folder, n, supersede)
    cands = round_one.by_key()
    bars: Dict[tuple, cd.Bars] = {}
    for key, f in data["files"].items():
        coin, tf = key.split("/")
        a, b = _span(record, tf)
        df = candles.exchange_candles(
            coin,
            tf,
            pd.Timestamp(a),
            pd.Timestamp(b),
            offline=True,
            exchanges=[record["exchange"]],
        )
        bars[(coin, tf)] = _bars_from_frame(coin, tf, df)
    start = int(reg.parse_time(record["window"]["start"]).timestamp())
    end = int(reg.parse_time(record["window"]["end"]).timestamp())
    rows_data = []
    from signal_audit.pairs import row_pairs

    for k in record["rows"]:
        key = engine.RowKey(k["candidate"], k["exchange"], k["coin"], k["timeframe"])
        c = cands[key.candidate]
        inputs = {ic: bars[(ic, key.timeframe)] for ic in c.input_coins}
        rows_data.append(
            (key, row_pairs(c, bars[(key.coin, key.timeframe)], inputs, start, end))
        )
    dep = record["dependence"]
    result = engine.evaluate_round(
        rows_data,
        draws=int(dep["bootstrap_draws"]),
        seed=int(dep["seed"]),
        family_error=float(record["family"]["error"]),
        mde_sims=int(record["power"]["mde_sims_per_run"]),
        mde_replicates=int(record["power"]["mde_runs"]),
    )
    results = rp.results_record(result, n, state.registration_sha256, state.to_dict())
    os.makedirs(os.path.join(folder, "series"), exist_ok=True)
    for row in result.rows:
        k = row.key
        name = f"{k.candidate}_{k.exchange}_{k.coin}_{k.timeframe}.csv"
        with open(
            os.path.join(folder, "series", name), "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(rp.series_csv(row))
    _write_json(os.path.join(folder, "results.json"), results)
    text = rp.report_markdown(record, results, superseded)
    with open(
        os.path.join(REPO, "docs", "dev", f"SIG-AUDIT-REPORT-round-{n}.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(text)
    return results


def _supersede(folder: str, n: int, note: Optional[str]) -> List[Dict[str, Any]]:
    """After results only defect fixes, with the earlier verdicts kept beside the new
    ones (section 12, step 6)."""
    path = os.path.join(folder, "results.json")
    old_dir = os.path.join(folder, "superseded")
    earlier = []
    if os.path.isdir(old_dir):
        for name in sorted(os.listdir(old_dir)):
            p = os.path.join(old_dir, name, "results.json")
            if os.path.exists(p):
                old = _read_json(p)
                old["note"] = _read_json(os.path.join(old_dir, name, "note.json"))[
                    "note"
                ]
                old["commit"] = (old.get("state") or {}).get("head")
                earlier.append(old)
    if not os.path.exists(path):
        return earlier
    if not (note and note.strip()):
        raise Stop('results exist: a re-run needs --supersede "<what changed and why>"')
    old = _read_json(path)
    target = os.path.join(
        old_dir, f"{len(earlier) + 1}-{(old.get('state') or {}).get('head', 'x')[:7]}"
    )
    os.makedirs(target)
    _write_json(os.path.join(target, "note.json"), {"note": note.strip()})
    shutil.move(path, os.path.join(target, "results.json"))
    old["note"] = note.strip()
    old["commit"] = (old.get("state") or {}).get("head")
    return earlier + [old]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("rank", "draft", "freeze", "fetch", "run"):
        p = sub.add_parser(name)
        p.add_argument("--round", type=int, required=True)
        if name == "rank":
            p.add_argument("--ranking-date", required=True)
            p.add_argument("--window-days", type=int, default=270)
        if name == "draft":
            p.add_argument("--window-end", required=True)
            p.add_argument("--window-start")
        if name == "run":
            p.add_argument("--supersede")
    args = parser.parse_args(argv)
    try:
        if args.command == "rank":
            rank(args.round, args.ranking_date, args.window_days)
        elif args.command == "draft":
            draft(args.round, args.window_end, args.window_start)
        elif args.command == "freeze":
            freeze(args.round)
        elif args.command == "fetch":
            fetch(args.round)
        else:
            run(args.round, args.supersede)
    except (Stop, reg.Refused) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
