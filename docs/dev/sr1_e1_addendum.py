"""SR1-E1's development report, addendum 1: the S3 and S4 verdict lines reworded.

The sealed report (``SR1-E1-REPORT-dev.md``) is never edited. This renders the
corrected lines from the same sealed results with the corrected words in
``strategy_lab.e1``, after checking each input's SHA-256. No figure, test, outcome or
verdict changes.

    python docs/dev/sr1_e1_addendum.py <app dir> <docs/dev/sr1-e1 dir> <out.md>
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

ISSUED = "2026-11-08"
INPUTS = {
    "results.json": "697b09c700a986c6783539c17875107cc5032a7117abff68ad1bdafaf7c9fac7",
    "experiment.json": "9a095a5993295968b86d3ef7c12d9cf9b6a85ef12cd6468522fc547bfc1ad1b1",
    "SR1-E1-REPORT-dev.md": "6ab7821fb8c3e36fa351fb21f4eb47cdf22aed7d962d9103cecddda1bff78bc9",
}
MEMBERS = ("S3", "S4")


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def money(x: float) -> str:
    return f"${x:+,.2f}"


def requirement_rows(result, verdict, halt_pct):
    """F3's five requirements for one member: met or failed, with the figures."""
    r, rep = result["requirements"], result["report"]
    first, second = rep["trades_by_half"]
    h1, h2 = rep["net_by_half"]
    by_coin = rep["net_by_coin"]
    best = max(by_coin, key=by_coin.get)

    def cell(ok, text):
        return f"Met: {text}" if ok else f"**Failed:** {text}"

    return [
        cell(r["trades"], f"{rep['trades']} trades, {first} and {second} by half"),
        cell(
            verdict["holm_pass"],
            (
                f"p = {result['test']['p']:.4f}, passes Holm over 4"
                if verdict["holm_pass"]
                else f"p = {result['test']['p']:.4f}, does not pass Holm over 4"
            ),
        ),
        cell(r["stable"], f"first half {money(h1)}, second half {money(h2)}"),
        cell(
            r["not_one_coin"],
            f"{money(rep['without_best_coin'])} without {best}",
        ),
        cell(
            r["within_halt"],
            f"{rep['max_drawdown']:.2%} against {halt_pct:g}%",
        ),
    ]


def render(app: str, folder: str) -> str:
    sys.path.insert(0, app)
    from strategy_lab import e1

    seen = {}
    for name, want in INPUTS.items():
        got = sha256(os.path.join(folder, name))
        if got != want:
            raise SystemExit(f"{name}: SHA-256 {got}, expected {want}")
        seen[name] = got
    with open(os.path.join(folder, "results.json"), encoding="utf-8") as f:
        sealed = json.load(f)
    with open(os.path.join(folder, "experiment.json"), encoding="utf-8") as f:
        record = json.load(f)
    halt_pct = record["accounts"]["sizing"]["halt_pct"]
    if halt_pct != e1.HALT_PCT:
        raise SystemExit(f"halt level {halt_pct} in the record, {e1.HALT_PCT} in e1")
    members = {m.id: m for m in e1.MEMBERS}

    L = [
        "# SR1-E1 development report: addendum 1",
        "",
        f"Issued {ISSUED}. It corrects the wording of two verdict lines, S3 and S4, "
        "in `SR1-E1-REPORT-dev.md`. That report is sealed evidence and stays unchanged.",
        "",
        "- **What changes:** the words of the S3 and S4 lines and of the note under "
        "family S's table.",
        "- **What does not change:** every figure, test, p-value, outcome and verdict. "
        "S3 and S4 remain failed economic assessments.",
        "- **How it was made:** `docs/dev/sr1_e1_addendum.py` renders the corrected "
        "lines from the same sealed results, with the corrected words in "
        "`strategy_lab.e1`. It checks these files first:",
        "",
        "| File | SHA-256 |",
        "|---|---|",
    ]
    L += [f"| `{name}` | `{h}` |" for name, h in seen.items()]
    L += [
        "",
        "## Why",
        "",
        "Each original line named the F3 requirement that was not met, but not that it "
        'failed. For example, "Not shown to be profitable after fees: a profit in each '
        'half" can be read as saying there was a profit in each half. The opposite is '
        "true: STRAT-004 lost money in the first half. Each original line also gave its "
        "bootstrap p-value, below 0.01, without saying in the line that this meets only "
        "one of F3's five requirements.",
        "",
        "## The corrected lines",
        "",
    ]
    for mid in MEMBERS:
        v = sealed["verdicts"][mid]
        line = e1.member_line(
            members[mid], sealed["members"][mid], v["passed"], v["holm_pass"]
        )
        L += [f"- **{mid}.** {line}"]
    L += ["", "They replace these original lines:", ""]
    for mid in MEMBERS:
        L += [f"- **{mid}.** {sealed['verdicts'][mid]['line']}"]
    L += [
        "",
        "## F3's five requirements, one by one",
        "",
        "A pass needs all five. A bootstrap p-value that passes Holm meets the second "
        "requirement only.",
        "",
        "| Member | Outcome | At least 100 trades and 30 in each half | Bootstrap "
        "test passes Holm | A positive net profit in both halves | A positive net "
        "profit without the most profitable coin | Maximum drawdown below the halt "
        "level |",
        "|---|---|---|---|---|---|---|",
    ]
    for mid in MEMBERS:
        v = sealed["verdicts"][mid]
        rows = requirement_rows(sealed["members"][mid], v, halt_pct)
        L += [f"| {mid} | {v['outcome'].capitalize()} | " + " | ".join(rows) + " |"]
    L += [
        "",
        "## The same results on the account",
        "",
        "Return per capital-day is the net profit divided by the capital-days: the "
        "dollars committed times the days they were held. It says nothing about the "
        "cash left idle. The whole account is shown next to it, because most of the "
        "account stayed in cash.",
        "",
        "| Member | Strategy | Return per capital-day | Return on the account over the "
        "period | A year, on the account | Mean share of the account committed |",
        "|---|---|---|---|---|---|",
    ]
    for mid in MEMBERS:
        sid = members[mid].strategy
        fig = sealed["cells"][sid]["£10,000"]["strategy"]
        L += [
            f"| {mid} | {sid} | {fig['rpcd']:+.4%} | {fig['return_on_account']:+.2%} "
            f"| {fig['annualised']:+.2%} | {fig['mean_committed']:.2%} |"
        ]
    L += [
        "",
        "## The corrected note under family S's table",
        "",
        'For S3 and S4 the day-block bootstrap is the family member, and "p passes '
        "Holm\" is about it alone. It is one of F3's five requirements, and a pass needs "
        "all five: each line names the requirement that failed. With blocks of "
        f"{sealed['block_days']['S']} days (section 2), that bootstrap carries little "
        "information.",
        "",
        "Development only: not evidence for enabling anything.",
        "",
    ]
    return "\n".join(L)


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    text = render(os.path.abspath(argv[1]), os.path.abspath(argv[2]))
    with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {argv[3]}: SHA-256 {sha256(argv[3])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
