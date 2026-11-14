"""
SR1-E2's report (``run_sr1_e2.py``): the frozen record and ``strategy_lab.e2.evaluate``'s
results as markdown. It formats only; nothing here scores or decides.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional, Sequence

DEV_ONLY = "Development only: not evidence for enabling anything."
OUTCOME = {
    "pass": "Pass",
    "fail": "Fail",
    "too_few": "Too few trades to tell",
    "not_assessable": "Not assessable",
}


def _f(x: Optional[float], spec: str, none: str = "n/a") -> str:
    if x is None:
        return none
    try:
        return format(float(x), spec)
    except (TypeError, ValueError):
        return none


def money(x) -> str:
    return "n/a" if x is None else f"{float(x):+,.2f}"


def pct(x, digits: int = 2) -> str:
    return _f(x, f"+.{digits}%")


def share(x, digits: int = 1) -> str:
    return _f(x, f".{digits}%")


def rpcd(x) -> str:
    return _f(x, "+.4%")


def pval(x) -> str:
    """4 decimals, or 2 significant figures below 0.001 (a pooled p is never 0)."""
    if x is None:
        return "n/a"
    p = float(x)
    if not p > 0:
        return f"{p:.4f}"
    return f"{p:.{max(4, 1 - math.floor(math.log10(p)))}f}"


def day(s) -> str:
    if s is None or int(s) < 0:
        return "not reached"
    return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime("%Y-%m-%d")


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out + [""]


def _row(name: str, f: Mapping[str, Any], extra: Sequence[Any] = ()) -> List[Any]:
    return [
        name, f.get("trades"), money(f.get("net_usd")), rpcd(f.get("rpcd")),
        pct(f.get("return_on_account")), share(f.get("max_drawdown")),
        share(f.get("intrabar_max_drawdown")), share(f.get("mean_committed")),
        f.get("skipped_cash"), f.get("skipped_minimum"), *extra,
    ]  # fmt: skip


def _yes(x) -> str:
    return "n/a" if x is None else ("yes" if x else "no")


HEAD = [
    "", "Trades", "Net $", "RPCD", "Return", "Max DD (closes)", "Max DD (lows)",
    "Mean committed", "Skipped: cash", "Skipped: minimum",
]  # fmt: skip


def report(record: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    L: List[str] = []
    rehearsal = result.get("rehearsal")
    L += [
        "# SR1-E2: the Donchian ensemble, development report",
        "",
        f"> **{DEV_ONLY}** SR1-E2 read the development period only (2021-01-01 to "
        "2025-05-06). These months had already been looked at for this book (section 3, "
        "earlier exposures). The lockbox (2025-05-06 to 2026-11-06) was not opened. "
        "Nothing is activated, promoted or enabled by this report.",
        "",
    ]
    if rehearsal:
        L += [f"> **REHEARSAL: {rehearsal}. These figures mean nothing.**", ""]

    # 1. power, before the result -----------------------------------------------------------
    pw = result.get("power") or {}
    b1p, b2p = pw.get("B1") or {}, pw.get("B2") or {}
    hp = pw.get("hold comparison") or {}
    L += ["## 1. Power (before the result)", ""]
    L += [
        f"Each member at Holm's first level (5% / {pw.get('k')}) and "
        f"{share(pw.get('power'), 0)} power; the hold comparison one-sided at 5%. The "
        f"lockbox projections assume the same daily spread over its "
        f"{pw.get('lockbox_days')} days (against {pw.get('development_days')} here).",
        "",
    ]
    L += table(
        ["Test", "Smallest detectable effect", "On the lockbox's months", "Notes"],
        [
            ["B1: the book against random entries",
             f"{rpcd(b1p.get('smallest_detectable'))} a capital-day",
             f"about {_f(b1p.get('lockbox_trades_projected'), ',.0f')} trades",
             f"random median {rpcd(b1p.get('random_median'))}; too few to tell if it "
             f"does not pass: {'yes' if b1p.get('too_few') else 'no'}"],
            ["B2: return per capital-day above 0",
             f"{rpcd(b2p.get('smallest_detectable'))} a capital-day",
             f"{rpcd(b2p.get('smallest_detectable_lockbox'))} a capital-day",
             "studentised stationary bootstrap's standard error"],
            ["The hold comparison (shown)",
             f"{_f(hp.get('smallest_detectable_yearly'), '+.3f')} a year (log return)",
             f"{_f(hp.get('smallest_detectable_yearly_lockbox'), '+.3f')} a year",
             "mean daily log-return difference x 365"],
        ],
    )  # fmt: skip

    # 2. verdicts ---------------------------------------------------------------------------------
    L += ["## 2. Verdicts", ""]
    L += [
        "One family, B (K = 2), corrected by Holm at 5%. The trading line compares with "
        'random entries; only the economic line can say "profitable".',
        "",
    ]
    rows = []
    for mid in ("B1", "B2"):
        v = result["verdicts"][mid]
        m = result["members"][mid]
        runs = (
            m.get("runs") if mid == "B1" else (m.get("test") or {}).get("runs")
        ) or []
        ps = [float(r["p"] if isinstance(r, Mapping) else r) for r in runs]
        rows.append(
            [mid, OUTCOME[v["outcome"]], pval(v["p"]),
             f"{pval(min(ps))} to {pval(max(ps))}" if ps else "n/a",
             pval(v.get("holm_adjusted_p")), "yes" if v["holm_pass"] else "no"]
        )  # fmt: skip
    L += table(
        ["Member", "Outcome", "p (pooled)", "p in each run", "Holm-adjusted p",
         "p passes Holm"],
        rows,
    )  # fmt: skip
    for mid in ("B1", "B2"):
        L += [f"- **{mid}.** {result['verdicts'][mid]['line']}"]
    L += [""]
    L += [
        "**Finalist:** "
        + (
            "yes. B1 and B2 both passed: the ensemble at its frozen configuration is a "
            "finalist for the final check on the lockbox, which needs the owner's "
            "separate decision (O5) and its own registration."
            if result.get("finalist")
            else "no. The ensemble is not a finalist, and the lockbox stays closed."
        ),
        "",
        f"**The halt:** {result['halt']['sentence']} That is at the bars' lows; at the "
        f"closes it was {day(result['halt']['book_reached_s'])}. The halt is reported, "
        "not modelled: the replay keeps trading after it, as the registration declared "
        "(D1).",
        "",
    ]

    # 3. registration ----------------------------------------------------------------------------
    acc = record["accounts"]
    rate = acc.get("rate") or {}
    ver = rate.get("verification") or {}
    mk = record["market"]
    exp = record.get("earlier_exposures") or {}
    L += ["## 3. Registration", ""]
    L += [
        f"- **Record:** `{record.get('id')}`, frozen {record.get('frozen_at')}, SHA-256 "
        f"`{record.get('sha256')}`; the approved design's SHA-256 "
        f"`{record.get('design_sha256')}`. Every member, seed, cost, account and rule was "
        "fixed there before anything was scored.",
        f"- **Code:** {len(record.get('code') or {})} files' SHA-256s, including the "
        "ensemble, STRAT-007, the sizing, the gap rule and the research statistics.",
        f"- **GBP/USD:** {acc['gbp_usd']} ({rate.get('source')}, {rate.get('rate_date')}; "
        f"retrieved {rate.get('retrieved_at')}). Checked against "
        f"{ver.get('source', 'n/a')}: {_f(ver.get('cross'), '.5f')}, a difference of "
        f"{share(ver.get('relative_difference'), 3)}.",
        "- **Accounts:** "
        + ", ".join(
            f"£{float(g):,.0f} = ${float(u):,.2f}"
            for g, u in sorted(acc["usd"].items(), key=lambda kv: -float(kv[0]))
        )
        + f"; £{acc['deciding_gbp']:,.0f} decides.",
        f"- **Costs:** {record['costs']['fee']:.2%} taker + "
        f"{record['costs']['allowance']:.2%} slippage a fill ({record['costs']['fee_source']}). "
        f"Venue rules for {len(record['costs']['minimum_usd'])} coins, "
        f"{record['costs'].get('venue_source')}, read {record['costs'].get('venue_read_at')}.",
        f"- **Candles:** {len(mk['series_sha256'])} series, from "
        f"{', '.join(sorted(set(v for v in (mk.get('served_by') or {}).values() if v)) or ['n/a'])} "
        f"(Settings order: {', '.join(mk['exchange_order'])}), offline, each read once. "
        f"Coins: {', '.join(mk['coins_with_development_bars'])}. Left out: "
        + ("; ".join(f"{k} ({v})" for k, v in sorted(mk["left_out"].items())) or "none")
        + ".",
        "- **Earlier exposures** (recorded before the run): "
        + "; ".join(f"PR #{x['pr']}, {x['what']}" for x in exp.get("runs") or [])
        + (
            f"; the exploration sandbox's trial log, {exp['trial_log']['lines']} lines, "
            f"{exp['trial_log']['explorations']} of them explorations."
            if exp.get("trial_log")
            else "."
        ),
        f"- **Run:** {result.get('seconds')} s. Trials logged by kind: "
        + ", ".join(
            f"{k} {v}"
            for k, v in sorted((result.get("trial_counts") or {}).items())
            if v
        )
        + ".",
        "",
    ]

    # 4. the book against the hold ---------------------------------------------------------------
    book, hold = result["book"], result["equal_weight_hold"]
    b2 = result["members"]["B2"]["report"]
    L += ["## 4. The book against the equal-weight hold (£10,000)", ""]
    L += table(HEAD, [_row("The book", book), _row("Equal-weight hold", hold)])
    L += [
        f"- **Drawdown (D1):** the book's {share(b2['intrabar_max_drawdown'])} against the "
        f"hold's {share(b2['hold_intrabar_max_drawdown'])}, each at the bars' lows from a "
        f"peak at the earlier bars' highs (at the closes: {share(b2['max_drawdown'])} "
        f"and {share(b2['hold_max_drawdown'])}).",
        f"- **Halves (by entry day):** {b2['trades_by_half'][0]} and "
        f"{b2['trades_by_half'][1]} trades; net {money(b2['net_by_half'][0])} and "
        f"{money(b2['net_by_half'][1])}.",
        f"- **Without the most profitable coin** ({b2.get('best_coin')}, every member's "
        f"trades on it summed): {money(b2['without_best_coin'])}.",
    ]
    L += [
        f"- **The hold** buys each of the {len(result.get('coins') or [])} coins with its "
        f"own 1/N of the starting account (${_f(hold.get('share_usd'), ',.2f')}) at its "
        "first decision bar; a late-listed coin's share waits as cash until then. "
        + (
            "Not bought: "
            + "; ".join(f"{c} ({why})" for c, why in sorted(hold["not_bought"].items()))
            + "."
            if hold.get("not_bought")
            else "Every coin was bought."
        ),
        "",
    ]
    comp = (result.get("shown_p") or {}).get("hold comparison") or {}
    hold_cmp = result.get("hold_comparison") or {}
    L += ["### The yearly lead over the hold (shown, D3)", ""]
    if hold_cmp.get("assessable"):
        L += [
            f"Mean daily log-return difference (book less hold) x 365: "
            f"{_f(hold_cmp.get('annualised_mean'), '+.3f')}; studentised stationary "
            f"bootstrap (mean block {_f(hold_cmp.get('mean_block'), '.1f')} days), 10 runs "
            f"of 2,000: p = {pval(hold_cmp.get('p'))}, 95% interval (median of the runs' "
            f"bounds) {_f(hold_cmp['interval'][0], '+.3f')} to "
            f"{_f(hold_cmp['interval'][1], '+.3f')}; {share(hold_cmp.get('share_days_ahead'))} "
            f"of {hold_cmp.get('days')} days ahead. Benjamini-Hochberg flag: "
            f"{'yes' if comp.get('bh_flag') else 'no'}.",
            "",
        ]
    else:
        L += [f"Not assessable: {hold_cmp.get('reason')}.", ""]
    L += ["### By year and by member", ""]
    L += table(
        ["Year", "Trades", "Net $", "RPCD"],
        [[y, v["trades"], money(v["net_usd"]), rpcd(v["rpcd"])]
         for y, v in sorted(book["by_year"].items())],
    )  # fmt: skip
    L += table(
        ["Member (days)", "Trades", "Net $", "RPCD"],
        [[n, v["trades"], money(v["net_usd"]), rpcd(v["rpcd"])]
         for n, v in sorted(book["by_member"].items(), key=lambda kv: int(kv[0]))],
    )  # fmt: skip
    L += table(
        ["Coin", "Trades", "Net $", "RPCD"],
        [[c, v["trades"], money(v["net_usd"]), rpcd(v["rpcd"])]
         for c, v in sorted(book["by_coin"].items())],
    )  # fmt: skip

    # 5. random entries, matched holding ---------------------------------------------------------
    b1 = result["members"]["B1"]
    mh = result.get("matched_holding") or {}
    L += ["## 5. Random entries for the book (B1) and matched holding (shown)", ""]
    if b1.get("assessable"):
        L += [
            f"- **REF-RANDOM-E:** {b1.get('draws'):,} draws (10 runs of 200). Return per "
            f"capital-day: the book {rpcd(b1.get('value'))}, the draws' median "
            f"{rpcd(b1.get('median'))} (5th to 95th percentile "
            f"{rpcd(b1['percentiles'][0])} to {rpcd(b1['percentiles'][3])}); "
            f"{share(b1.get('share_at_or_above'))} of draws at or above the book. Entries "
            f"wanted {b1.get('entries_wanted')}, reached (median) "
            f"{_f(b1.get('entries_reached_median'), '.0f')}; {b1.get('draws_short')} draws "
            "ran out of bars before their last entry.",
        ]
    if mh.get("assessable"):
        L += [
            f"- **Matched holding** (reported only): {mh['draws']:,} draws; median return "
            f"per capital-day {rpcd(mh['median_rpcd'])}; "
            f"{share(mh['share_at_or_above'])} at or above the book; median drawdown at "
            f"the lows {share(mh.get('median_intrabar_max_drawdown'))}, "
            f"{share(mh.get('share_drawdown_at_or_below'))} at or below the book's; "
            f"{mh['trades_dropped']} of {mh['trades_wanted'] * mh['draws']:,} holds found "
            "no place.",
        ]
    L += [""]

    # 6. members alone ----------------------------------------------------------------------------
    sp = result.get("shown_p") or {}
    L += ["## 6. Each member alone (the coin's whole allocation; shown)", ""]
    rows = []
    for n, v in sorted(
        (result.get("members_alone") or {}).items(), key=lambda kv: int(kv[0])
    ):
        flag = (sp.get(f"member {n} alone") or {}).get("bh_flag")
        rows.append(
            _row(f"{n} days", v["figures"],
                 [_f(v.get("trades_per_coin_year"), ".1f"), _yes(v.get("below_hold")),
                  pval(v.get("p")), "yes" if flag else "no"])
        )  # fmt: skip
    L += table(
        HEAD + ["Trades a coin a year", "DD below the hold's", "p (RPCD > 0)", "BH"],
        rows,
    )

    # 7. sizing -----------------------------------------------------------------------------------
    L += ["## 7. Volatility-sized books (shown; the book's own sizing decides, D4)", ""]
    rows = []
    for name, v in (result.get("sizing") or {}).items():
        flag = (sp.get(name) or {}).get("bh_flag")
        rows.append(
            _row(name, v["figures"], [_f(v.get("mean_scale"), ".2f"),
                                     _yes(v.get("below_hold")), pval(v.get("p")),
                                     "yes" if flag else "no"])
        )  # fmt: skip
    L += table(HEAD + ["Mean scale", "DD below the hold's", "p (RPCD > 0)", "BH"], rows)

    # 8. PBO ---------------------------------------------------------------------------------------
    pbo = result.get("pbo") or {}
    L += ["## 8. Probability of backtest overfitting (shown)", ""]
    L += [
        f"CSCV over {pbo.get('blocks')} equal blocks of days, each scored by its marked "
        f"profit over its capital-days, across {len(pbo.get('contestants') or [])} "
        f"contestants (the seven members alone and the book): PBO = "
        f"{_f(pbo.get('pbo'), '.3f')}.",
        "",
    ]

    # 9. robustness ---------------------------------------------------------------------------------
    L += ["## 9. Robustness (shown, never deciding)", ""]
    rows = []
    notes = (record.get("robustness") or {}).get("notes") or {}
    for name, v in (result.get("robustness") or {}).items():
        if not v.get("run"):
            rows.append([name, "not run", "", "", "", "", "", "", "", "",
                         v.get("reason", ""), "", "", "", ""])  # fmt: skip
            continue
        flag = (sp.get(f"robust {name}") or {}).get("bh_flag")
        rows.append(
            _row(name, v["figures"],
                 [", ".join(v["coins"]),
                  share((v.get("hold") or {}).get("intrabar_max_drawdown")),
                  _yes(v.get("below_hold")), pval(v.get("p")), "yes" if flag else "no"])
        )  # fmt: skip
    L += table(
        HEAD
        + ["Coins", "Hold's DD (lows)", "DD below the hold's", "p (RPCD > 0)", "BH"],
        rows,
    )
    L += [f"- **{k}:** {v}" for k, v in notes.items()]
    for name, v in (result.get("robustness") or {}).items():
        missing = ((v.get("hold") or {}).get("not_bought")) or {}
        if missing:
            L += [
                f"- **{name}, the hold:** not bought: "
                + "; ".join(f"{c} ({why})" for c, why in sorted(missing.items()))
                + "."
            ]
    L += [""]

    # 10. the halt ----------------------------------------------------------------------------------
    h = result["halt"]
    L += ["## 10. The 8% halt (reported, not modelled)", ""]
    L += table(
        ["", "First reached (lows)", "First reached (closes)"],
        [
            ["The book", day(h["book_intrabar_reached_s"]), day(h["book_reached_s"])],
            ["Equal-weight hold", day(h["hold_intrabar_reached_s"]), day(h["hold_reached_s"])],
        ],
    )  # fmt: skip
    if int(h["book_intrabar_reached_s"]) >= 0 or int(h["book_reached_s"]) >= 0:
        L += [
            "Trading the book as configured would need the trader's halt changed. For "
            "this evaluation only, the registration replaced F3's halt requirement by "
            "the comparison with the hold (D1).",
            "",
        ]
    else:
        L += ["The book never reached the trader's halt.", ""]
    L += [
        "## 11. Limits",
        "",
        "- **Not unseen evidence.** These months were explored for this book before "
        "(section 3).",
        "- **One market history and survivorship:** today's coins; the BTC and ETH and "
        "the listed-by-2021 rows are shown for that reason.",
        "- **Venue rules** are today's; fees are assumed proportional with no fixed fee.",
        "- **The halt is reported, not modelled**, and fills at the next open differ "
        "from paper and live fills.",
        "",
        "## 12. Recommendation",
        "",
        "<!-- written after the results were read -->",
        "",
    ]
    return "\n".join(L)
