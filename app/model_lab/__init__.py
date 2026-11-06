"""
The model lab: compares entry models ("contestants") under the trader's fixed strategy
(docs/dev/specs/FDS-MH-001-multi-model-harness.md).

A contestant decides only when to enter. The exits, DCA, sizing and fees are the
trader's, the same for every contestant (``replay``). Each contestant is scored walk-
forward on bars it was not fitted on (``walkforward``), against random entries that
keep its patience (``baselines``), pooled over coins, with the number of contestants
tried corrected for (``stats``). A batch is frozen before it runs, and every scored
contestant is logged as a trial (``batch``). The last months of every series stay
locked: nothing in a run reads them.

* ``series``: the candles, through the exchange layer (the primary exchange first).
* ``replay``: the trade an entry at each hour makes.
* ``walkforward``: the fold calendar and each contestant's decisions, fold by fold.
* ``baselines``: random entries made with the same waits (R1), and the contestant's own
  schedule moved to other dates (R2).
* ``stats``: p-values, Benjamini-Hochberg, Holm, the smallest detectable edge and the
  probability of backtest overfitting.
* ``contestants`` and ``catalogue``: the entry models and their fixed parameters.
* ``batch``: freeze, run, the trial log, the results and the report.

Nothing here places an order, publishes a model or changes a setting. It runs from
Settings > Training; there is no command line.
"""
