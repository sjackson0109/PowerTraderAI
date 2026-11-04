"""
LLM Research: market analysis, trade signals and research reports for the coins in
Settings, answered through the LLM provider layer (``llm_providers.LLMRouter``: the
preferred provider, then the fallbacks) and kept in ``llm_store``.

Market data comes from the exchange layer (``pt_multi_exchange.market_exchanges``:
the primary exchange first, public market data): the last 200 closed hourly candles
of each coin, in the market and format of the exchange that served them
(``exchange_symbols``). From them: the last close, the 24-hour change and volume,
the 7-day high and low, RSI(14) and the 50- and 200-hour moving averages, and the
last 24 closes. No price, symbol or model name is written here.

Prompts are templates with ``${name}`` fields (``PROMPT_FIELDS``); each edit is a
new version in the store, and every answer records the version it came from.
"""

from __future__ import annotations

import string
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import exchange_symbols
import llm_settings
import llm_signals
from llm_store import AnalysisRecord, LLMStore, SignalRecord

BARS = 200  # hourly candles read for each coin
HOUR_MS = 3600 * 1000

DEFAULT_PROMPTS = {
    "analysis": (
        "You are a cryptocurrency market analyst. Analyse ${coin} (${pair}, prices "
        "in ${quote}) from the market data below.\n\n"
        "${market_data}\n\n"
        "Write the analysis in Markdown with these sections: ## Summary, ## Trend and "
        "momentum, ## Support and resistance, ## Risks, ## Outlook. Explain your "
        "reasoning and use only the data given; say where it is not enough to "
        "judge.\n\n"
        "End with one line in exactly this form: SIGNAL: BUY, SIGNAL: SELL or "
        "SIGNAL: HOLD"
    ),
    "signal": (
        "You are a cryptocurrency trading analyst. Give one trade signal for ${coin} "
        "(${pair}, prices in ${quote}) from the market data below.\n\n"
        "${market_data}\n\n"
        "Answer with one JSON object and nothing else, with these keys:\n"
        '"direction": "BUY", "SELL" or "HOLD"\n'
        '"strength": "very_bearish", "bearish", "neutral", "bullish" or '
        '"very_bullish"\n'
        '"confidence": a number from 0 to 100\n'
        '"price_target": a price in ${quote}, or null\n'
        '"stop_loss": a price in ${quote}, or null\n'
        '"time_horizon": "SHORT" (up to 1 day), "MEDIUM" (up to 1 week) or "LONG" '
        "(up to 1 month)\n"
        '"reasoning": a short explanation'
    ),
    "report": (
        "You are a cryptocurrency research analyst. Write a ${report_type} research "
        "report in Markdown for ${coins}, from the market data below.\n\n"
        "${market_data}\n\n"
        "Use these sections: ## Summary, ## Market performance, ## Technical picture, "
        "## Opportunities, ## Risks, ## Outlook. Use only the data given, and say "
        "where it is not enough to judge."
    ),
}
PROMPT_FIELDS = {
    "analysis": ("coin", "pair", "quote", "market_data"),
    "signal": ("coin", "pair", "quote", "market_data"),
    "report": ("report_type", "coins", "market_data"),
}
MAX_TOKENS = {"analysis": 1500, "signal": 600, "report": 2500}
REPORT_TYPES = ("Market Overview", "Coin Report")
# The market data block in a prompt is about this long (for cost estimates).
MARKET_DATA_CHARS = 1200
CHARS_PER_TOKEN = 4


def render(template: str, **values: Any) -> str:
    """The template with its ``${name}`` fields filled in (others left as they are)."""
    return string.Template(template).safe_substitute(
        {k: "" if v is None else str(v) for k, v in values.items()}
    )


# --- market data --------------------------------------------------------------------


def _rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI of ``closes``; None with too few."""
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        change = b - a
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _sma(closes: Sequence[float], n: int) -> Optional[float]:
    return sum(closes[-n:]) / n if len(closes) >= n else None


def _price(value: Optional[float]) -> str:
    if value is None:
        return "not known"
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


@dataclass
class MarketSnapshot:
    coin: str
    pair: str
    exchange: str
    quote: str
    price: Optional[float] = None
    bar_ms: Optional[int] = None  # the last closed bar's open time
    change_24h_pct: Optional[float] = None
    volume_24h: Optional[float] = None
    high_7d: Optional[float] = None
    low_7d: Optional[float] = None
    rsi_14: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    closes_24h: List[float] = field(default_factory=list)
    problem: str = ""

    def facts(self) -> Dict[str, Any]:
        return {
            "coin": self.coin,
            "pair": self.pair,
            "exchange": self.exchange,
            "quote": self.quote,
            "price": self.price,
            "bar_ms": self.bar_ms,
            "change_24h_pct": self.change_24h_pct,
            "volume_24h": self.volume_24h,
            "high_7d": self.high_7d,
            "low_7d": self.low_7d,
            "rsi_14": self.rsi_14,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "problem": self.problem,
        }

    def text(self, closes: bool = True) -> str:
        """The market data block of a prompt."""
        if self.price is None:
            return f"{self.coin}: no market data ({self.problem or 'not available'})"
        when = time.strftime(
            "%Y-%m-%d %H:%M UTC", time.gmtime((self.bar_ms or 0) / 1000)
        )
        lines = [
            f"Market: {self.pair} (prices in {self.quote})",
            f"Last hourly close: {_price(self.price)} (bar opened {when})",
        ]
        if self.change_24h_pct is not None:
            lines.append(f"24-hour change: {self.change_24h_pct:+.2f}%")
        if self.volume_24h is not None:
            lines.append(f"24-hour volume: {self.volume_24h:,.4f} {self.coin}")
        if self.high_7d is not None:
            lines.append(
                f"7-day high / low: {_price(self.high_7d)} / {_price(self.low_7d)}"
            )
        if self.rsi_14 is not None:
            lines.append(f"RSI (14, hourly): {self.rsi_14:.1f}")
        if self.sma_50 is not None:
            averages = f"50-hour {_price(self.sma_50)}"
            if self.sma_200 is not None:
                averages += f", 200-hour {_price(self.sma_200)}"
            lines.append(f"Moving averages (hourly): {averages}")
        if closes and self.closes_24h:
            lines.append(
                "Hourly closes, last 24 hours (oldest first): "
                + ", ".join(_price(c) for c in self.closes_24h)
            )
        return "\n".join(lines)


class MarketData:
    """Hourly candles from the exchange layer. ``layer`` returns the shared
    MultiExchangeManager (``pt_multi_exchange.market_exchanges`` by default)."""

    def __init__(
        self,
        layer: Optional[Callable[[], Any]] = None,
        clock: Callable[[], float] = time.time,
    ):
        self._layer = layer
        self.clock = clock

    def layer(self):
        if self._layer is not None:
            return self._layer()
        from pt_multi_exchange import market_exchanges

        return market_exchanges()

    def pair(self, coin: str) -> exchange_symbols.MarketPair:
        return exchange_symbols.market_pair(coin, self.layer)

    def bars(self, coin: str, start_ms: int, end_ms: int, only: Optional[str] = None):
        """``Sourced``: closed hourly bars of ``coin`` from the exchange layer."""
        manager = self.layer()
        try:
            return manager.candles(coin, "1h", int(start_ms), int(end_ms), only=only)
        except Exception:
            if only is None:
                raise
            return manager.candles(coin, "1h", int(start_ms), int(end_ms))

    def snapshot(self, coin: str) -> MarketSnapshot:
        coin = exchange_symbols.coin_of(coin)
        shown = self.pair(coin)
        now_ms = int(self.clock() * 1000)
        end = (now_ms // HOUR_MS) * HOUR_MS - HOUR_MS
        start = end - (BARS - 1) * HOUR_MS
        snap = MarketSnapshot(coin, shown.pair, shown.exchange, shown.quote)
        try:
            sourced = self.bars(coin, start, end)
        except Exception as exc:
            snap.problem = f"{type(exc).__name__}: {exc}"[:300]
            return snap
        rows = list(sourced.value or [])
        if not rows:
            snap.problem = "no candles"
            return snap
        served = exchange_symbols.MarketPair(
            coin,
            str(sourced.pair or shown.pair),
            str(sourced.exchange or ""),
            shown.quote,
        )
        snap.pair, snap.exchange = served.pair, served.exchange
        snap.quote = exchange_symbols.quote_of(coin, served.pair)
        closes = [float(r[4]) for r in rows]
        snap.price = closes[-1]
        snap.bar_ms = int(rows[-1][0])
        if len(closes) > 24 and closes[-25]:
            snap.change_24h_pct = (closes[-1] / closes[-25] - 1.0) * 100.0
        snap.volume_24h = sum(float(r[5]) for r in rows[-24:])
        week = rows[-168:]
        snap.high_7d = max(float(r[2]) for r in week)
        snap.low_7d = min(float(r[3]) for r in week)
        snap.rsi_14 = _rsi(closes)
        snap.sma_50 = _sma(closes, 50)
        snap.sma_200 = _sma(closes, 200)
        snap.closes_24h = closes[-24:]
        return snap


# --- results ---------------------------------------------------------------------------


@dataclass
class AnalysisResult:
    record: AnalysisRecord
    routed: Any  # llm_providers.RoutedCompletion
    snapshot: MarketSnapshot
    signal: Optional[str]  # the SIGNAL line of the analysis


@dataclass
class SignalResult:
    record: SignalRecord
    routed: Any


@dataclass
class ReportResult:
    text: str
    report_type: str
    coins: List[str]
    provider: str
    model: str
    prompt_version: int
    ts: float
    routed: Any = None

    def markdown_file(self) -> str:
        """The report as a Markdown file: a header naming its source, then the
        report."""
        from llm_settings import provider_name

        when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ts))
        header = [
            "---",
            f"title: {self.report_type}",
            f"coins: {', '.join(self.coins)}",
            f"provider: {provider_name(self.provider)}",
            f"model: {self.model}",
            f"prompt_version: report v{self.prompt_version}",
            f"generated: {when}",
            "---",
            "",
        ]
        return "\n".join(header) + self.text.strip() + "\n"


@dataclass(frozen=True)
class CostEstimate:
    provider: str
    model: str
    per_refresh: Optional[float]  # dollars; None: not known (no price set)
    per_day: Optional[float]

    @property
    def free(self) -> bool:
        return self.per_refresh == 0.0


class LLMResearchEngine:
    """Analyses, signals and reports. ``router`` an LLMRouter, ``store`` an
    LLMStore, ``market`` a MarketData; each is built with its defaults when not
    given (no request is made until one is asked for)."""

    def __init__(
        self,
        router: Any = None,
        store: Optional[LLMStore] = None,
        market: Optional[MarketData] = None,
        clock: Callable[[], float] = time.time,
        trading_mode: Optional[Callable[[], str]] = None,
    ):
        self.store = store if store is not None else LLMStore()
        if router is None:
            from llm_providers import LLMRouter

            router = LLMRouter(store=self.store)
        self.router = router
        self.market = market or MarketData(clock=clock)
        self.clock = clock
        self._trading_mode = trading_mode

    # ---- prompts ----

    def prompt(self, kind: str):
        """The prompt version in use for ``kind`` (version 1 is the default)."""
        return self.store.ensure_prompt(kind, DEFAULT_PROMPTS[kind])

    def trading_mode(self) -> str:
        if self._trading_mode is not None:
            return self._trading_mode()
        try:
            from trading_mode import read_trading_settings

            return "live" if read_trading_settings().is_live else "paper"
        except Exception:
            return "paper"

    # ---- analysis ----

    def analyze(self, coin: str) -> AnalysisResult:
        snap = self.market.snapshot(coin)
        version = self.prompt("analysis")
        text = render(
            version.template,
            coin=snap.coin,
            pair=snap.pair,
            quote=snap.quote,
            market_data=snap.text(),
        )
        routed = self.router.complete(
            text, purpose="analysis", max_tokens=MAX_TOKENS["analysis"]
        )
        record = self.store.add_analysis(
            AnalysisRecord(
                ts=self.clock(),
                coin=snap.coin,
                provider=routed.provider,
                model=routed.model,
                prompt_version=version.version,
                text=routed.completion.text,
                pair=snap.pair,
                exchange=snap.exchange,
                facts=dict(
                    snap.facts(),
                    signal=llm_signals.analysis_signal(routed.completion.text),
                    warning=routed.warning(),
                ),
            )
        )
        return AnalysisResult(
            record, routed, snap, llm_signals.analysis_signal(routed.completion.text)
        )

    # ---- signals ----

    def signal(
        self,
        coin: str,
        source: str = "manual",
        trading_mode: Optional[str] = None,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> SignalResult:
        """A new trade signal for ``coin``, kept in the store."""
        snap = snapshot or self.market.snapshot(coin)
        version = self.prompt("signal")
        text = render(
            version.template,
            coin=snap.coin,
            pair=snap.pair,
            quote=snap.quote,
            market_data=snap.text(),
        )
        routed = self.router.complete(
            text, purpose="signal", max_tokens=MAX_TOKENS["signal"]
        )
        parsed = llm_signals.parse_signal(routed.completion.text)
        record = self.store.add_signal(
            SignalRecord(
                ts=self.clock(),
                coin=snap.coin,
                provider=routed.provider,
                model=routed.model,
                prompt_version=version.version,
                price=snap.price,
                pair=snap.pair,
                exchange=snap.exchange,
                source=source,
                trading_mode=trading_mode or self.trading_mode(),
                **parsed,
            )
        )
        return SignalResult(record, routed)

    def score_pending(self, costs: Optional[llm_signals.Costs] = None) -> int:
        """Score the signals whose outcome is known now; returns how many were."""
        now_ms = int(self.clock() * 1000)
        pending = self.store.unscored_signals()
        if not pending:
            return 0
        costs = costs or llm_signals.trade_costs(self.market.layer)
        done = 0
        for s in pending:
            if s.direction not in ("BUY", "SELL") or not s.price:
                if s.direction == "HOLD":
                    self.store.set_outcome(
                        s.id, "no direction", None, None, None, self.clock()
                    )
                continue
            start = int(s.ts * 1000)
            hours = llm_signals.HORIZON_HOURS.get(s.time_horizon, 24 * 7)
            end = min(now_ms - HOUR_MS, start + hours * HOUR_MS)
            if end <= start:
                continue
            try:
                sourced = self.market.bars(
                    s.coin, (start // HOUR_MS) * HOUR_MS, end, only=s.exchange or None
                )
            except Exception:
                continue
            outcome = llm_signals.score_signal(
                s.direction,
                s.price,
                start,
                s.time_horizon,
                s.price_target,
                s.stop_loss,
                list(sourced.value or []),
                costs,
                now_ms,
            )
            if outcome is None:
                continue
            self.store.set_outcome(
                s.id,
                outcome.outcome,
                outcome.net_return,
                outcome.hit,
                outcome.exit_price,
                self.clock(),
            )
            done += 1
        return done

    # ---- reports ----

    def report(self, report_type: str, coins: Sequence[str]) -> ReportResult:
        coins = [
            exchange_symbols.coin_of(c) for c in coins if exchange_symbols.coin_of(c)
        ]
        if not coins:
            raise ValueError("no coins for the report")
        snaps = [self.market.snapshot(c) for c in coins]
        one = len(snaps) == 1
        market = "\n\n".join(s.text(closes=one) for s in snaps)
        version = self.prompt("report")
        text = render(
            version.template,
            report_type=report_type,
            coins=", ".join(f"{s.coin} ({s.pair})" for s in snaps),
            market_data=market,
        )
        routed = self.router.complete(
            text, purpose="report", max_tokens=MAX_TOKENS["report"]
        )
        return ReportResult(
            routed.completion.text,
            report_type,
            coins,
            routed.provider,
            routed.model,
            version.version,
            self.clock(),
            routed,
        )

    # ---- cost estimate ----

    def estimate(self, coins: Sequence[str], minutes: float) -> List[CostEstimate]:
        """What one refresh (an analysis and a signal for each coin) and a day of
        refreshes every ``minutes`` would cost with each provider in the order that
        is set up: 0 for Ollama, None while a paid model's price is not set."""
        settings = self.router.settings()
        out = []
        for p in llm_settings.order(settings):
            cfg = settings["providers"][p]
            if not cfg["enabled"]:
                continue
            if p in llm_settings.KEYED and not self.router.api_key(p):
                continue
            model = cfg["model"] or self.router.recommended(p) or ""
            price = llm_settings.price_of(settings, p, model) if model else None
            if p not in llm_settings.PAID:
                per = 0.0
            elif price is None:
                per = None
            else:
                per = 0.0
                for kind in ("analysis", "signal"):
                    tokens = self.store.average_tokens(p, model, kind) or {
                        "input": (len(self.prompt(kind).template) + MARKET_DATA_CHARS)
                        / CHARS_PER_TOKEN,
                        "output": MAX_TOKENS[kind],
                    }
                    per += (
                        tokens["input"] * price["input"]
                        + tokens["output"] * price["output"]
                    ) / 1e6
                per *= len(coins)
            per_day = None if per is None else per * (1440.0 / max(1.0, float(minutes)))
            out.append(CostEstimate(p, model, per, per_day))
        return out
