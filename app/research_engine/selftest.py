"""
``engine.selftest``: a small job that checks the engine end to end. It reads no
market data.

It takes ``steps`` steps of ``sleep`` seconds. At each step it draws one number from
a generator seeded with ``(seed, step)``, so a paused and resumed run gives the same
numbers as an uninterrupted one. It saves a checkpoint after every step. Options for
the engine's own tests:
* ``fail``: raise once the steps are done;
* ``nan_result``: return a result that is not plain JSON;
* ``exit_code``: end the process abruptly;
* ``allocate_mib`` and ``hold_seconds``: hold that much memory;
* ``ignore_stop``: never check for a pause or cancel request.
"""

from __future__ import annotations

import os
import time

from research_engine.jobs import JobContext, job_kind

MIB = 1024**2


@job_kind("engine.selftest", version=1)
def selftest(params: dict, ctx: JobContext) -> dict:
    import numpy as np
    import psutil

    started = time.time()
    steps = int(params.get("steps", 3))
    sleep = float(params.get("sleep", 0.0))
    ignore_stop = bool(params.get("ignore_stop", False))
    state = dict(ctx.checkpoint or {"step": 0, "draws": [], "resumed": 0})
    if ctx.checkpoint:
        state["resumed"] += 1
    if params.get("exit_code") is not None:
        os._exit(int(params["exit_code"]))
    held = b"\x01" * (int(params.get("allocate_mib", 0)) * MIB)
    deadline = time.time() + float(params.get("hold_seconds", 0.0))
    while held and time.time() < deadline:
        if not ignore_stop and ctx.should_stop():
            return {}
        time.sleep(0.05)
    while state["step"] < steps:
        if not ignore_stop and ctx.should_stop():
            ctx.save_checkpoint(state)
            return {}
        rng = np.random.default_rng([ctx.seed, state["step"]])
        state["draws"].append(float(rng.random()))
        state["step"] += 1
        ctx.save_checkpoint(state)
        ctx.progress(state["step"] / steps, f"step {state['step']} of {steps}")
        time.sleep(sleep)
    if params.get("fail"):
        raise RuntimeError("the self-test was asked to fail")
    if params.get("nan_result"):
        return {"value": float("nan")}
    return {
        "draws": state["draws"],
        "resumed": state["resumed"],
        "pid": os.getpid(),
        "started": started,
        "ended": time.time(),
        "nice": int(psutil.Process().nice()),
    }
