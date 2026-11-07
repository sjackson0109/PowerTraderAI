"""
Signal fusion (docs/dev/specs/FDS-SIG-004-price-volume-signal-fusion.md): one assessment per
entry, from price, volume, volatility and liquidity, behind every existing control.

The assessment has two parts. A predictive part may only veto an entry the active strategy
already wants; a protective part may only skip or shrink it. Nothing here opens a trade or
makes one larger, and nothing here is wired to trading: every setting is off by default,
and enabling one needs the evidence and the owner's decision FDS-SIG-004 section 6.7 sets
out.

* ``evaluation``: the scoring rules, the block bootstrap, the portfolio replay, the random
  baselines R3 and R3s, and the findings F1, F2 and F3, Q2 and Q3.
"""
