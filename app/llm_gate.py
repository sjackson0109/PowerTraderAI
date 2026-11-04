"""
The LLM signal gate: when a provider, model and prompt version may move beyond
"log only".

A (provider, model, prompt version) passes once the signals it made while trading
was in paper mode include at least ``holdout_min_signals`` scored ones (a buy or a
sell whose outcome is known, llm_signals.score_signal), and at least
``holdout_min_hit_rate`` of them won after fees (training_settings). Only paper
signals count, so live trading uses one only after it has passed in paper mode. A
new prompt version, or a model that answered after a fallback, starts with no
scored signals: it is logged only until it passes.

The trader's entry hook (``EntryHook.check``)
---------------------------------------------
pt_trader calls it when the strategy or the neural levels are about to open a trade
(never for a sale, a DCA buy or anything else). An LLM signal can only confirm or
veto that entry: the hook never places an order. By ``llm.signal_mode``:

* ``off``: nothing is asked for; the entry goes ahead.
* ``log_only`` (the default): a signal is asked for on a background thread and kept
  (Trade Signals), unless one for the coin is younger than ``signal_reuse_minutes``;
  the entry goes ahead at once.
* ``confirm``, ``veto``, ``confirm_and_veto``: the trader waits at most
  ``signal_timeout_s`` for a signal (a recent one is used again). It counts only
  when its provider/model is ticked for trading (``signal_use``) and its provider,
  model and prompt version have passed the gate:

  ======================  ==========  ==========  ===================
  usable signal           confirm     veto        confirm_and_veto
  ======================  ==========  ==========  ===================
  BUY                     enter       enter       enter (confirmed)
  HOLD                    skip        enter       skip (not confirmed)
  SELL                    skip        skip        skip (vetoed)
  none usable             enter       enter       enter
  ======================  ==========  ==========  ===================

  "None usable" is no answer in time, a failed request, an answer with no
  direction, a provider/model not ticked, or one that has not passed the gate: its
  signal is logged only and the entry goes ahead as the strategy decided. Each of
  these decisions is kept (``llm_store.decisions``, with the trade's client order
  id, and the filled order's id once placed) and printed in the trader's log with
  its reason.

Any error in the hook lets the entry go ahead; a slow provider costs at most the
wait. ``REQUESTS_ENABLED`` is switched off for the test session (app/conftest.py),
so no trader test asks a provider for anything.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

import llm_settings
import training_settings
from llm_settings import provider_name, use_key

GATE_MODE = "paper"  # the signals the gate counts
REQUESTS_ENABLED = True  # tests switch it off (app/conftest.py)


@dataclass(frozen=True)
class GateStatus:
    provider: str
    model: str
    prompt_version: int
    scored: int
    hits: int
    min_signals: int
    min_hit_rate: float

    @property
    def hit_rate(self) -> Optional[float]:
        return self.hits / self.scored if self.scored else None

    @property
    def passed(self) -> bool:
        rate = self.hit_rate
        return (
            self.scored >= self.min_signals
            and rate is not None
            and rate >= self.min_hit_rate
        )

    def text(self) -> str:
        """One line for Settings and the decision log."""
        rate = self.hit_rate
        rate_text = "no hit rate yet" if rate is None else f"{rate:.0%} after fees"
        if self.passed:
            return f"passed: {self.hits} of {self.scored} won, {rate_text}"
        if self.scored < self.min_signals:
            return f"not passed: {self.scored} of {self.min_signals} signals scored" + (
                "" if rate is None else f", {rate_text}"
            )
        return f"not passed: {rate_text}, {self.min_hit_rate:.0%} needed"


def gate_status(
    store: Any,
    provider: str,
    model: str,
    prompt_version: int,
    training: Optional[dict] = None,
) -> GateStatus:
    """The gate for one provider/model/prompt version, from the paper signals
    scored so far. ``training`` is the training section (read fresh when None)."""
    training = training or training_settings.read_training_settings()
    scored = store.scored(provider, model, int(prompt_version), GATE_MODE)
    return GateStatus(
        provider=provider,
        model=model,
        prompt_version=int(prompt_version),
        scored=len(scored),
        hits=sum(1 for s in scored if s.hit),
        min_signals=int(training["holdout_min_signals"]),
        min_hit_rate=float(training["holdout_min_hit_rate"]),
    )


# --- the trader's entry hook ----------------------------------------------------------

DECISION_WORDS = {
    "off": "off",
    "logged": "logged only",
    "confirmed": "confirmed",
    "not_confirmed": "not confirmed: the entry is skipped",
    "vetoed": "vetoed: the entry is skipped",
    "not_vetoed": "not vetoed",
    "no_signal": "no usable signal",
}


@dataclass(frozen=True)
class EntryVerdict:
    allow: bool
    decision: str  # a DECISION_WORDS key
    reason: str
    signal_id: Optional[int] = None


def _describe(signal: Any) -> str:
    confidence = (
        "" if signal.confidence is None else f" ({signal.confidence:.0f}% confidence)"
    )
    return (
        f"{provider_name(signal.provider)} {signal.model}, signal prompt "
        f"v{signal.prompt_version}, signal {signal.id}: {signal.direction}{confidence}"
    )


def decide(mode: str, signal: Any, why: str = "") -> EntryVerdict:
    """The table in the module docstring. ``signal`` is a usable signal record, or
    None (``why`` says why there is none)."""
    if signal is None:
        reason = (why or "no signal") + "; the entry goes ahead as the strategy decided"
        return EntryVerdict(True, "no_signal", reason)
    text, sid, direction = _describe(signal), signal.id, signal.direction
    if mode == "veto":
        if direction == "SELL":
            return EntryVerdict(False, "vetoed", text, sid)
        return EntryVerdict(True, "not_vetoed", text, sid)
    if direction == "BUY":
        return EntryVerdict(True, "confirmed", text, sid)
    if mode == "confirm_and_veto" and direction == "SELL":
        return EntryVerdict(False, "vetoed", text, sid)
    return EntryVerdict(False, "not_confirmed", text, sid)


class EntryHook:
    """See the module docstring. ``settings_source`` is the trader's (None:
    pt_config.json, read on every call); ``engine_factory`` builds the
    LLMResearchEngine that asks for a signal (tests pass a fake)."""

    def __init__(
        self,
        settings_source: Any = None,
        engine_factory: Optional[Callable[[], Any]] = None,
        store: Any = None,
        clock: Callable[[], float] = time.time,
    ):
        self._source = settings_source
        self._factory = engine_factory
        self._store = store
        self._engine = None
        self.clock = clock
        self._lock = threading.Lock()
        self._inflight: Dict[str, Tuple[threading.Thread, dict]] = {}
        self._decisions: Dict[str, int] = {}  # client order id -> decision id
        self._failed: Dict[str, float] = {}  # coin -> when its last request failed
        self._last: Dict[str, tuple] = {}  # coin -> its last decision

    def store(self):
        if self._store is None:
            from llm_store import LLMStore

            self._store = LLMStore()
        return self._store

    def engine(self):
        if self._engine is None:
            if self._factory is not None:
                self._engine = self._factory()
            else:
                from llm_providers import LLMRouter
                from llm_research_engine import LLMResearchEngine

                store = self.store()
                router = LLMRouter(
                    settings=lambda: llm_settings.read_llm_settings(self._source),
                    store=store,
                )
                self._engine = LLMResearchEngine(router=router, store=store)
        return self._engine

    def threads(self):
        return [t for t, _ in self._inflight.values()]

    # ---- signals ----

    def _recent(self, coin: str, cfg: dict, trading_mode: str):
        latest = self.store().latest_signal(coin)
        if latest is None or latest.trading_mode != trading_mode:
            return None
        if self.clock() - latest.ts > cfg["signal_reuse_minutes"] * 60.0:
            return None
        return latest

    def running(self, coin: str) -> bool:
        found = self._inflight.get(coin)
        return found is not None and found[0].is_alive()

    def _backing_off(self, coin: str, cfg: dict) -> Optional[str]:
        """Why no request is made for ``coin`` now: its last one failed less than
        the reuse time ago (at least a minute), so a provider that is down is not
        asked on every pass of the trader's loop."""
        failed = self._failed.get(coin)
        if failed is None:
            return None
        if self.clock() - failed < max(60.0, cfg["signal_reuse_minutes"] * 60.0):
            when = time.strftime("%H:%M:%S", time.localtime(failed))
            return f"no signal (the last request for {coin}, at {when}, got none)"
        return None

    def _start(self, coin: str, trading_mode: str) -> Tuple[threading.Thread, dict]:
        """A signal request for ``coin`` on a background thread (one at a time per
        coin: a request still running is waited on, not repeated)."""
        with self._lock:
            running = self._inflight.get(coin)
            if running is not None and running[0].is_alive():
                return running
            holder: dict = {}

            def work() -> None:
                try:
                    holder["result"] = self.engine().signal(
                        coin, source="entry", trading_mode=trading_mode
                    )
                    self._failed.pop(coin, None)
                except Exception as exc:  # kept for the waiting trader, never raised
                    holder["error"] = exc
                    self._failed[coin] = self.clock()

            thread = threading.Thread(
                target=work, name=f"llm-entry-{coin}", daemon=True
            )
            self._inflight[coin] = (thread, holder)
            thread.start()
            return thread, holder

    def unusable(self, signal: Any, cfg: dict) -> str:
        """Why ``signal`` may not confirm or veto an entry ("" when it may)."""
        if signal.direction not in ("BUY", "SELL", "HOLD"):
            return "the signal had no direction"
        who = f"{provider_name(signal.provider)} {signal.model}"
        if not cfg["signal_use"].get(use_key(signal.provider, signal.model)):
            return f"{who} is not ticked for use in trading (signal {signal.id})"
        gate = gate_status(
            self.store(),
            signal.provider,
            signal.model,
            signal.prompt_version,
            training_settings.read_training_settings(self._source),
        )
        if not gate.passed:
            return (
                f"{who}, signal prompt v{signal.prompt_version} has not passed the "
                f"gate ({gate.text()}; signal {signal.id})"
            )
        return ""

    def _usable_signal(self, coin: str, cfg: dict, trading_mode: str):
        signal = self._recent(coin, cfg, trading_mode)
        if signal is None:
            if not REQUESTS_ENABLED:
                return None, "LLM requests are off"
            if self.running(coin):  # asked for at an earlier pass: not waited on again
                return None, f"a signal for {coin} is still being asked for"
            backing_off = self._backing_off(coin, cfg)
            if backing_off:
                return None, backing_off
            thread, holder = self._start(coin, trading_mode)
            wait = cfg["signal_timeout_s"]
            thread.join(wait)
            if thread.is_alive():
                return None, f"no signal within {wait:g} s"
            if "error" in holder:
                return None, f"no signal ({holder['error']})"[:300]
            signal = holder["result"].record
        why = self.unusable(signal, cfg)
        return (None, why) if why else (signal, "")

    # ---- the hook ----

    def check(self, coin: str, trade_ref: str = "", live: bool = False) -> EntryVerdict:
        """May the entry the strategy wants for ``coin`` go ahead? Never raises."""
        try:
            cfg = llm_settings.read_llm_settings(self._source)
        except Exception:
            return EntryVerdict(True, "off", "")
        mode = cfg["signal_mode"]
        if mode == "off":
            return EntryVerdict(True, "off", "")
        trading_mode = "live" if live else "paper"
        if mode == "log_only":
            try:
                if (
                    REQUESTS_ENABLED
                    and not self.running(coin)
                    and not self._backing_off(coin, cfg)
                    and self._recent(coin, cfg, trading_mode) is None
                ):
                    self._start(coin, trading_mode)
            except Exception:
                pass
            return EntryVerdict(True, "logged", "")
        try:
            signal, why = self._usable_signal(coin, cfg, trading_mode)
            verdict = decide(mode, signal, why)
        except Exception as exc:
            verdict = decide(mode, None, f"the LLM check failed ({type(exc).__name__})")
        # The loop asks again on every pass while the strategy wants the entry: a
        # skip for the same reason is kept and printed once
        repeat = (mode, verdict.decision, verdict.signal_id, verdict.reason)
        if not verdict.allow and self._last.get(coin) == repeat:
            return verdict
        self._last[coin] = repeat
        try:
            decision_id = self.store().add_decision(
                coin,
                mode,
                verdict.decision,
                verdict.reason,
                verdict.allow,
                verdict.signal_id,
                trade_ref,
                trading_mode,
                self.clock(),
            )
            if trade_ref and verdict.allow:
                self._decisions[trade_ref] = decision_id
        except Exception:
            pass
        try:
            print(
                f"LLM signal for {coin} ({llm_settings.SIGNAL_MODE_NAMES[mode].lower()}): "
                f"{DECISION_WORDS[verdict.decision]}. {verdict.reason}"
                + (f" [order {trade_ref}]" if trade_ref else "")
            )
        except Exception:
            pass
        return verdict

    def placed(self, trade_ref: str, order_id: Any) -> None:
        """The entry ``trade_ref`` was filled as order ``order_id``: the decision
        that let it through is linked to it. Never raises."""
        decision_id = self._decisions.pop(trade_ref, None)
        if decision_id is None or not order_id:
            return
        try:
            self.store().link_decision(decision_id, str(order_id))
        except Exception:
            pass
