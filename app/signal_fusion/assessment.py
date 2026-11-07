"""
The entry assessment and its effect (FDS-SIG-004 sections 5.8.3 to 5.8.5).

**Four settings, each Off by default:** the entry assessment (the predictive veto: Off,
Log only, Veto), the volatility shrink, the participation cap and the spread cap (each
Off, Log only, On). A setting that cannot be On yet is not offered (section 6.7); this
module only applies what it is given.

**Two stages.** The predictive veto runs right after the LLM hook, before sizing
(``predictive``). The protective part runs right after the trader's own sizing, before the
order's risk check (``protective``), in this order: the shrink, the minimum check, the
spread cap, then the participation cap on the shrunk amount. The first part that skips
ends the assessment, and the record names it.

**What happens when something is missing:**

* a part that is Off computes nothing and has no effect;
* a part in Log only has no effect, whatever it computes or however it fails; its result
  and any failure are recorded;
* the predictive veto On with its inputs unavailable fails open: no veto, the reason
  recorded;
* a protective part On with its input missing, stale or in error fails closed: the entry
  is skipped, with the reason;
* there is no blanket handler: each part is evaluated and fails by its own rule, and no
  exception from an enabled protective part can become "allow".

**Invariants:** the result is only "allow" (unchanged), "skip", or a scale in (0, 1]. A
shrunk entry below the venue's minimum entry is skipped, never raised. Exits, sells, DCA
buys and stops never call this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

OFF = "off"
LOG_ONLY = "log_only"
VETO = "veto"
ON = "on"
PREDICTIVE_MODES = (OFF, LOG_ONLY, VETO)
PROTECTIVE_MODES = (OFF, LOG_ONLY, ON)


@dataclass(frozen=True)
class Settings:
    entry_assessment: str = OFF
    volatility_shrink: str = OFF
    participation_cap: str = OFF
    spread_cap: str = OFF
    participation_pi: float = 0.01
    spread_max: float = 0.005
    quote_max_age_s: float = 60.0

    def __post_init__(self):
        if self.entry_assessment not in PREDICTIVE_MODES:
            raise ValueError(f"entry assessment: {self.entry_assessment!r}")
        for name in ("volatility_shrink", "participation_cap", "spread_cap"):
            if getattr(self, name) not in PROTECTIVE_MODES:
                raise ValueError(f"{name}: {getattr(self, name)!r}")

    def all_off(self) -> bool:
        return (
            self.entry_assessment == OFF
            and self.volatility_shrink == OFF
            and self.participation_cap == OFF
            and self.spread_cap == OFF
        )


@dataclass
class Part:
    name: str
    mode: str
    available: bool = False
    reason: str = ""
    value: Optional[float] = None
    would: str = "allow"  # what it would do: allow, veto, skip or scale
    scale: float = 1.0


@dataclass
class Result:
    effect: str = "allow"  # allow, skip or scale
    scale: float = 1.0
    part: str = ""
    reason: str = ""
    parts: List[Part] = field(default_factory=list)

    def __post_init__(self):
        self.check()

    def check(self) -> None:
        if self.effect not in ("allow", "skip", "scale"):
            raise ValueError(
                f"an assessment can only allow, skip or scale: {self.effect}"
            )
        if not 0.0 < self.scale <= 1.0:
            raise ValueError("a scale is in (0, 1]: nothing makes an entry larger")


def _run(fn: Callable[[], Any]):
    """(value, error text)."""
    try:
        return fn(), ""
    except Exception as exc:  # each part fails by its own rule, below
        return None, f"{type(exc).__name__}: {exc}"


# --- the predictive veto ---------------------------------------------------------------------


def predictive(
    settings: Settings, expected_value: Callable[[], Optional[float]]
) -> Result:
    """The predictive veto. ``expected_value`` gives EV after costs (section 5.8.1), or
    None, or raises, when its inputs are unavailable. It fails open."""
    mode = settings.entry_assessment
    part = Part("entry_assessment", mode)
    if mode == OFF:
        return Result(parts=[part])
    ev, error = _run(expected_value)
    if error or ev is None:
        part.reason = error or "the assessment is unavailable"
        return Result(parts=[part])  # fails open, recorded
    part.available = True
    part.value = float(ev)
    part.would = "veto" if ev <= 0 else "allow"
    if mode == VETO and part.would == "veto":
        return Result(
            "skip", 1.0, part.name, "expected value after costs at or below 0", [part]
        )
    return Result(parts=[part])


# --- the protective part ----------------------------------------------------------------------


def _protective_part(name: str, mode: str, check: Callable[[], Any]) -> Part:
    """Run one protective check. ``check`` returns (ok, value, reason) with ok None when
    its input is missing; or raises."""
    part = Part(name, mode)
    if mode == OFF:
        return part
    out, error = _run(check)
    if error:
        part.reason = error
        part.would = "skip"  # an error in an enabled limit never lets the entry through
        return part
    ok, value, reason = out
    part.value = value
    if ok is None:
        part.reason = reason or "its input is missing"
        part.would = "skip"
        return part
    part.available = True
    part.would = "allow" if ok else "skip"
    part.reason = "" if ok else reason
    return part


def protective(
    settings: Settings,
    amount_usd: float,
    minimum_entry_usd: Optional[float],
    shrink_scale: Callable[[], Optional[float]],
    spread_check: Callable[[], Any],
    participation_check: Callable[[float], Any],
) -> Result:
    """The protective part, on the amount the trader's own sizing gave. Each check is
    given as a function, so that a part that is Off computes nothing."""
    parts: List[Part] = []
    scale = 1.0

    # the shrink
    sp = Part("volatility_shrink", settings.volatility_shrink)
    if settings.volatility_shrink != OFF:
        s, error = _run(shrink_scale)
        if error or s is None or not (0.0 < float(s) <= 1.0):
            sp.reason = error or "the volatility forecast is unavailable"
            sp.would = "skip"
        else:
            sp.available = True
            sp.value = float(s)
            sp.would = "scale" if s < 1.0 else "allow"
            sp.scale = float(s)
    parts.append(sp)
    if sp.mode == ON:
        if sp.would == "skip":
            return Result("skip", 1.0, sp.name, sp.reason, parts)
        scale = sp.scale
    amount = float(amount_usd) * scale

    # the minimum check: a shrunk entry below the minimum is skipped, never raised
    if scale < 1.0 and minimum_entry_usd and amount < float(minimum_entry_usd):
        mp = Part(
            "minimum",
            ON,
            True,
            "below the venue's minimum entry once shrunk",
            amount,
            "skip",
        )
        parts.append(mp)
        return Result("skip", 1.0, mp.name, mp.reason, parts)

    # the spread cap, then the participation cap on the (shrunk) amount
    for name, mode, check in (
        ("spread_cap", settings.spread_cap, spread_check),
        (
            "participation_cap",
            settings.participation_cap,
            lambda: participation_check(amount),
        ),
    ):
        p = _protective_part(name, mode, check)
        parts.append(p)
        if mode == ON and p.would == "skip":
            return Result("skip", 1.0, p.name, p.reason or "over the limit", parts)

    if scale < 1.0:
        return Result("scale", scale, "volatility_shrink", "", parts)
    return Result(parts=parts)


def record(
    when_s: int,
    coin: str,
    venues: Dict[str, str],
    source: str,
    pre: Result,
    post: Optional[Result],
    fields: Dict[str, Any],
) -> Dict[str, Any]:
    """The assessment's record (section 5.8.2)."""
    final = post if (pre.effect == "allow" and post is not None) else pre

    def parts(r: Optional[Result]):
        return [p.__dict__ for p in r.parts] if r else []

    return {
        "when_s": int(when_s),
        "coin": coin,
        "venues": dict(venues),
        "source": source,
        "effect": final.effect,
        "scale": final.scale,
        "part": final.part,
        "reason": final.reason,
        "parts": parts(pre) + parts(post),
        **fields,
    }
