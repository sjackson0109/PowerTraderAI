"""
Statistics shared by the research labs (PTAI-RD-001 milestone M2, "one statistics
module").

* ``resampling``: the stationary bootstrap on marked daily results, for strategies that
  hold positions for weeks, and on the mean of a daily series.
* ``multiple``: testing a family at once: Holm, Benjamini-Hochberg, Romano-Wolf.
* ``overfitting``: the deflated Sharpe ratio and the probability of backtest
  overfitting.
* ``power``: the minimum detectable effect, power, and the three verdicts (detected,
  below the smallest effect worth having, inconclusive).
"""
