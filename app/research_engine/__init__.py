"""
The local research engine (PTAI-RD-001 milestone M5): runs research jobs on the
owner's workstation, in bounded worker processes kept apart from trading.

* ``resources``: what the machine has (cores, memory, GPU, disk) and the operating
  modes' limits (maximum throughput, balanced, low resource).
* ``store``: the persistent job queue (SQLite). A job is identified by its kind,
  parameters and seed, so an identical job is never queued twice.
* ``jobs``: job kinds and the context a job runs with (seed, checkpoint, progress,
  stop requests).
* ``scheduler``: starts queued jobs in worker processes by priority, within the
  mode's limits, at below-normal priority, and records each job's time, memory and
  outcome.

Nothing here places orders, reads trading credentials or imports the trader.
"""
