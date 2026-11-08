"""
The strategy lab (FDS-SR-001): any catalogue strategy, evaluated as the trader would
trade it, on cached candles.

* ``candidates``: a strategy's trades on one coin, as the backtester's rules make them:
  the trade from every bar it enters on, and from any bar a baseline asks for, each
  replayed once through the strategy's and its overlays' own exits.
* ``simulate``: one load of candles for a set of coins, and the portfolio replay
  (``signal_fusion.evaluation.replay``) at several account sizes from it.
* ``baselines``: buy-and-hold, cash, and random entries replayed through the strategy's
  own exits.
* ``venue``: today's minimum order and sell-size step per coin, through the exchange
  layer (primary first).

Nothing here places an order, changes a setting or registers an experiment.
"""
