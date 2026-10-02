import json
import math
import os
import time
import traceback
import uuid
from typing import Any, Dict, Optional

import colorama
import pt_paths
from colorama import Fore, Style
from pt_cost import CostManager, PerformanceTier
from pt_exchange_abstraction import OrderResult
from pt_logging import get_logger
from pt_risk import RiskLimits, RiskManager
from pt_validation import InputValidator, ValidationError
from signal_engine import SignalEngine
from strategies.base import Action
from strategies.settings import read_strategy_settings
from trading_mode import (
    OrderTarget,
    TradingModeError,
    configure_paper_exchange,
    read_emergency_drawdown_pct,
    read_paper_settings,
    read_trading_settings,
    resolve_order_target,
)

# -----------------------------
# GUI HUB OUTPUTS
# -----------------------------
# Base directory shared with the hub. Each trading mode keeps its own ledger and
# history in a sub-directory (see TradingSettings.data_subdir) so paper and
# testnet fills never mix into the live books.
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
    "start_allocation_pct": 0.005,
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
START_ALLOC_PCT = 0.005
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
                    TRADE_START_LEVEL, START_ALLOC_PCT, DCA_MULTIPLIER, DCA_LEVELS, MAX_DCA_BUYS_PER_24H,
                    TRAILING_GAP_PCT, PM_START_PCT_NO_DCA, PM_START_PCT_WITH_DCA
    """
    global crypto_symbols, main_dir, base_paths
    global TRADE_START_LEVEL, START_ALLOC_PCT, DCA_MULTIPLIER, DCA_LEVELS, MAX_DCA_BUYS_PER_24H
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


class _TraderRiskAdapter:
    """
    The trader's view of risk management, backed by pt_risk.RiskManager.

    RiskManager exposes ``validate_trade`` / flag attributes; the trader wants a
    per-order approve/block answer and a per-cycle drawdown check. Drawdown is
    measured against the peak account value seen by this trader, using the
    thresholds RiskManager already defines (warning / critical / emergency).
    """

    def __init__(
        self, manager: Optional[RiskManager] = None, settings_source: Any = None
    ):
        self.manager = manager or RiskManager(RiskLimits())
        self.settings_source = settings_source
        self.peak_value = 0.0
        self.error_count = 0

    def is_trading_halted(self) -> bool:
        return bool(
            self.manager.is_trading_halted or self.manager.emergency_stop_triggered
        )

    def update_portfolio_value(self, value: float) -> None:
        self.manager.portfolio_value = float(value)
        self.peak_value = max(self.peak_value, float(value))

    def validate_order(self, order: dict, portfolio_value: float) -> dict:
        self.manager.portfolio_value = float(portfolio_value)
        approved, reason = self.manager.validate_trade(
            order["symbol"], float(order["quantity"]), float(order["price"])
        )
        return {"approved": approved, "reason": reason}

    def check_emergency_conditions(self, portfolio_value: float) -> dict:
        warnings = []
        if self.peak_value <= 0.0:
            return {"emergency_stop": False, "reason": "", "warnings": warnings}

        drawdown = (self.peak_value - float(portfolio_value)) / self.peak_value
        limits = dict(self.manager.risk_thresholds["portfolio_drawdown"])
        # risk.emergency_drawdown_pct (default 8.0, valid 1-50) sets the stop
        limits["emergency"] = read_emergency_drawdown_pct(self.settings_source) / 100.0
        if drawdown >= limits["emergency"]:
            return {
                "emergency_stop": True,
                "reason": f"Account drawdown {drawdown:.1%} reached the {limits['emergency']:.0%} emergency limit",
                "warnings": warnings,
            }
        for level in ("critical", "warning"):
            if drawdown >= limits[level]:
                warnings.append(f"Account drawdown {drawdown:.1%} ({level} level)")
                break
        return {"emergency_stop": False, "reason": "", "warnings": warnings}

    def emergency_stop(self) -> None:
        self.manager.emergency_stop()

    def record_error(self, message: str) -> None:
        self.error_count += 1
        logger.error(f"Trader loop error #{self.error_count}: {message}")


class CryptoAPITrading:
    def __init__(self, settings_source: Any = None, signal_engine: Optional[SignalEngine] = None):
        """
        ``settings_source`` is where the trading-mode gate reads trading.mode /
        trading.active_broker from (None = the settings file, re-read fresh on
        every order; a dict or SettingsManager is accepted for tests).
        ``signal_engine`` supplies rule-based decisions when ``strategy.engine``
        is "catalogue" (tests inject one with scripted candles).
        """
        self._settings_source = settings_source
        self.signal_engine = signal_engine or SignalEngine(settings_source=settings_source)
        self._catalogue_mode = False

        # This mode's own ledger / history / status files
        self._settings = read_trading_settings(self._settings_source)
        self.data_dir = os.path.join(HUB_DATA_DIR, self._settings.data_subdir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.trader_status_path = os.path.join(self.data_dir, "trader_status.json")
        self.trade_history_path = os.path.join(self.data_dir, "trade_history.jsonl")
        self.pnl_ledger_path = os.path.join(self.data_dir, "pnl_ledger.json")
        self.account_value_history_path = os.path.join(
            self.data_dir, "account_value_history.jsonl"
        )
        # Open strategy positions + overlay state (stops, cooldowns) survive a restart
        self.signal_engine.attach_state(os.path.join(self.data_dir, "strategy_state.json"))
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
        self._pnl_ledger = self._load_pnl_ledger()
        self._reconcile_pending_orders()

        # Initialize Risk and Cost Management
        self.risk_manager = _TraderRiskAdapter(settings_source=self._settings_source)
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
                return data
        except Exception:
            pass
        return {
            "total_realized_profit_usd": 0.0,
            "last_updated_ts": time.time(),
            "open_positions": {},
            "pending_orders": {},
        }

    def _save_pnl_ledger(self) -> None:
        try:
            self._pnl_ledger["last_updated_ts"] = time.time()
            self._atomic_write_json(self.pnl_ledger_path, self._pnl_ledger)
        except Exception:
            pass

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
                            fees_usd=None,
                            buying_power_before=bp_before,
                            buying_power_after=bp_after,
                            buying_power_delta=bp_delta,
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
    ) -> None:
        """
        Minimal local ledger for GUI:
        - append trade_history.jsonl
        - update pnl_ledger.json on sells (now using buying power delta when available)
        - persist per-coin open position cost (USD) so realized profit is exact
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
        if price_source is not None:
            # Paper fills record where their price came from (live/stale/simulated)
            entry["price_source"] = price_source
            entry["quote_ts"] = quote_ts
            entry["age_s"] = age_s
            self._note_price_event(price_source, ts)
        self._append_jsonl(self.trade_history_path, entry)

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
            with open(path, "r") as f:
                raw = f.read().strip()
            val = int(float(raw))
            return val
        except Exception:
            return 0

    @staticmethod
    def _read_short_dca_signal(symbol: str) -> int:
        """
        Reads short_dca_signal.txt from the per-coin folder (same folder rules as trader.py).

        Used for:
        - Start gate: start trades at level 3+
        - DCA assist: levels 4-7 map to trader DCA stages 0-3 (trade starts at level 3 => stage 0)
        """
        sym = str(symbol).upper().strip()
        folder = base_paths.get(
            sym, main_dir if sym == "BTC" else os.path.join(main_dir, sym)
        )
        path = os.path.join(folder, "short_dca_signal.txt")
        try:
            with open(path, "r") as f:
                raw = f.read().strip()
            val = int(float(raw))
            return val
        except Exception:
            return 0

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

    def _warn_throttled(self, key: str, message: str, every: float = 60.0) -> None:
        """WARNING at most once per ``every`` seconds per key (the loop runs 2x/s)."""
        now = time.time()
        if now - self._warn_ts.get(key, 0.0) >= every:
            self._warn_ts[key] = now
            logger.warning(message)

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
                    if side in ("buy", "sell"):
                        fills.append((float(entry.get("ts")), side))
                except (TypeError, ValueError):
                    continue

            if not fills:
                print(f"No recorded trades for {full_symbol}. Skipping.")
                continue

            # Buys after the most recent sell belong to the current trade
            last_sell_ts = max((ts for ts, side in fills if side == "sell"), default=None)
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

                    if side == "sell":
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
        return [f"{str(s).upper().strip()}-USD" for s in crypto_symbols if str(s).strip()]

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

    def _risk_check(self, symbol: str, side: str, quantity: float, price: float):
        """Shared pre-order risk gate. Returns True when the order may proceed."""
        if self.risk_manager.is_trading_halted():
            print(
                f"{Fore.RED}RISK HALT: Trading is currently halted by risk management system{Style.RESET_ALL}"
            )
            return False

        portfolio_value = self._get_account_value()
        if portfolio_value is None:
            portfolio_value = self._get_buying_power()
        self.risk_manager.update_portfolio_value(portfolio_value)

        validation = self.risk_manager.validate_order(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_value": quantity * price,
            },
            portfolio_value,
        )
        if not validation["approved"]:
            print(f"{Fore.YELLOW}RISK BLOCK: {validation['reason']}{Style.RESET_ALL}")
            return False
        return True

    def _gate_or_refuse(self) -> Optional[OrderTarget]:
        """Run the gate; on refusal report it and return None (no order may follow)."""
        # Fail closed on the signal source too: an unknown strategy engine / id
        # (or unusable strategy settings) means no orders at all.
        problem = read_strategy_settings(self._settings_source).problem
        if problem:
            print(f"{Fore.RED}ORDER REFUSED: invalid strategy configuration: {problem}{Style.RESET_ALL}")
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
    ) -> Any:
        """
        Place one market order on ``target`` (obtained from the trading-mode
        gate) and do the accounting once it is filled. Returns a small order
        dict on a fill, None when the order was rejected, not filled or
        unconfirmed.
        """
        # --- exact profit tracking snapshot (BEFORE placing order) ---
        buying_power_before = self._get_buying_power()

        try:
            result = target.place_order(symbol, side, asset_quantity)
        except Exception as exc:
            msg = self._describe_exchange_error(exc, "order placement", target.key)
            print(f"{Fore.RED}ORDER FAILED ({symbol} {side}): {msg}{Style.RESET_ALL}")
            logger.error(f"Order failed ({symbol} {side} via {target.key}): {msg}")
            return None

        order_id = result.order_id

        if str(result.status).lower().strip() == "rejected" and result.reason:
            # e.g. PRICE_UNAVAILABLE: nothing was filled, nothing is pending; the
            # next cycle simply tries again.
            self._note_price_event("unavailable")
            print(f"{Fore.YELLOW}ORDER REJECTED ({symbol} {side}): {result.reason}{Style.RESET_ALL}")
            logger.warning(
                f"Order rejected ({symbol} {side} via {target.key}): {result.reason}; "
                "will retry next cycle"
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

        # --- exact profit tracking snapshot (AFTER the order is complete) ---
        buying_power_after = self._get_buying_power()
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
            fees_usd=None,
            buying_power_before=buying_power_before,
            buying_power_after=buying_power_after,
            buying_power_delta=buying_power_delta,
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
        }

    @staticmethod
    def _provenance(order: OrderResult, target: OrderTarget) -> dict:
        """Ledger columns for where a paper fill's price came from ({} for live)."""
        if target.is_live:
            return {}
        return {
            "price_source": order.price_source or "unknown",
            "quote_ts": order.quote_ts,
            "age_s": order.age_s,
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

    def _report_position_stops(self, symbol: str, pos, decision, positions: dict) -> None:
        """Per-cycle telemetry for an open strategy position: effective stop, which
        overlay owns it, and each overlay's state (console + trader_status.json)."""
        overlays = [o["id"] for o in read_strategy_settings(self._settings_source).overlays]
        stop = decision.stop_price if decision.stop_price is not None else pos.current_stop
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
                entry["trail_line"] = float(stop)  # the hub charts this as the sell line
                entry["trail_active"] = True
        stop_txt = self._fmt_price(stop) if stop else "none"
        print(
            f"  Stop {symbol}: {stop_txt} (owner {owner or 'none'}) | overlays: "
            f"{', '.join(overlays) or 'none'} | state: {json.dumps(pos.overlay_state, default=str)}"
        )

    def _signals_status(self) -> dict:
        s = read_strategy_settings(self._settings_source)
        return {
            "engine": s.engine,
            "strategy_id": s.active_id if s.is_catalogue else None,
            "timeframe": s.timeframe if s.is_catalogue else None,
            "overlays": [o["id"] for o in s.overlays] if s.is_catalogue else [],
            "blocked": s.problem,
            "note": s.note,
            "last_decisions": {
                base: {
                    "action": d.action.value,
                    "reason": d.reason,
                    "bar_time": str(d.bar_time),
                    "stop": d.stop_price,
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
    ) -> Any:
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
        if not self._risk_check(symbol, side, asset_quantity, current_price):
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
        strategy_cfg = read_strategy_settings(self._settings_source)
        self._catalogue_mode = strategy_cfg.is_catalogue and not strategy_cfg.problem
        if strategy_cfg.problem:
            self._warn_throttled(
                "strategy-config",
                f"Strategy configuration invalid; no orders will be placed: {strategy_cfg.problem}",
                every=300.0,
            )
        catalogue_mode = self._catalogue_mode

        # Fetch account details
        account = self.get_account()
        # Fetch holdings
        holdings = self.get_holdings()
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

        current_buy_prices, current_sell_prices, valid_symbols = self.get_price(symbols)

        # Calculate total account value (robust: never drop a held coin to $0 on transient API misses)
        snapshot_ok = True

        # buying power
        try:
            if isinstance(account, dict) and "error" in account:
                raise ValueError(account["error"])  # transient/unsupported: not a $0 balance
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

        for holding in holdings_list:
            try:
                asset = holding.get("asset_code")
                if asset == "USDC":
                    continue

                qty = float(holding.get("total_quantity", 0.0))
                if qty <= 0.0:
                    continue

                sym = f"{asset}-USD"
                bp = float(current_buy_prices.get(sym, 0.0) or 0.0)
                sp = float(current_sell_prices.get(sym, 0.0) or 0.0)

                # If any held asset is missing a usable price this tick, do NOT allow a new "low" snapshot
                if bp <= 0.0 or sp <= 0.0:
                    snapshot_ok = False
                    continue

                holdings_buy_value += qty * bp
                holdings_sell_value += qty * sp
            except Exception:
                snapshot_ok = False
                continue

        total_account_value = buying_power + holdings_sell_value
        in_use = (
            (holdings_sell_value / total_account_value) * 100
            if total_account_value > 0
            else 0.0
        )

        # If this tick is incomplete, fall back to last known-good snapshot so the GUI chart never gets a bogus dip.
        if (not snapshot_ok) or (total_account_value <= 0.0):
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
            # Save last complete snapshot
            self._last_good_account_snapshot = {
                "total_account_value": float(total_account_value),
                "buying_power": float(buying_power),
                "holdings_sell_value": float(holdings_sell_value),
                "holdings_buy_value": float(holdings_buy_value),
                "percent_in_trade": float(in_use),
            }

        os.system("cls" if os.name == "nt" else "clear")
        print("\n--- Account Summary ---")
        print(f"Total Account Value: ${total_account_value:.2f}")
        print(f"Holdings Value: ${holdings_sell_value:.2f}")
        print(f"Percent In Trade: {in_use:.2f}%")
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

            # --- Catalogue engine: the strategy (+ overlays) own the exit ---------------
            # Legacy trailing-PM sells and DCA buys below are skipped in this mode.
            # Only positions this trader opened (they have a ledger cost basis) are
            # managed, and only the quantity the ledger says it bought is sold.
            if catalogue_mode:
                exit_qty = self._catalogue_exit_quantity(symbol, quantity)
                if avg_cost_basis > 0 and exit_qty > 0:
                    pos = self.signal_engine.ensure_position(symbol, avg_cost_basis)
                    decision = self.signal_engine.decide(symbol, pos)
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
                        if response and isinstance(response, dict) and "errors" not in response:
                            trades_made = True
                            self.signal_engine.record_exit(
                                symbol, response.get("price") or current_sell_price, decision.bar_time
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

            if hard_hit or neural_hit:
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
                if recent_dca >= int(getattr(self, "max_dca_buys_per_24h", 2)):
                    print(
                        f"  Skipping DCA for {symbol}. "
                        f"Already placed {recent_dca} DCA buys in the last 24h (max {self.max_dca_buys_per_24h})."
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

        alloc_pct = float(START_ALLOC_PCT or 0.005)
        allocation_in_usd = total_account_value * (alloc_pct / 100.0)
        if allocation_in_usd < 0.5:
            allocation_in_usd = 0.5

        holding_full_symbols = [
            f"{h['asset_code']}-USD" for h in holdings.get("results", [])
        ]

        start_index = 0
        while start_index < len(crypto_symbols):
            base_symbol = crypto_symbols[start_index].upper().strip()
            full_symbol = f"{base_symbol}-USD"

            # Skip if already held
            if full_symbol in holding_full_symbols:
                start_index += 1
                continue

            entry_decision = None
            buy_count = sell_count = 0
            if catalogue_mode:
                # Not held -> the strategy's record of a position (if any) is stale.
                self.signal_engine.forget(base_symbol)
                entry_decision = self.signal_engine.decide(base_symbol, None)
                if entry_decision is None or entry_decision.action is not Action.ENTER_LONG:
                    start_index += 1
                    continue
            else:
                # Neural signals are used as a "permission to start" gate.
                buy_count = self._read_long_dca_signal(base_symbol)
                sell_count = self._read_short_dca_signal(base_symbol)

                start_level = max(1, min(int(TRADE_START_LEVEL or 3), 7))

                # Default behavior: long must be >= start_level and short must be 0
                if not (buy_count >= start_level and sell_count == 0):
                    start_index += 1
                    continue

            response = self.place_buy_order(
                str(uuid.uuid4()),
                "buy",
                "market",
                full_symbol,
                allocation_in_usd,
                tag="ENTRY" if catalogue_mode else None,
            )

            if response and "errors" not in response:
                trades_made = True
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
                holding_full_symbols = [
                    f"{h['asset_code']}-USD" for h in holdings.get("results", [])
                ]

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

    def run(self):
        while True:
            try:
                # Risk monitoring at start of each cycle (needs a complete account
                # snapshot, so it starts after the first manage_trades() pass)
                current_portfolio_value = self._get_account_value()
                if current_portfolio_value is not None:
                    self.risk_manager.update_portfolio_value(current_portfolio_value)

                    # Check for emergency conditions
                    risk_status = self.risk_manager.check_emergency_conditions(
                        current_portfolio_value
                    )
                    if risk_status["emergency_stop"]:
                        print(
                            f"{Fore.RED}EMERGENCY STOP: {risk_status['reason']}{Style.RESET_ALL}"
                        )
                        print(
                            f"{Fore.RED}Trading halted until manual intervention{Style.RESET_ALL}"
                        )
                        self.risk_manager.emergency_stop()
                        break

                    # Log risk warnings
                    if risk_status["warnings"]:
                        for warning in risk_status["warnings"]:
                            print(
                                f"{Fore.YELLOW}RISK WARNING: {warning}{Style.RESET_ALL}"
                            )

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
