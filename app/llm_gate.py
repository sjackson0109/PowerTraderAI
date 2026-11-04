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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import training_settings

GATE_MODE = "paper"  # the signals the gate counts


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
