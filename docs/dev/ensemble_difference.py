"""
How sure the ensemble book's lead over the equal-weight hold is, for the exploration's
report: the annualised mean of the daily log-return difference (book less hold), with a
stationary bootstrap of the days (Politis and Romano 1994, mean block 20 days), as 10
seeded runs of 500 resamples (seeds 910000 to 910009), pooled and per run.

Descriptive only: the months were used before, and nothing here was registered.

    python ensemble_difference.py <ensemble_periods.json>
"""

from __future__ import annotations

import json
import sys

import numpy as np

BLOCK = 20
RESAMPLES = 500
SEEDS = [910_000 + s for s in range(10)]


def _daily(part):
    return {r["period"]: r["return"] for r in part["periods"]["day"]["returns"]}


def _resample_mean(x: np.ndarray, rng: np.random.Generator) -> float:
    n = len(x)
    idx = np.empty(n, dtype=int)
    i = rng.integers(n)
    for t in range(n):
        if t and rng.random() < 1.0 / BLOCK:
            i = rng.integers(n)
        idx[t] = i
        i = (i + 1) % n
    return float(x[idx].mean() * 365)


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for name, part in data.items():
        book, hold = _daily(part["book"]), _daily(part["equal_weight_hold"])
        days = sorted(set(book) & set(hold))
        x = np.log1p([book[d] for d in days]) - np.log1p([hold[d] for d in days])
        runs, pooled = [], []
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            draws = np.array([_resample_mean(x, rng) for _ in range(RESAMPLES)])
            pooled.append(draws)
            runs.append(
                {
                    "seed": seed,
                    "interval_95": [
                        float(np.percentile(draws, 2.5)),
                        float(np.percentile(draws, 97.5)),
                    ],
                    "share_at_or_below_zero": float(np.mean(draws <= 0)),
                }
            )
        allx = np.concatenate(pooled)
        out[name] = {
            "days": len(days),
            "first": days[0],
            "last": days[-1],
            "annualised_mean_difference": float(x.mean() * 365),
            "pooled": {
                "resamples": int(len(allx)),
                "interval_95": [
                    float(np.percentile(allx, 2.5)),
                    float(np.percentile(allx, 97.5)),
                ],
                "share_at_or_below_zero": float(np.mean(allx <= 0)),
            },
            "runs": runs,
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
