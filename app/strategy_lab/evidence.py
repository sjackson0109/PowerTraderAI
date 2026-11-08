"""
Model evidence per strategy, for Settings > Strategy, "Model evidence..." (FDS-SR-001
section 5.8).

Two sources, both frozen:

* ``RECORDED``: evidence from runs written up before the strategy lab existed, copied
  here verbatim from their reports in a reviewed change (like ``looks.STRATEGY_LOOKS``).
* A declared experiment's ``results.json``, next to its sealed ``experiment.json``
  (``write_results``; FDS-SR-001 M5c, which needs the owner's approval to run). A results
  file is sealed too, and one whose record or results changed is not shown.

Each line is one finding of one kind, kept apart (section 6.6): **prediction** (do the
forecasts improve), **trading** (does the strategy or filter beat its matched
baseline) and **economic** (is it profitable after costs). The words state facts only.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import List, Mapping, Sequence

from model_lab.batch import _seal, _write_json
from strategy_lab import experiment

KINDS = ("prediction", "trading", "economic")
KIND_NAMES = {"prediction": "Prediction", "trading": "Trading", "economic": "Economic"}


@dataclass(frozen=True)
class Line:
    strategy_id: str
    model: str  # what was compared, in plain words
    kind: str  # prediction, trading or economic
    text: str  # the finding, verbatim
    period: str  # the data it covered
    recorded: str  # when, and that it is development only where it is


_SIG4 = "2021-01-01 to 2025-05-06, 11 coins, 1-hour candles, 0.50% fee"
_DEV = "2026-11-07, development only"

RECORDED = (
    Line(
        "STRAT-001",
        "Price and volume model against price only",
        "prediction",
        "No forecast improvement detected (Δ log loss = +0.00033, smallest detectable "
        "Δ log loss = 0.00112, n = 351099)",
        _SIG4,
        _DEV,
    ),
    Line(
        "STRAT-001",
        "Price and volume model's calibration",
        "prediction",
        "Calibration not assessable; no skill above the base rate shown",
        _SIG4,
        _DEV,
    ),
    Line(
        "STRAT-001",
        "Price and volume veto against price-only veto",
        "trading",
        "No improvement over price alone detected (smallest detectable difference = "
        "+0.00298 a capital-day)",
        _SIG4,
        _DEV,
    ),
    Line(
        "STRAT-001",
        "Volatility shrink against random sizing",
        "trading",
        "No reduction in drawdown compared with random sizing detected",
        _SIG4,
        _DEV,
    ),
    Line(
        "STRAT-001",
        "Price and volume veto",
        "economic",
        "Not shown to be profitable after fees: a profit per capital-day "
        "(385 trades, net -$131 on $10,000)",
        _SIG4,
        _DEV,
    ),
)


def results_path(experiment_id: str) -> str:
    return os.path.join(experiment.experiment_dir(experiment_id), "results.json")


def write_results(experiment_id: str, lines: Sequence[Line]) -> dict:
    """Seal and write a frozen experiment's result lines (never overwritten)."""
    experiment.verify(experiment_id)
    path = results_path(experiment_id)
    if os.path.exists(path):
        raise experiment.ExperimentError(
            f"experiment {experiment_id} already has results"
        )
    for line in lines:
        if line.kind not in KINDS:
            raise experiment.ExperimentError(f"unknown finding kind {line.kind!r}")
    record = _seal(
        {"experiment": experiment_id, "lines": [asdict(line) for line in lines]}
    )
    _write_json(path, record)
    return record


def _from_experiments(strategy_id: str) -> List[Line]:
    folder = os.path.join(experiment.lab_dir(), "experiments")
    out: List[Line] = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        path = results_path(name)
        if not os.path.exists(path):
            continue
        try:
            experiment.verify(name)
            with open(path, encoding="utf-8") as f:
                record = json.load(f)
        except (experiment.ExperimentError, OSError, ValueError):
            continue  # changed since it was frozen: not shown
        body = {k: v for k, v in record.items() if k != "sha256"}
        if _seal(body)["sha256"] != record.get("sha256"):
            continue
        for item in record.get("lines") or []:
            if isinstance(item, Mapping) and item.get("strategy_id") == strategy_id:
                out.append(Line(**{k: item[k] for k in Line.__dataclass_fields__}))
    return out


def lines_for(strategy_id: str) -> List[Line]:
    """Every finding about models with ``strategy_id``: recorded first, then the
    declared experiments', each in its kind's order."""
    found = [line for line in RECORDED if line.strategy_id == strategy_id]
    found += _from_experiments(strategy_id)
    return sorted(found, key=lambda line: KINDS.index(line.kind))
