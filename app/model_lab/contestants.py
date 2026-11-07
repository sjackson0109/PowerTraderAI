"""
Entry models ("contestants", FDS-MH-001 section 5.5). A contestant decides only when
to enter: ``fit(data, until)`` learns from bars that closed by ``until`` (a rule has
nothing to learn), and the fit's ``entries(coin, close_s)`` gives one value per hour:
1 enter if flat, 0 don't, -1 undecided. A value at an hour uses only bars that closed
by that hour.

**Daily values** come from the 1-hour bars (``Series.daily``: complete UTC days). At an
hour, a daily rule reads the last UTC day that had ended by then; when that day was not
built (an hour of it is missing), the hour is undecided. A rule over N days reads the
last N built days.

The untrained rules (batch 1, section 7):

* ``rule.smaN``: the daily close above the average of the last N daily closes;
* ``rule.mom14``: the daily close above the daily close 14 days before it;
* ``rule.high20``: the daily close at or above the highest of the 20 before it;
* ``rule.btc50``: BTC's daily close above its 50-day average (for every coin);
* ``rule.dip24``: the 24-hour return (this hour's close over the close 24 hours
  earlier; undecided when that bar is missing) below the coin's own 10th percentile of
  the 24-hour returns of the 90 days before the hour;
* ``ref.always``: enter whenever flat. A reference only, not tested: its random
  baselines are itself.

``pattern`` is the trainer's pattern model, as the trader uses it: an entry when the
long count is at least the trade rules' ``trade_start_level`` and the short count is 0.
It is fitted per coin per fold by the trainer itself (``pt_pattern_trainer.train``,
on the coin's bars from the batch's exchange), and its counts come from
``model_gate.hourly_signals``, as the entry gate's do.

**Trained, pooled contestants** (section 5.5, phase C). One fit per fold on every batch
coin's rows before the fold (``features``, ``targets``): rows whose features are all
numbers and whose label is resolved and purged, each weighted by its uniqueness.

* ``linear.<target>.q<N>``: logistic regression (T1) on the 26 features, standardised on
  the training rows; L2 penalty, C = 1.
* ``trees.<target>.q<N>``: scikit-learn's histogram gradient-boosted trees on the 26
  features (section 7's settings), a classifier for T1 and a regressor for T2. T2's labels
  are winsorised at the training rows' 1st and 99th percentiles.
* Batch PV-1 (section 7a): ``pv.linear.t1.P.q50`` (block P), ``pv.linear.t1.PV.q50``
  (P + V) and ``pv.linear.t1.PVp.q50`` (P + the placebo's first variant), on the common
  rows only; the placebo's variants 2 to 5 (``pv.linear.t1.PVp<j>.q50``) are fitted for
  their probabilities only (``forecast_only``) and are not tested.

**Thresholds.** A fit enters when its score (T1's probability, or T2's predicted value) is
in the top q of the scores it gave its own training rows: at or above their (1 - q)
quantile. Nothing is chosen on held-out bars. An hour whose features are not all numbers,
or (PV-1) is not a common row, is undecided.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from model_lab.series import HOUR_S, Series, last_completed_day
from model_lab.walkforward import LabData


class Fitted:
    def entries(self, coin: str, close_s: Sequence[int]) -> np.ndarray:
        raise NotImplementedError

    def probabilities(self, coin: str, close_s: Sequence[int]) -> Optional[np.ndarray]:
        """One probability of the fit's target per hour (NaN where undecided), or None
        when it has none (amendment 1). Entries never read it."""
        return None


class Contestant:
    key: str = ""
    family: str = ""  # "reference", "rule", "pattern", "linear" or "trees"
    params: Dict[str, Any] = {}
    pooled: bool = True  # one fit for all coins, or one per coin
    trained: bool = False
    tested: bool = True  # False: shown as a reference, not tested
    neural_dca: bool = False  # it has long counts, for the neural DCA line
    history_days: int = 0  # a trained contestant's bars before its first fit
    description: str = ""

    def fit(self, data: LabData, until: int, coin: Optional[str] = None) -> Fitted:
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "family": self.family,
            "params": dict(self.params),
            "description": self.description,
            "pooled": self.pooled,
            "tested": self.tested,
        }


def _at(series: Series, close_s: Sequence[int]) -> Tuple[np.ndarray, np.ndarray]:
    """For each close time, the series' bar closing then: (its position, whether there
    is one)."""
    close_s = np.asarray(close_s, dtype=np.int64)
    k = np.searchsorted(series.close_s, close_s, "left")
    safe = np.minimum(k, max(len(series) - 1, 0))
    found = (
        (k < len(series)) & (series.close_s[safe] == close_s)
        if len(series)
        else (np.zeros(len(close_s), dtype=bool))
    )
    return safe, found


class _RuleFit(Fitted):
    def __init__(self, rule: "Rule", data: LabData):
        self.rule = rule
        self.data = data

    def entries(self, coin: str, close_s: Sequence[int]) -> np.ndarray:
        return self.rule.decide(self.data, coin, close_s)


class Rule(Contestant):
    family = "rule"

    def fit(self, data: LabData, until: int, coin: Optional[str] = None) -> Fitted:
        return _RuleFit(self, data)

    def decide(self, data: LabData, coin: str, close_s: Sequence[int]) -> np.ndarray:
        raise NotImplementedError


def _daily_decision(series: Series, close_s, on_day) -> np.ndarray:
    """For each hour, ``on_day``'s value (1, 0 or -1) for the last completed day."""
    days = series.daily
    k = days.index_of(last_completed_day(close_s))
    by_day = on_day(days.close)
    return np.where(k >= 0, by_day[np.maximum(k, 0)], -1).astype(np.int8)


def _above_average(n: int):
    def on_day(close: np.ndarray) -> np.ndarray:
        out = np.full(len(close), -1, dtype=np.int8)
        if len(close) >= n:
            total = np.concatenate([[0.0], np.cumsum(close)])
            mean = (total[n:] - total[:-n]) / n  # day k = n-1 ... len-1
            out[n - 1 :] = (close[n - 1 :] > mean).astype(np.int8)
        return out

    return on_day


class DailyAboveAverage(Rule):
    def __init__(self, days: int, context: bool = False):
        self.days = int(days)
        self.context = context
        if context:
            self.key = f"rule.btc{days}"
            self.description = f"BTC's daily close above its {days}-day average"
        else:
            self.key = f"rule.sma{days}"
            self.description = f"Daily close above its {days}-day average"
        self.params = {"days": self.days, "bars": "complete UTC days"}
        if context:
            self.params["coin"] = "BTC, for every coin"

    def decide(self, data: LabData, coin: str, close_s) -> np.ndarray:
        series = data.series[data.context if self.context else coin]
        return _daily_decision(series, close_s, _above_average(self.days))


class Momentum(Rule):
    def __init__(self, days: int):
        self.days = int(days)
        self.key = f"rule.mom{days}"
        self.description = f"Daily close above its close {days} days earlier"
        self.params = {"days": self.days, "bars": "complete UTC days"}

    def decide(self, data: LabData, coin: str, close_s) -> np.ndarray:
        n = self.days

        def on_day(close: np.ndarray) -> np.ndarray:
            out = np.full(len(close), -1, dtype=np.int8)
            out[n:] = (close[n:] > close[:-n]).astype(np.int8)
            return out

        return _daily_decision(data.series[coin], close_s, on_day)


class NewHigh(Rule):
    def __init__(self, days: int):
        self.days = int(days)
        self.key = f"rule.high{days}"
        self.description = (
            f"Daily close at or above the highest of the previous {days} daily closes"
        )
        self.params = {"days": self.days, "bars": "complete UTC days"}

    def decide(self, data: LabData, coin: str, close_s) -> np.ndarray:
        n = self.days

        def on_day(close: np.ndarray) -> np.ndarray:
            out = np.full(len(close), -1, dtype=np.int8)
            if len(close) > n:
                windows = np.lib.stride_tricks.sliding_window_view(close[:-1], n)
                out[n:] = (close[n:] >= windows.max(axis=1)).astype(np.int8)
            return out

        return _daily_decision(data.series[coin], close_s, on_day)


class Dip(Rule):
    def __init__(self, hours: int = 24, percentile: float = 10.0, days: int = 90):
        self.hours = int(hours)
        self.percentile = float(percentile)
        self.days = int(days)
        self.key = f"rule.dip{hours}"
        self.description = (
            f"{hours}-hour return below the coin's own {percentile:g}th percentile of "
            f"the last {days} days"
        )
        self.params = {
            "hours": self.hours,
            "percentile": self.percentile,
            "days": self.days,
            "bars": "hourly",
        }

    def returns(self, series: Series) -> np.ndarray:
        """Each bar's return over ``hours`` (NaN when the bar that long before is
        missing)."""
        back = series.close_s - self.hours * HOUR_S
        k, found = _at(series, back)
        out = np.full(len(series), np.nan)
        out[found] = series.close[found] / series.close[k[found]] - 1.0
        return out

    def decide(self, data: LabData, coin: str, close_s) -> np.ndarray:
        import pandas as pd

        series = data.series[coin]
        r = self.returns(series)
        keep = ~np.isnan(r)
        index = pd.to_datetime(series.close_s[keep], unit="s", utc=True)
        values = pd.Series(r[keep], index=index)
        line = values.rolling(f"{self.days}D", closed="left").quantile(
            self.percentile / 100.0
        )
        threshold = np.full(len(series), np.nan)
        threshold[keep] = line.to_numpy()
        k, found = _at(series, close_s)
        rk, tk = r[k], threshold[k]
        ok = found & ~np.isnan(rk) & ~np.isnan(tk)
        return np.where(ok, (rk < tk).astype(np.int8), -1).astype(np.int8)


class AlwaysFlat(Rule):
    key = "ref.always"
    family = "reference"
    tested = False
    description = "Enter whenever flat"
    params: Dict[str, Any] = {}

    def decide(self, data: LabData, coin: str, close_s) -> np.ndarray:
        _k, found = _at(data.series[coin], close_s)
        return np.where(found, 1, -1).astype(np.int8)


# --- the pattern model ------------------------------------------------------------------


def _quiet(*_args, **_kwargs):
    pass


class PatternFit(Fitted):
    """One pattern-model fit: the trainer's model, and the coin's bars from the same
    exchange to read its counts."""

    def __init__(
        self, model, coin: str, data: LabData, start_s: int, until: int, files
    ):
        self.model = model
        self.coin = coin
        self.data = data
        self.start_s = start_s
        self.until = until
        self.files = files

    def record(self, coin: str) -> Dict[str, Any]:
        from model_lab.series import iso

        return {
            "fit_start": iso(self.start_s),
            "fit_end": iso(self.until),
            "files_sha256": self.files,
        }

    def counts(
        self, coin: str, close_s
    ) -> Tuple[List[Optional[int]], List[Optional[int]]]:
        """The long and short counts at each hour (None: undecided), as the entry
        gate reads them."""
        from datetime import datetime, timezone

        import model_gate
        import pt_pattern_trainer as ppt

        close_s = [int(t) for t in close_s]
        if not close_s:
            return [], []
        start = datetime.fromtimestamp(close_s[0] - HOUR_S, tz=timezone.utc)
        end = datetime.fromtimestamp(close_s[-1], tz=timezone.utc)
        fit_start = datetime.fromtimestamp(self.start_s, tz=timezone.utc)
        series = self.data.series[coin]
        loader = ppt.BarLoader(
            coin,
            max(fit_start, start - ppt.GATE_LOOKBACK),
            end,
            self.data.offline,
            self.data.cache_dir,
            exchanges=[series.exchange],
        )
        frames = {}
        for tf_choice in ppt.TF_CHOICES:
            tf = ppt.CANDLE_TF[tf_choice]
            try:
                loader.bars(tf_choice)
                frames[tf] = loader.frames[tf]
            except ppt.TrainerError:
                frames[tf] = ppt._empty_frame()
        hours = model_gate.hourly_signals(
            self.model, frames, int(start.timestamp()), int(end.timestamp())
        )
        at = {t: (n, m) for t, n, m in zip(hours.close_s, hours.longs, hours.shorts)}
        longs = [at.get(t, (None, None))[0] for t in close_s]
        shorts = [at.get(t, (None, None))[1] for t in close_s]
        return longs, shorts

    def counts_and_entries(self, coin: str, close_s):
        longs, shorts = self.counts(coin, close_s)
        level = self.data.rules.trade_start_level
        values = np.array(
            [
                -1 if n is None else int(n >= level and m == 0)
                for n, m in zip(longs, shorts)
            ],
            dtype=np.int8,
        )
        return longs, values

    def entries(self, coin: str, close_s) -> np.ndarray:
        return self.counts_and_entries(coin, close_s)[1]


class Pattern(Contestant):
    key = "pattern"
    family = "pattern"
    pooled = False
    trained = True
    neural_dca = True
    history_days = 365  # a coin joins once it has 12 months of bars
    description = "The pattern model, as the trader uses it"

    @property
    def params(self) -> Dict[str, Any]:  # type: ignore[override]
        return {
            "entry": "long count at least the trade start level, short count 0",
            "fit": "the trainer's, per coin, on every bar before the fold",
        }

    def fit(self, data: LabData, until: int, coin: Optional[str] = None) -> PatternFit:
        from datetime import datetime, timezone

        import pt_paths
        import pt_pattern_trainer as ppt
        from pattern_model import PatternModel, model_file_names

        series = data.series[coin]
        start_s = max(int(data.start_s), series.first_open_s)
        parent = os.path.join(pt_paths.cache_dir(), "model-lab-fits")
        os.makedirs(parent, exist_ok=True)
        work = tempfile.mkdtemp(dir=parent)
        try:
            ppt.train(
                coin,
                work,
                datetime.fromtimestamp(start_s, tz=timezone.utc),
                datetime.fromtimestamp(int(until), tz=timezone.utc),
                seed=data.seed,
                offline=data.offline,
                cache_dir=data.cache_dir,
                log=_quiet,
                exchanges=[series.exchange],
            )
            model = PatternModel.from_folder(work)
            files = {
                name: ppt._file_sha256(os.path.join(work, name))
                for name in model_file_names()
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return PatternFit(model, coin, data, start_s, int(until), files)


# --- trained, pooled contestants (phase C) --------------------------------------------------

FEATURE_HISTORY_DAYS = 50  # section 5.4: a coin joins once it has 50 days of bars
TREES_SETTINGS = {
    "learning_rate": 0.05,
    "max_iter": 300,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 200,
    "l2_regularization": 1.0,
    "early_stopping": False,
}
TARGET_WORDS = {
    "t1": "clean win: the profit line before the first DCA level, within 336 hours",
    "t2": "return per day held of the replayed trade, 30 days at most",
}


def _sha256_rows(keys) -> str:
    import hashlib

    h = hashlib.sha256()
    for coin, close_s in keys:
        h.update(coin.encode("utf-8"))
        h.update(np.asarray(close_s, dtype=np.int64).tobytes())
    return h.hexdigest()


class ModelFit(Fitted):
    """One fold's fit of a trained, pooled contestant."""

    def __init__(self, contestant, data, until, model, mean, std, threshold, n, rows):
        self.contestant = contestant
        self.data = data
        self.until = int(until)
        self.model = model
        self.mean = mean
        self.std = std
        self.threshold = threshold
        self.rows = n
        self.rows_sha256 = rows

    def _scores(self, coin: str, close_s) -> Tuple[np.ndarray, np.ndarray]:
        """(whether each hour is decided, each decided hour's score)."""
        from model_lab import features as ft

        t = ft.table(self.data, coin)
        k = t.grid.positions(close_s)
        if self.model is None or not len(t.grid):
            return np.zeros(len(k), dtype=bool), np.zeros(0)
        mask = self.contestant.rows_mask(self.data, coin)
        decided = (k >= 0) & mask[np.maximum(k, 0)]
        x = self.contestant.matrix(self.data, coin)[k[decided]]
        return decided, self.contestant.score(self, x)

    def entries(self, coin: str, close_s) -> np.ndarray:
        decided, scores = self._scores(coin, close_s)
        out = np.full(len(decided), -1, dtype=np.int8)
        out[decided] = (scores >= self.threshold).astype(np.int8)
        return out

    def probabilities(self, coin: str, close_s) -> Optional[np.ndarray]:
        if self.contestant.target != "t1":
            return None
        decided, scores = self._scores(coin, close_s)
        out = np.full(len(decided), np.nan)
        out[decided] = scores
        return out

    def record(self, coin: str) -> Dict[str, Any]:
        from model_lab.series import iso

        return {
            "fit_end": iso(self.until),
            "training_rows": self.rows,
            "rows_sha256": self.rows_sha256,
            "threshold": self.threshold,
        }


class Model(Contestant):
    """A trained, pooled contestant (the module docstring)."""

    trained = True
    pooled = True
    history_days = FEATURE_HISTORY_DAYS

    def __init__(
        self,
        family: str,
        target: str,
        q: float,
        blocks: Sequence[str] = ("P", "v1"),
        key: Optional[str] = None,
        description: Optional[str] = None,
        common_rows: bool = False,
        forecast_only: bool = False,
    ):
        from model_lab import features as ft

        self.family = family
        self.target = target
        self.q = float(q)
        self.blocks = tuple(blocks)
        # batch 1's 26 keep section 5.5's order
        self.names = (
            ft.FEATURES_26
            if self.blocks == ("P", "v1")
            else ft.block_names(self.blocks)
        )
        self.common_rows = bool(common_rows)
        self.forecast_only = bool(forecast_only)
        self.tested = not forecast_only
        self.join_on_first_decided = bool(common_rows)
        top = f"q{int(round(self.q * 100))}"
        self.key = key or f"{family}.{target}.{top}"
        kind = "Logistic regression" if family == "linear" else "Gradient-boosted trees"
        self.description = description or (
            f"{kind} on "
            + ("clean wins" if target == "t1" else "return per day held")
            + f", top {self.q:.0%}"
        )
        self.params = {
            "target": TARGET_WORDS[target],
            "top": f"{self.q:.0%} of the scores of its own training rows",
            "features": f"{len(self.names)}: " + " + ".join(self.blocks),
            "rows": "every batch coin's rows before the fold, purged, weighted by "
            "uniqueness" + ("; common rows only" if common_rows else ""),
            **(
                {"model": "logistic regression, L2 penalty, C = 1, standardised"}
                if family == "linear"
                else {"model": "histogram gradient-boosted trees", **TREES_SETTINGS}
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "blocks": list(self.blocks),
            "forecast_only": self.forecast_only,
        }

    # rows -------------------------------------------------------------------------------

    def coins(self, data: LabData) -> List[str]:
        """The batch's coins (those with a fee): the rows a fit pools."""
        return sorted(data.fees) if data.fees else sorted(data.series)

    def matrix(self, data: LabData, coin: str) -> np.ndarray:
        from model_lab import features as ft

        key = ("matrix", self.names, coin)
        if key not in data.cache:
            data.cache[key] = ft.table(data, coin).matrix(self.names)
        return data.cache[key]

    def rows_mask(self, data: LabData, coin: str) -> np.ndarray:
        """The grid hours this contestant may use at all: features complete, and (PV-1)
        a common row."""
        from model_lab import features as ft

        key = ("mask", self.names, self.common_rows, coin)
        if key not in data.cache:
            t = ft.table(data, coin)
            ok = t.grid.present & np.isfinite(self.matrix(data, coin)).all(axis=1)
            if self.common_rows:
                ok &= ft.common_mask(t)
            data.cache[key] = ok
        return data.cache[key]

    def training(self, data: LabData, until: int):
        """(X, y, w, row keys) pooled over the batch's coins, for a fit at ``until``."""
        from model_lab import features as ft
        from model_lab import targets as tg

        xs, ys, ws, keys = [], [], [], []
        for coin in self.coins(data):
            t = ft.table(data, coin)
            if not len(t.grid):
                continue
            label, end = tg.labels(data, coin, self.target)
            ok = self.rows_mask(data, coin) & tg.usable(
                t.grid, label, until, self.target
            )
            rows = np.nonzero(ok)[0]
            if not len(rows):
                continue
            xs.append(self.matrix(data, coin)[rows])
            ys.append(label[rows])
            ws.append(tg.uniqueness(rows, end, len(t.grid)))
            keys.append((coin, t.grid.close_s[rows]))
        if not xs:
            return np.zeros((0, len(self.names))), np.zeros(0), np.zeros(0), keys
        return np.vstack(xs), np.concatenate(ys), np.concatenate(ws), keys

    # the model --------------------------------------------------------------------------

    def score(self, fit: ModelFit, x: np.ndarray) -> np.ndarray:
        if not len(x):
            return np.zeros(0)
        if self.family == "linear":
            x = (x - fit.mean) / fit.std
        if self.target == "t1":
            return fit.model.predict_proba(x)[:, 1]
        return fit.model.predict(x)

    def fit(self, data: LabData, until: int, coin: Optional[str] = None) -> ModelFit:
        x, y, w, keys = self.training(data, until)
        rows = _sha256_rows(keys)
        n = int(len(y))
        if n == 0 or (self.target == "t1" and len(np.unique(y)) < 2):
            return ModelFit(self, data, until, None, None, None, None, n, rows)
        mean = std = None
        if self.family == "linear":
            from sklearn.linear_model import LogisticRegression

            mean = x.mean(axis=0)
            std = x.std(axis=0)
            std = np.where(std > 0, std, 1.0)
            model = LogisticRegression(C=1.0, max_iter=1000)
            model.fit((x - mean) / std, y.astype(int), sample_weight=w)
        elif self.target == "t1":
            from sklearn.ensemble import HistGradientBoostingClassifier

            model = HistGradientBoostingClassifier(
                **TREES_SETTINGS, random_state=int(data.seed)
            )
            model.fit(x, y.astype(int), sample_weight=w)
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor

            lo, hi = np.percentile(y, [1.0, 99.0])
            model = HistGradientBoostingRegressor(
                **TREES_SETTINGS, random_state=int(data.seed)
            )
            model.fit(x, np.clip(y, lo, hi), sample_weight=w)
        fit = ModelFit(self, data, until, model, mean, std, None, n, rows)
        own = self.score(fit, x)
        fit.threshold = float(np.quantile(own, 1.0 - self.q))
        return fit


def batch_1_models() -> List[Model]:
    """Batch 1's trained, pooled contestants (section 7, numbers 9 to 14)."""
    return [
        Model("linear", "t1", 0.5),
        Model("linear", "t1", 0.2),
        Model("trees", "t1", 0.5),
        Model("trees", "t1", 0.2),
        Model("trees", "t2", 0.5),
        Model("trees", "t2", 0.2),
    ]


def pv_1_models() -> List[Model]:
    """Batch PV-1's contestants (section 7a), then the placebo's variants 2 to 5."""
    words = "Logistic regression on clean wins from "
    out = [
        Model(
            "linear",
            "t1",
            0.5,
            ("P",),
            "pv.linear.t1.P.q50",
            words + "price only, top 50%",
            common_rows=True,
        ),
        Model(
            "linear",
            "t1",
            0.5,
            ("P", "V"),
            "pv.linear.t1.PV.q50",
            words + "price and volume, top 50%",
            common_rows=True,
        ),
        Model(
            "linear",
            "t1",
            0.5,
            ("P", "Vp1"),
            "pv.linear.t1.PVp.q50",
            words + "price and volume from an earlier time, top 50%",
            common_rows=True,
        ),
    ]
    for j in range(2, 6):
        out.append(
            Model(
                "linear",
                "t1",
                0.5,
                ("P", f"Vp{j}"),
                f"pv.linear.t1.PVp{j}.q50",
                words + f"price and volume from an earlier time ({j}), top 50%",
                common_rows=True,
                forecast_only=True,
            )
        )
    return out
