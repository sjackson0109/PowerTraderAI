import hashlib
import json
import math
import os
import time
import traceback
import uuid
from typing import Any, Dict, Optional

import colorama
import paper_coins
import position_sizing
import pt_paths
import risk_state
from colorama import Fore, Style
from market_data.listing import not_trading_reason
from pt_cost import CostManager, PerformanceTier
from pt_exchange_abstraction import (
    OrderResult,
    TradingFees,
    usable_fees,
    usable_minimum,
)
from pt_logging import get_logger
from pt_risk import RiskLimits, RiskManager
from pt_validation import InputValidator, ValidationError
from signal_engine import SignalEngine
from strategies.base import Action
from strategies.settings import read_strategy_settings
from trading_mode import (
    BELOW_MINIMUM,
    LiveTradingRefused,
    OrderTarget,
    TradingModeError,
    check_live_key,
    configure_paper_exchange,
    move_root_live_books,
    read_drawdown_levels,
    read_paper_settings,
    read_trading_settings,
    resolve_order_target,
    settings_problem,
)

# -----------------------------
# GUI HUB OUTPUTS
# -----------------------------
# Base directory shared with the hub. Each trading mode keeps its own ledger and
# history in a sub-directory (see TradingSettings.data_subdir) so paper, testnet
# and preview fills never mix into the live books, and each live broker has its own.
HUB_DATA_DIR = os.environ.get("POWERTRADER_HUB_DIR") or pt_paths.hub_dir()
os.makedirs(HUB_DATA_DIR, exist_ok=True)

# Assets that are cash, not positions
CASH_ASSETS = frozenset({"USD", "ZUSD", "USDT", "USDC", "BUSD"})
# Balance entries that count as buying power, in order of preference
BUYING_POWER_ASSETS = ("USD", "USDT")

# Order states after which nothing further will change
TERMINAL_ORDER_STATES = frozenset(
    {"filled", "canceled", "cancelled", "rejected", "failed", "error", "expired"}
)

# In preview mode the same order is previewed at most once in this long: an entry
# signal stands for a whole bar, and nothing is bought to stop it repeating
PREVIEW_REPEAT_SECONDS = 15 * 60
# How long a coin's minimum order is kept for telling dust from a position
DUST_MINIMUM_SECONDS = 60 * 60
# An order the exchange refuses for its size is tried again every cycle (an exit
# can be worth the minimum again later); the refusal is reported once in this long
BELOW_MINIMUM_REPORT_SECONDS = 60 * 60
# An order whose send raised (a timeout, a dropped connection) may have been made
# all the same. Its intent stays in pnl_ledger.json (``order_intents``). Where the
# exchange answers a repeated client order id with the order it already made, the
# next order on that coin and side is the same order sent again, for this long:
UNKNOWN_ORDER_RESEND_SECONDS = 15 * 60
# Elsewhere no order is sent on that coin and side for this long, so the holdings
# can show whether it was made (an entry is never made in a coin already held):
UNKNOWN_ORDER_WAIT_SECONDS = 60
# A held asset with no price this pass is valued at its last bid while that is at
# most this old; after that it is left out of the account value (and listed in
# Settings > Risk), so one asset without a USD price cannot stop the drawdown check.
# One with no price yet in this run holds the value back (the pass forms none, buys
# wait) for this long since the run first saw it so, and is then left out the same
# way: a quote missing on the first pass after a start cannot drop a large holding.
HELD_PRICE_MAX_AGE_SECONDS = 10 * 60
NO_USD_PRICE = "no USD price"
PRICE_TOO_OLD = f"no price for over {HELD_PRICE_MAX_AGE_SECONDS // 60} minutes"
NOT_YET_PRICED = "no price yet"
# With no account value at all for this long (the balances cannot be read), the
# drawdown cannot be checked: buys wait until there is one again; sells go on
ACCOUNT_VALUE_MAX_AGE_SECONDS = 10 * 60
# The drawdown stop compares its balances each pass with the last ones it settled on,
# after the fills recorded since. A change no fill explains is classified only once
# the balances have been still this long (fixed, as long as the wait for an order of
# unknown outcome), so both legs of a trade land in one change. Meanwhile buys wait
# and the stop is checked without the change; sells go on. Then a net rise is a
# deposit (the peak is scaled with it, keeping the drawdown) and a net fall a loss.
BALANCE_CHANGE_SETTLE_SECONDS = 60
# A change worth less than this (a fill's rounding) is not a change
BALANCE_CHANGE_TOLERANCE_USD = 0.01
# The cash assets are one balance in that comparison: moving USD into USDC is none
CASH_KEY = "USD"


# Initialize colorama
colorama.init(autoreset=True)

# -----------------------------
# GUI SETTINGS (coins list + main_neural_dir)
# -----------------------------
_GUI_SETTINGS_PATH = (
    os.environ.get("POWERTRADER_GUI_SETTINGS") or pt_paths.gui_settings_file()
)

_gui_settings_cache = {
    "mtime": None,
    "coins": ["BTC", "ETH", "XRP", "BNB", "DOGE"],  # fallback defaults
    "main_neural_dir": None,
    "trade_start_level": 3,
    "start_allocation_pct": position_sizing.DEFAULT_START_ALLOCATION_PCT,
    "max_coin_allocation_pct": position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT,
    "min_order_margin_pct": position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT,
    "dca_multiplier": 2.0,
    "dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0],
    "max_dca_buys_per_24h": 2,
    # Trailing PM settings (defaults match previous hardcoded behavior)
    "pm_start_pct_no_dca": 5.0,
    "pm_start_pct_with_dca": 2.5,
    "trailing_gap_pct": 0.5,
}


def _load_gui_settings() -> dict:
    """
    Reads gui_settings.json and returns a dict with:
    - coins: uppercased list
    - main_neural_dir: string (may be None)
    Caches by mtime so it is cheap to call frequently.
    """
    try:
        if not os.path.isfile(_GUI_SETTINGS_PATH):
            return dict(_gui_settings_cache)

        mtime = os.path.getmtime(_GUI_SETTINGS_PATH)
        if _gui_settings_cache["mtime"] == mtime:
            return dict(_gui_settings_cache)

        # Validate file path to prevent directory traversal: settings live in
        # the user config folder
        allowed_dirs = [pt_paths.config_dir()]
        from pt_files import validate_file_path

        if not validate_file_path(_GUI_SETTINGS_PATH, allowed_dirs):
            logger = get_logger()
            logger.warning(f"Invalid configuration file path: {_GUI_SETTINGS_PATH}")
            return dict(_gui_settings_cache)

        with open(_GUI_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}

        # Use input validator for configuration validation
        try:
            validated_config = InputValidator.validate_config_data(data)
        except ValidationError as e:
            logger = get_logger()
            logger.error(f"Configuration validation failed: {e}")
            return dict(_gui_settings_cache)

        # Update cache with validated data
        _gui_settings_cache["mtime"] = mtime
        for key, value in validated_config.items():
            _gui_settings_cache[key] = value

        return dict(_gui_settings_cache)

    except Exception as e:
        # Use secure exception handling
        logger = get_logger(__name__)
        logger.error(f"Error loading GUI settings: {e}")
        return dict(_gui_settings_cache)


def _build_base_paths(main_dir_in: str, coins_in: list) -> dict:
    """
    Safety rule:
    - BTC uses main_dir directly
    - other coins use <main_dir>/<SYM> ONLY if that folder exists
      (no fallback to BTC folder — avoids corrupting BTC data)
    """
    out = {"BTC": main_dir_in}
    try:
        for sym in coins_in:
            sym = str(sym).strip().upper()
            if not sym:
                continue
            if sym == "BTC":
                out["BTC"] = main_dir_in
                continue
            sub = os.path.join(main_dir_in, sym)
            if os.path.isdir(sub):
                out[sym] = sub
    except Exception:
        pass
    return out


# Live globals (will be refreshed inside manage_trades())
crypto_symbols = ["BTC", "ETH", "XRP", "BNB", "DOGE"]

# Default main_dir behavior if settings are missing (the user data folder)
main_dir = pt_paths.neural_dir()
base_paths = {"BTC": main_dir}
TRADE_START_LEVEL = 3
# The neural runner rewrites its signal counts about once a minute; an older file
# (runner stopped, or carried over from an earlier install) counts as 0.
SIGNAL_MAX_AGE_SECONDS = 15 * 60
START_ALLOC_PCT = position_sizing.DEFAULT_START_ALLOCATION_PCT
MAX_COIN_PCT = position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT
# Room an entry raised to the exchange's minimum order keeps above it (Settings)
MIN_ORDER_MARGIN_PCT = position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT
DCA_MULTIPLIER = 2.0
DCA_LEVELS = [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0]
MAX_DCA_BUYS_PER_24H = 2

# Trailing PM hot-reload globals (defaults match previous hardcoded behavior)
TRAILING_GAP_PCT = 0.5
PM_START_PCT_NO_DCA = 5.0
PM_START_PCT_WITH_DCA = 2.5


_last_settings_mtime = None


def _refresh_paths_and_symbols():
    """
    Hot-reload GUI settings while trader is running.
    Updates globals: crypto_symbols, main_dir, base_paths,
                    TRADE_START_LEVEL, START_ALLOC_PCT, MAX_COIN_PCT, DCA_MULTIPLIER, DCA_LEVELS,
                    MAX_DCA_BUYS_PER_24H, MIN_ORDER_MARGIN_PCT,
                    TRAILING_GAP_PCT, PM_START_PCT_NO_DCA, PM_START_PCT_WITH_DCA
    """
    global crypto_symbols, main_dir, base_paths
    global TRADE_START_LEVEL, START_ALLOC_PCT, MAX_COIN_PCT, DCA_MULTIPLIER, DCA_LEVELS
    global MAX_DCA_BUYS_PER_24H, MIN_ORDER_MARGIN_PCT
    global TRAILING_GAP_PCT, PM_START_PCT_NO_DCA, PM_START_PCT_WITH_DCA
    global _last_settings_mtime

    s = _load_gui_settings()
    mtime = s.get("mtime", None)

    # If settings file doesn't exist, keep current defaults
    if mtime is None:
        return

    if _last_settings_mtime == mtime:
        return

    _last_settings_mtime = mtime

    coins = s.get("coins") or list(crypto_symbols)
    mndir = pt_paths.neural_dir(s.get("main_neural_dir"))
    TRADE_START_LEVEL = max(
        1,
        min(int(s.get("trade_start_level", TRADE_START_LEVEL) or TRADE_START_LEVEL), 7),
    )
    START_ALLOC_PCT = float(
        s.get("start_allocation_pct", START_ALLOC_PCT) or START_ALLOC_PCT
    )
    if START_ALLOC_PCT < 0.0:
        START_ALLOC_PCT = 0.0
    MAX_COIN_PCT = float(s.get("max_coin_allocation_pct", MAX_COIN_PCT) or MAX_COIN_PCT)

    # 0 is a valid margin (0-20); anything else invalid is the default
    margin = s.get("min_order_margin_pct", position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT)
    if not position_sizing.valid_min_order_margin_pct(margin):
        logger.warning(
            f"Invalid min_order_margin_pct={margin!r} (valid "
            f"{position_sizing.MIN_ORDER_MARGIN_RANGE[0]:g}-"
            f"{position_sizing.MIN_ORDER_MARGIN_RANGE[1]:g}); using "
            f"{position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT:g}"
        )
        margin = position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT
    MIN_ORDER_MARGIN_PCT = float(margin)

    DCA_MULTIPLIER = float(s.get("dca_multiplier", DCA_MULTIPLIER) or DCA_MULTIPLIER)
    if DCA_MULTIPLIER < 0.0:
        DCA_MULTIPLIER = 0.0

    DCA_LEVELS = list(s.get("dca_levels", DCA_LEVELS) or DCA_LEVELS)

    try:
        MAX_DCA_BUYS_PER_24H = int(
            float(
                s.get("max_dca_buys_per_24h", MAX_DCA_BUYS_PER_24H)
                or MAX_DCA_BUYS_PER_24H
            )
        )
    except Exception:
        MAX_DCA_BUYS_PER_24H = int(MAX_DCA_BUYS_PER_24H)
    if MAX_DCA_BUYS_PER_24H < 0:
        MAX_DCA_BUYS_PER_24H = 0

    # Trailing PM hot-reload values
    TRAILING_GAP_PCT = float(
        s.get("trailing_gap_pct", TRAILING_GAP_PCT) or TRAILING_GAP_PCT
    )
    if TRAILING_GAP_PCT < 0.0:
        TRAILING_GAP_PCT = 0.0

    PM_START_PCT_NO_DCA = float(
        s.get("pm_start_pct_no_dca", PM_START_PCT_NO_DCA) or PM_START_PCT_NO_DCA
    )
    if PM_START_PCT_NO_DCA < 0.0:
        PM_START_PCT_NO_DCA = 0.0

    PM_START_PCT_WITH_DCA = float(
        s.get("pm_start_pct_with_dca", PM_START_PCT_WITH_DCA) or PM_START_PCT_WITH_DCA
    )
    if PM_START_PCT_WITH_DCA < 0.0:
        PM_START_PCT_WITH_DCA = 0.0

    # Keep it safe if folder isn't real on this machine
    if not os.path.isdir(mndir):
        mndir = pt_paths.neural_dir()

    crypto_symbols = list(coins)
    main_dir = mndir
    base_paths = _build_base_paths(main_dir, crypto_symbols)


# Initialize secure logging
logger = get_logger(__name__)
logger.info("PowerTrader Crypto Trader initialized")


def _market_exchanges():
    """The exchanges in Settings, primary first, for public market information
    (``pt_multi_exchange.market_exchanges``: no credentials, nothing written)."""
    from pt_multi_exchange import market_exchanges

    return market_exchanges()


def _cash_first(item: tuple) -> tuple:
    return (item[0] != CASH_KEY, item[0])


class _TraderRiskAdapter:
    """
    The trader's view of risk management, backed by pt_risk.RiskManager.

    RiskManager exposes ``validate_trade`` / flag attributes; the trader wants a
    per-order approve/block answer and a per-cycle drawdown check. Drawdown is
    measured against the peak account value seen by this trader, at the warning /
    critical / emergency levels in Settings > Risk (read before every check).

    With ``state_dir`` (the trader's books folder) the peak and an emergency stop's
    halt are kept in ``risk_state.json`` across restarts, and Settings > Risk's Reset
    peak and Resume trading are applied from ``risk_requests.json``
    (``risk_state``). Nothing else clears a halt.
    """

    def __init__(
        self,
        manager: Optional[RiskManager] = None,
        settings_source: Any = None,
        state_dir: Optional[str] = None,
    ):
        self.manager = manager or RiskManager(RiskLimits())
        self.settings_source = settings_source
        self.peak_value = 0.0
        self.error_count = 0
        self.state_dir = state_dir
        self._state: Dict[str, Any] = {}
        self._requests_mtime: Any = object()  # not read yet
        self.halt_reason = ""
        if state_dir:
            self._state = risk_state.read_state(state_dir)
            self.peak_value = max(0.0, float(self._state.get("peak_value") or 0.0))
            if self._state.get("halted"):
                # halted before this start: still halted until Resume trading
                self.halt_reason = str(self._state.get("halt_reason") or "")
                self.manager.is_trading_halted = True
                self.manager.emergency_stop_triggered = True
            self._apply_requests()

    def _save_state(self) -> bool:
        if not self.state_dir:
            return True
        self._state["peak_value"] = self.peak_value
        try:
            risk_state.write_state(self.state_dir, self._state)
        except OSError as exc:
            logger.error(f"Risk state not saved: {exc}")
            return False
        return True

    def _apply_requests(self) -> None:
        """Settings > Risk requests (Reset peak, Resume trading) not applied yet;
        the request file is read again only when it changes."""
        path = risk_state.requests_path(self.state_dir)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if mtime == self._requests_mtime:
            return
        self._requests_mtime = mtime
        before = dict(self._state, peak_value=self.peak_value)
        after = risk_state.apply_requests(
            before, risk_state.read_requests(self.state_dir)
        )
        if after != before:
            self._state = after
            self.peak_value = float(after.get("peak_value") or 0.0)
            if after.get("peak_reset_ts") != before.get("peak_reset_ts"):
                print(
                    f"Peak account value reset to ${self.peak_value:,.2f}"
                    if self.peak_value > 0.0
                    else "Peak account value cleared: the next account value is the peak"
                )
            if before.get("halted") and not after.get("halted"):
                self.manager.reset_emergency_stop(manual_override=True)
                self.halt_reason = ""
                print("Trading resumed (Resume trading in Settings > Risk)")
            self._save_state()

    def is_trading_halted(self) -> bool:
        return bool(
            self.manager.is_trading_halted or self.manager.emergency_stop_triggered
        )

    def report(self, not_counted: Optional[list], buys_waiting: str) -> None:
        """For Settings > Risk: the held assets this pass's account value left out,
        as (asset, quantity, why) (None: no value this pass, the last list stays),
        and why buys wait ("" when they do not). Saved only when either changes."""
        before = (self._state.get("not_counted"), self._state.get("buys_waiting"))
        if not_counted is not None:
            self._state["not_counted"] = [
                {"asset": asset, "quantity": float(qty), "why": why}
                for asset, qty, why in not_counted
            ]
        if buys_waiting != (self._state.get("buys_waiting") or ""):
            self._state["buys_waiting"] = buys_waiting
            self._state["buys_waiting_ts"] = time.time() if buys_waiting else 0.0
        if (self._state.get("not_counted"), self._state.get("buys_waiting")) != before:
            self._save_state()

    def measures_all_balances(self) -> bool:
        """Whether the peak is in the stop's own measure (every balance, funds on
        hold included, the cash assets at $1): from this version's first pass."""
        return self._state.get("peak_measure") == risk_state.ALL_BALANCES

    def measure_all_balances(self, new_value: float, old_value: float) -> bool:
        """Once: the stop measures every balance where it measured the account value.
        A peak saved by an earlier version (on the account value) is scaled by
        ``new_value / old_value``, both from the same pass, so a drawdown in progress
        is kept; the scaling is saved (``peak_scaled``) and printed. Equal values
        (nothing on hold, no stablecoin: always so in paper) change nothing. Without
        both values above 0 it waits for a pass with them. True once it is done."""
        if self.measures_all_balances():
            return True
        if self.peak_value > 0.0 and abs(float(new_value) - float(old_value)) > 0.005:
            if not (new_value > 0.0 and old_value > 0.0):
                return False
            before = self.peak_value
            self.peak_value = before * float(new_value) / float(old_value)
            self._state["peak_scaled"] = {
                "ts": time.time(),
                "from": before,
                "to": self.peak_value,
                "account_value": float(old_value),
                "all_balances": float(new_value),
            }
            message = (
                f"Peak account value scaled from ${before:,.2f} to "
                f"${self.peak_value:,.2f}: the drawdown now counts every balance, "
                "funds on hold included, with USD and the stablecoins at $1"
            )
            print(message)
            logger.info(message)
        self._state["peak_measure"] = risk_state.ALL_BALANCES
        self._save_state()
        return True

    def last_balances(self) -> Optional[tuple]:
        """(balances, when read) the stop last settled on, or None when there are
        none (a new install, an older file, or a Reset peak since)."""
        raw = self._state.get("last_balances")
        if not isinstance(raw, dict):
            return None
        balances = {}
        for asset, qty in raw.items():
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                continue
            if math.isfinite(qty):
                balances[str(asset)] = qty
        try:
            ts = float(self._state.get("last_balances_ts") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        return balances, ts

    def keep_balances(self, balances: Dict[str, float], ts: float) -> None:
        """The balances to compare the next ones with; saved when they change."""
        kept = {a: float(q) for a, q in sorted(balances.items()) if abs(q) > 1e-12}
        if kept != self._state.get("last_balances"):
            self._state["last_balances"] = kept
            self._state["last_balances_ts"] = float(ts)
            self._save_state()

    def count_change(
        self, change: Dict[str, float], value: float, before: float, after: float
    ) -> None:
        """A settled change no recorded fill explains, worth ``value`` at the bids:
        a rise is a deposit, so the peak is scaled by ``after / before`` (the stop's
        value with and without it) and the drawdown is what it was; a fall is a loss
        and changes nothing. Kept for Settings > Risk (the last 10)."""
        assets = {a: float(q) for a, q in sorted(change.items(), key=_cash_first)}
        listed = ", ".join(f"{a} {q:+g}" for a, q in assets.items())
        entry = {"ts": time.time(), "value": float(value), "assets": assets}
        if value > 0.0:
            entry["kind"] = "deposit"
            message = (
                f"Balances rose by ${value:,.2f} with no recorded fill ({listed}): "
                "counted as a deposit"
            )
            if self.peak_value > 0.0 and before > 0.0:
                entry["peak_from"] = self.peak_value
                self.peak_value *= float(after) / float(before)
                entry["peak_to"] = self.peak_value
                message += (
                    f"; peak scaled from ${entry['peak_from']:,.2f} to "
                    f"${self.peak_value:,.2f}, keeping the drawdown"
                )
        else:
            entry["kind"] = "loss"
            message = (
                f"Balances fell by ${-value:,.2f} with no recorded fill ({listed}): "
                "counted as a loss"
            )
        print(message)
        logger.warning(message)
        changes = self._state.get("balance_changes")
        changes = changes if isinstance(changes, list) else []
        self._state["balance_changes"] = (changes + [entry])[-10:]
        self._save_state()

    def update_portfolio_value(self, value: float) -> None:
        if self.state_dir:
            self._apply_requests()
        self.manager.portfolio_value = float(value)
        if float(value) > self.peak_value:
            self.peak_value = float(value)
            self._state["peak_ts"] = time.time()
            self._save_state()

    def validate_order(
        self, order: dict, portfolio_value: float, max_buy_usd: float
    ) -> dict:
        """A halt refuses every buy; a sell still goes through, so exits and stops keep
        working. A buy may be worth at most ``max_buy_usd`` (the trader passes the
        coin's budget). A sell is never refused for its size: it only reduces a
        holding, and a cap there would leave a position that cannot be sold.

        RiskManager.validate_trade is not used for size: it caps every order, sells
        included, at 1% of the account, below the trader's own sizing rules."""
        self.manager.portfolio_value = float(portfolio_value)
        if self.is_trading_halted() and order.get("side") != "sell":
            return {
                "approved": False,
                "reason": "Buying is halted by risk controls (sells still go through)",
            }
        value = float(order["quantity"]) * float(order["price"])
        # half a cent: the quantity is rounded to 8 decimals, so value can pass the
        # limit by a fraction of a cent
        if order.get("side") == "buy" and value > float(max_buy_usd) + 0.005:
            return {
                "approved": False,
                "reason": f"Trade size exceeds risk limits: ${value:,.2f} "
                f"(at most ${float(max_buy_usd):,.2f} per buy)",
            }
        return {"approved": True, "reason": "Trade approved"}

    def check_emergency_conditions(self, portfolio_value: float) -> dict:
        warnings = []
        if self.peak_value <= 0.0:
            return {"emergency_stop": False, "reason": "", "warnings": warnings}

        drawdown = (self.peak_value - float(portfolio_value)) / self.peak_value
        # risk.drawdown_warning_pct / risk.drawdown_critical_pct (defaults 3 and 5)
        # and risk.emergency_drawdown_pct (default 8.0, valid 1-50), the stop
        levels = read_drawdown_levels(self.settings_source)
        self.manager.set_drawdown_levels(
            levels.warning_pct, levels.critical_pct, levels.emergency_pct
        )
        limits = dict(self.manager.risk_thresholds["portfolio_drawdown"])
        if drawdown >= limits["emergency"]:
            return {
                "emergency_stop": True,
                "reason": f"Account drawdown {drawdown:.1%} reached the {levels.emergency_pct:g}% emergency limit",
                "warnings": warnings,
            }
        for level in ("critical", "warning"):
            if drawdown >= limits[level]:
                warnings.append(f"Account drawdown {drawdown:.1%} ({level} level)")
                break
        return {"emergency_stop": False, "reason": "", "warnings": warnings}

    def emergency_stop(self, reason: str = "", value: Optional[float] = None) -> None:
        """Halt trading, and keep the halt (and ``reason``) for the next start."""
        self.manager.emergency_stop()
        self.halt_reason = reason or "Emergency stop"
        if not self.state_dir:
            return
        self._state = risk_state.halted_state(
            self._state, self.halt_reason, value, time.time()
        )
        if not self._save_state():
            print(
                f"{Fore.RED}The halt could not be saved: check the books folder "
                f"{self.state_dir} before starting the trader again{Style.RESET_ALL}"
            )

    def record_error(self, message: str) -> None:
        self.error_count += 1
        logger.error(f"Trader loop error #{self.error_count}: {message}")


class CryptoAPITrading:
    def __init__(
        self, settings_source: Any = None, signal_engine: Optional[SignalEngine] = None
    ):
        """
        ``settings_source`` is where the trading-mode gate reads trading.mode /
        trading.active_broker from (None = the settings file, re-read fresh on
        every order; a dict or SettingsManager is accepted for tests).
        ``signal_engine`` supplies rule-based decisions when ``strategy.engine``
        is "catalogue" (tests inject one with scripted candles).
        """
        self._settings_source = settings_source
        self.signal_engine = signal_engine or SignalEngine(
            settings_source=settings_source
        )
        self._catalogue_mode = False

        # This mode's own ledger / history / status files
        self._settings = read_trading_settings(self._settings_source)
        if self._settings.is_live and not self._settings.uses_testnet:
            # books from before each live broker had its own folder move once; a
            # move that cannot be finished stops the trader before it reads them
            try:
                move_root_live_books(HUB_DATA_DIR, self._settings.active_broker)
            except (OSError, ValueError) as exc:
                raise LiveTradingRefused(
                    f"Live trading refused: the live books could not be moved: {exc}"
                ) from exc
        self.data_dir = os.path.join(HUB_DATA_DIR, self._settings.data_subdir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.trader_status_path = os.path.join(self.data_dir, "trader_status.json")
        self.trade_history_path = os.path.join(self.data_dir, "trade_history.jsonl")
        self.pnl_ledger_path = os.path.join(self.data_dir, "pnl_ledger.json")
        self.account_value_history_path = os.path.join(
            self.data_dir, "account_value_history.jsonl"
        )
        # Open strategy positions + overlay state (stops, cooldowns) survive a restart
        self.signal_engine.attach_state(
            os.path.join(self.data_dir, "strategy_state.json")
        )
        if not self._settings.is_live:
            # Keep the paper book across restarts so it matches the paper ledger
            configure_paper_exchange(
                state_path=os.path.join(self.data_dir, "paper_account.json"),
                settings_source=self._settings_source,
            )

        # Resolve the trading target once at start-up. In live mode without a
        # broker this raises (LiveTradingRefused) and the trader does not start.
        # The trader is pinned to this target for its whole run: every order
        # re-runs the gate and is refused if the mode/broker has since changed.
        self._target: OrderTarget = resolve_order_target(self._settings_source)
        if self._target.key != self._settings.key:
            raise TradingModeError(
                "Trading settings changed while the trader was starting; try again."
            )
        if self._target.is_live:
            # the broker's read-only key check: a key that cannot trade is refused
            key = check_live_key(self._target.exchange, preview=self._target.preview)
            if not key.ok:
                raise LiveTradingRefused(f"Live trading refused: {key.message}")
            print(f"[PowerTrader] API key: {key.message}")
            if key.warning:
                print(f"{Fore.YELLOW}WARNING: {key.warning}{Style.RESET_ALL}")
                logger.warning(key.warning)
        self._previewed: Dict[tuple, float] = {}  # (symbol, side) -> last preview
        # <COIN>-USD -> (when read, the exchange's minimum order) for _is_dust
        self._dust_minimums: Dict[str, tuple] = {}

        print(f"[PowerTrader] Trading target: {self._settings.label}")
        logger.info(f"Trader pinned to target '{self._target.key}'")

        # How long to wait for an order to reach a final state
        self._order_wait_seconds = 60.0
        self._order_poll_seconds = 1.0
        self._reconcile_wait_seconds = 10.0

        # keep a copy of the folder map (same idea as trader.py)
        self.path_map = dict(base_paths)

        # Cache last known bid/ask per symbol so transient API misses don't zero out account value
        self._last_good_bid_ask = {}

        # Cache last *complete* account snapshot so transient holdings/price misses can't write a bogus low value
        self._last_good_account_snapshot = {
            "total_account_value": None,
            "buying_power": None,
            "holdings_sell_value": None,
            "holdings_buy_value": None,
            "percent_in_trade": None,
        }
        # When an account value was last formed (this start, until the first pass
        # forms one), and why there is none since: with none for
        # ACCOUNT_VALUE_MAX_AGE_SECONDS, buys wait
        self._account_value_ts = time.time()
        self._no_value_why = ""
        # whether this run has formed an account value, and whether a pass has found
        # none yet (buys wait until the first one: no buy before a drawdown check)
        self._value_formed = False
        self._no_value_yet = False
        # <ASSET>-USD -> when this run first saw it held with no price at all
        self._unpriced_since: Dict[str, float] = {}
        # a change in the stop's balances no recorded fill explains, waiting to
        # settle: {"change": {asset: quantity}, "since": when first seen}
        self._balance_change: Optional[dict] = None

        self.dca_levels_triggered = {}  # Track DCA levels for each crypto
        self.dca_levels = list(DCA_LEVELS)  # Hard DCA triggers (percent PnL)

        # --- Trailing profit margin (per-coin state) ---
        # Each coin keeps its own trailing PM line, peak, and "was above line" flag.
        self.trailing_pm = (
            {}
        )  # { "BTC": {"active": bool, "line": float, "peak": float, "was_above": bool}, . }
        self.trailing_gap_pct = float(TRAILING_GAP_PCT)  # % trail gap behind peak
        self.pm_start_pct_no_dca = float(PM_START_PCT_NO_DCA)
        self.pm_start_pct_with_dca = float(PM_START_PCT_WITH_DCA)

        # Track trailing-related settings so we can reset trailing state if they change
        self._last_trailing_settings_sig = (
            float(self.trailing_gap_pct),
            float(self.pm_start_pct_no_dca),
            float(self.pm_start_pct_with_dca),
        )

        # Price-integrity bookkeeping (paper mode): degraded events seen in the
        # last hour, seeded from the ledger so a restart doesn't hide them
        self._degraded_events: list = []
        self._warn_ts: Dict[str, float] = {}
        self._last_price_summary_ts = 0.0
        if not self._target.is_live:
            hour_ago = time.time() - 3600.0
            for row in self._read_trade_history():
                try:
                    if (
                        row.get("price_source") in self._DEGRADED_PRICE_EVENTS
                        and float(row.get("ts", 0.0)) >= hour_ago
                    ):
                        self._degraded_events.append(float(row["ts"]))
                except (TypeError, ValueError):
                    continue

        # GUI hub persistence
        # <COIN> -> True when its last fill was a sell that ended the trade (_open_trade)
        self._trade_ended: Dict[str, bool] = self._ended_trades()
        self._pnl_ledger = self._load_pnl_ledger()
        self._reconcile_pending_orders()
        self._report_unknown_orders()

        # Initialize Risk and Cost Management
        self.risk_manager = _TraderRiskAdapter(
            settings_source=self._settings_source, state_dir=self.data_dir
        )
        self.cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

        # Cost basis comes from the local ledger; DCA stages from local history
        self.cost_basis = (
            self.calculate_cost_basis()
        )  # Initialize cost basis at startup
        self.initialize_dca_levels()  # Initialize DCA levels based on recorded buys

        # --- DCA rate-limit (per trade, per coin, rolling 24h window) ---
        self.max_dca_buys_per_24h = int(MAX_DCA_BUYS_PER_24H)
        self.dca_window_seconds = 24 * 60 * 60

        self._dca_buy_ts = {}  # { "BTC": [ts, ts, ...] } (DCA buys only)
        self._dca_last_sell_ts = {}  # { "BTC": ts_of_last_sell }
        self._seed_dca_window_from_history()
        self._log_price_summary()

    def _atomic_write_json(self, path: str, data: dict) -> None:
        try:
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass

    def _append_jsonl(self, path: str, obj: dict) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj) + "\n")
        except Exception:
            pass

    def _load_pnl_ledger(self) -> dict:
        try:
            if os.path.isfile(self.pnl_ledger_path):
                with open(self.pnl_ledger_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if not isinstance(data, dict):
                    data = {}
                # Back-compat upgrades
                data.setdefault("total_realized_profit_usd", 0.0)
                data.setdefault("last_updated_ts", time.time())
                data.setdefault(
                    "open_positions", {}
                )  # { "BTC": {"usd_cost": float, "qty": float} }
                data.setdefault("pending_orders", {})  # { "<order_id>": {...} }
                # { "<symbol>|<side>": {...} }: sends whose outcome is unknown
                data.setdefault("order_intents", {})
                return data
        except Exception:
            pass
        return {
            "total_realized_profit_usd": 0.0,
            "last_updated_ts": time.time(),
            "open_positions": {},
            "pending_orders": {},
            "order_intents": {},
        }

    def _save_pnl_ledger(self) -> bool:
        """Write the ledger; False when it could not be written."""
        try:
            self._pnl_ledger["last_updated_ts"] = time.time()
            self._atomic_write_json(self.pnl_ledger_path, self._pnl_ledger)
        except Exception:
            return False
        return True

    # -- order intents: an order is on disk before it is sent (N5) ------------------

    def _order_intents(self) -> dict:
        intents = self._pnl_ledger.setdefault("order_intents", {})
        if not isinstance(intents, dict):
            intents = self._pnl_ledger["order_intents"] = {}
        return intents

    def _order_intent(self, symbol: str, side: str) -> Optional[dict]:
        intent = self._order_intents().get(f"{symbol}|{side}")
        return intent if isinstance(intent, dict) else None

    def _keep_order_intent(self, symbol: str, side: str, intent: dict) -> bool:
        """Record ``intent`` on disk; False when it could not be (then the order must
        not be sent)."""
        self._order_intents()[f"{symbol}|{side}"] = intent
        return self._save_pnl_ledger()

    def _drop_order_intent(self, symbol: str, side: str) -> None:
        if self._order_intents().pop(f"{symbol}|{side}", None) is not None:
            self._save_pnl_ledger()

    @staticmethod
    def _resends_safely(target: OrderTarget) -> bool:
        """Whether an order sent again with the same client order id cannot make a
        second one: the exchange answers a repeated id with the order it made."""
        return bool(
            getattr(target.exchange, "REPEATED_CLIENT_ORDER_ID_RETURNS_ORDER", False)
        )

    def _unknown_order(self, target: OrderTarget, symbol: str, side: str):
        """What to do about an earlier ``side`` order on ``symbol`` whose outcome is
        unknown: ``("none", None)`` (there is none, or it is given up),
        ``("resend", intent)`` (send that order again, same id and quantity) or
        ``("wait", intent)`` (send nothing yet)."""
        intent = self._order_intent(symbol, side)
        if intent is None:
            return "none", None
        age = time.time() - float(intent.get("first_ts") or 0.0)
        same_account = intent.get("account") == target.key
        if same_account and self._resends_safely(target):
            if age < UNKNOWN_ORDER_RESEND_SECONDS:
                return "resend", intent
        elif same_account and age < UNKNOWN_ORDER_WAIT_SECONDS:
            return "wait", intent
        message = (
            f"Order {intent.get('client_order_id')} ({symbol} {side}, sent "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(intent.get('first_ts') or 0))}): "
            "its outcome is still unknown. Check the exchange's order history; new "
            "orders are sent again."
        )
        print(f"{Fore.RED}{message}{Style.RESET_ALL}")
        logger.error(message)
        self._drop_order_intent(symbol, side)
        return "none", None

    def _report_unknown_orders(self) -> None:
        """At start: every kept order whose outcome is unknown."""
        for key, intent in sorted(self._order_intents().items()):
            if isinstance(intent, dict):
                message = (
                    f"Order {intent.get('client_order_id')} ({key.replace('|', ' ')}) "
                    "was being sent when the trader last stopped or lost the "
                    "connection: its outcome is unknown."
                )
                print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")
                logger.warning(message)

    def _trade_history_has_order_id(self, order_id: str) -> bool:
        try:
            if not order_id:
                return False
            if not os.path.isfile(self.trade_history_path):
                return False
            with open(self.trade_history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if str(obj.get("order_id", "")).strip() == str(order_id).strip():
                        return True
        except Exception:
            return False
        return False

    def _get_buying_power(self) -> float:
        try:
            acct = self.get_account()
            if isinstance(acct, dict):
                return float(acct.get("buying_power", 0.0) or 0.0)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _extract_fill_from_order(order: OrderResult) -> tuple:
        """Returns (filled_qty, fill_price). fill_price is None when the exchange
        doesn't report one (e.g. market orders on some brokers)."""
        try:
            qty = float(order.amount or 0.0)
            price = float(order.price or 0.0)
        except (TypeError, ValueError):
            return 0.0, None
        return (qty if qty > 0.0 else 0.0), (price if price > 0.0 else None)

    @staticmethod
    def _order_cash_change(order: OrderResult, side: str) -> Optional[float]:
        """The cash an order moved, from the exchange's own numbers: minus (value +
        fee) for a buy, plus (value - fee) for a sell. None when the exchange does
        not report the filled value (the change in buying power is used then)."""
        if order.filled_value is None:
            return None
        try:
            value, fee = float(order.filled_value), float(order.fee or 0.0)
        except (TypeError, ValueError):
            return None
        return -(value + fee) if str(side).lower() == "buy" else value - fee

    def _wait_for_order_terminal(
        self,
        target: OrderTarget,
        order_id: str,
        initial: Optional[OrderResult] = None,
        timeout: Optional[float] = None,
    ) -> Optional[OrderResult]:
        """
        Polls ``target.get_order_status`` until the order is filled / canceled /
        rejected and returns that OrderResult. Returns None if the order can't be
        confirmed within ``timeout`` (or the broker can't report order status).
        """
        deadline = time.time() + float(
            self._order_wait_seconds if timeout is None else timeout
        )
        result = initial
        while True:
            if result is not None and (
                str(result.status).lower().strip() in TERMINAL_ORDER_STATES
            ):
                return result
            if time.time() >= deadline:
                return None
            time.sleep(self._order_poll_seconds)
            try:
                result = target.get_order_status(order_id)
            except (NotImplementedError, LookupError):
                return None
            except Exception:
                result = None  # transient; keep polling until the deadline

    def _reconcile_pending_orders(self) -> None:
        """
        If the hub/trader restarts mid-order, we keep the pre-order buying_power on disk and
        finish the accounting once the order shows as terminal on the exchange. Orders
        that can't be confirmed in time stay pending and are retried on the next start.
        """
        try:
            pending = self._pnl_ledger.get("pending_orders", {})
            if not isinstance(pending, dict) or not pending:
                return

            # Keep sweeping while a pass resolves something; stop once a pass is stuck.
            while True:
                pending = self._pnl_ledger.get("pending_orders", {})
                if not isinstance(pending, dict) or not pending:
                    break

                progressed = False

                for order_id, info in list(pending.items()):
                    try:
                        if self._trade_history_has_order_id(order_id):
                            # Already recorded (e.g., crash after writing history) -> just clear pending.
                            self._pnl_ledger["pending_orders"].pop(order_id, None)
                            self._save_pnl_ledger()
                            progressed = True
                            continue

                        symbol = str(info.get("symbol", "")).strip()
                        side = str(info.get("side", "")).strip().lower()
                        bp_before = float(info.get("buying_power_before", 0.0) or 0.0)

                        if not symbol or not side or not order_id:
                            self._pnl_ledger["pending_orders"].pop(order_id, None)
                            self._save_pnl_ledger()
                            progressed = True
                            continue

                        order = self._wait_for_order_terminal(
                            self._target,
                            order_id,
                            timeout=self._reconcile_wait_seconds,
                        )
                        if not order:
                            continue  # unconfirmed: stays pending for the next start

                        state = str(order.status).lower().strip()
                        if state != "filled":
                            # Not filled -> no trade to record, clear pending.
                            self._pnl_ledger["pending_orders"].pop(order_id, None)
                            self._save_pnl_ledger()
                            progressed = True
                            continue

                        filled_qty, avg_price = self._extract_fill_from_order(order)
                        bp_after = self._get_buying_power()
                        bp_delta = self._order_cash_change(order, side)
                        if bp_delta is None:
                            bp_delta = float(bp_after) - float(bp_before)

                        self._record_trade(
                            side=side,
                            symbol=symbol,
                            qty=float(filled_qty),
                            price=float(avg_price) if avg_price is not None else None,
                            avg_cost_basis=info.get("avg_cost_basis", None),
                            pnl_pct=info.get("pnl_pct", None),
                            tag=info.get("tag", None),
                            order_id=order_id,
                            fees_usd=order.fee,
                            buying_power_before=bp_before,
                            buying_power_after=bp_after,
                            buying_power_delta=bp_delta,
                            closes_position=not getattr(order, "partial", False),
                            fee_detail=self._fee_detail(order),
                            **self._provenance(order, self._target),
                        )

                        # Clear pending now that we recorded it
                        self._pnl_ledger["pending_orders"].pop(order_id, None)
                        self._save_pnl_ledger()
                        progressed = True

                    except Exception:
                        continue

                if not progressed:
                    break

        except Exception:
            pass

    def _record_trade(
        self,
        side: str,
        symbol: str,
        qty: float,
        price: Optional[float] = None,
        avg_cost_basis: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        tag: Optional[str] = None,
        order_id: Optional[str] = None,
        fees_usd: Optional[float] = None,
        buying_power_before: Optional[float] = None,
        buying_power_after: Optional[float] = None,
        buying_power_delta: Optional[float] = None,
        price_source: Optional[str] = None,
        quote_ts: Optional[float] = None,
        age_s: Optional[float] = None,
        price_exchange: Optional[str] = None,
        closes_position: bool = True,
        fee_detail: Optional[dict] = None,
    ) -> None:
        """
        Minimal local ledger for GUI:
        - append trade_history.jsonl
        - update pnl_ledger.json on sells (now using buying power delta when available)
        - persist per-coin open position cost (USD) so realized profit is exact

        A sell row says whether it ended the trade (``closes_position``): a sell
        that stopped part-way did not, so the DCA stages and the 24h DCA window
        rebuilt from the history carry on past it. ``fee_detail`` (``_fee_detail``)
        says how the fee in ``fees_usd`` was worked out.
        """
        ts = time.time()

        side_l = str(side or "").lower().strip()
        base = str(symbol or "").upper().split("-")[0].strip()

        # Ensure ledger keys exist (back-compat)
        try:
            if not isinstance(self._pnl_ledger, dict):
                self._pnl_ledger = {}
            self._pnl_ledger.setdefault("total_realized_profit_usd", 0.0)
            self._pnl_ledger.setdefault("open_positions", {})
            self._pnl_ledger.setdefault("pending_orders", {})
        except Exception:
            pass

        realized = None
        position_cost_used = None
        position_cost_after = None

        # --- Exact USD-based accounting (your design) ---
        if base and (buying_power_delta is not None):
            try:
                bp_delta = float(buying_power_delta)
            except Exception:
                bp_delta = None

            if bp_delta is not None:
                try:
                    open_pos = self._pnl_ledger.get("open_positions", {})
                    if not isinstance(open_pos, dict):
                        open_pos = {}
                        self._pnl_ledger["open_positions"] = open_pos

                    pos = open_pos.get(base, None)
                    if not isinstance(pos, dict):
                        pos = {"usd_cost": 0.0, "qty": 0.0}
                        open_pos[base] = pos

                    pos_usd_cost = float(pos.get("usd_cost", 0.0) or 0.0)
                    pos_qty = float(pos.get("qty", 0.0) or 0.0)

                    q = float(qty or 0.0)

                    if side_l == "buy":
                        usd_used = -bp_delta  # buying power drops on buys
                        if usd_used < 0.0:
                            usd_used = 0.0

                        pos["usd_cost"] = float(pos_usd_cost) + float(usd_used)
                        pos["qty"] = float(pos_qty) + float(q if q > 0.0 else 0.0)

                        position_cost_after = float(pos["usd_cost"])

                        # Save because open position changed (needs to persist across restarts)
                        self._save_pnl_ledger()

                    elif side_l == "sell":
                        usd_got = bp_delta  # buying power rises on sells
                        if usd_got < 0.0:
                            usd_got = 0.0

                        # If partial sell ever happens, allocate cost pro-rata by qty.
                        if pos_qty > 0.0 and q > 0.0:
                            frac = min(1.0, float(q) / float(pos_qty))
                        else:
                            frac = 1.0

                        cost_used = float(pos_usd_cost) * float(frac)
                        pos["usd_cost"] = float(pos_usd_cost) - float(cost_used)
                        pos["qty"] = float(pos_qty) - float(q if q > 0.0 else 0.0)

                        position_cost_used = float(cost_used)
                        position_cost_after = float(pos.get("usd_cost", 0.0) or 0.0)

                        realized = float(usd_got) - float(cost_used)
                        self._pnl_ledger["total_realized_profit_usd"] = float(
                            self._pnl_ledger.get("total_realized_profit_usd", 0.0)
                            or 0.0
                        ) + float(realized)

                        # Clean up tiny dust
                        if (
                            float(pos.get("qty", 0.0) or 0.0) <= 1e-12
                            or float(pos.get("usd_cost", 0.0) or 0.0) <= 1e-6
                        ):
                            open_pos.pop(base, None)

                        self._save_pnl_ledger()

                except Exception:
                    pass

        # --- Fallback (old behavior) if we couldn't compute from buying power ---
        if (
            realized is None
            and side_l == "sell"
            and price is not None
            and avg_cost_basis is not None
        ):
            try:
                fee_val = float(fees_usd) if fees_usd is not None else 0.0
                realized = (float(price) - float(avg_cost_basis)) * float(qty) - fee_val
                self._pnl_ledger["total_realized_profit_usd"] = float(
                    self._pnl_ledger.get("total_realized_profit_usd", 0.0)
                ) + float(realized)
                self._save_pnl_ledger()
            except Exception:
                realized = None

        entry = {
            "ts": ts,
            "side": side,
            "tag": tag,
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "avg_cost_basis": avg_cost_basis,
            "pnl_pct": pnl_pct,
            "fees_usd": fees_usd,
            "realized_profit_usd": realized,
            "order_id": order_id,
            "buying_power_before": (
                float(buying_power_before) if buying_power_before is not None else None
            ),
            "buying_power_after": (
                float(buying_power_after) if buying_power_after is not None else None
            ),
            "buying_power_delta": (
                float(buying_power_delta) if buying_power_delta is not None else None
            ),
            "position_cost_used_usd": (
                float(position_cost_used) if position_cost_used is not None else None
            ),
            "position_cost_after_usd": (
                float(position_cost_after) if position_cost_after is not None else None
            ),
        }
        if fee_detail:
            entry.update(fee_detail)
        if price_source is not None:
            # Paper fills record where their price came from (live/stale/simulated)
            entry["price_source"] = price_source
            entry["quote_ts"] = quote_ts
            entry["age_s"] = age_s
            entry["price_exchange"] = price_exchange or ""
            self._note_price_event(price_source, ts)
        if side_l == "sell":
            entry["closes_position"] = bool(closes_position)
        entry.update(self._strategy_fields())
        self._append_jsonl(self.trade_history_path, entry)
        if base and side_l == "buy":
            self._trade_ended[base] = False
        elif base and side_l == "sell" and closes_position:
            self._trade_ended[base] = True

    def _strategy_fields(self) -> dict:
        """What decided the trade, for its record (FDS-SR-001 section 5.11): the
        strategy in effect when the order was placed, its version, the SHA-256 of its
        full parameters, its timeframe and its overlays. Records only: never read to
        trade, and an error here leaves the record without them."""
        try:
            s = read_strategy_settings(self._settings_source)
            if s.is_legacy:
                return {"strategy_id": "legacy_neural"}
            if s.problem:
                return {}
            from strategies.catalogue import create, get_entry

            params = dict(create(s.active_id, **dict(s.params)).params)
            canonical = json.dumps(
                params, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            return {
                "strategy_id": s.active_id,
                "strategy_version": get_entry(s.active_id)["version"],
                "strategy_params_sha256": hashlib.sha256(canonical).hexdigest(),
                "strategy_timeframe": s.timeframe,
                "strategy_overlays": [
                    {"id": o["id"], "version": get_entry(o["id"])["version"]}
                    for o in s.overlays
                ],
            }
        except Exception:
            return {}

    @staticmethod
    def _sell_ends_trade(entry: dict) -> bool:
        """A sell row ends the trade unless it says it did not (rows written before
        ``closes_position`` existed end it, as they always did)."""
        return entry.get("closes_position") is not False

    def _ended_trades(self) -> Dict[str, bool]:
        """Whether each coin's last fill in this mode's trade history was a sell that
        ended its trade (a buy, or a sell that stopped part-way, leaves it open)."""
        ended: Dict[str, bool] = {}
        for row in self._read_trade_history():
            base = str(row.get("symbol", "") or "").upper().split("-")[0].strip()
            side = str(row.get("side", "") or "").lower().strip()
            if base and side == "buy":
                ended[base] = False
            elif base and side == "sell" and self._sell_ends_trade(row):
                ended[base] = True
        return ended

    def _open_trade(self, base: str) -> bool:
        """Whether this trader has a trade open in ``base``: the ledger holds a position
        in it, and no sell has ended that trade since its last buy (what such a sell
        leaves behind is a remainder, not a trade)."""
        if self._trade_ended.get(base, False):
            return False
        try:
            pos = (self._pnl_ledger.get("open_positions") or {}).get(base) or {}
            return float(pos.get("qty", 0.0) or 0.0) > 0.0
        except (AttributeError, TypeError, ValueError):
            return False

    def _write_trader_status(self, status: dict) -> None:
        self._atomic_write_json(self.trader_status_path, status)

    @staticmethod
    def _fmt_price(price: float) -> str:
        """
        Dynamic decimal formatting by magnitude:
        - >= 1.0   -> 2 decimals (BTC/ETH/etc won't show 8 decimals)
        - <  1.0   -> enough decimals to show meaningful digits (based on first non-zero),
                     then trim trailing zeros.
        """
        try:
            p = float(price)
        except Exception:
            return "N/A"

        if p == 0:
            return "0"

        ap = abs(p)

        if ap >= 1.0:
            decimals = 2
        else:
            # Example:
            # 0.5      -> decimals ~ 4 (prints "0.5" after trimming zeros)
            # 0.05     -> 5
            # 0.005    -> 6
            # 0.000012 -> 8
            decimals = int(-math.floor(math.log10(ap))) + 3
            decimals = max(2, min(12, decimals))

        s = f"{p:.{decimals}f}"

        # Trim useless trailing zeros for cleaner output (0.5000 -> 0.5)
        if "." in s:
            s = s.rstrip("0").rstrip(".")

        return s

    @staticmethod
    def _read_long_dca_signal(symbol: str) -> int:
        """
        Reads long_dca_signal.txt from the per-coin folder (same folder rules as trader.py).

        Used for:
        - Start gate: start trades at level 3+
        - DCA assist: levels 4-7 map to trader DCA stages 0-3 (trade starts at level 3 => stage 0)
        """
        sym = str(symbol).upper().strip()
        folder = base_paths.get(
            sym, main_dir if sym == "BTC" else os.path.join(main_dir, sym)
        )
        path = os.path.join(folder, "long_dca_signal.txt")
        try:
            if time.time() - os.path.getmtime(path) > SIGNAL_MAX_AGE_SECONDS:
                return 0  # stale: the runner is not updating it
            with open(path, "r") as f:
                raw = f.read().strip()
            val = int(float(raw))
            return val
        except Exception:
            return 0

    def _market_not_trading(self, symbol: str) -> Optional[str]:
        """Why ``symbol`` must get no buys, or None. The runner and the trainer record
        in the coin's folder when its market is not trading (delisted, halted,
        or never listed): no entry and no DCA buy is made in such a coin. Sells are
        not blocked. The reason is printed once per coin."""
        sym = str(symbol).upper().strip()
        folder = base_paths.get(
            sym, main_dir if sym == "BTC" else os.path.join(main_dir, sym)
        )
        reason = not_trading_reason(folder)
        noted = self.__dict__.setdefault("_not_trading_noted", set())
        if reason is None:
            noted.discard(sym)
        elif sym not in noted:
            noted.add(sym)
            print(
                f"  No buys in {sym}: {reason}. Lifted once the runner or a training "
                "run sees its market trading."
            )
        return reason

    @staticmethod
    def _read_short_dca_signal(symbol: str) -> Optional[int]:
        """
        Reads short_dca_signal.txt from the per-coin folder (same folder rules as trader.py).

        Used for:
        - Start gate: start trades at level 3+
        - DCA assist: levels 4-7 map to trader DCA stages 0-3 (trade starts at level 3 => stage 0)

        A missing, stale or unreadable file returns None, which blocks a new trade
        (the gate needs short == 0): an unknown short count is not "no shorts".
        """
        sym = str(symbol).upper().strip()
        folder = base_paths.get(
            sym, main_dir if sym == "BTC" else os.path.join(main_dir, sym)
        )
        path = os.path.join(folder, "short_dca_signal.txt")
        try:
            if time.time() - os.path.getmtime(path) > SIGNAL_MAX_AGE_SECONDS:
                return None  # stale: the runner is not updating it
            with open(path, "r") as f:
                raw = f.read().strip()
            val = int(float(raw))
            return val
        except Exception:
            return None

    @staticmethod
    def _read_long_price_levels(symbol: str) -> list:
        """
        Reads low_bound_prices.html from the per-coin folder and returns a list of LONG (blue) price levels.

        Returned ordering is highest->lowest so:
          N1 = 1st blue line (top)
          ...
          N7 = 7th blue line (bottom)
        """
        sym = str(symbol).upper().strip()
        folder = base_paths.get(
            sym, main_dir if sym == "BTC" else os.path.join(main_dir, sym)
        )
        path = os.path.join(folder, "low_bound_prices.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = (f.read() or "").strip()
            if not raw:
                return []

            # Normalize common formats: python-list, comma-separated, newline-separated
            raw = raw.strip().strip("[]()")
            raw = raw.replace(",", " ").replace(";", " ").replace("|", " ")
            raw = raw.replace("\n", " ").replace("\t", " ")
            parts = [p for p in raw.split() if p]

            vals = []
            for p in parts:
                try:
                    vals.append(float(p))
                except Exception:
                    continue

            # De-dupe, then sort high->low for stable N1..N7 mapping
            out = []
            seen = set()
            for v in vals:
                k = round(float(v), 12)
                if k in seen:
                    continue
                seen.add(k)
                out.append(float(v))
            out.sort(reverse=True)
            return out
        except Exception:
            return []

    def _read_trade_history(self) -> list:
        """All entries of this mode's local trade_history.jsonl (oldest first)."""
        entries = []
        if not os.path.isfile(self.trade_history_path):
            return entries
        try:
            with open(self.trade_history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        if not self._target.is_live:
                            # Rows written before FDS-096b have no provenance columns
                            obj.setdefault("price_source", "unknown")
                            obj.setdefault("quote_ts", None)
                            obj.setdefault("age_s", None)
                        entries.append(obj)
        except Exception:
            pass
        return entries

    # --- price integrity (paper mode, FDS-096b) -----------------------------

    # Price events that mean "this was not a live price" (or no price at all)
    _DEGRADED_PRICE_EVENTS = ("stale", "simulated", "unavailable")

    def _note_price_event(self, source: str, ts: Optional[float] = None) -> None:
        if source in self._DEGRADED_PRICE_EVENTS:
            self._degraded_events.append(float(ts if ts is not None else time.time()))

    def _degraded_last_hour(self) -> int:
        cutoff = time.time() - 3600.0
        self._degraded_events = [t for t in self._degraded_events if t >= cutoff]
        return len(self._degraded_events)

    def _fills_by_source(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in self._read_trade_history():
            source = str(row.get("price_source", "unknown"))
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _price_integrity_status(self) -> Optional[dict]:
        """Status block for the hub's mode strip; None outside paper mode."""
        if self._target.is_live:
            return None
        degraded = self._degraded_last_hour()
        return {
            "state": "degraded" if degraded else "live",
            "degraded_last_hour": degraded,
            "policy": read_paper_settings(self._settings_source).price_fallback_policy,
            "fills_by_source": self._fills_by_source(),
        }

    def _log_price_summary(self) -> None:
        """One line: paper fills by price_source (start-up and hourly)."""
        if self._target.is_live:
            return
        counts = self._fills_by_source()
        summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        logger.info(
            f"Paper fills by price_source: {summary} (total {sum(counts.values())}); "
            f"degraded events in last hour: {self._degraded_last_hour()}"
        )
        self._last_price_summary_ts = time.time()

    def _decide(self, base: str, position: Any) -> Any:
        """The strategy's decision for ``base`` (``SignalEngine.decide``), or None, a
        HOLD, when deciding raised: one coin's error never ends the pass, so the other
        coins are still decided and managed and the status is still written (N8)."""
        try:
            return self.signal_engine.decide(base, position)
        except Exception as exc:
            message = (
                f"No decision for {base} this pass ({type(exc).__name__}: {exc}); "
                "it holds, and the other coins go on"
            )
            if time.time() - self._warn_ts.get(f"decide:{base}", 0.0) >= 300.0:
                self._warn_ts[f"decide:{base}"] = time.time()
                print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")
                logger.exception(message)
            return None

    def _warn_throttled(self, key: str, message: str, every: float = 60.0) -> None:
        """WARNING at most once per ``every`` seconds per key (the loop runs 2x/s)."""
        now = time.time()
        if now - self._warn_ts.get(key, 0.0) >= every:
            self._warn_ts[key] = now
            logger.warning(message)

    def _entry_coins(self) -> list:
        """The coins this trader may open new trades in: the coins in Settings, or in
        paper mode the paper-trading coins chosen in Settings (paper_coins.py). Held
        positions are managed whatever this returns."""
        coins = paper_coins.normalise(crypto_symbols)
        if not self._settings.is_live:
            coins = paper_coins.entry_coins(_load_gui_settings(), coins)
        if coins != getattr(self, "_last_entry_coins", None):
            self._last_entry_coins = coins
            print(
                "[PowerTrader] New trades open in: "
                + (", ".join(coins) if coins else "no coins")
            )
        return coins

    def _llm_hook(self):
        """The LLM signal hook (llm_gate.EntryHook), made on first use."""
        hook = getattr(self, "_llm_entry_hook", None)
        if hook is None:
            import llm_gate

            hook = self._llm_entry_hook = llm_gate.EntryHook(self._settings_source)
        return hook

    def _llm_entry_allowed(self, coin: str, client_order_id: str) -> bool:
        """False only when a usable LLM signal vetoes, or does not confirm, the
        entry the strategy wants (llm_gate). It never places an order, waits at
        most the signal wait in Settings, and any failure lets the entry go ahead."""
        try:
            verdict = self._llm_hook().check(
                coin, client_order_id, live=self._settings.is_live
            )
            return bool(verdict.allow)
        except Exception:
            return True

    def _entry_assessment_capture(
        self,
        coin: str,
        symbol: str,
        amount_usd: float,
        minimum_entry_usd: Optional[float],
        ask: Any,
        bid: Any,
        source: str,
    ) -> Optional[Dict[str, Any]]:
        """What the entry assessment needs, captured right after sizing; None when every
        part of it is Off (then nothing is computed). It reads the settings only, and
        never changes or delays the entry (signal_fusion.settings, signal_fusion.live).
        """
        try:
            from signal_fusion import live
            from signal_fusion import settings as fusion_settings

            settings = fusion_settings.read(self._settings_source)
            if settings.all_off():
                return None
            return live.capture(
                settings,
                coin,
                symbol,
                source,
                amount_usd,
                minimum_entry_usd,
                ask,
                bid,
                getattr(self, "_quotes_at", None),
            )
        except Exception:
            return None  # Log only at most: a failure here changes nothing

    def _entry_assessment_log(self, captured: Optional[Dict[str, Any]]) -> None:
        """Record what the entry assessment would have done, after the order was placed.
        In this version every part is Off or Log only, so it changes no order, and an
        error in it is recorded, never raised into the trader."""
        if captured is None:
            return
        try:
            from signal_fusion import live

            fees = self._trading_fees(captured["symbol"])
            captured["fee"] = getattr(fees, "taker", None)
            captured["fee_source"] = getattr(fees, "source", None)
            live.log(captured)
        except Exception:
            pass

    def _llm_entry_placed(self, client_order_id: str, response: Any) -> None:
        """Link the LLM decision that let an entry through to its filled order."""
        try:
            self._llm_hook().placed(client_order_id, (response or {}).get("id"))
        except Exception:
            pass

    def initialize_dca_levels(self):
        """
        Initializes the DCA levels_triggered dictionary from the local trade history:
        for each held asset, the number of buys after the first buy that followed
        the most recent sell.
        """
        holdings = self.get_holdings()
        if not holdings or "results" not in holdings:
            print("No holdings found. Skipping DCA levels initialization.")
            return

        history = self._read_trade_history()

        for holding in holdings.get("results", []):
            symbol = holding["asset_code"]
            full_symbol = f"{symbol}-USD"

            fills = []
            for entry in history:
                try:
                    if str(entry.get("symbol", "")).upper().strip() != full_symbol:
                        continue
                    side = str(entry.get("side", "")).lower().strip()
                    if side == "buy" or (
                        side == "sell" and self._sell_ends_trade(entry)
                    ):
                        fills.append((float(entry.get("ts")), side))
                except (TypeError, ValueError):
                    continue

            if not fills:
                print(f"No recorded trades for {full_symbol}. Skipping.")
                continue

            # Buys after the most recent sell that ended a trade belong to the
            # current trade (a sell that stopped part-way did not end it)
            last_sell_ts = max(
                (ts for ts, side in fills if side == "sell"), default=None
            )
            current_buys = sorted(
                ts
                for ts, side in fills
                if side == "buy" and (last_sell_ts is None or ts > last_sell_ts)
            )
            if not current_buys:
                print(f"No buys after the most recent sell for {full_symbol}.")
                self.dca_levels_triggered[symbol] = []
                continue

            # Every buy after the first one is a DCA stage. Track by stage index
            # (0, 1, 2, ...) rather than % values so neural-vs-hardcoded stays clean
            # and the -50% stage can repeat indefinitely.
            triggered_levels_count = len(current_buys) - 1
            self.dca_levels_triggered[symbol] = list(range(triggered_levels_count))
            print(f"Initialized DCA stages for {symbol}: {triggered_levels_count}")

    def _seed_dca_window_from_history(self) -> None:
        """
        Seeds in-memory DCA buy timestamps from this mode's trade history so the 24h limit
        works across restarts.

        Uses the local GUI trade history (tag == "DCA") and resets per trade at the most recent sell.
        """
        now_ts = time.time()
        cutoff = now_ts - float(getattr(self, "dca_window_seconds", 86400))

        self._dca_buy_ts = {}
        self._dca_last_sell_ts = {}

        if not os.path.isfile(self.trade_history_path):
            return

        try:
            with open(self.trade_history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue

                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    ts = obj.get("ts", None)
                    side = str(obj.get("side", "")).lower()
                    tag = obj.get("tag", None)
                    sym_full = str(obj.get("symbol", "")).upper().strip()
                    base = sym_full.split("-")[0].strip() if sym_full else ""
                    if not base:
                        continue

                    try:
                        ts_f = float(ts)
                    except Exception:
                        continue

                    if side == "sell" and self._sell_ends_trade(obj):
                        prev = float(self._dca_last_sell_ts.get(base, 0.0) or 0.0)
                        if ts_f > prev:
                            self._dca_last_sell_ts[base] = ts_f

                    elif side == "buy" and tag == "DCA":
                        self._dca_buy_ts.setdefault(base, []).append(ts_f)

        except Exception:
            return

        # Keep only DCA buys after the last sell (current trade) and within rolling 24h
        for base, ts_list in list(self._dca_buy_ts.items()):
            last_sell = float(self._dca_last_sell_ts.get(base, 0.0) or 0.0)
            kept = [t for t in ts_list if (t > last_sell) and (t >= cutoff)]
            kept.sort()
            self._dca_buy_ts[base] = kept

    def _dca_window_count(
        self, base_symbol: str, now_ts: Optional[float] = None
    ) -> int:
        """
        Count of DCA buys for this coin within rolling 24h in the *current trade*.
        Current trade boundary = most recent sell we observed for this coin.
        """
        base = str(base_symbol).upper().strip()
        if not base:
            return 0

        now = float(now_ts if now_ts is not None else time.time())
        cutoff = now - float(getattr(self, "dca_window_seconds", 86400))
        last_sell = float(self._dca_last_sell_ts.get(base, 0.0) or 0.0)

        ts_list = list(self._dca_buy_ts.get(base, []) or [])
        ts_list = [t for t in ts_list if (t > last_sell) and (t >= cutoff)]
        self._dca_buy_ts[base] = ts_list
        return len(ts_list)

    def _note_dca_buy(self, base_symbol: str, ts: Optional[float] = None) -> None:
        base = str(base_symbol).upper().strip()
        if not base:
            return
        t = float(ts if ts is not None else time.time())
        self._dca_buy_ts.setdefault(base, []).append(t)
        self._dca_window_count(base, now_ts=t)  # prune in-place

    def _reset_dca_window_for_trade(
        self, base_symbol: str, sold: bool = False, ts: Optional[float] = None
    ) -> None:
        base = str(base_symbol).upper().strip()
        if not base:
            return
        if sold:
            self._dca_last_sell_ts[base] = float(ts if ts is not None else time.time())
        self._dca_buy_ts[base] = []

    # ------------------------------------------------------------------
    # Exchange access.
    #
    # Everything below talks to the AbstractExchange interface through the
    # OrderTarget handed out by the trading-mode gate
    # (trading_mode.resolve_order_target). There is deliberately no direct
    # broker REST code in this module: balances, prices and orders all go
    # through self._target / the target the gate returns for an order.
    # ------------------------------------------------------------------

    def _resolve_target_for_order(self) -> OrderTarget:
        """
        The gate. Must be called before every order and its result is the only
        thing an order may be sent to. Raises TradingModeError when live trading
        is refused, or when the mode/broker changed since this trader started
        (this trader's ledger and history belong to the mode it started in).
        """
        target = resolve_order_target(self._settings_source)
        if target.key != self._target.key:
            raise TradingModeError(
                f"Trading mode changed from '{self._target.key}' to "
                f"'{target.key}' since the trader started. Restart the trader "
                "to apply it."
            )
        return target

    def _trading_mode_unchanged(self) -> bool:
        """Cheap per-tick check (builds no exchange)."""
        return read_trading_settings(self._settings_source).key == self._target.key

    @staticmethod
    def _describe_exchange_error(exc: Exception, what: str, broker: str) -> str:
        if isinstance(exc, NotImplementedError):
            return f"Broker '{broker}' does not implement {what} yet"
        return f"{what} failed: {str(exc)[:200]}"

    @staticmethod
    def _buying_power_from(balances: Dict[str, float]) -> float:
        for asset in BUYING_POWER_ASSETS:
            if asset in balances:
                return float(balances[asset] or 0.0)
        return 0.0

    def get_account(self) -> Any:
        try:
            balances = self._target.get_balance()
        except Exception as exc:
            return {
                "error": self._describe_exchange_error(
                    exc, "balance retrieval", self._target.key
                )
            }
        return self._account_from(balances)

    def _account_from(self, balances: Dict[str, float]) -> dict:
        return {"buying_power": self._buying_power_from(balances)}

    def get_holdings(self) -> Any:
        try:
            balances = self._target.get_balance()
        except Exception as exc:
            return {
                "error": self._describe_exchange_error(
                    exc, "balance retrieval", self._target.key
                )
            }
        return self._holdings_from(balances)

    def _read_balances(self) -> tuple:
        """A pass's one balance read (``OrderTarget.get_balance_and_holds``):
        (account, holdings, every balance with funds on hold), the first two as
        ``get_account`` and ``get_holdings`` give them, the last for the drawdown
        stop (``_stop_balances``). When the balances cannot be read the first two
        are the error and the last None. Outside the pass (after a trade) the
        balances are read afresh with ``get_account`` and ``get_holdings``."""
        try:
            available, with_holds = self._target.get_balance_and_holds()
            if not isinstance(available, dict) or not isinstance(with_holds, dict):
                raise ValueError("the exchange's answer is not two balance lists")
        except Exception as exc:
            error = self._describe_exchange_error(
                exc, "balance retrieval", self._target.key
            )
            return {"error": error}, {"error": error}, None
        return (
            self._account_from(available),
            self._holdings_from(available),
            self._stop_balances(with_holds),
        )

    @staticmethod
    def _holdings_from(balances: Dict[str, float]) -> dict:
        results = []
        for asset, qty in balances.items():
            code = str(asset).upper().strip()
            if code in CASH_ASSETS:
                continue
            try:
                code = InputValidator.validate_crypto_symbol(code)
                quantity = float(qty)
            except (ValidationError, TypeError, ValueError):
                continue  # skip assets we can't price/trade safely
            if quantity > 0.0:
                results.append({"asset_code": code, "total_quantity": quantity})
        return {"results": results}

    def get_trading_pairs(self) -> Any:
        # AbstractExchange has no pair listing; trade the configured coins.
        return [
            f"{str(s).upper().strip()}-USD" for s in crypto_symbols if str(s).strip()
        ]

    def calculate_cost_basis(self):
        """
        Per-unit cost basis from the local P&L ledger (the ledger is updated on
        every fill, whichever exchange or paper account it came from). Assets
        bought outside this trader have no ledger entry and get no cost basis,
        so no take-profit / DCA decisions are made on them.
        """
        open_positions = (self._pnl_ledger or {}).get("open_positions", {})
        cost_basis = {}
        if not isinstance(open_positions, dict):
            return cost_basis
        for asset_code, pos in open_positions.items():
            try:
                qty = float(pos.get("qty", 0.0) or 0.0)
                usd_cost = float(pos.get("usd_cost", 0.0) or 0.0)
            except (AttributeError, TypeError, ValueError):
                continue
            cost_basis[asset_code] = (usd_cost / qty) if qty > 0.0 else 0.0
        return cost_basis

    def get_price(self, symbols: list) -> Dict[str, float]:
        buy_prices = {}
        sell_prices = {}
        valid_symbols = []

        for symbol in symbols:
            if symbol == "USDC-USD":
                continue

            ask = bid = 0.0
            try:
                market_data = self._target.get_market_data(symbol)
                ask = float(market_data.ask)
                bid = float(market_data.bid)
            except Exception as exc:
                if not self._target.is_live:
                    # Paper: say why there is no price (e.g. PRICE_UNAVAILABLE)
                    self._note_price_event("unavailable")
                    self._warn_throttled(
                        f"price:{symbol}",
                        f"No usable paper price for {symbol}: {exc}; retrying next cycle",
                    )

            if ask > 0.0 and bid > 0.0:
                buy_prices[symbol] = ask
                sell_prices[symbol] = bid
                valid_symbols.append(symbol)

                # Update cache for transient failures later
                self._last_good_bid_ask[symbol] = {
                    "ask": ask,
                    "bid": bid,
                    "ts": time.time(),
                }
            else:
                # Fallback to cached bid/ask so account value never drops due to a transient miss
                cached = self._last_good_bid_ask.get(symbol)
                if cached and not self._target.is_live:
                    # Paper never trades on a price older than max_quote_age_s
                    max_age = read_paper_settings(self._settings_source).max_quote_age_s
                    if time.time() - float(cached.get("ts", 0.0)) > max_age:
                        cached = None
                if cached:
                    ask = float(cached.get("ask", 0.0) or 0.0)
                    bid = float(cached.get("bid", 0.0) or 0.0)
                    if ask > 0.0 and bid > 0.0:
                        buy_prices[symbol] = ask
                        sell_prices[symbol] = bid
                        valid_symbols.append(symbol)

        return buy_prices, sell_prices, valid_symbols

    def _get_account_value(self) -> Optional[float]:
        """Last complete account snapshot value, or None before the first one."""
        value = (self._last_good_account_snapshot or {}).get("total_account_value")
        return float(value) if value is not None else None

    def _get_halt_value(self) -> Optional[float]:
        """What the drawdown stop measures, from the last complete snapshot: every
        balance, funds on hold included, the cash assets at $1 (``_halt_equity``);
        the account value until the saved peak is in that measure. None before the
        first snapshot."""
        last = self._last_good_account_snapshot or {}
        value = last.get("halt_equity")
        if value is None:
            value = last.get("total_account_value")
        return float(value) if value is not None else None

    @staticmethod
    def _stop_balances(balances: Dict[str, float]) -> Dict[str, float]:
        """Every balance with the funds held for open orders included, by asset code,
        for the drawdown stop. Codes the trader cannot price are left out, as in
        ``get_holdings``."""
        totals: Dict[str, float] = {}
        for asset, qty in balances.items():
            code = str(asset).upper().strip()
            try:
                if code not in CASH_ASSETS:
                    code = InputValidator.validate_crypto_symbol(code)
                quantity = float(qty)
            except (ValidationError, TypeError, ValueError):
                continue
            if quantity > 0.0 and math.isfinite(quantity):
                totals[code] = totals.get(code, 0.0) + quantity
        return totals

    def _halt_equity(
        self, totals: Dict[str, float], buy_prices: dict, sell_prices: dict, now: float
    ) -> tuple:
        """(value, left out, not yet priced) of the drawdown stop's own measure of
        ``totals``: the cash assets (CASH_ASSETS) at $1 and every other asset at its
        bid, or left out as in the account value (``_held_price``; (asset, quantity,
        why)). An asset with no price yet in this run holds the value back, as in the
        account value. The owner's own coins count like any other."""
        value = 0.0
        not_counted = []
        not_yet = []
        for code, qty in totals.items():
            if code in CASH_ASSETS:
                value += qty
                continue
            _ask, bid, why = self._held_price(
                f"{code}-USD", buy_prices, sell_prices, now
            )
            if why == NOT_YET_PRICED:
                not_yet.append(code)
            elif why:
                not_counted.append((code, qty, why))
            else:
                value += qty * bid
        return value, not_counted, not_yet

    def _settled_value(
        self,
        totals: Dict[str, float],
        buy_prices: dict,
        sell_prices: dict,
        value: float,
        now: float,
    ) -> float:
        """The value the drawdown stop checks this pass. ``totals`` (the stop's
        balances, worth ``value``) are compared with the last balances it settled on
        plus the fills recorded since; each asset is valued at its bid
        (``_held_price``; one with no usable price, or none yet in this run, is not
        compared this pass, and what the fills say it holds is kept for later). A change no fill explains
        waits BALANCE_CHANGE_SETTLE_SECONDS, restarting whenever it changes; until
        then buys wait and the value without it is checked. Settled, a net rise is a
        deposit and a net fall a loss (``count_change``). A rise is never read as a
        gain, so a misread can only make the stop stricter; this holds with an order
        of unknown outcome too, so such a change is classified all the same."""
        rm = self.risk_manager
        held: Dict[str, float] = {}
        for code, qty in totals.items():
            key = CASH_KEY if code in CASH_ASSETS else code
            held[key] = held.get(key, 0.0) + float(qty)
        bids: Dict[str, float] = {}

        def bid(asset: str) -> Optional[float]:
            if asset == CASH_KEY:
                return 1.0
            if asset not in bids:
                _ask, price, why = self._held_price(
                    f"{asset}-USD", buy_prices, sell_prices, now
                )
                bids[asset] = None if why else price
            return bids[asset]

        counted = {a: q for a, q in held.items() if bid(a) is not None}
        saved = rm.last_balances()
        if saved is None:
            self._balance_change = None
            rm.keep_balances(counted, now)  # nothing to compare with yet
            return value
        last, last_ts = saved
        expected = dict(last)
        for asset, qty in self._fill_changes_since(last_ts).items():
            expected[asset] = expected.get(asset, 0.0) + qty
        change: Dict[str, float] = {}
        compared = set()
        for asset in set(expected) | set(counted):
            price = bid(asset)
            if price is None:
                continue
            compared.add(asset)
            moved = counted.get(asset, 0.0) - expected.get(asset, 0.0)
            if abs(moved * price) >= BALANCE_CHANGE_TOLERANCE_USD:
                change[asset] = moved
        # what to compare with next: these balances, and for an asset not valued
        # this pass, what the fills say it holds
        settled = {a: q for a, q in expected.items() if a not in compared}
        settled.update(counted)
        if not change:
            self._balance_change = None
            rm.keep_balances(settled, now)
            return value
        flow = sum(qty * bid(asset) for asset, qty in change.items())
        before = float(value) - flow
        pending = self._balance_change
        if pending is None or not self._same_change(pending["change"], change, bid):
            pending = self._balance_change = {"change": change, "since": now}
        if now - pending["since"] < BALANCE_CHANGE_SETTLE_SECONDS:
            return before
        rm.count_change(change, flow, before, value)
        self._balance_change = None
        rm.keep_balances(settled, now)
        return value

    @staticmethod
    def _same_change(seen: dict, change: dict, bid) -> bool:
        """Whether the balances are where they were when ``seen`` was found."""
        if set(seen) != set(change):
            return False
        return all(
            abs((change[a] - seen[a]) * bid(a)) < BALANCE_CHANGE_TOLERANCE_USD
            for a in change
        )

    def _fill_changes_since(self, since: float) -> Dict[str, float]:
        """What the fills recorded after ``since`` did to the balances, from
        trade_history.jsonl (this trader's and Order Management's): each coin's
        quantity, a fee charged in another asset (``other_fees``), and the cash
        (CASH_KEY), from the row's cash change or else its quantity, price and fee.
        A row whose cash cannot be told explains only its coin. Read again only
        when the file changes."""
        try:
            stat = os.stat(self.trade_history_path)
            key = (since, stat.st_size, stat.st_mtime)
        except OSError:
            key = (since, None, None)
        cached = getattr(self, "_fill_changes", None)
        if cached is not None and cached[0] == key:
            return dict(cached[1])
        changes: Dict[str, float] = {}
        for row in self._read_trade_history():
            try:
                if float(row.get("ts") or 0.0) <= since:
                    continue
                side = str(row.get("side") or "").lower().strip()
                base = str(row.get("symbol") or "").upper().split("-")[0].strip()
                qty = float(row.get("qty") or 0.0)
            except (TypeError, ValueError):
                continue
            if side not in ("buy", "sell") or not base or not qty > 0.0:
                continue
            changes[base] = changes.get(base, 0.0) + (qty if side == "buy" else -qty)
            others = row.get("other_fees")
            for asset, fee in (others if isinstance(others, dict) else {}).items():
                try:
                    key_asset = str(asset).upper()
                    key_asset = CASH_KEY if key_asset in CASH_ASSETS else key_asset
                    changes[key_asset] = changes.get(key_asset, 0.0) - float(fee)
                except (TypeError, ValueError):
                    continue
            try:
                cash = row.get("buying_power_delta")
                if cash is None:
                    value = qty * float(row["price"])
                    fee = float(row.get("fees_usd") or 0.0)
                    cash = -(value + fee) if side == "buy" else value - fee
                changes[CASH_KEY] = changes.get(CASH_KEY, 0.0) + float(cash)
            except (KeyError, TypeError, ValueError):
                continue  # its cash cannot be told: left unexplained
        self._fill_changes = (key, dict(changes))
        return changes

    def _held_price(
        self, symbol: str, buy_prices: dict, sell_prices: dict, now: float
    ) -> tuple:
        """(ask, bid, "") for a held asset in the account value: this pass's price,
        or its last one while that is at most HELD_PRICE_MAX_AGE_SECONDS old. Else
        (0.0, 0.0, why not): PRICE_TOO_OLD when its last one is older, and with none
        in this run NOT_YET_PRICED (the pass forms no value) until it has gone
        HELD_PRICE_MAX_AGE_SECONDS so since this run first saw it, then NO_USD_PRICE.
        Both PRICE_TOO_OLD and NO_USD_PRICE leave it out of the value."""
        cached = self._last_good_bid_ask.get(symbol) or {}
        age = now - float(cached.get("ts", 0.0) or 0.0) if cached else None
        ask = float(buy_prices.get(symbol, 0.0) or 0.0)
        bid = float(sell_prices.get(symbol, 0.0) or 0.0)
        unpriced = self.__dict__.setdefault("_unpriced_since", {})
        if (
            ask > 0.0
            and bid > 0.0
            and (age is None or age <= HELD_PRICE_MAX_AGE_SECONDS)
        ):
            unpriced.pop(symbol, None)
            return ask, bid, ""
        if age is not None and age <= HELD_PRICE_MAX_AGE_SECONDS:
            ask = float(cached.get("ask", 0.0) or 0.0)
            bid = float(cached.get("bid", 0.0) or 0.0)
            if ask > 0.0 and bid > 0.0:
                return ask, bid, ""
        if cached:
            return 0.0, 0.0, PRICE_TOO_OLD
        since = unpriced.setdefault(symbol, now)
        if now - since < HELD_PRICE_MAX_AGE_SECONDS:
            return 0.0, 0.0, NOT_YET_PRICED
        return 0.0, 0.0, NO_USD_PRICE

    def _buys_wait_reason(self) -> str:
        """Why buys wait ("" when they do not): while this run's passes have formed
        no account value yet, and with none for over ACCOUNT_VALUE_MAX_AGE_SECONDS,
        the drawdown cannot be checked, so buys wait until there is one again; and
        while a balance change no recorded fill explains settles
        (``_settled_value``). Sells are never held back."""
        since = getattr(self, "_account_value_ts", None)
        why = getattr(self, "_no_value_why", "") or "the balances could not be read"
        if getattr(self, "_no_value_yet", False):
            return f"no account value yet since the trader started ({why})"
        if since is not None and time.time() - since > ACCOUNT_VALUE_MAX_AGE_SECONDS:
            minutes = ACCOUNT_VALUE_MAX_AGE_SECONDS // 60
            return f"no account value for over {minutes} minutes ({why})"
        if getattr(self, "_balance_change", None):
            return (
                "the balances changed with no recorded fill; buys go on once they "
                f"have been unchanged for {BALANCE_CHANGE_SETTLE_SECONDS} seconds"
            )
        return ""

    def _risk_check(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        minimum_entry_usd: Optional[float] = None,
    ):
        """Shared pre-order risk gate. Returns True when the order may proceed. A halt
        refuses buys only: a sell (an exit, a stop, the trailing margin) goes through.
        """
        if side != "sell" and self.risk_manager.is_trading_halted():
            print(
                f"{Fore.RED}RISK HALT: buying is halted by the emergency stop; sells "
                f"still go through{Style.RESET_ALL}"
            )
            return False
        waiting = self._buys_wait_reason()
        if side != "sell" and waiting:
            print(
                f"{Fore.YELLOW}BUYS WAITING: {waiting}; sells still go "
                f"through{Style.RESET_ALL}"
            )
            return False

        portfolio_value = self._get_account_value()
        if portfolio_value is None:
            portfolio_value = self._get_buying_power()
        # the peak is raised on what the stop measures; the buy is sized on the
        # account value
        measured = self._get_halt_value()
        self.risk_manager.update_portfolio_value(
            portfolio_value if measured is None else measured
        )

        # One buy may use the coin's whole budget (Max per coin %); the exchange's
        # minimum order is always allowed, as the entry is raised to it (with its
        # room for the spread and fees, ``minimum_entry_usd``)
        max_buy_usd = 0.0
        if side == "buy":
            max_buy_usd = position_sizing.coin_budget_usd(portfolio_value, MAX_COIN_PCT)
            if quantity * price > max_buy_usd:
                minimum = minimum_entry_usd or self._minimum_order_usd(symbol) or 0.0
                max_buy_usd = max(max_buy_usd, minimum)
        validation = self.risk_manager.validate_order(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_value": quantity * price,
            },
            portfolio_value,
            max_buy_usd,
        )
        if not validation["approved"]:
            print(f"{Fore.YELLOW}RISK BLOCK: {validation['reason']}{Style.RESET_ALL}")
            return False
        return True

    def _gate_or_refuse(self) -> Optional[OrderTarget]:
        """Run the gate; on refusal report it and return None (no order may follow)."""
        # Fail closed on the signal source too: an unknown strategy engine / id
        # (or unusable strategy settings), or a strategy or overlay not authorised for
        # this trader's mode (FDS-SR-001 section 5.3), means no orders at all.
        problem = read_strategy_settings(
            self._settings_source, mode=self._target.mode
        ).problem
        if problem:
            print(
                f"{Fore.RED}ORDER REFUSED: invalid strategy configuration: {problem}{Style.RESET_ALL}"
            )
            logger.error(f"Order refused: invalid strategy configuration: {problem}")
            return None
        try:
            return self._resolve_target_for_order()
        except TradingModeError as exc:
            print(f"{Fore.RED}ORDER REFUSED: {exc}{Style.RESET_ALL}")
            logger.error(f"Order refused by trading-mode gate: {exc}")
            return None

    def _place_gated_order(
        self,
        target: OrderTarget,
        side: str,
        symbol: str,
        asset_quantity: float,
        expected_price: Optional[float],
        avg_cost_basis: Optional[float],
        pnl_pct: Optional[float],
        tag: Optional[str],
        client_order_id: Optional[str] = None,
    ) -> Any:
        """
        Place one market order on ``target`` (obtained from the trading-mode
        gate) and do the accounting once it is filled. Returns a small order
        dict on a fill, None when the order was rejected, not filled,
        unconfirmed or only previewed. ``client_order_id`` makes the order
        idempotent on a broker that takes one.
        """
        if target.preview:
            last = self._previewed.get((symbol, side), 0.0)
            if time.time() - last < PREVIEW_REPEAT_SECONDS:
                return None
            self._previewed[(symbol, side)] = time.time()

        # An earlier order here whose outcome is unknown is never sent again under a
        # new id: it is sent again as it was, or nothing is sent yet (N5)
        intent = None
        if not target.preview:
            how, intent = self._unknown_order(target, symbol, side)
            if how == "wait":
                self._warn_throttled(
                    f"unknown-order:{symbol}|{side}",
                    f"No {side} order for {symbol} yet: the outcome of order "
                    f"{intent.get('client_order_id')} is unknown, and the holdings "
                    "may still show it.",
                    every=30.0,
                )
                return None
            if how == "resend":
                client_order_id = str(intent["client_order_id"])
                asset_quantity = float(intent["quantity"])
                intent["attempts"] = int(intent.get("attempts") or 1) + 1
                print(
                    f"  Sending order {client_order_id} ({symbol} {side}) again with "
                    "the same id: the last send's outcome is unknown."
                )
            else:
                client_order_id = client_order_id or str(uuid.uuid4())
                intent = {
                    "client_order_id": client_order_id,
                    "symbol": symbol,
                    "side": side,
                    "quantity": float(asset_quantity),
                    "tag": tag,
                    "account": target.key,
                    "first_ts": time.time(),
                    "attempts": 1,
                }
            intent["last_ts"] = time.time()
            if not self._keep_order_intent(symbol, side, intent):
                message = (
                    f"ORDER NOT SENT ({symbol} {side}): it could not be recorded "
                    f"first in {self.pnl_ledger_path}"
                )
                print(f"{Fore.RED}{message}{Style.RESET_ALL}")
                logger.error(message)
                return None

        # --- exact profit tracking snapshot (BEFORE placing order) ---
        buying_power_before = self._get_buying_power()

        try:
            result = target.place_order(
                symbol, side, asset_quantity, client_order_id=client_order_id
            )
        except Exception as exc:
            msg = self._describe_exchange_error(exc, "order placement", target.key)
            print(f"{Fore.RED}ORDER FAILED ({symbol} {side}): {msg}{Style.RESET_ALL}")
            logger.error(f"Order failed ({symbol} {side} via {target.key}): {msg}")
            if intent is not None:
                # it may have been made all the same: kept until the outcome is known
                later = (
                    "the next order here sends it again with the same id"
                    if self._resends_safely(target)
                    else f"no {side} order for {symbol} for "
                    f"{UNKNOWN_ORDER_WAIT_SECONDS} s"
                )
                print(
                    f"  Order {client_order_id} may have been made: its outcome is "
                    f"unknown, so {later}."
                )
            return None

        # the exchange answered: the outcome is known (made, refused or previewed)
        if intent is not None:
            self._drop_order_intent(symbol, side)

        order_id = result.order_id

        if str(result.status).lower().strip() == "preview":
            # nothing was placed: the log says what would have been, nothing is recorded
            print(
                f"{Fore.CYAN}ORDER PREVIEW ({symbol} {side}, {tag or 'order'}): "
                f"{result.reason}{Style.RESET_ALL}"
            )
            logger.info(
                f"Order preview ({symbol} {side} via {target.key}): {result.reason}"
            )
            return None

        if str(result.status).lower().strip() == "rejected" and result.reason:
            # e.g. PRICE_UNAVAILABLE: nothing was filled, nothing is pending; the
            # next cycle simply tries again. An order too small for the exchange
            # (BELOW_MINIMUM) is not a missing price.
            if not str(result.reason).startswith(BELOW_MINIMUM):
                self._note_price_event("unavailable")
            else:
                key = f"below-minimum:{symbol}|{side}"
                if time.time() - self._warn_ts.get(key, 0.0) < (
                    BELOW_MINIMUM_REPORT_SECONDS
                ):
                    return None  # already reported
                self._warn_ts[key] = time.time()
            print(
                f"{Fore.YELLOW}ORDER REJECTED ({symbol} {side}): {result.reason}{Style.RESET_ALL}"
            )
            logger.warning(
                f"Order rejected ({symbol} {side} via {target.key}): {result.reason}; "
                "will retry next cycle"
            )
            return None

        if order_id and self._trade_history_has_order_id(order_id):
            # The broker answered with an order already in the books (a repeated
            # client order id gets the order it already made): one exchange fill is
            # recorded once, never again.
            self._clear_pending(order_id)
            print(f"  Order {order_id} ({symbol} {side}) is already recorded.")
            logger.warning(
                f"Order {order_id} ({symbol} {side} via {target.key}) is already in "
                "the trade history; not recorded again"
            )
            return None

        # Persist the pre-order buying power so restarts can reconcile precisely
        try:
            if order_id:
                self._pnl_ledger.setdefault("pending_orders", {})
                self._pnl_ledger["pending_orders"][order_id] = {
                    "symbol": symbol,
                    "side": side,
                    "buying_power_before": float(buying_power_before),
                    "avg_cost_basis": (
                        float(avg_cost_basis) if avg_cost_basis is not None else None
                    ),
                    "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                    "tag": tag,
                    "created_ts": time.time(),
                }
                self._save_pnl_ledger()
        except Exception:
            pass

        # Wait until the order is complete, then account from what actually filled
        final = self._wait_for_order_terminal(target, order_id, initial=result)
        if final is None:
            # Left in pending_orders; _reconcile_pending_orders() settles it on restart.
            logger.warning(f"Order {order_id} ({symbol} {side}) not confirmed in time")
            print(f"  Order {order_id} not confirmed yet; will reconcile on restart.")
            return None

        if str(final.status).lower().strip() != "filled":
            # Not filled -> clear pending and do not record a trade
            self._clear_pending(order_id)
            return None

        filled_qty, fill_price = self._extract_fill_from_order(final)
        if filled_qty <= 0.0:
            filled_qty = float(asset_quantity)
        if fill_price is None and expected_price is not None:
            fill_price = float(expected_price)

        # If we managed to get a fill price, update the displayed PnL% too
        if side == "sell" and avg_cost_basis is not None and fill_price is not None:
            try:
                acb = float(avg_cost_basis)
                if acb > 0:
                    pnl_pct = ((float(fill_price) - acb) / acb) * 100.0
            except Exception:
                pass

        if final.reason:
            print(f"  Order {order_id} ({symbol} {side}): {final.reason}")

        # --- exact profit tracking snapshot (AFTER the order is complete) ---
        buying_power_after = self._get_buying_power()
        # the exchange's own value and fee when it reports them, else the change in
        # buying power
        buying_power_delta = self._order_cash_change(final, side)
        if buying_power_delta is None:
            buying_power_delta = float(buying_power_after) - float(buying_power_before)

        self._record_trade(
            side=side,
            symbol=symbol,
            qty=float(filled_qty),
            price=float(fill_price) if fill_price is not None else None,
            avg_cost_basis=(
                float(avg_cost_basis) if avg_cost_basis is not None else None
            ),
            pnl_pct=float(pnl_pct) if pnl_pct is not None else None,
            tag=tag,
            order_id=order_id,
            fees_usd=final.fee,
            buying_power_before=buying_power_before,
            buying_power_after=buying_power_after,
            buying_power_delta=buying_power_delta,
            closes_position=not getattr(final, "partial", False),
            fee_detail=self._fee_detail(final),
            **self._provenance(final, target),
        )
        self._clear_pending(order_id)

        return {
            "id": order_id,
            "state": "filled",
            "symbol": symbol,
            "side": side,
            "quantity": float(filled_qty),
            "price": float(fill_price) if fill_price is not None else None,
            "mode": target.key,
            # the order stopped part-way: the rest of the position is still held
            "partial": bool(getattr(final, "partial", False)),
        }

    @staticmethod
    def _fee_detail(order: OrderResult) -> dict:
        """Ledger columns for how a fill's fee was worked out, where the exchange (or
        the paper account) says: its currency, the rate charged (a fraction of the
        filled value), "maker" or "taker", and whose rates and from where. A fee
        charged in another asset than the quote currency (BNB on Binance) is in
        ``other_fees``, asset -> amount as the exchange gave it."""
        detail = {
            "fee_currency": getattr(order, "fee_currency", ""),
            "fee_rate": getattr(order, "fee_rate", None),
            "fee_type": getattr(order, "fee_type", ""),
            "fee_exchange": getattr(order, "fee_exchange", ""),
            "fee_source": getattr(order, "fee_source", ""),
        }
        detail = {
            k: v
            for k, v in detail.items()
            if isinstance(v, (str, int, float)) and v != ""
        }
        other_fees = getattr(order, "other_fees", None)
        if isinstance(other_fees, dict) and other_fees:
            detail["other_fees"] = dict(other_fees)
        return detail

    @staticmethod
    def _provenance(order: OrderResult, target: OrderTarget) -> dict:
        """Ledger columns for where a paper fill's price came from ({} for live)."""
        if target.is_live:
            return {}
        return {
            "price_source": order.price_source or "unknown",
            "quote_ts": order.quote_ts,
            "age_s": order.age_s,
            # the exchange whose quote priced the fill (FDS-MX-001 phase B)
            "price_exchange": getattr(order, "price_exchange", "") or "",
        }

    def _catalogue_exit_quantity(self, symbol: str, holding_qty: float) -> float:
        """Quantity a strategy exit may sell: what this trader's ledger says it
        bought, capped by the exchange balance (never the user's other holdings)."""
        try:
            pos = (self._pnl_ledger.get("open_positions") or {}).get(symbol) or {}
            ledger_qty = float(pos.get("qty", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            return 0.0
        return max(0.0, min(float(holding_qty), ledger_qty))

    def _report_position_stops(
        self, symbol: str, pos, decision, positions: dict
    ) -> None:
        """Per-cycle telemetry for an open strategy position: effective stop, which
        overlay owns it, and each overlay's state (console + trader_status.json)."""
        overlays = [
            o["id"] for o in read_strategy_settings(self._settings_source).overlays
        ]
        stop = (
            decision.stop_price if decision.stop_price is not None else pos.current_stop
        )
        owner = decision.stop_owner or pos.stop_owner
        entry = positions.get(symbol)
        if entry is not None:
            entry.update(
                overlays=overlays,
                effective_stop=stop,
                stop_owner=owner,
                overlay_state=pos.overlay_state,
            )
            if stop:
                entry["trail_line"] = float(
                    stop
                )  # the hub charts this as the sell line
                entry["trail_active"] = True
        stop_txt = self._fmt_price(stop) if stop else "none"
        print(
            f"  Stop {symbol}: {stop_txt} (owner {owner or 'none'}) | overlays: "
            f"{', '.join(overlays) or 'none'} | state: {json.dumps(pos.overlay_state, default=str)}"
        )

    def _signals_status(self) -> dict:
        # with the trading mode, as the order gate reads them: an entry not cleared
        # for this mode is blocked here too
        s = read_strategy_settings(self._settings_source, mode=self._target.mode)
        # settings problems, or a strategy whose model the engine cannot use
        blocked = s.problem or (
            self.signal_engine.block_reason() if s.is_catalogue else None
        )
        return {
            "engine": s.engine,
            "strategy_id": s.active_id if s.is_catalogue else None,
            "timeframe": s.timeframe if s.is_catalogue else None,
            "overlays": [o["id"] for o in s.overlays] if s.is_catalogue else [],
            "blocked": blocked,
            "note": "SIGNALS: BLOCKED" if blocked else s.note,
            "last_decisions": {
                base: {
                    "action": d.action.value,
                    "reason": d.reason,
                    "bar_time": str(d.bar_time),
                    "stop": d.stop_price,
                    # whose bars decided it (N15)
                    "exchange": getattr(self.signal_engine, "last_exchanges", {}).get(
                        base
                    ),
                }
                for base, d in self.signal_engine.last_decisions.items()
            },
        }

    def _clear_pending(self, order_id: str) -> None:
        try:
            if order_id:
                self._pnl_ledger.get("pending_orders", {}).pop(order_id, None)
                self._save_pnl_ledger()
        except Exception:
            pass

    def _minimum_order_usd(self, symbol: str) -> Optional[float]:
        """The smallest order the exchange takes for ``symbol``, or None when no
        exchange states one. Live: the broker the order goes to. Paper: the exchanges
        in Settings, primary first, then the others."""
        try:
            if self._settings.is_live:
                minimum = self._target.exchange.min_order_usd(symbol)
            else:
                minimum = _market_exchanges().min_order_usd(symbol)
        except Exception:
            return None
        return usable_minimum(minimum)

    def _trading_fees(self, symbol: str) -> Optional[TradingFees]:
        """The maker and taker fee rates an order on ``symbol`` pays where this trader's
        orders go: the broker's when trading live; in paper trading, the rates the
        paper account charges (the exchanges in Settings, primary first). None when
        they are not known."""
        try:
            return usable_fees(self._target.exchange.trading_fees(symbol))
        except Exception:
            return None

    def _entry_size(
        self, symbol: str, account_value: float, ask: Any, bid: Any
    ) -> tuple:
        """(the amount for a new trade in ``symbol``, the smallest entry the exchange's
        minimum order needs, or None when it states none). Start allocation % of the
        account; below the minimum order it is raised to the minimum plus the spread
        of the coin's quote (``ask`` vs ``bid``), a market buy's and a market sell's
        fees and the margin in Settings, so the new position is still worth the
        minimum at the bid after its fees."""
        minimum = self._minimum_order_usd(symbol)
        fees = self._trading_fees(symbol) if minimum else None
        terms = {
            "minimum_usd": minimum,
            "spread": position_sizing.quote_spread(ask, bid),
            "round_trip_fee": 2.0 * fees.taker if fees is not None else 0.0,
            "margin_pct": MIN_ORDER_MARGIN_PCT,
        }
        return (
            position_sizing.entry_usd(account_value, START_ALLOC_PCT, **terms),
            position_sizing.minimum_entry_usd(**terms),
        )

    def _is_dust(self, full_symbol: str, quantity: Any, sell_price: Any) -> bool:
        """A holding worth less than the smallest order the exchange takes (what a
        sell rounded down to the exchange's step can leave) cannot be sold, so it
        is not a position: it does not stop a new entry, and no exit or DCA is
        tried on it. An open trade is never dust (a coin bought at the ask can be
        worth a little less at the bid): only what a sell left, or a holding the
        ledger has no trade for. False when the price or the minimum is not known."""
        if self._open_trade(str(full_symbol).upper().split("-")[0].strip()):
            return False
        try:
            value = float(quantity) * float(sell_price)
        except (TypeError, ValueError):
            return False
        if value <= 0.0:
            return False
        read = self._dust_minimums.get(full_symbol)
        if read is None or time.time() - read[0] > DUST_MINIMUM_SECONDS:
            read = (time.time(), self._minimum_order_usd(full_symbol))
            self._dust_minimums[full_symbol] = read
        minimum = read[1]
        return bool(minimum) and value < float(minimum)

    def _held_symbols(self, holdings: Any, sell_prices: Dict[str, Any]) -> list:
        """``<COIN>-USD`` for each holding that is a position (dust left out)."""
        held = []
        for holding in (
            holdings.get("results", []) if isinstance(holdings, dict) else []
        ):
            full_symbol = f"{holding['asset_code']}-USD"
            if not self._is_dust(
                full_symbol,
                holding.get("total_quantity", 0.0),
                sell_prices.get(full_symbol, 0.0),
            ):
                held.append(full_symbol)
        return held

    def place_buy_order(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        symbol: str,
        amount_in_usd: float,
        avg_cost_basis: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        tag: Optional[str] = None,
        minimum_entry_usd: Optional[float] = None,
    ) -> Any:
        """``minimum_entry_usd``: an entry raised to the exchange's minimum order is
        allowed up to that amount whatever the coin's budget (``_entry_size``)."""
        # Gate first: a refused order must not cost a single price lookup.
        target = self._gate_or_refuse()
        if target is None:
            return None

        # Fetch the current price of the asset (for sizing only)
        current_buy_prices, _, _ = self.get_price([symbol])
        current_price = current_buy_prices.get(symbol)
        if not current_price:
            print(f"  No price available for {symbol}; skipping buy.")
            return None
        asset_quantity = round(amount_in_usd / current_price, 8)

        # --- Risk Management Checks ---
        if not self._risk_check(
            symbol, side, asset_quantity, current_price, minimum_entry_usd
        ):
            return None

        return self._place_gated_order(
            target,
            side=side,
            symbol=symbol,
            asset_quantity=asset_quantity,
            expected_price=current_price,
            avg_cost_basis=avg_cost_basis,
            pnl_pct=pnl_pct,
            tag=tag,
            client_order_id=client_order_id,
        )

    def place_sell_order(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        symbol: str,
        asset_quantity: float,
        expected_price: Optional[float] = None,
        avg_cost_basis: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> Any:
        # Gate first: a refused order must not cost a single price lookup.
        target = self._gate_or_refuse()
        if target is None:
            return None

        # Get current price for validation
        _, current_sell_prices, _ = self.get_price([symbol])
        current_price = current_sell_prices.get(symbol)
        if not current_price:
            print(f"  No price available for {symbol}; skipping sell.")
            return None

        # --- Risk Management Checks ---
        if not self._risk_check(symbol, side, asset_quantity, current_price):
            return None

        return self._place_gated_order(
            target,
            side=side,
            symbol=symbol,
            asset_quantity=asset_quantity,
            expected_price=(
                float(expected_price) if expected_price is not None else current_price
            ),
            avg_cost_basis=avg_cost_basis,
            pnl_pct=pnl_pct,
            tag=tag,
            client_order_id=client_order_id,
        )

    def manage_trades(self):
        trades_made = False  # Flag to track if any trade was made in this iteration

        # Hot-reload coins list + paths + trade params from GUI settings while running
        try:
            _refresh_paths_and_symbols()
            self.path_map = dict(base_paths)
            self.dca_levels = list(DCA_LEVELS)
            self.max_dca_buys_per_24h = int(MAX_DCA_BUYS_PER_24H)

            # Trailing PM settings (hot-reload)
            old_sig = getattr(self, "_last_trailing_settings_sig", None)

            new_gap = float(TRAILING_GAP_PCT)
            new_pm0 = float(PM_START_PCT_NO_DCA)
            new_pm1 = float(PM_START_PCT_WITH_DCA)

            self.trailing_gap_pct = new_gap
            self.pm_start_pct_no_dca = new_pm0
            self.pm_start_pct_with_dca = new_pm1

            new_sig = (float(new_gap), float(new_pm0), float(new_pm1))

            # If trailing settings changed, reset ALL trailing PM state so:
            # - the line updates immediately
            # - peak/armed/was_above are cleared
            if (old_sig is not None) and (new_sig != old_sig):
                self.trailing_pm = {}

            self._last_trailing_settings_sig = new_sig
        except Exception:
            pass

        # The trader is pinned to the mode/broker it started in. If the setting
        # changed underneath it, stop touching the exchange until it is restarted.
        if not self._trading_mode_unchanged():
            # a settings file that cannot be read reads as paper: say that instead
            unreadable = settings_problem(self._settings_source)
            if unreadable:
                print(
                    f"{Fore.YELLOW}No orders will be placed: {unreadable}."
                    f"{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.YELLOW}Trading mode changed since start-up (started as "
                    f"'{self._target.key}'). No orders will be placed; restart the "
                    f"trader to apply it.{Style.RESET_ALL}"
                )
            time.sleep(5)
            return

        if time.time() - self._last_price_summary_ts >= 3600.0:
            self._log_price_summary()

        # Signal source for this tick. "catalogue": the rule-based strategy (+ overlays)
        # decides entries and exits and the legacy DCA / trailing-PM logic is off.
        # "legacy_neural": the old neural-signal logic (untrained mock - see
        # docs/technical/ARCHITECTURE.md). An invalid configuration trades nothing.
        strategy_cfg = read_strategy_settings(
            self._settings_source, mode=self._target.mode
        )
        self._catalogue_mode = strategy_cfg.is_catalogue and not strategy_cfg.problem
        if strategy_cfg.problem:
            self._warn_throttled(
                "strategy-config",
                f"Strategy configuration invalid; no orders will be placed: {strategy_cfg.problem}",
                every=300.0,
            )
        catalogue_mode = self._catalogue_mode

        # One balance read for the pass: the account (buying power), the holdings
        # and every balance with funds on hold (what the drawdown stop measures)
        account, holdings, totals = self._read_balances()
        # Fetch trading pairs
        trading_pairs = self.get_trading_pairs()

        # Use the stored cost_basis instead of recalculating
        cost_basis = self.cost_basis
        # Fetch current prices
        symbols = [
            holding["asset_code"] + "-USD" for holding in holdings.get("results", [])
        ]

        # ALSO fetch prices for tracked coins even if not currently held (so GUI can show bid/ask lines)
        for s in crypto_symbols:
            full = f"{s}-USD"
            if full not in symbols:
                symbols.append(full)
        # ...and every other asset in the balances (one held for an order too)
        for code in totals or {}:
            full = f"{code}-USD"
            if code not in CASH_ASSETS and full not in symbols:
                symbols.append(full)

        current_buy_prices, current_sell_prices, valid_symbols = self.get_price(symbols)
        # when this pass's quotes were read: the entry assessment's record gives their
        # age (signal_fusion.live); nothing decides on it
        self._quotes_at = time.time()

        # Calculate total account value (robust: never drop a held coin to $0 on transient API misses)
        snapshot_ok = True

        # buying power
        try:
            if isinstance(account, dict) and "error" in account:
                raise ValueError(
                    account["error"]
                )  # transient/unsupported: not a $0 balance
            buying_power = float(account.get("buying_power", 0))
        except Exception:
            buying_power = 0.0
            snapshot_ok = False

        # holdings list (treat missing/invalid holdings payload as transient error)
        try:
            holdings_list = (
                holdings.get("results", None) if isinstance(holdings, dict) else None
            )
            if not isinstance(holdings_list, list):
                holdings_list = []
                snapshot_ok = False
        except Exception:
            holdings_list = []
            snapshot_ok = False

        holdings_buy_value = 0.0
        holdings_sell_value = 0.0
        # held assets left out of the account value: (asset, quantity, why), and
        # those with no price yet in this run (they hold the value back)
        not_counted = []
        not_yet_priced = []
        now = time.time()

        for holding in holdings_list:
            try:
                asset = holding.get("asset_code")
                if asset == "USDC":
                    continue

                qty = float(holding.get("total_quantity", 0.0))
                if qty <= 0.0:
                    continue

                sym = f"{asset}-USD"
                bp, sp, why = self._held_price(
                    sym, current_buy_prices, current_sell_prices, now
                )

                # A held asset with no usable price is left out of the value and
                # listed; one with no price yet in this run holds the value back
                if why == NOT_YET_PRICED:
                    not_yet_priced.append(str(asset))
                    snapshot_ok = False
                    continue
                if why:
                    not_counted.append((str(asset), qty, why))
                    continue

                holdings_buy_value += qty * bp
                holdings_sell_value += qty * sp
            except Exception:
                snapshot_ok = False
                continue

        # The drawdown stop's own measure: every balance, funds on hold included, the
        # cash assets at $1 and every other asset at its bid. Entries are still sized
        # on the account value. A pass that cannot read it forms no value.
        halt_equity, halt_not_counted = None, None
        if totals is None:
            snapshot_ok = False
        else:
            halt_equity, halt_not_counted, not_yet = self._halt_equity(
                totals, current_buy_prices, current_sell_prices, now
            )
            for code in not_yet:
                snapshot_ok = False
                if code not in not_yet_priced:
                    not_yet_priced.append(code)

        total_account_value = buying_power + holdings_sell_value
        in_use = (
            (holdings_sell_value / total_account_value) * 100
            if total_account_value > 0
            else 0.0
        )

        # If this tick is incomplete, fall back to last known-good snapshot so the GUI chart never gets a bogus dip.
        value_formed = snapshot_ok and total_account_value > 0.0
        if not value_formed:
            if not_yet_priced:
                self._no_value_why = f"no price yet for {', '.join(not_yet_priced)}"
            elif not snapshot_ok:
                self._no_value_why = "the balances could not be read"
            else:
                self._no_value_why = "nothing in the account has a USD value"
            # until this run forms a value, buys wait: none before a drawdown check
            self._no_value_yet = not getattr(self, "_value_formed", False)
            last = getattr(self, "_last_good_account_snapshot", None) or {}
            if last.get("total_account_value") is not None:
                total_account_value = float(last["total_account_value"])
                buying_power = float(last.get("buying_power", buying_power or 0.0))
                holdings_sell_value = float(
                    last.get("holdings_sell_value", holdings_sell_value or 0.0)
                )
                holdings_buy_value = float(
                    last.get("holdings_buy_value", holdings_buy_value or 0.0)
                )
                in_use = float(last.get("percent_in_trade", in_use or 0.0))
        else:
            # A peak saved on the account value is scaled to the stop's measure once,
            # here; until then the stop measures the account value, as the peak was
            measured = None
            if self.risk_manager.measure_all_balances(halt_equity, total_account_value):
                # a deposit never reduces the drawdown
                measured = self._settled_value(
                    totals, current_buy_prices, current_sell_prices, halt_equity, now
                )
            # Save last complete snapshot
            self._last_good_account_snapshot = {
                "total_account_value": float(total_account_value),
                "buying_power": float(buying_power),
                "holdings_sell_value": float(holdings_sell_value),
                "holdings_buy_value": float(holdings_buy_value),
                "percent_in_trade": float(in_use),
                "halt_equity": measured,
            }
            self._account_value_ts = now
            self._value_formed = True
            self._no_value_yet = False
            not_counted = halt_not_counted
        # what the stop's value leaves out, and whether buys wait, for Settings > Risk
        buys_waiting = self._buys_wait_reason()
        self.risk_manager.report(not_counted if value_formed else None, buys_waiting)

        os.system("cls" if os.name == "nt" else "clear")
        print("\n--- Account Summary ---")
        print(f"Total Account Value: ${total_account_value:.2f}")
        print(f"Holdings Value: ${holdings_sell_value:.2f}")
        print(f"Percent In Trade: {in_use:.2f}%")
        if value_formed and not_counted:
            left_out = ", ".join(f"{a} {q:g} ({why})" for a, q, why in not_counted)
            print(
                f"{Fore.YELLOW}Not counted in the account value: "
                f"{left_out}{Style.RESET_ALL}"
            )
        if buys_waiting:
            print(
                f"{Fore.YELLOW}BUYS WAITING: {buys_waiting}. Exits, stops and the "
                f"trailing margin still sell.{Style.RESET_ALL}"
            )
        # The drawdown is checked on the value this pass formed, before anything is
        # bought (run() does not check it again at the next cycle's start)
        if value_formed:
            self._check_drawdown(self._get_halt_value())
            self._last_good_account_snapshot["checked"] = True
        print(
            f"Trailing PM: start +{self.pm_start_pct_no_dca:.2f}% (no DCA) / +{self.pm_start_pct_with_dca:.2f}% (with DCA) "
            f"| gap {self.trailing_gap_pct:.2f}%"
        )
        print("\n--- Current Trades ---")

        positions = {}
        for holding in holdings.get("results", []):
            symbol = holding["asset_code"]
            full_symbol = f"{symbol}-USD"

            if full_symbol not in valid_symbols or symbol == "USDC":
                continue

            quantity = float(holding["total_quantity"])
            current_buy_price = current_buy_prices.get(full_symbol, 0)
            current_sell_price = current_sell_prices.get(full_symbol, 0)
            avg_cost_basis = cost_basis.get(symbol, 0)

            if avg_cost_basis > 0:
                gain_loss_percentage_buy = (
                    (current_buy_price - avg_cost_basis) / avg_cost_basis
                ) * 100
                gain_loss_percentage_sell = (
                    (current_sell_price - avg_cost_basis) / avg_cost_basis
                ) * 100
            else:
                gain_loss_percentage_buy = 0
                gain_loss_percentage_sell = 0
                print(
                    f"  Warning: Average Cost Basis is 0 for {symbol}, Gain/Loss calculation skipped."
                )

            value = quantity * current_sell_price
            triggered_levels_count = len(self.dca_levels_triggered.get(symbol, []))
            triggered_levels = triggered_levels_count  # Number of DCA levels triggered

            # Determine the next DCA trigger for this coin (hardcoded % and optional neural level)
            next_stage = triggered_levels_count  # stage 0 == first DCA after entry (trade starts at neural level 3)

            # Hardcoded % for this stage (repeat -50% after we reach it)
            hard_next = (
                self.dca_levels[next_stage]
                if next_stage < len(self.dca_levels)
                else self.dca_levels[-1]
            )

            # Neural DCA applies to the levels BELOW the trade-start level.
            # Example: trade_start_level=3 => stages 0..3 map to N4..N7 (4 total).
            start_level = max(1, min(int(TRADE_START_LEVEL or 3), 7))
            neural_dca_max = max(0, 7 - start_level)

            if next_stage < neural_dca_max:
                neural_next = start_level + 1 + next_stage
                next_dca_display = f"{hard_next:.2f}% / N{neural_next}"
            else:
                next_dca_display = f"{hard_next:.2f}%"

            # --- DCA DISPLAY LINE (show whichever trigger will be hit first: higher of NEURAL line vs HARD line) ---
            # Hardcoded gives an actual price line: cost_basis * (1 + hard_next%).
            # Neural gives an actual price line from low_bound_prices.html (N1..N7).
            dca_line_source = "HARD"
            dca_line_price = 0.0
            dca_line_pct = 0.0

            if avg_cost_basis > 0:
                # Hardcoded trigger line price
                hard_line_price = avg_cost_basis * (1.0 + (hard_next / 100.0))

                # Default to hardcoded unless neural line is higher (hit first)
                dca_line_price = hard_line_price

                if next_stage < neural_dca_max:
                    neural_level_needed_disp = start_level + 1 + next_stage
                    neural_levels = self._read_long_price_levels(
                        symbol
                    )  # highest->lowest == N1..N7

                    neural_line_price = 0.0
                    if len(neural_levels) >= neural_level_needed_disp:
                        neural_line_price = float(
                            neural_levels[neural_level_needed_disp - 1]
                        )

                    # Whichever is higher will be hit first as price drops
                    if neural_line_price > dca_line_price:
                        dca_line_price = neural_line_price
                        dca_line_source = f"NEURAL N{neural_level_needed_disp}"

                # PnL% shown alongside DCA is the normal buy-side PnL%
                # (same calculation as GUI "Buy Price PnL": current buy/ask vs avg cost basis)
                dca_line_pct = gain_loss_percentage_buy

            dca_line_price_disp = (
                self._fmt_price(dca_line_price) if avg_cost_basis > 0 else "N/A"
            )

            # Set color code:
            # - DCA is green if we're above the chosen DCA line, red if we're below it
            # - SELL stays based on profit vs cost basis (your original behavior)
            if dca_line_pct >= 0:
                color = Fore.GREEN
            else:
                color = Fore.RED

            if gain_loss_percentage_sell >= 0:
                color2 = Fore.GREEN
            else:
                color2 = Fore.RED

            # --- Trailing PM display (per-coin, isolated) ---
            # Display uses current state if present; otherwise shows the base PM start line.
            trail_status = "N/A"
            pm_start_pct_disp = 0.0
            base_pm_line_disp = 0.0
            trail_line_disp = 0.0
            trail_peak_disp = 0.0
            above_disp = False
            dist_to_trail_pct = 0.0

            if avg_cost_basis > 0:
                pm_start_pct_disp = (
                    self.pm_start_pct_no_dca
                    if int(triggered_levels) == 0
                    else self.pm_start_pct_with_dca
                )
                base_pm_line_disp = avg_cost_basis * (1.0 + (pm_start_pct_disp / 100.0))

                state = self.trailing_pm.get(symbol)
                if state is None:
                    trail_line_disp = base_pm_line_disp
                    trail_peak_disp = 0.0
                    active_disp = False
                else:
                    trail_line_disp = float(state.get("line", base_pm_line_disp))
                    trail_peak_disp = float(state.get("peak", 0.0))
                    active_disp = bool(state.get("active", False))

                above_disp = current_sell_price >= trail_line_disp
                # If we're already above the line, trailing is effectively "on/armed" (even if active flips this tick)
                trail_status = "ON" if (active_disp or above_disp) else "OFF"

                if trail_line_disp > 0:
                    dist_to_trail_pct = (
                        (current_sell_price - trail_line_disp) / trail_line_disp
                    ) * 100.0
            with open(
                os.path.join(self.data_dir, symbol + "_current_price.txt"), "w+"
            ) as file:
                file.write(str(current_buy_price))
            positions[symbol] = {
                "quantity": quantity,
                "avg_cost_basis": avg_cost_basis,
                "current_buy_price": current_buy_price,
                "current_sell_price": current_sell_price,
                "gain_loss_pct_buy": gain_loss_percentage_buy,
                "gain_loss_pct_sell": gain_loss_percentage_sell,
                "value_usd": value,
                "dca_triggered_stages": int(triggered_levels_count),
                "next_dca_display": next_dca_display,
                "dca_line_price": float(dca_line_price) if dca_line_price else 0.0,
                "dca_line_source": dca_line_source,
                "dca_line_pct": float(dca_line_pct) if dca_line_pct else 0.0,
                "trail_active": True if (trail_status == "ON") else False,
                "trail_line": float(trail_line_disp) if trail_line_disp else 0.0,
                "trail_peak": float(trail_peak_disp) if trail_peak_disp else 0.0,
                "dist_to_trail_pct": (
                    float(dist_to_trail_pct) if dist_to_trail_pct else 0.0
                ),
            }

            print(
                f"\nSymbol: {symbol}"
                f"  |  DCA: {color}{dca_line_pct:+.2f}%{Style.RESET_ALL} @ {self._fmt_price(current_buy_price)} (Line: {dca_line_price_disp} {dca_line_source} | Next: {next_dca_display})"
                f"  |  Gain/Loss SELL: {color2}{gain_loss_percentage_sell:.2f}%{Style.RESET_ALL} @ {self._fmt_price(current_sell_price)}"
                f"  |  DCA Levels Triggered: {triggered_levels}"
                f"  |  Trade Value: ${value:.2f}"
            )

            if avg_cost_basis > 0:
                print(
                    f"  Trailing Profit Margin"
                    f"  |  Line: {self._fmt_price(trail_line_disp)}"
                    f"  |  Above: {above_disp}"
                )
            else:
                print("  PM/Trail: N/A (avg_cost_basis is 0)")

            # A remainder too small to sell is shown above but left alone: no exit
            # or DCA on it (the exchange would refuse the order every cycle).
            if self._is_dust(full_symbol, quantity, current_sell_price):
                self._warn_throttled(
                    f"dust:{symbol}",
                    f"{quantity:g} {symbol} is worth less than the smallest order the "
                    "exchange takes; it is left alone and does not stop a new trade.",
                    every=3600.0,
                )
                continue

            # --- Catalogue engine: the strategy (+ overlays) own the exit ---------------
            # Legacy trailing-PM sells and DCA buys below are skipped in this mode.
            # Only positions this trader opened (they have a ledger cost basis) are
            # managed, and only the quantity the ledger says it bought is sold.
            if catalogue_mode:
                exit_qty = self._catalogue_exit_quantity(symbol, quantity)
                if avg_cost_basis > 0 and exit_qty > 0:
                    pos = self.signal_engine.ensure_position(symbol, avg_cost_basis)
                    decision = self._decide(symbol, pos)
                    if decision is not None:
                        self._report_position_stops(symbol, pos, decision, positions)
                    if decision is not None and decision.action is Action.EXIT_LONG:
                        print(
                            f"  {decision.strategy_id} EXIT for {symbol}: {decision.reason}"
                        )
                        response = self.place_sell_order(
                            str(uuid.uuid4()),
                            "sell",
                            "market",
                            full_symbol,
                            exit_qty,
                            expected_price=current_sell_price,
                            avg_cost_basis=avg_cost_basis,
                            pnl_pct=gain_loss_percentage_sell,
                            tag=f"EXIT:{decision.exit_rule or 'strategy'}",
                        )
                        if (
                            response
                            and isinstance(response, dict)
                            and "errors" not in response
                        ):
                            trades_made = True
                            if response.get("partial"):
                                # Part of the position is still held: its strategy
                                # position and stops stay, so the exit sells the rest.
                                print(
                                    f"  Sold {response.get('quantity')} of {exit_qty} "
                                    f"{symbol}; the rest is still held."
                                )
                            else:
                                # the cooldown counts from the bar the sale filled
                                # in, as the backtester counts it
                                self.signal_engine.record_exit(
                                    symbol,
                                    response.get("price") or current_sell_price,
                                    self.signal_engine.fill_bar(decision.bar_time),
                                )
                                self.trailing_pm.pop(symbol, None)
                                self._reset_dca_window_for_trade(symbol, sold=True)
                                print(f"  Successfully sold {exit_qty} {symbol}.")
                            time.sleep(5)
                            holdings = self.get_holdings()
                elif avg_cost_basis <= 0:
                    self._warn_throttled(
                        f"unmanaged:{symbol}",
                        f"{symbol} is held but was not opened by this trader (no ledger cost "
                        "basis); the strategy will not sell it.",
                        every=3600.0,
                    )
                continue

            # --- Trailing profit margin (0.5% trail gap) ---
            # PM "start line" is the normal 5% / 2.5% line (depending on DCA levels hit).
            # Trailing activates once price is ABOVE the PM start line, then line follows peaks up
            # by 0.5%. Forced sell happens ONLY when price goes from ABOVE the trailing line to BELOW it.
            if avg_cost_basis > 0:
                pm_start_pct = (
                    self.pm_start_pct_no_dca
                    if int(triggered_levels) == 0
                    else self.pm_start_pct_with_dca
                )
                base_pm_line = avg_cost_basis * (1.0 + (pm_start_pct / 100.0))
                trail_gap = self.trailing_gap_pct / 100.0  # 0.5% => 0.005

                # If trailing settings changed since this coin's state was created, reset it.
                settings_sig = (
                    float(self.trailing_gap_pct),
                    float(self.pm_start_pct_no_dca),
                    float(self.pm_start_pct_with_dca),
                )

                state = self.trailing_pm.get(symbol)
                if (state is None) or (state.get("settings_sig") != settings_sig):
                    state = {
                        "active": False,
                        "line": base_pm_line,
                        "peak": 0.0,
                        "was_above": False,
                        "settings_sig": settings_sig,
                    }
                    self.trailing_pm[symbol] = state
                else:
                    # Keep signature up to date
                    state["settings_sig"] = settings_sig

                    # IMPORTANT:
                    # If trailing hasn't activated yet, this is just the PM line.
                    # It MUST track the current avg_cost_basis (so it can move DOWN after each DCA).
                    if not state.get("active", False):
                        state["line"] = base_pm_line
                    else:
                        # Once trailing is active, the line should never be below the base PM start line.
                        if state.get("line", 0.0) < base_pm_line:
                            state["line"] = base_pm_line

                # Use SELL price because that's what you actually get when you market sell
                above_now = current_sell_price >= state["line"]

                # Activate trailing once we first get above the base PM line
                if (not state["active"]) and above_now:
                    state["active"] = True
                    state["peak"] = current_sell_price

                # If active, update peak and move trailing line up behind it
                if state["active"]:
                    if current_sell_price > state["peak"]:
                        state["peak"] = current_sell_price

                    new_line = state["peak"] * (1.0 - trail_gap)
                    if new_line < base_pm_line:
                        new_line = base_pm_line
                    if new_line > state["line"]:
                        state["line"] = new_line

                    # Forced sell on cross from ABOVE -> BELOW trailing line
                    if state["was_above"] and (current_sell_price < state["line"]):
                        print(
                            f"  Trailing PM hit for {symbol}. "
                            f"Sell price {current_sell_price:.8f} fell below trailing line {state['line']:.8f}."
                        )
                        response = self.place_sell_order(
                            str(uuid.uuid4()),
                            "sell",
                            "market",
                            full_symbol,
                            quantity,
                            expected_price=current_sell_price,
                            avg_cost_basis=avg_cost_basis,
                            pnl_pct=gain_loss_percentage_sell,
                            tag="TRAIL_SELL",
                        )

                        if (
                            response
                            and isinstance(response, dict)
                            and "errors" not in response
                        ):
                            trades_made = True
                            if response.get("partial"):
                                # Part of the position is still held: the trailing
                                # line (still crossed) and the DCA window stay, so the
                                # next cycle sells the rest.
                                print(
                                    f"  Sold {response.get('quantity')} of {quantity} "
                                    f"{symbol}; the rest is still held."
                                )
                            else:
                                self.trailing_pm.pop(
                                    symbol, None
                                )  # clear per-coin trailing state on exit

                                # Trade ended -> reset rolling 24h DCA window for this coin
                                self._reset_dca_window_for_trade(symbol, sold=True)

                                print(f"  Successfully sold {quantity} {symbol}.")
                            time.sleep(5)
                            holdings = self.get_holdings()
                            continue

                # Save this tick’s position relative to the line (needed for “above -> below” detection)
                state["was_above"] = above_now

            # DCA (NEURAL or hardcoded %, whichever hits first for the current stage)
            # Trade starts at neural level 3 => trader is at stage 0.
            # Neural-driven DCA stages (max 4):
            #   stage 0 => neural 4 OR -2.5%
            #   stage 1 => neural 5 OR -5.0%
            #   stage 2 => neural 6 OR -10.0%
            #   stage 3 => neural 7 OR -20.0%
            # After that: hardcoded only (-30, -40, -50, then repeat -50 forever).
            current_stage = len(self.dca_levels_triggered.get(symbol, []))

            # Hardcoded loss % for this stage (repeat last level after list ends)
            hard_level = (
                self.dca_levels[current_stage]
                if current_stage < len(self.dca_levels)
                else self.dca_levels[-1]
            )
            hard_hit = gain_loss_percentage_buy <= hard_level

            # Neural trigger only for first 4 DCA stages
            neural_level_needed = None
            neural_level_now = None
            neural_hit = False
            if current_stage < 4:
                neural_level_needed = current_stage + 4
                neural_level_now = self._read_long_dca_signal(symbol)

                # Keep it sane: don't DCA from neural if we're not even below cost basis.
                neural_hit = (gain_loss_percentage_buy < 0) and (
                    neural_level_now >= neural_level_needed
                )

            if (hard_hit or neural_hit) and self._market_not_trading(symbol):
                pass  # its market is not trading: no DCA buy (reason printed once)
            elif (hard_hit or neural_hit) and self.risk_manager.is_trading_halted():
                pass  # buying is halted: no DCA buy (run() says why)
            elif hard_hit or neural_hit:
                if neural_hit and hard_hit:
                    reason = f"NEURAL L{neural_level_now}>=L{neural_level_needed} OR HARD {hard_level:.2f}%"
                elif neural_hit:
                    reason = f"NEURAL L{neural_level_now}>=L{neural_level_needed}"
                else:
                    reason = f"HARD {hard_level:.2f}%"

                print(f"  DCAing {symbol} (stage {current_stage + 1}) via {reason}.")

                print(f"  Current Value: ${value:.2f}")
                dca_amount = value * float(DCA_MULTIPLIER or 0.0)
                print(f"  DCA Amount: ${dca_amount:.2f}")
                print(f"  Buying Power: ${buying_power:.2f}")

                recent_dca = self._dca_window_count(symbol)
                invested = float(avg_cost_basis or 0.0) * float(quantity or 0.0)
                if recent_dca >= int(getattr(self, "max_dca_buys_per_24h", 2)):
                    print(
                        f"  Skipping DCA for {symbol}. "
                        f"Already placed {recent_dca} DCA buys in the last 24h (max {self.max_dca_buys_per_24h})."
                    )

                elif not position_sizing.dca_fits_budget(
                    invested, dca_amount, total_account_value, MAX_COIN_PCT
                ):
                    budget = position_sizing.coin_budget_usd(
                        total_account_value, MAX_COIN_PCT
                    )
                    print(
                        f"  Skipping DCA for {symbol}. It would take the coin to "
                        f"${invested + dca_amount:.2f}, past its budget of ${budget:.2f} "
                        f"(Max per coin {MAX_COIN_PCT:g}% of ${total_account_value:.2f})."
                    )

                elif dca_amount <= buying_power:
                    response = self.place_buy_order(
                        str(uuid.uuid4()),
                        "buy",
                        "market",
                        full_symbol,
                        dca_amount,
                        avg_cost_basis=avg_cost_basis,
                        pnl_pct=gain_loss_percentage_buy,
                        tag="DCA",
                    )

                    print(f"  Buy Response: {response}")
                    if response and "errors" not in response:
                        # record that we completed THIS stage (no matter what triggered it)
                        self.dca_levels_triggered.setdefault(symbol, []).append(
                            current_stage
                        )

                        # Only record a DCA buy timestamp on success (so skips never advance anything)
                        self._note_dca_buy(symbol)

                        # DCA changes avg_cost_basis, so the PM line must be rebuilt from the new basis
                        # (this will re-init to 5% if DCA=0, or 2.5% if DCA>=1)
                        self.trailing_pm.pop(symbol, None)

                        trades_made = True
                        print(f"  Successfully placed DCA buy order for {symbol}.")
                    else:
                        print(f"  Failed to place DCA buy order for {symbol}.")

                else:
                    print(f"  Skipping DCA for {symbol}. Not enough funds.")

            else:
                pass

        # --- ensure GUI gets bid/ask lines even for coins not currently held ---
        try:
            for sym in crypto_symbols:
                if sym in positions:
                    continue

                full_symbol = f"{sym}-USD"
                if full_symbol not in valid_symbols or sym == "USDC":
                    continue

                current_buy_price = current_buy_prices.get(full_symbol, 0.0)
                current_sell_price = current_sell_prices.get(full_symbol, 0.0)

                # keep the per-coin current price file behavior for consistency
                try:
                    with open(
                        os.path.join(self.data_dir, sym + "_current_price.txt"), "w+"
                    ) as file:
                        file.write(str(current_buy_price))
                except Exception:
                    pass

                positions[sym] = {
                    "quantity": 0.0,
                    "avg_cost_basis": 0.0,
                    "current_buy_price": current_buy_price,
                    "current_sell_price": current_sell_price,
                    "gain_loss_pct_buy": 0.0,
                    "gain_loss_pct_sell": 0.0,
                    "value_usd": 0.0,
                    "dca_triggered_stages": int(
                        len(self.dca_levels_triggered.get(sym, []))
                    ),
                    "next_dca_display": "",
                    "dca_line_price": 0.0,
                    "dca_line_source": "N/A",
                    "dca_line_pct": 0.0,
                    "trail_active": False,
                    "trail_line": 0.0,
                    "trail_peak": 0.0,
                    "dist_to_trail_pct": 0.0,
                }
        except Exception:
            pass

        if not trading_pairs:
            return

        holding_full_symbols = self._held_symbols(holdings, current_sell_prices)

        entry_coins = set(self._entry_coins())
        start_index = 0
        # buying is halted (an emergency stop), or buys wait (no account value): no
        # new trade is looked for, so no entry decision, LLM check or entry
        # assessment is made either
        if self.risk_manager.is_trading_halted() or buys_waiting:
            start_index = len(crypto_symbols)
        while start_index < len(crypto_symbols):
            base_symbol = crypto_symbols[start_index].upper().strip()
            full_symbol = f"{base_symbol}-USD"

            # Skip if already held
            if full_symbol in holding_full_symbols:
                start_index += 1
                continue

            # Paper trading may be limited to some of the coins (Settings)
            if base_symbol not in entry_coins:
                start_index += 1
                continue

            # Never open a position in a coin whose market is not trading
            if self._market_not_trading(base_symbol):
                start_index += 1
                continue

            entry_decision = None
            buy_count = sell_count = 0
            if catalogue_mode:
                # Not held -> the strategy's record of a position (if any) is stale.
                self.signal_engine.forget(base_symbol)
                entry_decision = self._decide(base_symbol, None)
                if (
                    entry_decision is None
                    or entry_decision.action is not Action.ENTER_LONG
                ):
                    start_index += 1
                    continue
            else:
                # Neural signals are used as a "permission to start" gate.
                buy_count = self._read_long_dca_signal(base_symbol)
                sell_count = self._read_short_dca_signal(base_symbol)
                # The runner sets long to 0, then writes short, then long: a long
                # count that changed while short was read means a pair mid-update.
                if self._read_long_dca_signal(base_symbol) != buy_count:
                    buy_count = 0

                start_level = max(1, min(int(TRADE_START_LEVEL or 3), 7))

                # Default behavior: long must be >= start_level and short must be 0
                if not (buy_count >= start_level and sell_count == 0):
                    start_index += 1
                    continue

            # An LLM signal may confirm or veto this entry, never make one
            # (Settings > LLM Providers; off and log only change nothing here)
            client_order_id = str(uuid.uuid4())
            if not self._llm_entry_allowed(base_symbol, client_order_id):
                start_index += 1
                continue

            # Start allocation % of the account, raised to the exchange's minimum with
            # room for this quote's spread and the fees
            allocation_in_usd, minimum_entry = self._entry_size(
                full_symbol,
                total_account_value,
                current_buy_prices.get(full_symbol),
                current_sell_prices.get(full_symbol),
            )
            # The entry assessment (Settings > Strategy and Risk): Off by default, and
            # Log only at most in this version, so it never changes this order; what it
            # would have done is recorded after the order is placed
            assessing = self._entry_assessment_capture(
                base_symbol,
                full_symbol,
                allocation_in_usd,
                minimum_entry,
                current_buy_prices.get(full_symbol),
                current_sell_prices.get(full_symbol),
                "strategy" if catalogue_mode else "thinker",
            )
            response = self.place_buy_order(
                client_order_id,
                "buy",
                "market",
                full_symbol,
                allocation_in_usd,
                tag="ENTRY" if catalogue_mode else None,
                minimum_entry_usd=minimum_entry,
            )
            self._entry_assessment_log(assessing)

            if response and "errors" not in response:
                trades_made = True
                self._llm_entry_placed(client_order_id, response)
                if entry_decision is not None:
                    self.signal_engine.record_entry(
                        base_symbol,
                        response.get("price") or 0.0,
                        entry_decision.bar_time,
                    )
                # Do NOT pre-trigger any DCA levels. Hardcoded DCA will mark levels only when it hits your loss thresholds.
                self.dca_levels_triggered[base_symbol] = []

                # Fresh trade -> clear any rolling 24h DCA window for this coin
                self._reset_dca_window_for_trade(base_symbol, sold=False)

                # Reset trailing PM state for this coin (fresh trade, fresh trailing logic)
                self.trailing_pm.pop(base_symbol, None)

                if entry_decision is not None:
                    print(
                        f"Starting new trade for {full_symbol} ({entry_decision.strategy_id}: "
                        f"{entry_decision.reason}). Allocating ${allocation_in_usd:.2f}."
                    )
                else:
                    print(
                        f"Starting new trade for {full_symbol} (AI start signal long={buy_count}, short={sell_count}). "
                        f"Allocating ${allocation_in_usd:.2f}."
                    )
                time.sleep(5)
                holdings = self.get_holdings()
                holding_full_symbols = self._held_symbols(holdings, current_sell_prices)

            start_index += 1

        # If any trades were made, recalculate the cost basis
        if trades_made:
            time.sleep(5)
            print("Trades were made in this iteration. Recalculating cost basis...")
            new_cost_basis = self.calculate_cost_basis()
            if new_cost_basis:
                self.cost_basis = new_cost_basis
                print("Cost basis recalculated successfully.")
            else:
                print("Failed to recalculcate cost basis.")
            self.initialize_dca_levels()

        # --- GUI HUB STATUS WRITE ---
        try:
            status = {
                "timestamp": time.time(),
                "trading_mode": self._target.key,
                "signals": self._signals_status(),
                "account": {
                    "total_account_value": total_account_value,
                    # what the drawdown stop measures (Settings > Risk shows it)
                    "halt_equity": self._get_halt_value(),
                    "buying_power": buying_power,
                    "holdings_sell_value": holdings_sell_value,
                    "holdings_buy_value": holdings_buy_value,
                    "percent_in_trade": in_use,
                    # trailing PM config (matches what's printed above current trades)
                    "pm_start_pct_no_dca": float(
                        getattr(self, "pm_start_pct_no_dca", 0.0)
                    ),
                    "pm_start_pct_with_dca": float(
                        getattr(self, "pm_start_pct_with_dca", 0.0)
                    ),
                    "trailing_gap_pct": float(getattr(self, "trailing_gap_pct", 0.0)),
                },
                "positions": positions,
            }
            price_integrity = self._price_integrity_status()
            if price_integrity is not None:
                status["price_integrity"] = price_integrity
            self._append_jsonl(
                self.account_value_history_path,
                {"ts": status["timestamp"], "total_account_value": total_account_value},
            )
            self._write_trader_status(status)
        except Exception:
            pass

    def _say_halted(self, force: bool = False) -> None:
        """While buying is halted: why, and what still runs (every 5 minutes)."""
        now = time.time()
        if not force and now - getattr(self, "_halt_said_ts", 0.0) < 300.0:
            return
        self._halt_said_ts = now
        reason = self.risk_manager.halt_reason or "risk controls"
        print(f"{Fore.RED}BUYING HALTED: {reason}{Style.RESET_ALL}")
        print(
            f"{Fore.RED}No new trades or DCA buys until Resume trading in Settings > "
            f"Risk. Exits, stops and the trailing margin still sell.{Style.RESET_ALL}"
        )
        logger.warning(f"Buying halted ({reason}); held positions are still managed")

    def _check_drawdown(self, value: float) -> None:
        """The emergency stop's check of the account value ``value``: the peak is
        raised first (and Settings > Risk's requests applied), then the warnings, and
        at the emergency level a halt. An emergency stop halts buying: no new trade
        and no DCA buy, also after a restart, until Resume trading. What is held is
        still managed: exits, stops and the trailing margin still sell."""
        self.risk_manager.update_portfolio_value(value)
        if self.risk_manager.is_trading_halted():
            self._say_halted()
            return
        risk_status = self.risk_manager.check_emergency_conditions(value)
        if risk_status["emergency_stop"]:
            print(f"{Fore.RED}EMERGENCY STOP: {risk_status['reason']}{Style.RESET_ALL}")
            self.risk_manager.emergency_stop(risk_status["reason"], value)
            self._say_halted(force=True)

        # Log risk warnings
        for warning in risk_status["warnings"]:
            print(f"{Fore.YELLOW}RISK WARNING: {warning}{Style.RESET_ALL}")

    def run(self):
        while True:
            try:
                # Risk monitoring at start of each cycle (needs a complete account
                # snapshot, so it starts after the first manage_trades() pass). This
                # also applies Resume trading from Settings > Risk. A value the pass
                # that formed it has checked is not checked (or warned about) again.
                current_portfolio_value = self._get_halt_value()
                last = self._last_good_account_snapshot or {}
                if last.pop("checked", False) or current_portfolio_value is None:
                    if current_portfolio_value is not None:
                        self.risk_manager.update_portfolio_value(
                            current_portfolio_value
                        )
                    if self.risk_manager.is_trading_halted():
                        self._say_halted()
                else:
                    self._check_drawdown(current_portfolio_value)

                self.manage_trades()
                time.sleep(0.5)
            except Exception as e:
                print(traceback.format_exc())
                # Log the error with risk system
                self.risk_manager.record_error(str(e))
                time.sleep(5)  # don't hammer a failing exchange every half second


if __name__ == "__main__":
    try:
        trading_bot = CryptoAPITrading()
    except TradingModeError as exc:
        print(f"{Fore.RED}Trader not started: {exc}{Style.RESET_ALL}")
        raise SystemExit(2)
    trading_bot.run()
