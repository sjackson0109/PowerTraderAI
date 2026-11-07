"""
FDS-SIG-001: the signal-candidate audit script (section 12). Round N's files are in
``docs/dev/sig-audit/round-<N>/``; its report is ``docs/dev/SIG-AUDIT-REPORT-round-<N>.md``.

    python docs/dev/run_signal_audit.py rank --round 1 --ranking-date 2026-11-06
        step 0: on the round's exchange (the first in Settings, the primary first, that
        lists its markets, states daily quote volume and serves the round's history),
        rank its markets by 30-day quote volume, apply the exclusions and the history
        check, and write the ranking evidence (network: public market data only)
    python docs/dev/run_signal_audit.py draft --round 1 --window-end 2027-08-01T00:00:00Z
                                          [--replaces <cancelled round>]
        a draft registration.json from round one's candidates (FDS-SIG-002) and step
        0's evidence, for the owner's review; committing it (in its own commit, before
        the window starts) is the registration. A replacement for a cancelled round
        names it (its cancellation committed first)
    python docs/dev/run_signal_audit.py freeze --round 1
        step 2: freeze.json, for its own commit (the code freeze)
    python docs/dev/run_signal_audit.py fetch --round 1
        step 3, after the window ends: every audited and input coin's candles from the
        registered exchange, checked against a second fetch from it without the cache
        and against any earlier record, written once as compressed window-scoped
        snapshots in the round's folder (candles/), each with its bars' and its file's
        SHA-256, for the results commit (network: public data only)
    python docs/dev/run_signal_audit.py run --round 1 [--supersede "<what and why>"]
        steps 4 and 5: the refusals, the snapshots checked against their record (the
        candle cache is not read), every row, both Holm procedures, the verdicts
        (asserted and re-derived), the evidence series, results.json and the report.
        After results, only a defect fix runs, with --supersede: the earlier results,
        series and report are kept in superseded/ with their SHA-256
    python docs/dev/run_signal_audit.py cancel --round 1 --defect "<what and why>"
        step 6, a material defect found before results: cancellation.json, for its own
        commit; the round is then never run, and a new registration in a later round
        (draft --replaces 1) takes a window that starts after its own registration
    python docs/dev/run_signal_audit.py verify --round 1 [--refetch]
        the independent check: every snapshot against its record and the registration,
        the results re-derived from them with the frozen code and compared with
        results.json, and with --refetch each snapshot against the exchange again

Every command needs ``POWERTRADER_HOME`` set to a scratch folder outside the repo (the
candle cache stays there; the round's evidence, the ranking answers and the candle
snapshots, is written to the round's folder for its commits). No API key is read,
created or asked for; the only network use is the exchanges' public market data, in
``rank``, ``fetch`` and ``verify --refetch``. A registered round runs from its own
research worktree at the freeze commit (FDS-SIG-001 section 12.1).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(REPO, "app")
sys.path.insert(0, APP)

from signal_audit import round_one  # noqa: E402
from signal_audit import engine, evidence, ranking  # noqa: E402
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
        rows = evidence.rows_of(df)
        # the bars read, not the cache file: the cache is shared and grows
        files[r.coin] = {
            "exchange": df.attrs["exchange"],
            "pair": df.attrs["pair"],
            "bars": len(rows),
            "first_open_ms": rows[0][0] if rows else None,
            "last_open_ms": rows[-1][0] if rows else None,
            "sha256": evidence.bars_sha256(rows),
        }
        return ranking.check_history(open_s, span_start, span_end)

    selection = ranking.select_coins(ranked, history_of)
    os.makedirs(os.path.join(out, "ranking"), exist_ok=True)
    raw = ranking.write_raw_answers(
        os.path.join(out, "ranking", "raw.jsonl.gz"), answers
    )
    raw["file"] = os.path.relpath(raw["file"], REPO).replace("\\", "/")
    record = {
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
    _write_json(os.path.join(out, "ranking", "ranking.json"), record)
    print(
        f"round {n}: ranked on {choice.exchange}; coins {selection.coins}", flush=True
    )
    return record


# --- the draft registration -------------------------------------------------------------


def draft(
    n: int,
    window_end: str,
    window_start: Optional[str] = None,
    replaces: Optional[int] = None,
) -> Dict[str, Any]:
    """A draft registration from round one's candidates and step 0's evidence. Its
    window starts at the first 00:00 UTC after now (the registration is committed
    before then) unless given. ``replaces`` names the cancelled round it replaces
    (section 12, step 6), whose cancellation must be committed. A round that is
    cancelled or already registered is not drafted again."""
    folder = reg.round_dir(REPO, n)
    if os.path.exists(os.path.join(folder, reg.CANCELLATION)):
        raise Stop(f"round {n} is cancelled: its replacement is a later round")
    if reg.git(REPO, "ls-files", "--", f"{reg.rel_round_dir(n)}/registration.json"):
        raise Stop(f"round {n} already has a committed registration")
    replacement = reg.replacement_record(REPO, replaces) if replaces else None
    ranked_record = _read_json(
        os.path.join(reg.round_dir(REPO, n), "ranking", "ranking.json")
    )
    cands = round_one.candidates()
    coins = ranked_record["coins"]
    rows = reg.family_rows(cands, coins, reg.TIMEFRAMES, ranked_record["exchange"])
    F = reg.family_size(rows)
    start = window_start or reg.iso(reg.next_midnight(datetime.now(timezone.utc)))
    record = {
        "round": n,
        "spec": reg.SPEC,
        "candidates_spec": reg.CANDIDATES_SPEC,
        "kind": "round",
        "exchange": ranked_record["exchange"],
        "exchanges_considered": ranked_record["exchanges_considered"],
        "ranking": {
            "date": ranked_record["ranking_date"],
            "fetched_at": ranked_record["fetched_at"],
            "measure": ranked_record["measure"],
            "universe": ranked_record["universe"],
            "exclusions": ranked_record["exclusions"],
            "evidence": f"{reg.rel_round_dir(n)}/ranking/ranking.json",
            "raw_answers_sha256": ranked_record["raw_answers"]["file_sha256"],
        },
        "coins": coins,
        "input_coins": [round_one.INPUT_COIN],
        "replacements": ranked_record["replacements"],
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
    if replacement:
        record["replaces"] = replacement
    path = os.path.join(reg.round_dir(REPO, n), "registration.json")
    _write_json(path, record)
    print(f"draft registration {path}: F = {F}, window {start} to {window_end}")
    return record


def freeze(n: int) -> None:
    path = os.path.join(reg.round_dir(REPO, n), "freeze.json")
    _write_json(path, {"round": n, "frozen_paths": list(reg.FROZEN_PATHS)})
    print(f"{path}: commit it on its own (the code freeze)")


def cancel(n: int, defect: str) -> Dict[str, Any]:
    """Step 6, a material defect found before results: the cancellation record, for
    its own commit (``registration.cancellation_record``)."""
    record = reg.cancellation_record(REPO, n, defect)
    path = os.path.join(reg.round_dir(REPO, n), reg.CANCELLATION)
    _write_json(path, record)
    print(
        f"{path}: commit it on its own; round {n} is then never run. Its replacement is "
        f"a new registration in a later round (draft --replaces {n})"
    )
    return record


# --- step 3 ----------------------------------------------------------------------------


def snapshot_dir(n: int) -> str:
    """Round N's candle snapshots, in its folder, committed with the results (owner,
    D11; ``signal_audit.evidence``)."""
    return os.path.join(reg.round_dir(REPO, n), "candles")


def fetch(n: int) -> Dict[str, Any]:
    sandbox()
    folder = reg.round_dir(REPO, n)
    record = _read_json(os.path.join(folder, "registration.json"))
    if datetime.now(timezone.utc) < reg.parse_time(record["window"]["end"]):
        raise Stop("the window has not ended: no fetch before its end")
    manager = _manager()
    data_path = os.path.join(folder, "data.json")
    earlier = _read_json(data_path) if os.path.exists(data_path) else None
    try:
        data = evidence.fetch_round(record, manager, snapshot_dir(n), earlier)
    except evidence.EvidenceError as exc:
        raise Stop(str(exc)) from exc
    out = {
        "round": n,
        "exchange": data["exchange"],
        "files": data["files"],
        "snapshots": f"{reg.rel_round_dir(n)}/candles",
        "fetched_at": reg.iso(datetime.now(timezone.utc)),
    }
    if earlier and earlier.get("fetched_at"):
        out["first_fetched_at"] = earlier.get("first_fetched_at", earlier["fetched_at"])
    _write_json(data_path, out)
    return out


# --- steps 4 and 5 ---------------------------------------------------------------------


def report_path(n: int) -> str:
    return os.path.join(REPO, "docs", "dev", f"SIG-AUDIT-REPORT-round-{n}.md")


def evaluate(n: int, record: Mapping[str, Any], bars, state: Mapping[str, Any]):
    """Every registered row from the snapshots' bars, both Holm procedures and the
    verdicts: the round's result and its results record."""
    from signal_audit.pairs import row_pairs

    cands = round_one.by_key()
    start = int(reg.parse_time(record["window"]["start"]).timestamp())
    end = int(reg.parse_time(record["window"]["end"]).timestamp())
    rows_data = []
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
    sha = state.get("registration_sha256") or reg.file_sha256(
        os.path.join(reg.round_dir(REPO, n), "registration.json")
    )
    return result, rp.results_record(result, n, sha, dict(state))


def run(n: int, supersede: Optional[str] = None) -> Dict[str, Any]:
    sandbox()
    folder = reg.round_dir(REPO, n)
    state = reg.check_can_run(
        REPO, n, supersede=supersede, results_exist=reg.has_results(folder)
    )
    record = _read_json(os.path.join(folder, "registration.json"))
    data = _read_json(os.path.join(folder, "data.json"))
    try:
        bars = evidence.load_round(record, data, snapshot_dir(n))
    except evidence.EvidenceError as exc:
        raise Stop(str(exc)) from exc
    superseded = reg.supersede_results(folder, supersede, report_path(n))
    result, results = evaluate(n, record, bars, state.to_dict())
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
    with open(report_path(n), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return results


def verify(n: int, refetch: bool = False) -> Dict[str, Any]:
    """The independent check of a round's evidence (owner, D11): every snapshot
    against its record and the registration; the results re-derived from them and
    compared with results.json, when the code at HEAD is the code that produced them;
    and, with ``refetch``, each snapshot against the registered exchange's bars now.
    Nothing is written."""
    sandbox()
    folder = reg.round_dir(REPO, n)
    record = _read_json(os.path.join(folder, "registration.json"))
    data = _read_json(os.path.join(folder, "data.json"))
    try:
        bars = evidence.load_round(record, data, snapshot_dir(n))
    except evidence.EvidenceError as exc:
        raise Stop(str(exc)) from exc
    report = {"round": n, "snapshots": f"{len(data['files'])} match their record"}
    print(f"round {n}: {report['snapshots']} and the registration", flush=True)
    path = os.path.join(folder, "results.json")
    if os.path.exists(path):
        committed = _read_json(path)
        state = committed.get("state") or {}
        produced_by = state.get("head")
        changed = (
            reg.git(
                REPO,
                "diff",
                "--name-only",
                produced_by,
                "HEAD",
                "--",
                *reg.FROZEN_PATHS,
            ).split()
            if produced_by
            else ["(no commit recorded)"]
        )
        if changed:
            raise Stop(
                f"the frozen code at HEAD is not the code that produced the results "
                f"({produced_by}): {changed}; check out that commit to re-derive them"
            )
        _result, again = evaluate(n, record, bars, state)
        same = {k: v for k, v in again.items() if k != "state"} == {
            k: v for k, v in committed.items() if k != "state"
        }
        if not same:
            raise Stop(
                "the results re-derived from the snapshots differ from results.json"
            )
        report["results"] = "re-derived from the snapshots: identical"
        print(f"round {n}: results {report['results']}", flush=True)
    if refetch:
        found = evidence.refetch_differences(record, data, snapshot_dir(n), _manager())
        report["exchange"] = found or "every snapshot agrees with the exchange now"
        if found:
            raise Stop(f"the exchange's bars now differ from the snapshots: {found}")
        print(f"round {n}: {report['exchange']}", flush=True)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("rank", "draft", "freeze", "fetch", "run", "cancel", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--round", type=int, required=True)
        if name == "rank":
            p.add_argument("--ranking-date", required=True)
            p.add_argument("--window-days", type=int, default=270)
        if name == "draft":
            p.add_argument("--window-end", required=True)
            p.add_argument("--window-start")
            p.add_argument("--replaces", type=int)
        if name == "run":
            p.add_argument("--supersede")
        if name == "cancel":
            p.add_argument("--defect", required=True)
        if name == "verify":
            p.add_argument("--refetch", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "rank":
            rank(args.round, args.ranking_date, args.window_days)
        elif args.command == "draft":
            draft(args.round, args.window_end, args.window_start, args.replaces)
        elif args.command == "freeze":
            freeze(args.round)
        elif args.command == "fetch":
            fetch(args.round)
        elif args.command == "cancel":
            cancel(args.round, args.defect)
        elif args.command == "verify":
            verify(args.round, args.refetch)
        else:
            run(args.round, args.supersede)
    except (Stop, reg.Refused) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
