"""
``model_lab.batch``: one frozen model-lab batch (``model_lab.batch.run``) as a research
engine job (PTAI-RD-001 work package 5.4).

* The batch is frozen first (``model_lab.batch.freeze``); the job runs it as frozen.
  ``run`` refuses a batch whose code or scikit-learn version changed since, and the job
  fails with that reason.
* Its progress is the batch's own: the stage, and how far through it.
* Asked to pause or cancel, the batch stops between its steps (its status says
  "stopped"). A resumed job runs the batch again from the start: a batch writes its
  results only when it finishes.
* When it finishes, the trials it logged are brought into the programme trial ledger
  (``research_engine.ledger.sync``).

The one parameter is ``batch_id``. The job's seed is not used: the batch's seeds are
frozen in its record.
"""

from __future__ import annotations

from typing import Any, Dict

from research_engine.jobs import JobContext, StopRequested, job_kind


def run_job(params: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    """The job's work: run the batch, then bring its trials into the ledger."""
    unknown = sorted(set(params) - {"batch_id"})
    if unknown or not str(params.get("batch_id") or "").strip():
        raise ValueError(
            "a model-lab batch job takes one parameter, batch_id"
            + (f" (unknown: {unknown})" if unknown else "")
        )
    from model_lab import batch
    from research_engine import ledger

    batch_id = str(params["batch_id"])
    ctx.stop_if_asked()

    def progress(stage: str, done: int, total: int) -> None:
        share = done / total if total else 0.0
        ctx.progress(min(1.0, share), f"{stage}: {done} of {total}")

    results = batch.run(batch_id, progress=progress, stop=ctx.should_stop)
    if results is None:
        raise StopRequested(ctx.request or "cancel")
    added = ledger.sync(ctx.store.root)
    verdicts: Dict[str, int] = {}
    for contestant in (results.get("contestants") or {}).values():
        verdict = str(contestant.get("verdict"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {
        "batch_id": batch_id,
        "folder": batch.batch_dir(batch_id),
        "contestants": len(results.get("contestants") or {}),
        "verdicts": verdicts,
        "ledger_trials_added": added,
    }


@job_kind("model_lab.batch", version=1)
def model_batch(params: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    return run_job(params, ctx)
