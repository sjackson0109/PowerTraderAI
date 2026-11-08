"""
E1's report (``run_sr1_e1.py``): the frozen record and ``strategy_lab.e1.evaluate``'s
results as markdown. It formats only; nothing here scores or decides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

ACCOUNTS = ("£10,000", "£500", "£50")
DEV_ONLY = "Development only: not evidence for enabling anything."


def _f(x: Optional[float], spec: str, none: str = "n/a") -> str:
    if x is None:
        return none
    try:
        return format(float(x), spec)
    except (TypeError, ValueError):
        return none


def money(x) -> str:
    return "n/a" if x is None else f"{float(x):+,.2f}"


def amount(x) -> str:
    return "n/a" if x is None else f"{float(x):,.2f}"


def pct(x, digits: int = 2) -> str:
    return _f(x, f"+.{digits}%")


def share(x, digits: int = 1) -> str:
    return _f(x, f".{digits}%")


def rpcd(x) -> str:
    return _f(x, "+.4%")


def pval(x) -> str:
    return _f(x, ".4f")


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out + [""]


def _when(s: Optional[int]) -> str:
    if s is None or int(s) < 0:
        return "not reached"
    return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime("%Y-%m-%d")


def _run_ps(member: Mapping[str, Any]) -> List[float]:
    """Each seeded run's p for a member (a trading member's or an economic one's)."""
    runs = member.get("runs") or (member.get("test") or {}).get("runs") or []
    return [float(x) for x in runs if x is not None]


def _blocks_line(result: Mapping[str, Any]) -> str:
    """The economic bootstrap's block length, and how many blocks the period holds."""
    parts = []
    for fam, days in sorted((result.get("block_days") or {}).items()):
        span = [
            (m.get("test") or {}).get("days")
            for m in (result.get("members") or {}).values()
            if (m.get("test") or {}).get("days")
        ]
        held = f" in {span[0]:,} days, {span[0] / days:.1f} blocks" if span else ""
        intervals = "; ".join(
            f"{mid} {_f(t['interval'][0], '+.4%')} to {_f(t['interval'][1], '+.4%')}"
            for mid, m in sorted((result.get("members") or {}).items())
            for t in [m.get("test") or {}]
            if t.get("interval")
        )
        parts.append(
            f"family {fam}: {days} days by section 6.0's rule{held}. Its 95% intervals "
            f"(return per capital-day): {intervals}"
        )
    return "- **Day blocks:** " + ("; ".join(parts) or "n/a") + "."


OUTCOME = {
    "pass": "Pass",
    "fail": "Fail",
    "too_few": "Too few trades to tell",
    "not_assessable": "Not assessable",
}


def report(record: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    from strategy_lab import e1

    L: List[str] = []
    rehearsal = result.get("rehearsal")
    L += [
        "# FDS-SR-001 E1: development report",
        "",
        f"> **{DEV_ONLY}** E1 read the development period only (2021-01-01 to "
        "2025-05-06). The lockbox (2025-05-06 to 2026-11-06) was not opened. No "
        "strategy, gate or model is activated, promoted or enabled by this report.",
        "",
    ]
    if rehearsal:
        L += [f"> **REHEARSAL: {rehearsal}. These figures mean nothing.**", ""]

    # 1. verdicts -----------------------------------------------------------------------
    L += ["## 1. Verdicts", ""]
    L += [
        "Three families, each corrected on its own by Holm at 5% (E-D11). Trading lines "
        "compare against random baselines; only an economic line can say "
        '"profitable".',
        "",
    ]
    for fam, (name, k) in e1.FAMILIES.items():
        L += [f"### Family {fam}: {name} (K = {k})", ""]
        rows = []
        for m in e1.MEMBERS:
            if m.family != fam:
                continue
            v = result["verdicts"][m.id]
            runs = _run_ps(result["members"].get(m.id) or {})
            rows.append(
                [m.id, m.question, OUTCOME[v["outcome"]], pval(v["p"]),
                 f"{min(runs):.4f} to {max(runs):.4f}" if runs else "n/a",
                 "yes" if v["holm_pass"] else "no"]
            )  # fmt: skip
        L += table(
            [
                "Member",
                "Question",
                "Outcome",
                "p (pooled)",
                "p in each run",
                "p passes Holm",
            ],
            rows,
        )
        if fam == "S":
            L += [
                "For S3 and S4 the day-block bootstrap is the family member, and "
                '"p passes Holm" is about it alone. The outcome also needs every '
                "condition of FDS-SIG-004 F3; the line names the one that failed. With "
                f"blocks of {result.get('block_days', {}).get('S', 'n/a')} days (section 2) "
                "that bootstrap carries little information.",
                "",
            ]
        for m in e1.MEMBERS:
            if m.family == fam:
                L += [f"- **{m.id}.** {result['verdicts'][m.id]['line']}"]
        L += [""]

    # 2. registration ------------------------------------------------------------------------
    acc = record["accounts"]
    rate = acc.get("rate") or {}
    ver = rate.get("verification") or {}
    L += ["## 2. Registration", ""]
    L += [
        f"- **Record:** `{record.get('id')}`, frozen {record.get('frozen_at')}, SHA-256 "
        f"`{record.get('sha256')}`. Every member, seed, cost, account and rule was fixed "
        "there before anything was scored.",
        f"- **GBP/USD:** {acc['gbp_usd']} ({rate.get('source')}, {rate.get('rate_date')}; "
        f"retrieved {rate.get('retrieved_at')}). Checked against the "
        f"{ver.get('source', 'n/a')}: {_f(ver.get('cross'), '.5f')} on the same day, a "
        f"difference of {share(ver.get('relative_difference'), 3)} (tolerance "
        f"{share(ver.get('tolerance'), 2)}).",
        "- **Accounts:** "
        + ", ".join(
            f"£{float(g):,.0f} = ${float(u):,.2f}"
            for g, u in sorted(acc["usd"].items(), key=lambda kv: -float(kv[0]))
        )
        + f"; £{acc['deciding_gbp']:,.0f} decides. Sizing: {acc['sizing']['start_allocation_pct']}% "
        f"entries raised to the minimum entry, {acc['sizing']['max_coin_pct']}% a coin, "
        f"halt at {acc['sizing']['halt_pct']}% (reported, not modelled).",
        f"- **Costs:** {record['costs']['fee']:.2%} taker + {record['costs']['allowance']:.2%} "
        f"slippage a fill ({record['costs']['fee_source']}). Shown: "
        + "; ".join(f"{s['name']} ({s['note']})" for s in record["costs"]["scenarios"])
        + ".",
        f"- **Venue rules:** minimum orders and sell steps for "
        f"{len(record['costs']['minimum_usd'])} coins, read {record['costs'].get('venue_read_at')} "
        "(today's values; past values are not recorded).",
        f"- **Candles:** {len(record['market']['series_sha256'])} series from "
        f"{', '.join(sorted(set((record['market'].get('served_by') or {}).values())) or ['n/a'])} "
        f"(Settings order: {', '.join(record['market']['exchange_order'])}), offline, "
        "each read once. Coins with "
        f"development bars: {', '.join(record['market']['coins_with_development_bars'])}. "
        "Left out: "
        + (
            "; ".join(
                f"{k} ({v})" for k, v in sorted(record["market"]["left_out"].items())
            )
            or "none"
        )
        + ".",
        f"- **Model probabilities:** batch {record['models']['batch']}, "
        + ", ".join(f"`{k}` `{v[:12]}…`" for k, v in record["models"]["sha256"].items())
        + " (matching docs/dev/RUN-LOG-sig4-1.md).",
        _blocks_line(result),
        f"- **Run:** {result.get('seconds')} s. Trials logged by kind: "
        + ", ".join(
            f"{k} {v}"
            for k, v in sorted((result.get("trial_counts") or {}).items())
            if v
        )
        + ".",
        "",
    ]

    # 3. the strategies at the deciding account ------------------------------------------------
    cells = result["cells"]
    L += ["## 3. Each strategy at £10,000, against the baselines", ""]
    rows = []
    for sid, c in cells.items():
        a = c["£10,000"]
        s, h = a["strategy"], a["ref_hold"]
        rnd = _random_of(result, sid)
        rows.append(
            [sid, c["timeframe"], s["trades"], money(s["net_usd"]), money(s["net_gbp"]),
             rpcd(s["rpcd"]), pct(s["return_on_account"]), share(s["max_drawdown"]),
             share(s["time_in_market"]), money(h["net_usd"]), rpcd(h["rpcd"]),
             rpcd(rnd.get("median")) if rnd else "n/a", pval(rnd.get("p")) if rnd else "n/a"]
        )  # fmt: skip
    L += table(
        ["Strategy", "Bars", "Trades", "Net $", "Net £", "RPCD", "Return", "Max DD",
         "In market", "REF-HOLD net $", "REF-HOLD RPCD", "REF-RANDOM median RPCD",
         "p vs random"],
        rows,
    )  # fmt: skip
    L += [
        "RPCD is return per capital-day: summed net over summed (amount × days held). "
        "REF-CASH is 0 throughout. REF-HOLD buys each coin once at the strategy's first "
        "decision bar (so it differs with each strategy's warm-up), sized like a trade "
        "(1% of the account), and holds it to the end, so its dollar figures are small; "
        "compare RPCD.",
        "",
    ]
    L += ["### Trades, holding and capital", ""]
    rows = []
    for sid, c in cells.items():
        s = c["£10,000"]["strategy"]
        rows.append(
            [sid, s["candidates"] if "candidates" in s else c["candidates"], s["trades"],
             f"{s['trades_by_half'][0]} / {s['trades_by_half'][1]}",
             f"{money(s['net_by_half'][0])} / {money(s['net_by_half'][1])}",
             _f(s["holding_days_median"], ".1f"), _f(s["holding_days_p90"], ".1f"),
             share(s["win_rate"]), money(s["largest_loss_usd"]),
             share(s["mean_committed"], 2), share(s["peak_committed"], 2),
             _f(s["recovery_days"], ".0f", "not recovered")]
        )  # fmt: skip
    L += table(
        ["Strategy", "Candidates", "Trades", "By half", "Net by half $", "Median days",
         "90th pct days", "Win rate", "Largest loss $", "Mean committed",
         "Peak committed", "DD recovery days"],
        rows,
    )  # fmt: skip

    # 4. accounts -----------------------------------------------------------------------------
    L += ["## 4. The three accounts (E-D5)", ""]
    L += [
        "The same candles, candidate trades and period at each size; each account has "
        "its own minimum entries, sell rounding, cash and halt level.",
        "",
    ]
    rows = []
    for sid, c in cells.items():
        for acct in ACCOUNTS:
            s = c[acct]["strategy"]
            rnd = (
                c[acct].get("ref_random")
                if acct != "£10,000"
                else _random_of(result, sid)
            )
            rows.append(
                [sid, acct, s["trades"], money(s["net_usd"]), money(s["net_gbp"]),
                 rpcd(s["rpcd"]), pct(s["return_on_account"]), share(s["max_drawdown"]),
                 s["entries_raised_to_minimum"], s["skipped_cash"], s["skipped_minimum"],
                 money(s["unsold_remainder_usd"]),
                 pval(rnd.get("p")) if rnd else "n/a"]
            )  # fmt: skip
    L += table(
        ["Strategy", "Account", "Trades", "Net $", "Net £", "RPCD", "Return", "Max DD",
         "Raised", "No cash", "Below min", "Unsold $", "p vs random"],
        rows,
    )  # fmt: skip

    # 5. by coin and regime ---------------------------------------------------------------------
    L += ["## 5. By coin, year and market regime (£10,000)", ""]
    for sid in ("STRAT-004", "STRAT-005", "STRAT-001"):
        s = cells[sid]["£10,000"]["strategy"]
        L += [f"### {sid}", ""]
        rows = [
            [coin, v["trades"], money(v["net_usd"]), rpcd(v["rpcd"])]
            for coin, v in sorted(s["by_coin"].items())
        ]
        L += table(["Coin", "Trades", "Net $", "RPCD"], rows)
        reg = s.get("by_regime") or {}
        rows = []
        for dim, label in (
            ("year", "Year"),
            ("btc_trend", "BTC against its 200-day average"),
            ("btc_average", "BTC's 200-day average over 30 days"),
            ("volatility", "The coin's 30-day volatility (terciles)"),
        ):
            for bucket, v in sorted((reg.get(dim) or {}).items()):
                if bucket == "cuts":
                    continue
                rows.append(
                    [label, bucket, v["trades"], money(v["net_usd"]), rpcd(v["rpcd"])]
                )
        L += table(["Breakdown", "Bucket", "Trades", "Net $", "RPCD"], rows)

    # 6. the gate -------------------------------------------------------------------------------
    L += ["## 6. The regime gate (OVL-REGIME: BTC above its 200-day average)", ""]
    rows = []
    for sid in ("STRAT-001", "STRAT-004", "STRAT-005", "STRAT-000", "STRAT-002"):
        c = cells[sid]["£10,000"]
        g = c.get("with_gate")
        r = _gate_result(result, sid)
        if g is None:
            continue
        rows.append(
            [sid, c["strategy"]["trades"], money(c["strategy"]["net_usd"]),
             rpcd(c["strategy"]["rpcd"]), g["trades"], money(g["net_usd"]), rpcd(g["rpcd"]),
             share(g["max_drawdown"]), r.get("vetoed", "n/a"),
             rpcd(r.get("median")), pval(r.get("p")),
             "member" if sid in ("STRAT-001", "STRAT-004", "STRAT-005") else "shown"]
        )  # fmt: skip
    L += table(
        ["Strategy", "Trades", "Net $", "RPCD", "Gated trades", "Gated net $",
         "Gated RPCD", "Gated max DD", "Vetoes", "R3 median RPCD", "p vs R3", "Role"],
        rows,
    )  # fmt: skip

    # 7. models ----------------------------------------------------------------------------------
    L += ["## 7. Models with strategies", ""]
    L += [
        "The strategy and its exits are held fixed: a model can only veto a trade. The "
        "generic models forecast a T1 barrier outcome under the legacy rules, not the "
        "strategy's trade (section 9 item 11).",
        "",
        "Names: **PV model** and **P model** are the generic lab models "
        f"(`{record['models']['keys']['PV']}`, `{record['models']['keys']['P']}`); M1 and M2 "
        "use the PV model. **F_PV** and **F_P** are the strategy-specific models, refitted "
        "on each strategy's own candidate trades (shown only).",
        "",
    ]
    rows = []
    for sid in ("STRAT-004", "STRAT-005"):
        c = cells[sid]["£10,000"]
        pv = c.get("with_PV")
        m = result["members"]["M1" if sid == "STRAT-004" else "M2"]
        if pv:
            rows.append(
                [sid, "PV (member)", pv["trades"], money(pv["net_usd"]), rpcd(pv["rpcd"]),
                 m.get("vetoed", "n/a"), rpcd(m.get("median")), pval(m.get("p"))]
            )  # fmt: skip
        p = result["exploratory"].get(f"{sid} + P model vs R3") or {}
        rows.append(
            [sid, "P (shown)", p.get("trades", "n/a"), money(p.get("net_usd")),
             rpcd(p.get("value")), p.get("vetoed", "n/a"), rpcd(p.get("median")),
             pval(p.get("p"))]
        )  # fmt: skip
    L += table(
        ["Strategy", "Model", "Trades", "Net $", "RPCD", "Vetoes", "R3 median RPCD", "p vs R3"],
        rows,
    )  # fmt: skip
    L += ["### Prediction (shown; E1 declares no prediction test)", ""]
    rows = []
    for name, v in (result.get("prediction") or {}).items():
        if "calibration" in v:
            c = v["calibration"]
            rows.append(
                [name, _f(v.get("auc"), ".3f"),
                 f"BSS {_f(c.get('skill', {}).get('theta'), '+.4f')}, "
                 f"{str(c.get('outcome')).replace('_', ' ')}",
                 c.get("rows", "n/a")]
            )  # fmt: skip
        else:
            rows.append(
                [
                    name,
                    _f(v.get("auc"), ".3f"),
                    f"base rate {share(v.get('base_rate'))}",
                    v.get("rows"),
                ]
            )
    L += table(["Model", "AUC (trade won after fees)", "Other", "Rows"], rows)
    L += [
        "An AUC of 0.5 is no better than chance at ranking the strategy's winning trades "
        "above its losing ones.",
        "",
    ]

    # 8. fees -----------------------------------------------------------------------------------
    L += ["## 8. Fees (£10,000)", ""]
    rows = []
    for sid, c in cells.items():
        s = c["£10,000"]["strategy"]
        row = [sid, money(s["net_usd"]), rpcd(s["rpcd"])]
        for name, _fee, _n in e1.FEE_SCENARIOS:
            f = c["fees"][name]
            row += [money(f["net_usd"]), rpcd(f["rpcd"])]
        rows.append(row)
    L += table(
        ["Strategy", "0.50% net $", "0.50% RPCD", "1.20% net $", "1.20% RPCD",
         "0.60% maker net $ (hypothetical)", "0.60% maker RPCD"],
        rows,
    )  # fmt: skip
    L += [
        "The 0.60% maker scenario is hypothetical: the strategies place market orders, "
        "which are not filled at a maker rate.",
        "",
    ]

    # 9. robustness -----------------------------------------------------------------------------
    rob = result["robustness"]
    L += ["## 9. Robustness (section 6.4: shown, never deciding)", ""]
    rows = []
    for name, v in rob["variants"].items():
        f = v["figures"]
        r = v["ref_random"] or {}
        rows.append(
            [name, f["trades"], money(f["net_usd"]), rpcd(f["rpcd"]), share(f["max_drawdown"]),
             rpcd(r.get("median")), pval(r.get("p")), len(v["coins"])]
        )  # fmt: skip
    L += table(
        ["Variant", "Trades", "Net $", "RPCD", "Max DD", "REF-RANDOM median", "p (B = 1,000)", "Coins"],
        rows,
    )  # fmt: skip
    rows = [
        [name, ", ".join(v["contestants"]), _f(v["pbo"], ".3f")]
        for name, v in rob["pbo"].items()
    ]
    L += ["### Probability of backtest overfitting (CSCV, 16 blocks)", ""]
    L += table(["Set", "Contestants", "PBO"], rows)
    L += (
        ["Not run:", ""] + [f"- **{k}:** {v}" for k, v in rob["not_run"].items()] + [""]
    )

    # 10. exploratory -----------------------------------------------------------------------------
    L += ["## 10. Exploratory cells (Benjamini-Hochberg at q = 0.10; never a pass)", ""]
    rows = []
    for name, v in result["exploratory"].items():
        if v.get("assessable") is False:
            rows.append([name, "not assessable", "", "", v.get("reason", "")])
            continue
        rows.append(
            [name, pval(v.get("p")), rpcd(v.get("value", v.get("theta"))),
             rpcd(v.get("median")), "flagged" if v.get("bh_flag") else ""]
        )  # fmt: skip
    L += table(["Cell", "p", "Value", "Baseline median", "BH"], rows)

    # 11. halt --------------------------------------------------------------------------------------
    L += ["## 11. The 8% halt (reported, not modelled)", ""]
    rows = []
    for sid, c in cells.items():
        for acct in ACCOUNTS:
            h = c[acct]["strategy"]["halt"]
            reached = _when(h["reached_s"])
            hit = reached != "not reached"
            rows.append(
                [
                    sid,
                    acct,
                    reached,
                    amount(h["exposure_usd"]) if hit else "n/a",
                    amount(h["further_loss_30d_usd"]) if hit else "n/a",
                ]
            )
    L += table(
        [
            "Strategy",
            "Account",
            "First reached",
            "Open then $",
            "Worst further 30-day fall $",
        ],
        rows,
    )

    L += ["## 12. Limits", ""]
    L += [
        "- **Development only, one market history.** 2021 to 2025: two or three cycles, "
        "mostly rising for the coins that survived. Nothing here was checked on unseen "
        "months.",
        "- **Survivorship.** Today's coins, with no point-in-time universe (section 9 "
        "item 3); the BTC and ETH and the listed-by-2021 rows are shown for that reason.",
        "- **Venue rules** are today's; fees are assumed proportional with no fixed fee.",
        "- **The halt does not exit:** a halted trader manages nothing, and the replay "
        "cannot model the owner's resume.",
        "- **Paper and live fills** differ from the next open (section 9 item 8).",
        "",
        "## 13. Recommendation",
        "",
        "<!-- written after the results were read -->",
        "",
    ]
    return "\n".join(L)


def _random_of(result: Mapping[str, Any], sid: str) -> Dict[str, Any]:
    for mid, s in (("S1", "STRAT-004"), ("S2", "STRAT-005")):
        if s == sid:
            return result["members"][mid]
    return result["exploratory"].get(f"{sid} vs REF-RANDOM") or {}


def _gate_result(result: Mapping[str, Any], sid: str) -> Dict[str, Any]:
    for mid, s in (("G1", "STRAT-001"), ("G2", "STRAT-004"), ("G3", "STRAT-005")):
        if s == sid:
            return result["members"][mid]
    return result["exploratory"].get(f"{sid} + OVL-REGIME vs R3") or {}
