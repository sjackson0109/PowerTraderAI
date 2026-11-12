"""
``strategy_lab.run``: one strategy backtest (``strategy_lab.runs.run``) as a research
engine job, under the same rules as Settings > Strategy, "Run a backtest...":
* the development period only: a period reaching the reserved months (from
  2025-05-06) is refused before any candle is read;
* logged as an exploratory trial with its months, in the strategy lab's trial log,
  and saved under ``strategy_lab/runs``;
* an exploration, never evidence.

The parameters are ``strategy_lab.runs.RunConfig``'s fields except ``seed``: the job's
seed is the run's random-entry seed, so the job's key covers it. A job asked to pause
or cancel stops between the run's stages and saves nothing; a resumed run starts again.
"""

from __future__ import annotations

import dataclasses
import math
import threading
from typing import Any, Callable, Dict, Optional

from research_engine.jobs import JobContext, StopRequested, job_kind

_STAGES = (
    "Reading candles",
    "Finding the strategy's trades",
    "Reading minimum orders",
    "Replaying the account",
    "Replaying",  # the random-entry draws
)
WATCH_SECONDS = 0.5


def config_from(params: Dict[str, Any], seed: int):
    """The run's ``RunConfig``; unknown fields, and a ``seed`` field, are refused."""
    from strategy_lab.runs import RunConfig

    fields = {f.name for f in dataclasses.fields(RunConfig)} - {"seed"}
    unknown = sorted(set(params) - fields)
    if unknown:
        raise ValueError(
            f"unknown backtest settings {unknown}; the seed is the job's own"
            if "seed" in unknown
            else f"unknown backtest settings {unknown}"
        )
    return RunConfig(**params, seed=int(seed))


def _plain(value: Any) -> Any:
    """``value`` as plain JSON: an undefined figure (NaN or infinite) is None."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return _plain(value.item())  # a numpy scalar
    return value


def _summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """The run's figures, without its equity curve (that stays in its run.json)."""
    keys = (
        "period",
        "account_usd",
        "strategy_result",
        "holding_days",
        "per_coin",
        "buy_and_hold",
        "random_entries",
    )
    return _plain({"run_id": record.get("id"), **{k: record.get(k) for k in keys}})


def run_job(
    params: Dict[str, Any],
    ctx: JobContext,
    loader: Optional[Callable] = None,
    venue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """The job's work; ``loader`` and ``venue`` replace the exchange layer in tests."""
    from strategy_lab import runs

    config = config_from(params, ctx.seed)
    ctx.stop_if_asked()
    stop, done = threading.Event(), threading.Event()

    def watch() -> None:
        while not done.wait(WATCH_SECONDS):
            if ctx.should_stop():
                stop.set()
                return

    watcher = threading.Thread(target=watch, name="stop-watch", daemon=True)
    watcher.start()

    def progress(message: str) -> None:
        stage = next(
            (i for i, s in enumerate(_STAGES) if message.startswith(s)), len(_STAGES)
        )
        ctx.progress(stage / len(_STAGES), message)

    extra: Dict[str, Any] = {}
    if loader is not None:
        extra["loader"] = loader
    if venue is not None:
        extra["venue"] = venue
    try:
        record = runs.run(config, stop=stop, progress=progress, **extra)
    except runs.Stopped:
        raise StopRequested(ctx.request or "cancel") from None
    finally:
        done.set()
        watcher.join(timeout=5)
    return _summary(record)


@job_kind("strategy_lab.run", version=1)
def strategy_run(params: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    return run_job(params, ctx)
