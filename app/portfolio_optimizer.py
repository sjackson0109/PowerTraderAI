#!/usr/bin/env python3
"""
Portfolio Optimization Engine for PowerTrader
Modern Portfolio Theory: optimal weights and the efficient frontier.

Data (owner, 2026-11-05): ``load_candle_data`` reads the daily closes of the coins
in Settings from the candle cache (``market_data.candles.exchange_candles``: the
exchanges in Settings, primary first, each series from one exchange) over a window
(WINDOWS); ``load_price_file`` reads a price file (CSV) instead. The coins' closes
are lined up on the days every coin has one (MarketData), so each day's returns
are the coins' moves on that same day. Returns are simple daily returns;
annualised, the mean is multiplied by DAYS_PER_YEAR and the covariance too
(crypto trades every day of the year).

The current portfolio (``current_portfolio``) is Long-term Holdings': each coin's
share of the current value of the holdings given. ``targets_from_weights`` turns
optimised weights into each holding's target % (Long-term Holdings' Rebalancing
works from those).

Monte Carlo (simulate_portfolios): paths of portfolios' value over a horizon,
drawn from the window's daily returns, by resampling whole days (the default) or
as correlated normal draws: a model based on past data, not a forecast.
"""

import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# Optional imports with graceful degradation
try:
    import scipy.optimize
    from scipy.optimize import minimize

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

DAYS_PER_YEAR = 365  # crypto trades every day: daily figures are annualised over 365
# The windows offered for the daily closes, (label, days), and the one chosen at first
WINDOWS = (("90 days", 90), ("1 year", 365), ("3 years", 1095))
DEFAULT_WINDOW = "1 year"
# A coin with closes on fewer than this share of the window's days is left out: kept,
# it would shorten every coin's data to its own (a coin listed late)
MIN_WINDOW_SHARE = 0.5
MIN_RETURN_DAYS = 20  # the fewest days of returns the coins must share
SOURCE_CANDLES, SOURCE_FILE = "candles", "file"


class Stopped(Exception):
    """The work was stopped before it ended (its window was closed)."""


@dataclass
class MarketData:
    """Daily closes for the optimisation: one column per coin, one row per day
    (ascending), only the days every coin has a close."""

    prices: pd.DataFrame
    source: str = SOURCE_CANDLES  # SOURCE_CANDLES or SOURCE_FILE
    window_days: int = 0  # the window asked for (candles); 0 for a file
    bars: Dict[str, int] = field(default_factory=dict)  # coin -> its own closes
    exchanges: Dict[str, str] = field(default_factory=dict)  # coin -> exchange id
    left_out: Dict[str, str] = field(default_factory=dict)  # coin -> why
    path: str = ""  # the price file (SOURCE_FILE)

    @property
    def coins(self) -> List[str]:
        return [str(c) for c in self.prices.columns]

    @property
    def returns(self) -> pd.DataFrame:
        """Simple daily returns, one row per day after the first."""
        return self.prices.pct_change().iloc[1:]

    def expected_returns(self) -> pd.Series:
        """The mean daily return, annualised (x DAYS_PER_YEAR)."""
        return self.returns.mean() * DAYS_PER_YEAR

    def covariance(self) -> pd.DataFrame:
        """The covariance of the daily returns, annualised (x DAYS_PER_YEAR)."""
        return self.returns.cov() * DAYS_PER_YEAR

    def volatilities(self) -> pd.Series:
        """The annualised standard deviation of each coin's daily returns."""
        return pd.Series(
            np.sqrt(np.diag(self.covariance().values)), index=self.prices.columns
        )

    @property
    def first_day(self) -> Optional[pd.Timestamp]:
        return self.prices.index[0] if len(self.prices) else None

    @property
    def last_day(self) -> Optional[pd.Timestamp]:
        return self.prices.index[-1] if len(self.prices) else None

    def only(self, coins: Iterable[str]) -> "MarketData":
        """The same data for those of ``coins`` it has, in its own order."""
        wanted = {str(c).upper() for c in coins}
        kept = [c for c in self.coins if c in wanted]
        return MarketData(
            self.prices[kept],
            self.source,
            self.window_days,
            {c: n for c, n in self.bars.items() if c in kept},
            {c: e for c, e in self.exchanges.items() if c in kept},
            dict(self.left_out),
            self.path,
        )


def window_days(label: str) -> int:
    """A window's days, by its label ("1 year": 365)."""
    return dict(WINDOWS)[label]


def _why_no_candles(exc: BaseException) -> str:
    from pt_exchange_abstraction import MarketNotFound

    if isinstance(exc, MarketNotFound):
        return "no exchange in Settings has a market for it"
    return "no daily candles from the exchanges in Settings"


def load_candle_data(
    coins: Sequence[str],
    days: int,
    *,
    candles: Optional[Callable[..., pd.DataFrame]] = None,
    now=None,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int, str], None] = lambda done, total, coin: None,
) -> MarketData:
    """The daily closes of ``coins`` over the last ``days`` days, to the last closed
    daily bar, from the candle cache (``candles``: exchange_candles, the exchanges
    in Settings, primary first). A coin with no candles, or with closes on fewer
    than MIN_WINDOW_SHARE of the days, is left out (``left_out`` says why).
    ``progress(done, total, coin)`` is called before each coin; Stopped is raised
    when ``should_stop()`` turns true between coins."""
    if candles is None:
        from market_data.candles import exchange_candles as candles
    from market_data.candles import to_utc

    end = (pd.Timestamp.now(tz="UTC") if now is None else to_utc(now)).floor("D")
    start = end - pd.Timedelta(days=int(days))
    wanted = list(
        dict.fromkeys(str(c).strip().upper() for c in coins if str(c).strip())
    )
    fewest = max(MIN_RETURN_DAYS + 1, int(math.ceil(MIN_WINDOW_SHARE * int(days))))
    data = MarketData(pd.DataFrame(), SOURCE_CANDLES, int(days))
    closes: Dict[str, pd.Series] = {}
    for i, coin in enumerate(wanted):
        if should_stop():
            raise Stopped()
        progress(i, len(wanted), coin)
        try:
            df = candles(coin, "1d", start, end, closed_only=True)
        except Exception as exc:
            data.left_out[coin] = _why_no_candles(exc)
            continue
        if df is None or df.empty:
            data.left_out[coin] = "no daily candles in the window"
            continue
        # by the day: two exchanges' daily bars line up whatever hour they open at
        day = pd.DatetimeIndex(df["open_time"]).normalize()
        series = pd.Series(df["close"].astype(float).values, index=day)
        series = series[~series.index.duplicated(keep="last") & (series > 0)]
        data.bars[coin] = int(len(series))
        if len(series) < fewest:
            data.left_out[coin] = f"closes on {len(series)} of the {int(days)} days"
            continue
        closes[coin] = series
        exchange = df.attrs.get("exchange")
        if exchange:
            data.exchanges[coin] = str(exchange)
    if closes:
        data.prices = pd.DataFrame(closes).sort_index().dropna(how="any")
    return data


def load_price_file(path: str) -> MarketData:
    """Daily prices from a file the user picked: a CSV (or Excel) file with the
    dates in its first column and one column of prices per coin. Only the days with
    a price for every coin are kept."""
    if str(path).lower().endswith(".xlsx"):
        raw = pd.read_excel(path, index_col=0, parse_dates=True)
    else:
        raw = pd.read_csv(path, index_col=0, parse_dates=True)
    prices = raw.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    prices.columns = [str(c).strip().upper() for c in prices.columns]
    bars = {c: int(prices[c].count()) for c in prices.columns}
    prices = prices.sort_index().dropna(how="any")
    prices = prices.loc[:, (prices > 0).all()]
    return MarketData(prices, SOURCE_FILE, bars=bars, path=str(path))


def data_problem(data: MarketData) -> Optional[str]:
    """Why ``data`` cannot be optimised over (None when it can)."""
    if data.prices.shape[1] < 2:
        return "Optimization needs daily closes for at least two coins."
    if len(data.returns) < MIN_RETURN_DAYS:
        return (
            f"The coins share {len(data.returns)} days of returns; "
            f"optimization needs at least {MIN_RETURN_DAYS}."
        )
    return None


@dataclass
class CurrentPortfolio:
    """Holdings as weights of coins."""

    weights: Dict[str, float] = field(default_factory=dict)  # coin -> share, sum 1
    value: float = 0.0  # the current value of the holdings in those coins
    outside: Dict[str, float] = field(default_factory=dict)  # coin -> share of all
    holdings: int = 0  # the holdings given


def current_portfolio(
    holdings: Iterable[Any], coins: Optional[Iterable[str]] = None
) -> CurrentPortfolio:
    """Each coin's share of the current value of ``holdings`` (anything with
    ``symbol`` and ``current_value``, e.g. Long-term Holdings' holdings; a coin held
    more than once is summed). With ``coins``, the shares among those coins only:
    the others' shares of the whole value are in ``outside``."""
    holdings = list(holdings or ())
    values: Dict[str, float] = {}
    for h in holdings:
        coin = str(getattr(h, "symbol", "") or "").strip().upper()
        value = float(getattr(h, "current_value", 0.0) or 0.0)
        if coin and value > 0:
            values[coin] = values.get(coin, 0.0) + value
    wanted = None if coins is None else {str(c).upper() for c in coins}
    inside = {c: v for c, v in values.items() if wanted is None or c in wanted}
    total, covered = sum(values.values()), sum(inside.values())
    return CurrentPortfolio(
        weights={c: v / covered for c, v in inside.items()} if covered > 0 else {},
        value=covered,
        outside={
            c: v / total for c, v in values.items() if c not in inside and total > 0
        },
        holdings=len(holdings),
    )


def weights_vector(weights: Dict[str, float], coins: Sequence[str]) -> np.ndarray:
    """``weights`` in the order of ``coins`` (0 for a coin not in them)."""
    return np.array([float(weights.get(c, 0.0)) for c in coins], dtype=float)


TARGET_DECIMALS = 2  # a target % worked out from a weight is rounded to this


@dataclass
class TargetChange:
    """A holding's target % before and after weights are applied."""

    holding: Any
    old: float
    new: float


def targets_from_weights(
    holdings: Iterable[Any], weights: Dict[str, float]
) -> Tuple[List[TargetChange], Dict[str, float]]:
    """The target % each of ``holdings`` gets from ``weights`` (coin -> fraction):
    its coin's weight, shared among the holdings of that coin by their current
    value (equally when none has one), rounded to TARGET_DECIMALS. A holding whose
    coin has no weight gets 0 (no target). Also the weights of the coins none of
    ``holdings`` is in, which no target can carry."""
    holdings = list(holdings or ())
    by_coin: Dict[str, List[Any]] = {}
    for h in holdings:
        by_coin.setdefault(str(h.symbol).strip().upper(), []).append(h)
    new: Dict[int, float] = {}
    for coin, group in by_coin.items():
        weight = float(weights.get(coin, 0.0)) * 100.0
        values = [max(0.0, float(h.current_value or 0.0)) for h in group]
        total = sum(values)
        for h, value in zip(group, values):
            share = value / total if total > 0 else 1.0 / len(group)
            new[id(h)] = round(weight * share, TARGET_DECIMALS)
    changes = [
        TargetChange(h, float(h.target_percentage or 0.0), new[id(h)]) for h in holdings
    ]
    unheld = {c: float(w) for c, w in weights.items() if c not in by_coin and w > 0}
    return changes, unheld


def constraint_problem(n_assets: int, constraints: Dict) -> Optional[str]:
    """Why no weights of ``n_assets`` coins can keep to the max_weight and
    min_weight (fractions) of ``constraints``, or None."""
    top = float(constraints.get("max_weight", 1.0))
    bottom = float(constraints.get("min_weight", 0.0))
    if n_assets * top < 1.0 - 1e-9:
        return (
            f"With {n_assets} coins the max weight per coin must be at least "
            f"{100.0 / n_assets:.1f}%."
        )
    if n_assets * bottom > 1.0 + 1e-9:
        return (
            f"With {n_assets} coins the min weight per coin can be at most "
            f"{100.0 / n_assets:.1f}%."
        )
    return None


def greedy_weights(score: np.ndarray, low: float, high: float) -> np.ndarray:
    """The weights within [low, high] summing to 1 that make ``score . w`` the
    largest: every coin at ``low``, then the rest to the highest scores first, up to
    ``high`` each (feasible limits: constraint_problem gives None)."""
    score = np.asarray(score, dtype=float)
    weights = np.full(len(score), low)
    left = 1.0 - weights.sum()
    for i in np.argsort(-score, kind="stable"):
        add = min(high - low, max(left, 0.0))
        weights[i] += add
        left -= add
    return weights


def reachable_returns(expected_returns, constraints: Dict) -> Tuple[float, float]:
    """The lowest and highest expected return of weights within the max_weight and
    min_weight of ``constraints`` (feasible limits: constraint_problem gives
    None)."""
    mu = np.asarray(expected_returns, dtype=float)
    low, high = float(constraints["min_weight"]), float(constraints["max_weight"])
    return (
        float(np.dot(greedy_weights(-mu, low, high), mu)),
        float(np.dot(greedy_weights(mu, low, high), mu)),
    )


# ---- Monte Carlo ----

# How the daily returns of a path are drawn: resampled from the window's own days
# (each day's returns of every coin together), or correlated normal draws with the
# window's mean and covariance. The bootstrap keeps the fat tails of crypto
# returns, which normal draws understate: it is the default.
MC_BOOTSTRAP, MC_NORMAL = "bootstrap", "normal"
MC_METHODS = (("Historical bootstrap", MC_BOOTSTRAP), ("Normal", MC_NORMAL))
DEFAULT_MC_PATHS = 5000
DEFAULT_MC_DAYS = 30
MC_PERCENTILES = (5, 25, 50, 75, 95)  # the fan chart's bands and median
VAR_PERCENTILE = 5  # Value at Risk at 95%: the loss at the 5th percentile
MAX_MC_PATHS = 100_000
MAX_MC_DAYS = 1095
MAX_MC_CELLS = 10_000_000  # paths x days kept per portfolio (float32: 40 MB)
MC_CHUNK_CELLS = 2_000_000  # draws (paths x days x coins) made at a time


@dataclass
class PathStats:
    """One portfolio's simulated values: ``percentiles[p]`` is the p-th percentile
    of the value on each day, day 0 (the start) to the horizon."""

    start_value: float
    percentiles: Dict[int, np.ndarray]
    finals: np.ndarray  # each path's value at the horizon
    expected_final: float  # the mean of the final values
    median_final: float
    var_95: float  # start value - the 5th percentile of the final value
    drawdown_probability: float  # share of paths whose drawdown reached the limit


@dataclass
class Simulation:
    """Monte Carlo paths of portfolios' value: a model based on past daily
    returns, not a forecast."""

    method: str
    paths: int
    days: int
    seed: int
    drawdown_limit: float  # a fraction: 0.08 for an 8% drawdown
    first_day: Optional[pd.Timestamp]  # the days the returns came from
    last_day: Optional[pd.Timestamp]
    portfolios: Dict[str, PathStats] = field(default_factory=dict)


def max_drawdowns(values: np.ndarray) -> np.ndarray:
    """Each path's (row's) largest drawdown, a fraction: its largest fall from the
    highest value before it (the first value counts), as the trader's emergency
    stop measures an account's."""
    peaks = np.maximum.accumulate(values, axis=1)
    return (1.0 - values / np.where(peaks > 0, peaks, 1.0)).max(axis=1)


def _correlated(cov: np.ndarray) -> np.ndarray:
    """A matrix L with L @ L.T == cov: its Cholesky factor, or (cov not positive
    definite, e.g. two coins moving as one) from its eigenvalues, the negative ones
    taken as 0."""
    try:
        return np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        values, vectors = np.linalg.eigh(cov)
        return vectors * np.sqrt(np.clip(values, 0.0, None))


def simulate_portfolios(
    returns: pd.DataFrame,
    portfolios: Dict[str, Dict[str, float]],
    *,
    start_value: float,
    days: int = DEFAULT_MC_DAYS,
    paths: int = DEFAULT_MC_PATHS,
    method: str = MC_BOOTSTRAP,
    seed: int = 0,
    drawdown_limit: float = 0.08,
    should_stop: Callable[[], bool] = lambda: False,
) -> Simulation:
    """``paths`` paths of each portfolio's value over ``days`` days from
    ``start_value``, from the daily ``returns`` (one column per coin, one row per
    day). ``portfolios`` maps a name to its weights (coin -> fraction, rescaled to
    sum 1); the coins are bought at the start and held (no rebalancing on the way).

    Each day of a path draws one return per coin: ``MC_BOOTSTRAP`` resamples a day
    of ``returns`` (with replacement; the coins' moves on that day stay together),
    ``MC_NORMAL`` draws correlated normal returns with the window's mean and
    covariance (normal draws times its Cholesky factor). Every portfolio gets the
    same draws, so their differences come from the weights alone; ``seed`` makes
    the draws again. A path's drawdown on a day is its fall from its highest value
    so far (the start counts); ``drawdown_probability`` is the share of paths whose
    drawdown reached ``drawdown_limit`` on any day. Stopped is raised once
    ``should_stop()`` is true between batches of paths."""
    coins = [str(c) for c in returns.columns]
    history = returns.to_numpy(dtype=float)
    if history.ndim != 2 or len(history) < 2 or not coins:
        raise ValueError("The simulation needs at least two days of returns.")
    weights = {}
    for name, w in portfolios.items():
        vector = weights_vector(w, coins)
        if vector.sum() > 0:
            weights[name] = vector / vector.sum()
    if not weights:
        raise ValueError("No portfolio has a weight in the coins with returns.")
    days, paths = int(days), int(paths)
    n_coins = len(coins)
    rng = np.random.default_rng(int(seed))
    if method == MC_NORMAL:
        mean = history.mean(axis=0)
        factor = _correlated(np.atleast_2d(np.cov(history, rowvar=False)))
    elif method != MC_BOOTSTRAP:
        raise ValueError(f"Unknown simulation method: {method}")
    values = {name: np.empty((paths, days + 1), dtype=np.float32) for name in weights}
    batch = max(1, MC_CHUNK_CELLS // max(1, days * n_coins))
    for first in range(0, paths, batch):
        if should_stop():
            raise Stopped()
        count = min(batch, paths - first)
        if method == MC_BOOTSTRAP:
            draws = history[rng.integers(0, len(history), size=(count, days))]
        else:
            normal = rng.standard_normal((count, days, n_coins))
            draws = mean + normal @ factor.T
        # each coin's value multiple, day by day (a coin cannot fall below 0)
        growth = np.cumprod(1.0 + np.maximum(draws, -1.0), axis=1)
        for name, w in weights.items():
            block = values[name][first : first + count]
            block[:, 0] = start_value
            block[:, 1:] = start_value * (growth @ w)
    simulation = Simulation(
        method,
        paths,
        days,
        int(seed),
        float(drawdown_limit),
        returns.index[0] if len(returns) else None,
        returns.index[-1] if len(returns) else None,
    )
    for name, v in values.items():
        v = v.astype(float)
        finals = v[:, -1]
        simulation.portfolios[name] = PathStats(
            start_value=float(start_value),
            percentiles=dict(
                zip(MC_PERCENTILES, np.percentile(v, MC_PERCENTILES, axis=0))
            ),
            finals=finals,
            expected_final=float(finals.mean()),
            median_final=float(np.median(finals)),
            var_95=float(start_value - np.percentile(finals, VAR_PERCENTILE)),
            drawdown_probability=float(
                (max_drawdowns(v) >= drawdown_limit - 1e-12).mean()
            ),
        )
    return simulation


def simulation_problem(paths: int, days: int) -> Optional[str]:
    """Why ``paths`` paths of ``days`` days are not simulated (None when they are)."""
    if not 1 <= days <= MAX_MC_DAYS:
        return f"The horizon must be from 1 to {MAX_MC_DAYS} days."
    if not 100 <= paths <= MAX_MC_PATHS:
        return f"The paths must be from 100 to {MAX_MC_PATHS:,}."
    if paths * days > MAX_MC_CELLS:
        return f"Paths times days can be at most {MAX_MC_CELLS:,}."
    return None


class PortfolioOptimizer:
    """
    Advanced portfolio optimization engine implementing Modern Portfolio Theory,
    efficient frontier calculation, and sophisticated rebalancing strategies.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the portfolio optimizer with database storage."""
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("portfolio_optimization.db")
        self.db_path = db_path
        self.logger = self._setup_logging()
        self._init_database()

        # Risk-free rate (can be updated based on current treasury rates)
        self.risk_free_rate = 0.02  # 2% annual

        # Optimization constraints
        self.default_constraints = {
            "max_weight": 0.4,  # Maximum 40% in any single asset
            "min_weight": 0.01,  # Minimum 1% in any asset
            # Maximum portfolio volatility; None: no limit (a crypto portfolio's
            # annual volatility is usually well above the 25% this used to be)
            "max_volatility": None,
            "max_correlation": 0.8,  # Maximum correlation between assets
        }

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for portfolio optimization."""
        logger = logging.getLogger("PortfolioOptimizer")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _init_database(self):
        """Initialize database tables for portfolio optimization."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimized_portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_name TEXT UNIQUE,
                    optimization_type TEXT,
                    target_return REAL,
                    target_risk REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    constraints_json TEXT,
                    results_json TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    symbol TEXT,
                    weight REAL,
                    expected_return REAL,
                    volatility REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS rebalancing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    rebalance_date TIMESTAMP,
                    old_weights_json TEXT,
                    new_weights_json TEXT,
                    rebalance_reason TEXT,
                    transaction_costs REAL,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS efficient_frontier_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    expected_return REAL,
                    volatility REAL,
                    sharpe_ratio REAL,
                    weights_json TEXT,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

    def calculate_returns_covariance(
        self, price_data: pd.DataFrame, period: int = DAYS_PER_YEAR
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Calculate expected returns and covariance matrix from price data.

        Args:
            price_data: DataFrame with asset prices (columns = assets, index = dates)
            period: Number of periods for annualization (DAYS_PER_YEAR for daily
                crypto prices)

        Returns:
            Tuple of (expected_returns, covariance_matrix)
        """
        # Calculate returns
        returns = price_data.pct_change().dropna()

        # Expected returns (annualized)
        expected_returns = returns.mean() * period

        # Covariance matrix (annualized)
        covariance_matrix = returns.cov() * period

        return expected_returns, covariance_matrix

    def portfolio_performance(
        self, weights: np.ndarray, expected_returns: pd.Series, cov_matrix: pd.DataFrame
    ) -> Tuple[float, float, float]:
        """
        Calculate portfolio performance metrics.

        Args:
            weights: Asset weights array
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix

        Returns:
            Tuple of (portfolio_return, portfolio_volatility, sharpe_ratio)
        """
        # Portfolio return
        portfolio_return = np.dot(weights, expected_returns)

        # Portfolio volatility
        portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))

        # Sharpe ratio
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility

        return portfolio_return, portfolio_volatility, sharpe_ratio

    def optimize_portfolio(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        optimization_type: str = "max_sharpe",
        target_return: Optional[float] = None,
        constraints: Optional[Dict] = None,
    ) -> Dict:
        """
        Optimize portfolio weights based on specified objective.

        Args:
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix
            optimization_type: 'max_sharpe', 'min_variance', 'target_return'
            target_return: Required for 'target_return' optimization
            constraints: Custom constraints dictionary

        Returns:
            Dictionary with optimization results
        """
        if not SCIPY_AVAILABLE:
            self.logger.warning("SciPy not available - using equal weight allocation")
            n_assets = len(expected_returns)
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return {
                "weights": dict(zip(expected_returns.index, weights)),
                "expected_return": port_return,
                "volatility": port_vol,
                "sharpe_ratio": sharpe,
                "success": True,
                "method": "equal_weight_fallback",
            }

        # Merge constraints
        active_constraints = {**self.default_constraints}
        if constraints:
            active_constraints.update(constraints)

        n_assets = len(expected_returns)
        # numpy arrays in the optimiser's loop: a pandas product there costs far more
        # per call, and SLSQP makes thousands of them (seconds for a frontier)
        mu = np.asarray(expected_returns, dtype=float)
        cov = np.asarray(cov_matrix, dtype=float)

        # Bounds for weights (min_weight, max_weight)
        bounds = tuple(
            (active_constraints["min_weight"], active_constraints["max_weight"])
            for _ in range(n_assets)
        )

        # Constraint: weights sum to 1
        constraints_list = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

        # Volatility constraint (None: no limit)
        if active_constraints.get("max_volatility"):
            constraints_list.append(
                {
                    "type": "ineq",
                    "fun": lambda x: active_constraints["max_volatility"]
                    - np.sqrt(np.dot(x.T, np.dot(cov, x))),
                }
            )

        # Define objective function
        if optimization_type == "max_sharpe":
            # Maximize Sharpe ratio (minimize negative Sharpe ratio)
            def objective(weights):
                _, _, sharpe = self.portfolio_performance(weights, mu, cov)
                return -sharpe

        elif optimization_type == "min_variance":
            # Minimize portfolio variance
            def objective(weights):
                return np.dot(weights.T, np.dot(cov, weights))

        elif optimization_type == "target_return":
            if target_return is None:
                raise ValueError(
                    "target_return must be specified for target_return optimization"
                )

            # Minimize variance subject to target return
            constraints_list.append(
                {
                    "type": "eq",
                    "fun": lambda x: np.dot(x, mu) - target_return,
                }
            )

            def objective(weights):
                return np.dot(weights.T, np.dot(cov, weights))

        else:
            raise ValueError(f"Unknown optimization type: {optimization_type}")

        # Initial guess (equal weights)
        x0 = np.array([1.0 / n_assets] * n_assets)

        try:
            # Perform optimization
            result = minimize(
                objective,
                x0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints_list,
                options={"disp": False, "ftol": 1e-9, "maxiter": 1000},
            )

            if result.success:
                optimal_weights = result.x
                port_return, port_vol, sharpe = self.portfolio_performance(
                    optimal_weights, mu, cov
                )

                return {
                    "weights": dict(zip(expected_returns.index, optimal_weights)),
                    "expected_return": port_return,
                    "volatility": port_vol,
                    "sharpe_ratio": sharpe,
                    "success": True,
                    "method": optimization_type,
                    "optimization_result": result,
                }
            else:
                self.logger.warning(f"Optimization failed: {result.message}")
                # Fallback to equal weights
                weights = np.array([1.0 / n_assets] * n_assets)
                port_return, port_vol, sharpe = self.portfolio_performance(
                    weights, expected_returns, cov_matrix
                )
                return {
                    "weights": dict(zip(expected_returns.index, weights)),
                    "expected_return": port_return,
                    "volatility": port_vol,
                    "sharpe_ratio": sharpe,
                    "success": False,
                    "method": "equal_weight_fallback",
                    "error": result.message,
                }

        except Exception as e:
            self.logger.error(f"Optimization error: {e}")
            # Fallback to equal weights
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return {
                "weights": dict(zip(expected_returns.index, weights)),
                "expected_return": port_return,
                "volatility": port_vol,
                "sharpe_ratio": sharpe,
                "success": False,
                "method": "equal_weight_fallback",
                "error": str(e),
            }

    def calculate_efficient_frontier(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        num_points: int = 50,
        constraints: Optional[Dict] = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> pd.DataFrame:
        """
        Calculate the efficient frontier.

        Args:
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix
            num_points: Number of points on the efficient frontier
            constraints: The weight constraints, as optimize_portfolio takes them
            should_stop: Checked before each point: Stopped once it is true

        Returns:
            DataFrame with efficient frontier points
        """
        if not SCIPY_AVAILABLE:
            self.logger.warning(
                "SciPy not available - cannot calculate efficient frontier"
            )
            # Return a simple single point (equal weights)
            n_assets = len(expected_returns)
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return pd.DataFrame(
                {
                    "Return": [port_return],
                    "Volatility": [port_vol],
                    "Sharpe_Ratio": [sharpe],
                    "Weights": [dict(zip(expected_returns.index, weights))],
                }
            )

        # Define return range: from the minimum-variance portfolio's return (below
        # it, a portfolio with the same volatility returns more: not efficient) to
        # the highest return weights within the limits can reach (a target outside
        # the reachable returns only fails, slowly)
        active = {**self.default_constraints, **(constraints or {})}
        mu = np.asarray(expected_returns, dtype=float)
        if constraint_problem(len(mu), active) is None:
            min_ret, max_ret = reachable_returns(mu, active)
        else:
            min_ret, max_ret = float(mu.min()), float(mu.max())
        lowest = self.optimize_portfolio(
            expected_returns, cov_matrix, "min_variance", constraints=constraints
        )
        if lowest["success"]:
            min_ret = min(max(min_ret, float(lowest["expected_return"])), max_ret)
        target_returns = np.linspace(min_ret, max_ret, num_points)

        frontier_results = []

        for target_ret in target_returns:
            if should_stop():
                raise Stopped()
            try:
                result = self.optimize_portfolio(
                    expected_returns,
                    cov_matrix,
                    optimization_type="target_return",
                    target_return=target_ret,
                    constraints=constraints,
                )

                if result["success"]:
                    frontier_results.append(
                        {
                            "Return": result["expected_return"],
                            "Volatility": result["volatility"],
                            "Sharpe_Ratio": result["sharpe_ratio"],
                            "Weights": result["weights"],
                        }
                    )

            except Exception as e:
                self.logger.debug(f"Skipping target return {target_ret}: {e}")
                continue

        return pd.DataFrame(
            frontier_results,
            columns=["Return", "Volatility", "Sharpe_Ratio", "Weights"],
        )

    def save_optimized_portfolio(
        self,
        portfolio_name: str,
        optimization_result: Dict,
        optimization_type: str,
        constraints: Dict = None,
    ) -> int:
        """Save optimized portfolio to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Save main portfolio record
            cursor.execute(
                """
                INSERT OR REPLACE INTO optimized_portfolios
                (portfolio_name, optimization_type, target_return, target_risk,
                 constraints_json, results_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    portfolio_name,
                    optimization_type,
                    optimization_result.get("expected_return", 0),
                    optimization_result.get("volatility", 0),
                    json.dumps(constraints or {}),
                    json.dumps(optimization_result, default=str),
                ),
            )

            portfolio_id = cursor.lastrowid

            # Save asset allocations
            for symbol, weight in optimization_result["weights"].items():
                cursor.execute(
                    """
                    INSERT INTO asset_allocations
                    (portfolio_id, symbol, weight, expected_return, volatility)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (portfolio_id, symbol, weight, 0, 0),
                )  # TODO: Add individual asset metrics

        self.logger.info(
            f"Saved optimized portfolio '{portfolio_name}' with ID {portfolio_id}"
        )
        return portfolio_id

    def load_portfolio(self, portfolio_name: str) -> Optional[Dict]:
        """Load saved portfolio from database."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                """
                SELECT * FROM optimized_portfolios WHERE portfolio_name = ?
            """,
                (portfolio_name,),
            ).fetchone()

            if result:
                portfolio_data = {
                    "id": result[0],
                    "name": result[1],
                    "optimization_type": result[2],
                    "target_return": result[3],
                    "target_risk": result[4],
                    "created_at": result[5],
                    "constraints": json.loads(result[6]),
                    "results": json.loads(result[7]),
                }

                # Load allocations
                allocations = conn.execute(
                    """
                    SELECT symbol, weight FROM asset_allocations
                    WHERE portfolio_id = ?
                """,
                    (result[0],),
                ).fetchall()

                portfolio_data["allocations"] = dict(allocations)
                return portfolio_data

        return None

    def get_portfolio_summary(self) -> pd.DataFrame:
        """Get summary of all saved portfolios."""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                """
                SELECT portfolio_name, optimization_type, target_return,
                       target_risk, created_at
                FROM optimized_portfolios
                ORDER BY created_at DESC
            """,
                conn,
            )

        return df


# Example usage and testing
if __name__ == "__main__":
    # Create sample price data for testing
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", "2024-01-01", freq="D")

    # Simulate price data for 5 assets
    assets = ["BTC", "ETH", "ADA", "DOT", "LINK"]
    price_data = pd.DataFrame(index=dates, columns=assets)

    # Generate correlated random walks
    for i, asset in enumerate(assets):
        returns = np.random.normal(0.001, 0.02, len(dates))  # Daily returns
        prices = [100]  # Starting price
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        price_data[asset] = prices[: len(dates)]

    # Initialize optimizer
    optimizer = PortfolioOptimizer()

    # Calculate returns and covariance
    expected_returns, cov_matrix = optimizer.calculate_returns_covariance(price_data)

    print("Expected Returns (Annual):")
    print(expected_returns)
    print("\nCovariance Matrix:")
    print(cov_matrix)

    # Optimize for maximum Sharpe ratio
    result = optimizer.optimize_portfolio(expected_returns, cov_matrix, "max_sharpe")

    print(f"\nMax Sharpe Portfolio:")
    print(f"Expected Return: {result['expected_return']:.2%}")
    print(f"Volatility: {result['volatility']:.2%}")
    print(f"Sharpe Ratio: {result['sharpe_ratio']:.3f}")
    print("Weights:")
    for asset, weight in result["weights"].items():
        print(f"  {asset}: {weight:.1%}")

    # Save portfolio
    portfolio_id = optimizer.save_optimized_portfolio(
        "Test_Max_Sharpe", result, "max_sharpe"
    )

    # Calculate efficient frontier
    frontier = optimizer.calculate_efficient_frontier(expected_returns, cov_matrix, 20)
    print(f"\nEfficient Frontier calculated with {len(frontier)} points")

    print("\nPortfolio optimization system ready!")
