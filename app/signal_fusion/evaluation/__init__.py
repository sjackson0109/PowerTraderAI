"""
FDS-SIG-004's evaluation (phase A, section 8.3): the tools every test uses. Nothing here
reads candles or a model; the development run (phase C) feeds them.

* ``scoring``: log loss, the Brier score and its decomposition, the Brier skill score,
  calibration in the large and the calibration slope, sharpness, and QLIKE.
* ``bootstrap``: circular blocks of 28 calendar days, all coins together, the centred
  p-value and 10 seeded runs.
* ``replay``: the portfolio replay of one shared account, under the trader's sizing,
  budget, minimum, one trade per coin and free cash, for many paths at once.
* ``baselines``: R3 (a random veto at the filter's per-coin rate) and R3s (random sizing).
* ``findings``: F1, F2 and F3, Q2 and Q3, and their verdict lines.
"""
