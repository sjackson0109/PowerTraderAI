"""
Post-hoc diagnostics for the SR-001 bootstrap study: why a method's size is what it is.
They explain the results; they never decide (the selection rule is in the pre-statement).

    "$PY" docs/dev/sr1_bootstrap_diagnostics.py <study-out-dir> <diagnostics.json>

Reads the finished tasks that ``docs/dev/sr1_bootstrap_study.py`` saved in
``<study-out-dir>/parts`` (reproducible from its seeds) and ``results.json``. For every
cell and method it reports:

* **spread ratio:** the mean over replications of the bootstrap's standard deviation
  (from the 90% percentile interval's width ÷ 2 × 1.645) over SD0, the standard deviation
  of θ̂ over the oracle's 4,000 replications. Below 1, the bootstrap is too narrow;
* **robust spread ratio:** the median bootstrap standard deviation over θ̂'s robust scale
  in the study's own replications (interquartile range ÷ 1.349). SD0 is inflated where
  a few replications hold an extreme rally, so this ratio is the one to read there;
* **spread and θ̂:** the correlation between a replication's θ̂ and its bootstrap spread.
  A positive correlation makes a one-sided upper test conservative even when the spread
  is right on average;
* **θ̂ under the null:** its skewness, and the share above 1.645 × SD0 (what a test that
  knew SD0 would reject).
"""

from __future__ import annotations

import glob
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sr1_bootstrap_study as st  # noqa: E402


def main(out_dir: str, dest: str) -> int:
    with open(os.path.join(out_dir, "results.json"), encoding="utf-8") as fh:
        res = json.load(fh)
    by_id = {c["id"]: c for c in res["cells"]}
    out = {"note": "post-hoc diagnostics: they explain, they never decide", "cells": []}
    for cid, c in sorted(by_id.items()):
        src = c["alias"] if c.get("alias", -1) >= 0 else cid
        files = sorted(glob.glob(os.path.join(out_dir, "parts", f"study_{src}_*.pkl")))
        parts = [pickle.load(open(f, "rb")) for f in files]
        sd0 = c["oracle"]["A"]["sd0"]
        entry = {
            "cell": c["name"],
            "deciding": c["deciding"],
            "sd0": sd0,
            "methods": {},
        }
        if c["group"] == "fwer":
            th = np.concatenate([p["fwer"][:, 0, 0, 0] for p in parts])
        else:
            arr = np.concatenate([p["out"] for p in parts])
            th = arr[:, 0, st.F["theta"]]
            q75, q25 = np.percentile(th, [75, 25])
            robust = (q75 - q25) / 1.349
            for j, name in enumerate(st.METHODS):
                spread = (arr[:, j, st.F["hi90p"]] - arr[:, j, st.F["lo90p"]]) / (
                    2 * st.Z95
                )
                ok = np.isfinite(spread)
                corr = (
                    float(np.corrcoef(th[ok], spread[ok])[0, 1])
                    if ok.sum() > 2 and np.std(spread[ok]) > 0
                    else None
                )
                entry["methods"][name] = {
                    "spread_ratio": float(np.mean(spread[ok]) / sd0),
                    "robust_spread_ratio": float(np.median(spread[ok]) / robust),
                    "spread_theta_corr": corr,
                }
        m, s = float(np.mean(th)), float(np.std(th))
        entry["theta_null"] = {
            "mean_over_sd0": m / sd0,
            "skew": float(np.mean((th - m) ** 3) / s**3) if s > 0 else None,
            "share_above_1645_sd0": float(np.mean(th > st.Z95 * sd0)),
        }
        out["cells"].append(entry)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
