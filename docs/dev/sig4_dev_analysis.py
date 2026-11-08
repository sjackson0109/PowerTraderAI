"""
The development analysis of FDS-SIG-004 phase C (``run_sig4_dev.py analyse``).

Scored on the development period only: PV-1's walk-forward (folds from 2021-01-01 to
2025-05-06). No bar from 2025-05-06 on is read: every series is loaded to that hour.
Development decides only whether a forward confirmation is worth registering; a
development pass is never evidence for enabling anything (section 6.4.2).
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

import run_sig4_dev as cfg


def _epoch(text: str) -> int:
    from model_lab.series import epoch

    return epoch(text)


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


# --- data ------------------------------------------------------------------------------------


def load_series() -> Dict[str, Any]:
    from model_lab import series as series_mod

    out = {}
    for coin in cfg.COINS:
        try:
            out[coin] = series_mod.load(
                coin, cfg.START, cfg.DEV_END, offline=True, exchanges=[cfg.EXCHANGE]
            )
        except series_mod.SeriesError as exc:
            log(f"{coin}: no development bars ({exc})")
    return out


def frame_of(s):
    import pandas as pd

    return pd.DataFrame(
        {
            "open_time": pd.to_datetime(s.open_s, unit="s", utc=True),
            "open": s.open,
            "high": s.high,
            "low": s.low,
            "close": s.close,
            "volume": s.volume,
        }
    )


def minimums(coins) -> Dict[str, Optional[float]]:
    """Today's venue minimum order per coin, from the unauthenticated product endpoint.
    Past minimums are not recorded anywhere (section 13 item 4)."""
    from pt_exchanges import CoinbaseExchange

    ex = CoinbaseExchange()
    out = {}
    for c in coins:
        try:
            out[c] = ex.min_order_usd(f"{c}-USD")
        except Exception:
            out[c] = None
    return out


# --- F1 --------------------------------------------------------------------------------------


def f1_rows(batch_id: str, series: Dict[str, Any], rules, fees):
    """(y, the seven models' probabilities, hours, coins) on the common rows whose T1
    label resolves inside the development period."""
    from model_lab import batch, catalogue
    from model_lab import features as ft
    from model_lab import targets as tg

    keys = catalogue.BATCH_PV_1
    probs = {k: batch.read_probabilities(batch_id, k) for k in keys}
    ys, ps, ts, cs = [], {k: [] for k in keys}, [], []
    for coin in sorted(series):
        if coin not in probs[keys[0]]:
            continue
        g = ft.grid(series[coin])
        label, _end = tg.t1(g, rules, fees[coin])
        close_s, _ = probs[keys[0]][coin]
        k = g.positions(close_s)
        y = np.where(k >= 0, label[np.maximum(k, 0)], np.nan)
        cols = {key: probs[key][coin][1] for key in keys}
        ok = np.isfinite(y)
        for key in keys:
            ok &= np.isfinite(cols[key])
        ys.append(y[ok])
        ts.append(np.asarray(close_s)[ok])
        cs += [coin] * int(ok.sum())
        for key in keys:
            ps[key].append(cols[key][ok])
    return (
        np.concatenate(ys),
        {k: np.concatenate(v) for k, v in ps.items()},
        np.concatenate(ts),
        np.array(cs),
    )


# --- STRAT-001 opportunities ------------------------------------------------------------------


def opportunities(series: Dict[str, Any]):
    """Every coin's STRAT-001 trades on its development bars, with the decision-hour
    features, σ̂ and v2."""
    from model_lab import features as ft
    from signal_fusion import labels as lb
    from signal_fusion import volatility as vol

    btc = series.get("BTC")
    rows = []
    var_rows = {}
    for coin in sorted(series):
        s = series[coin]
        trades = lb.opportunities(frame_of(s), coin)
        table = ft.build(s, btc)
        g = table.grid
        v = vol.variances(g.high, g.low, g.close)
        truth = vol.realised(g.close)
        var_rows[coin] = (g.close_s, v, truth)
        xp = table.matrix(ft.P)
        xv = table.matrix(ft.P + ft.V)
        for t in trades:
            k = int(g.positions([t.signal_s])[0])
            if k < 0:
                continue
            rows.append(
                {
                    "coin": coin,
                    "trade": t,
                    "xp": xp[k],
                    "xv": xv[k],
                    "v2": float(table.column("v2")[k]),
                    "var": {name: float(v[name][k]) for name in vol.CANDIDATES},
                }
            )
    rows.sort(key=lambda r: (r["trade"].signal_s, r["coin"]))
    return rows, var_rows


def choose_sigma(var_rows, folds) -> Tuple[str, Dict[str, float]]:
    """σ̂'s candidate, by QLIKE on every coin's development hours."""
    from signal_fusion import volatility as vol

    first, last = folds[0][0], folds[-1][1]
    forecasts = {name: [] for name in vol.CANDIDATES}
    truths = []
    for coin, (close_s, v, truth) in var_rows.items():
        m = (close_s >= first) & (close_s < last)
        for name in vol.CANDIDATES:
            forecasts[name].append(v[name][m])
        truths.append(truth[m])
    f = {k: np.concatenate(x) for k, x in forecasts.items()}
    t = np.concatenate(truths)
    return vol.choose(f, t, np.arange(len(t)))


# --- the filters ------------------------------------------------------------------------------


def filters(rows, folds, fee: float, sigma_name: str):
    """F_P and F_PV on M at ``fee``: calibrated probabilities, the payoff tables, σ̂'s
    terciles and σ_ref per fold, EV and the veto, per opportunity."""
    from signal_fusion import labels as lb
    from signal_fusion import meta
    from signal_fusion import volatility as vol

    trades = [r["trade"] for r in rows]
    gross, label = lb.label_rows(trades, fee)
    signal = np.array([t.signal_s for t in trades], dtype=np.int64)
    exit_s = np.array([t.exit_s for t in trades], dtype=np.int64)
    sigma = vol.sigma(np.array([r["var"][sigma_name] for r in rows]))
    out = {
        "gross": gross,
        "label": label,
        "signal": signal,
        "exit": exit_s,
        "sigma": sigma,
    }
    fold = np.full(len(rows), -1)
    for k, (a, b) in enumerate(folds):
        fold[(signal >= a) & (signal < b)] = k
    out["fold"] = fold
    # σ_ref, terciles and payoffs per fold, from that fold's training trades
    sref = np.full(len(rows), np.nan)
    tercile = np.full(len(rows), -1)
    win = np.full(len(rows), np.nan)
    loss = np.full(len(rows), np.nan)
    tables = []
    for k, (a, _b) in enumerate(folds):
        train = (label >= 0) & (exit_s <= a) & np.isfinite(sigma)
        here = fold == k
        if train.sum() < 3:
            tables.append(None)
            continue
        cuts = vol.terciles(sigma[train])
        ref = vol.reference(sigma[train])
        pay = lb.payoffs(gross[train], label[train], vol.tercile_of(sigma[train], cuts))
        tables.append({"cuts": cuts, "sigma_ref": ref, "payoffs": pay.to_dict()})
        sref[here] = ref
        tc = vol.tercile_of(sigma[here], cuts)
        tercile[here] = tc
        for i, tt in zip(np.nonzero(here)[0], tc):
            win[i], loss[i] = pay.at(int(tt))
    out.update(
        {
            "sigma_ref": sref,
            "tercile": tercile,
            "win": win,
            "loss": loss,
            "tables": tables,
        }
    )
    for name, key in (("F_P", "xp"), ("F_PV", "xv")):
        x = np.vstack([r[key] for r in rows])
        wf = meta.walk_forward(x, label, signal, exit_s, folds)
        p = wf.calibrated
        ev = lb.expected_value(p, win, loss, fee, cfg.ALLOWANCE)
        assessable = np.isfinite(p) & np.isfinite(win) & np.isfinite(loss) & (fold >= 0)
        out[name] = {
            "p": p,
            "raw": wf.raw,
            "climatology": wf.climatology,
            "ev": ev,
            "assessable": assessable,
            "veto": assessable & (ev <= 0),
            "fits": wf.fits,
        }
    return out


# --- paths --------------------------------------------------------------------------------------


def as_opportunities(rows, assessable):
    from signal_fusion.evaluation.replay import Opportunity

    return [
        Opportunity(
            r["coin"],
            r["trade"].signal_s,
            r["trade"].exit_s,
            r["trade"].entry_price,
            r["trade"].exit_price,
            bool(a),
        )
        for r, a in zip(rows, assessable)
    ]


def prices_of(series):
    return {c: (s.close_s, s.close) for c, s in series.items()}


def path_trades(path, opps):
    """(entry time, net, capital-days) of path 0's trades."""
    return [(opps[i].entry_s, net, days) for i, _amount, net, days in path.detail]


def r3_rpcd(opps, prices, costs, account, candidates, counts, seed, stratified=True):
    from signal_fusion.evaluation import baselines as bl
    from signal_fusion.evaluation import bootstrap as bs
    from signal_fusion.evaluation.replay import replay

    coins = [o.coin for o in opps]
    values = []
    for run in range(bs.RUNS):
        v = bl.r3(
            coins,
            candidates,
            counts,
            len(opps),
            seed,
            run,
            bs.DRAWS_PER_RUN,
            stratified,
        )
        values.append(replay(opps, prices, costs, account, veto=v).rpcd)
        log(f"R3 run {run + 1}/{bs.RUNS}")
    return np.vstack(values)


def r3s_drawdowns(opps, prices, costs, account, candidates, scales, missing, seed):
    from signal_fusion.evaluation import baselines as bl
    from signal_fusion.evaluation import bootstrap as bs
    from signal_fusion.evaluation.replay import replay

    coins = [o.coin for o in opps]
    out = []
    for run in range(bs.RUNS):
        s = bl.r3s(coins, candidates, scales, len(opps), seed, run, bs.DRAWS_PER_RUN)
        veto = np.broadcast_to(missing, s.shape)
        out.append(
            replay(opps, prices, costs, account, veto=veto, scale=s).max_drawdown
        )
        log(f"R3s run {run + 1}/{bs.RUNS}")
    return np.vstack(out)


# --- the analysis -------------------------------------------------------------------------------


def analyse(batch_id: str, out_dir: str) -> Dict[str, Any]:
    import model_gate
    from model_lab import batch, walkforward
    from signal_fusion.evaluation import baselines as bl
    from signal_fusion.evaluation import bootstrap as bs
    from signal_fusion.evaluation import findings as fd
    from signal_fusion.evaluation import scoring as sc
    from signal_fusion.evaluation.replay import Account, Costs, replay

    record = batch.read_batch(batch_id)
    rules = model_gate.trade_rules(record["rules"])
    fees = cfg._fees()
    cal = walkforward.make_calendar(cfg.START, cfg.END)
    folds = [f for f in cal.folds if f[1] <= _epoch(cfg.DEV_END)]
    first_s, last_s = folds[0][0], folds[-1][1]
    seen = _epoch(cfg.SEEN_FROM)
    result: Dict[str, Any] = {
        "batch": batch_id,
        "development": [first_s, last_s],
        "folds": len(folds),
        "fees": {
            "deciding": cfg.FEE,
            "shown": cfg.FEE_HIGH,
            "allowance": cfg.ALLOWANCE,
        },
    }

    log("series")
    series = load_series()
    result["coins"] = {
        c: {"bars": len(s), "first": int(s.first_open_s)} for c, s in series.items()
    }

    # F1 ---------------------------------------------------------------------------------
    log("F1")
    y, ps, ts, cs = f1_rows(batch_id, series, rules, fees)
    keys = list(ps)
    p_price, p_volume = ps[keys[0]], ps[keys[1]]
    placebos = [ps[k] for k in keys[2:]]
    f1 = fd.f1(y, p_price, p_volume, placebos, ts, cfg.TEST_SEEDS["f1"], k=5)
    split = {}
    for name, m in (("before_look", ts < seen), ("seen", ts >= seen)):
        if m.any():
            split[name] = fd.f1(
                y[m],
                p_price[m],
                p_volume[m],
                [p[m] for p in placebos],
                ts[m],
                cfg.TEST_SEEDS["f1"],
                k=5,
            )["test"]
    f1["by_exposure"] = split
    f1["by_coin"] = {
        c: float(
            np.mean(
                sc.log_loss_rows(y[cs == c], p_price[cs == c])
                - sc.log_loss_rows(y[cs == c], p_volume[cs == c])
            )
        )
        for c in sorted(set(cs.tolist()))
    }
    result["F1"] = f1
    batch.log_trial(
        {
            "trial": f"{batch_id}/F1",
            "kind": "forecast",
            "p": f1["test"]["p"],
            "theta": f1["test"]["theta"],
            "rows": f1["rows"],
        }
    )

    # STRAT-001 ---------------------------------------------------------------------------
    log("STRAT-001 opportunities")
    rows, var_rows = opportunities(series)
    sigma_name, qlike = choose_sigma(var_rows, folds)
    result["sigma"] = {"chosen": sigma_name, "qlike": qlike}
    mins = minimums(series)
    result["minimums"] = mins
    prices = prices_of(series)
    fees_out = {}
    for fee in (cfg.FEE, cfg.FEE_HIGH):
        log(f"filters at {fee:.2%}")
        f = filters(rows, folds, fee, sigma_name)
        dev = f["fold"] >= 0
        idx = np.nonzero(dev)[0]
        dev_rows = [rows[i] for i in idx]
        costs = Costs(fee, cfg.ALLOWANCE, {c: m for c, m in mins.items() if m})
        block = bs.block_length(
            [(r["trade"].exit_s - r["trade"].signal_s) / 86400 for r in dev_rows]
        )
        per_fee: Dict[str, Any] = {"block_days": block, "opportunities": len(dev_rows)}
        for account_size in cfg.ACCOUNTS:
            acct = Account(start=account_size)
            opps_pv = as_opportunities(dev_rows, f["F_PV"]["assessable"][idx])
            opps_p = as_opportunities(dev_rows, f["F_P"]["assessable"][idx])
            paths = {}
            for name, opps, veto in (
                ("unfiltered", opps_pv, np.zeros(len(idx), bool)),
                ("F_P", opps_p, f["F_P"]["veto"][idx]),
                ("F_PV", opps_pv, f["F_PV"]["veto"][idx]),
            ):
                paths[name] = (
                    opps,
                    replay(opps, prices, costs, acct, veto=veto[None, :], detail=True),
                )
            summary = {
                name: {
                    "trades": int(pth.trades[0]),
                    "net": float(pth.net[0]),
                    "rpcd": float(pth.rpcd[0]),
                    "vetoed": int(pth.vetoed[0]),
                    "max_drawdown": float(pth.max_drawdown[0]),
                    "halt_s": int(pth.halt_s[0]),
                    "skipped_cash": int(pth.skipped_cash[0]),
                }
                for name, (opps, pth) in paths.items()
            }
            entry = {"paths": summary}
            if account_size == cfg.ACCOUNTS[0]:
                opps_v, pv = paths["F_PV"]
                _opps_p, pp = paths["F_P"]
                # F2 with R3
                cand = [i for i in pv.eligible() if opps_v[i].assessable]
                vetoed = [i for i, s in enumerate(pv.status) if s == "vetoed"]
                counts = bl.veto_counts([o.coin for o in opps_v], cand, vetoed)
                log(f"R3 at {fee:.2%}")
                r3 = r3_rpcd(
                    opps_v, prices, costs, acct, cand, counts, cfg.TEST_SEEDS["r3"]
                )
                f2 = fd.f2(
                    path_trades(pv, opps_v),
                    path_trades(pp, _opps_p),
                    float(pv.rpcd[0]),
                    r3,
                    first_s,
                    last_s,
                    cfg.TEST_SEEDS["f2"],
                    block,
                )
                f2["veto_counts"] = counts
                f2["edge"] = fd.smallest_detectable(r3, 5)
                entry["F2"] = f2
                # F3 for F_PV's path
                entry["F3"] = fd.f3(
                    pv,
                    [o.entry_s for o in opps_v],
                    [o.coin for o in opps_v],
                    first_s,
                    last_s,
                    cfg.TEST_SEEDS["f3"],
                    acct.halt_pct,
                    block,
                )
                # Q2 for F_PV (fold 2 on: calibrated rows with a label)
                pfv = f["F_PV"]["p"][idx]
                lab = f["label"][idx]
                ok = np.isfinite(pfv) & (lab >= 0)
                entry["Q2"] = fd.calibration(
                    lab[ok],
                    pfv[ok],
                    f["F_PV"]["climatology"][idx][ok],
                    f["signal"][idx][ok],
                    cfg.TEST_SEEDS["q2"],
                    5,
                    block,
                )
                # Q3: the shrink on every opportunity, against R3s
                sv = np.minimum(1.0, f["sigma_ref"][idx] / f["sigma"][idx])
                missing = ~np.isfinite(sv)
                sv = np.where(missing, 1.0, sv)
                opps_all = as_opportunities(dev_rows, ~missing)
                unscaled = replay(opps_all, prices, costs, acct, detail=True)
                shrunk = replay(
                    opps_all,
                    prices,
                    costs,
                    acct,
                    veto=missing[None, :],
                    scale=sv[None, :],
                    detail=True,
                )
                cand_s = [i for i in range(len(opps_all)) if not missing[i]]
                log(f"R3s at {fee:.2%}")
                mdds = r3s_drawdowns(
                    opps_all,
                    prices,
                    costs,
                    acct,
                    cand_s,
                    sv,
                    missing,
                    cfg.TEST_SEEDS["r3s"],
                )
                entry["Q3"] = fd.shrink(
                    shrunk,
                    path_trades(unscaled, opps_all),
                    path_trades(shrunk, opps_all),
                    mdds,
                    first_s,
                    last_s,
                    cfg.TEST_SEEDS["q3"],
                    block=block,
                )
                entry["Q3"]["skipped_minimum"] = int(shrunk.skipped_minimum[0])
                # the research's 1.5x rule, before the look only (shown)
                before = np.array([o.entry_s < seen for o in opps_all])
                v2 = np.array([r["v2"] for r in dev_rows])
                rule_veto = before & np.isfinite(v2) & (v2 <= math.log(1.5))
                opps_rule = [o for o, b in zip(opps_all, before) if b]
                rv = rule_veto[before]
                rp = replay(
                    opps_rule, prices, costs, acct, veto=rv[None, :], detail=True
                )
                cand_r = [i for i in rp.eligible()]
                counts_r = bl.veto_counts(
                    [o.coin for o in opps_rule],
                    cand_r,
                    [i for i, s in enumerate(rp.status) if s == "vetoed"],
                )
                log("R3 for the 1.5x rule")
                r3_rule = r3_rpcd(
                    opps_rule,
                    prices,
                    costs,
                    acct,
                    cand_r,
                    counts_r,
                    cfg.TEST_SEEDS["rule"],
                )
                entry["rule_1_5x"] = {
                    "opportunities": len(opps_rule),
                    "vetoed": int(rp.vetoed[0]),
                    "rpcd": float(rp.rpcd[0]),
                    "p_r3": bl.upper_p(float(rp.rpcd[0]), r3_rule),
                    "r3_median": float(np.median(r3_rule)),
                }
            per_fee[f"account_{int(account_size)}"] = entry
        per_fee["fits"] = {"F_P": f["F_P"]["fits"], "F_PV": f["F_PV"]["fits"]}
        per_fee["tables"] = f["tables"]
        fees_out[f"{fee:.4f}"] = per_fee
    result["STRAT-001"] = fees_out

    # the family at the deciding fee and account -------------------------------------------
    d = fees_out[f"{cfg.FEE:.4f}"][f"account_{int(cfg.ACCOUNTS[0])}"]
    family = {
        "F1": f1["test"]["p"],
        "F2": d["F2"]["test"]["p"],
        "Q2": d["Q2"]["skill"]["p"],
        "Q3": d["Q3"]["p"],
        "F3": d["F3"]["test"]["p"],
    }
    holm = dict(zip(family, fd.holm(list(family.values()))))
    passes = {
        "F1": fd.f1_passes(f1, holm["F1"]),
        "F2": bool(holm["F2"] and all(d["F2"]["conditions"].values())),
        "Q2": fd.calibration_passes(d["Q2"], holm["Q2"]),
        "Q3": fd.shrink_passes(d["Q3"], holm["Q3"]),
        "F3": fd.f3_passes(d["F3"], holm["F3"]),
    }
    pv = d["paths"]["F_PV"]
    verdicts = {
        "F1": fd.f1_line(f1, passes["F1"]),
        "F2": fd.f2_line(
            d["F2"], passes["F2"], pv["net"], pv["trades"], d["F2"]["edge"]
        ),
        "F3": fd.f3_line(
            d["F3"], passes["F3"], fd.f3_failed(d["F3"], holm["F3"]), holm["F3"]
        ),
        "Q3": fd.shrink_line(d["Q3"], passes["Q3"]),
        "Q2": {
            "calibrated": "Calibrated within tolerance",
            "miscalibrated": "Miscalibrated",
            "not_assessable": "Calibration not assessable",
        }[d["Q2"]["outcome"]]
        + (
            " with skill above the base rate"
            if passes["Q2"]
            else "; no skill above the base rate shown"
        ),
    }
    result["family"] = {"p": family, "holm": holm, "passes": passes}
    result["verdicts"] = verdicts
    for name, kind in (
        ("F2", "decision"),
        ("Q2", "calibration"),
        ("Q3", "sizing"),
        ("F3", "decision"),
    ):
        batch.log_trial(
            {"trial": f"{batch_id}/{name}", "kind": kind, "p": family[name]}
        )
    with open(os.path.join(out_dir, "analysis.json"), "w", encoding="utf-8") as fh:
        json.dump(_plain(result), fh, indent=1, sort_keys=True)
    return result


def _plain(x):
    """JSON-safe: arrays to lists, numpy numbers to Python ones, NaN to None."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if not math.isfinite(v) else v
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x
