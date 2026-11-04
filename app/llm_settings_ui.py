"""
Settings > LLM Providers: every LLM choice the app makes, in one window.

* **Providers** - Ollama (this computer), OpenAI, Anthropic and NVIDIA: each one's
  status (not configured, not tested, connected, error), its model (the Recommended
  one or any other the provider lists; Refresh models fetches the list), Set up
  (the API key, kept in the OS credential store; the base URL for Ollama and
  NVIDIA; requests a minute; a monthly spend cap; the model's price) and Test
  connection.
* **Order** - the preferred provider and the fallbacks, in the order they are asked,
  and how long a health check and an answer may take.
* **Signals in trading** - whether LLM signals confirm or veto the entries the
  strategy wants to make, how long the trader waits for one, how long a coin's
  signal is used again, and which provider/models may take part, with each one's
  gate.

Save writes the ``llm`` section of pt_config.json (llm_settings); an API key is
stored in the OS credential store when Save is pressed in its Set up box, and never
in a file. Slow work (model lists, connection tests) runs off the Tk thread
(ui_jobs) and stops when the window closes.
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

import llm_gate
import llm_settings
import training_settings
import ui_table
import ui_tokens
from llm_settings import (
    BASE_URL_SET_UP,
    KEYED,
    PAID,
    PROVIDERS,
    SIGNAL_MODE_NAMES,
    SIGNAL_MODES,
    provider_name,
    use_key,
)
from ui_jobs import BackgroundJobs

TITLE = "LLM Providers"
WRAP = 600

STATE_STYLES = {
    "connected": "Good.TLabel",
    "error": "Bad.TLabel",
    "not configured": "Warn.TLabel",
    "not tested": "Muted.TLabel",
}
MODE_HELP = {
    "off": "No signal is asked for when a trade is about to open.",
    "log_only": (
        "A signal is asked for and kept when a trade is about to open; the trade "
        "goes ahead as the strategy decided."
    ),
    "confirm": "A trade opens only when the signal says buy.",
    "veto": "A trade does not open when the signal says sell.",
    "confirm_and_veto": (
        "A buy signal confirms a trade and a sell signal vetoes it; a trade with a "
        "hold signal does not open."
    ),
}
NO_SIGNAL_HELP = (
    "With no signal that may be used (none within the wait, or one from a provider, "
    "model and prompt version that has not passed its gate or is not ticked below), "
    "the trade goes ahead as the strategy decided. A signal never opens a trade."
)
RECOMMENDED = "Recommended"


def _model_choices(
    recommended: Optional[str], ids: List[str], chosen: str
) -> List[str]:
    first = (
        f"{RECOMMENDED}: {recommended}"
        if recommended
        else f"{RECOMMENDED} (refresh the list)"
    )
    rest = list(ids)
    if chosen and chosen not in rest:
        rest.insert(0, chosen)
    return [first] + rest


def _number_text(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:g}"


def _parse(text: str, label: str, low: float, high: float, optional: bool = False):
    text = str(text or "").strip().replace("$", "").replace(",", "")
    if not text:
        if optional:
            return None
        raise ValueError(f"{label}: enter a number")
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{label}: {text!r} is not a number") from None
    if not low <= number <= high:
        raise ValueError(f"{label}: between {low:g} and {high:g}")
    return number


class ProviderSetup(tk.Toplevel):
    """Set up one provider: its key, base URL, requests a minute, monthly spend cap,
    the price of its model, and whether it is used."""

    def __init__(self, window: "LLMProvidersWindow", provider: str):
        super().__init__(window)
        self.window = window
        self.provider = provider
        self.title(f"Set up {provider_name(provider)}")
        self.transient(window)
        self.resizable(False, False)
        cfg = window.working["providers"][provider]
        self.model = window.model_in_use(provider)
        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=ui_tokens.SPACE["lg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        r = 0

        self.key_var = tk.StringVar(master=self)
        self.key_entry = None
        if provider in KEYED:
            ttk.Label(body, text="API key:").grid(row=r, column=0, sticky="w", pady=gap)
            self.key_entry = ttk.Entry(
                body, textvariable=self.key_var, show="*", width=48
            )
            self.key_entry.grid(row=r, column=1, sticky="ew", pady=gap)
            r += 1
            ttk.Label(
                body,
                text=window.key_hint(provider),
                style="Muted.TLabel",
                wraplength=420,
                justify="left",
            ).grid(row=r, column=1, sticky="w")
            r += 1

        self.url_var = tk.StringVar(master=self, value=cfg["base_url"])
        if provider in BASE_URL_SET_UP:
            ttk.Label(body, text="Base URL:").grid(
                row=r, column=0, sticky="w", pady=gap
            )
            ttk.Entry(body, textvariable=self.url_var, width=48).grid(
                row=r, column=1, sticky="ew", pady=gap
            )
            r += 1

        self.rpm_var = tk.StringVar(
            master=self, value=_number_text(cfg["requests_per_minute"])
        )
        ttk.Label(body, text="Requests per minute:").grid(
            row=r, column=0, sticky="w", pady=gap
        )
        ttk.Entry(body, textvariable=self.rpm_var, width=12).grid(
            row=r, column=1, sticky="w", pady=gap
        )
        r += 1

        self.cap_var = tk.StringVar(
            master=self, value=_number_text(cfg["monthly_cap_usd"])
        )
        price = (
            (window.working.get("prices") or {}).get(provider, {}).get(self.model or "")
        )
        self.in_var = tk.StringVar(
            master=self, value=_number_text(price and price["input"])
        )
        self.out_var = tk.StringVar(
            master=self, value=_number_text(price and price["output"])
        )
        if provider in PAID:
            ttk.Label(body, text="Monthly spend cap ($):").grid(
                row=r, column=0, sticky="w", pady=gap
            )
            ttk.Entry(body, textvariable=self.cap_var, width=12).grid(
                row=r, column=1, sticky="w", pady=gap
            )
            r += 1
            ttk.Label(
                body,
                text="Empty for no cap. Once this month's spend reaches it, the next "
                "provider is asked instead.",
                style="Muted.TLabel",
                wraplength=420,
                justify="left",
            ).grid(row=r, column=1, sticky="w")
            r += 1
            title = f"Price of {self.model}" if self.model else "Price of the model"
            ttk.Label(body, text=f"{title} ($ per million tokens):").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(gap * 2, 0)
            )
            r += 1
            prices = ttk.Frame(body)
            prices.grid(row=r, column=0, columnspan=2, sticky="w", pady=gap)
            ttk.Label(prices, text="Input").pack(side="left", padx=(0, 4))
            self.in_entry = ttk.Entry(prices, textvariable=self.in_var, width=10)
            self.in_entry.pack(side="left", padx=(0, gap * 2))
            ttk.Label(prices, text="Output").pack(side="left", padx=(0, 4))
            self.out_entry = ttk.Entry(prices, textvariable=self.out_var, width=10)
            self.out_entry.pack(side="left")
            if not self.model:
                for entry in (self.in_entry, self.out_entry):
                    entry.state(["disabled"])
            r += 1

        self.enabled_var = tk.BooleanVar(master=self, value=bool(cfg["enabled"]))
        ttk.Checkbutton(body, text="Use this provider", variable=self.enabled_var).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=gap
        )
        r += 1

        self.status_var = tk.StringVar(master=self)
        ttk.Label(
            body, textvariable=self.status_var, wraplength=420, justify="left"
        ).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(gap, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left")
        if provider in KEYED:
            ttk.Button(buttons, text="Remove saved key", command=self.remove_key).pack(
                side="left", padx=gap
            )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=gap
        )

    def save(self) -> bool:
        p = self.provider
        try:
            rpm = _parse(self.rpm_var.get(), "Requests per minute", 1, 10000)
            cap = (
                _parse(
                    self.cap_var.get(), "Monthly spend cap", 0, 100000, optional=True
                )
                if p in PAID
                else None
            )
            pin = pout = None
            if p in PAID and self.model:
                pin = _parse(self.in_var.get(), "Input price", 0, 10000, optional=True)
                pout = _parse(
                    self.out_var.get(), "Output price", 0, 10000, optional=True
                )
                if (pin is None) != (pout is None):
                    raise ValueError("Enter both prices, or neither")
            url = self.url_var.get().strip().rstrip("/")
            if p in BASE_URL_SET_UP and not url.startswith(("http://", "https://")):
                raise ValueError("Base URL: starts with http:// or https://")
        except ValueError as exc:
            self.status_var.set(str(exc))
            return False
        key = self.key_var.get().strip()
        if p in KEYED and key:
            try:
                self.window.secrets().set_secret(p, "api_key", key)
            except Exception as exc:
                self.status_var.set(str(exc))
                return False
        cfg = self.window.working["providers"][p]
        cfg.update(
            requests_per_minute=rpm,
            monthly_cap_usd=cap,
            enabled=bool(self.enabled_var.get()),
        )
        if p in BASE_URL_SET_UP:
            cfg["base_url"] = url
        if p in PAID and self.model:
            prices = self.window.working.setdefault("prices", {}).setdefault(p, {})
            if pin is None:
                prices.pop(self.model, None)
            else:
                prices[self.model] = {"input": pin, "output": pout}
        self.window.provider_changed(p, f"{provider_name(p)} set up.")
        self.destroy()
        return True

    def remove_key(self) -> None:
        try:
            self.window.secrets().delete_secret(self.provider, "api_key")
        except Exception as exc:
            self.status_var.set(str(exc))
            return
        self.window.provider_changed(self.provider, "The saved key was removed.")
        self.destroy()


class LLMProvidersWindow(tk.Toplevel):
    """See the module docstring. ``router`` is an LLMRouter (built on this window's
    working settings by default), ``manager_factory`` makes the SettingsManager that
    reads and saves pt_config.json."""

    def __init__(
        self,
        parent: tk.Misc,
        router: Any = None,
        store: Any = None,
        manager_factory: Optional[Callable[[], Any]] = None,
        on_saved: Optional[Callable[[], None]] = None,
        messagebox=None,
        palette: Optional[dict] = None,
        secrets: Any = None,
    ):
        super().__init__(parent)
        self.title(TITLE)
        self.geometry("960x760")
        self.minsize(760, 520)
        palette = palette or {}
        if palette.get("BG"):
            self.configure(bg=palette["BG"])
        if manager_factory is None:
            from pt_settings_manager import SettingsManager

            manager_factory = SettingsManager
        self._factory = manager_factory
        self._on_saved = on_saved
        self._box = messagebox or _messagebox
        self._secrets = secrets
        manager = manager_factory()
        self.saved = llm_settings.read_llm_settings(manager)
        self.working = copy.deepcopy(self.saved)
        self.training = training_settings.read_training_settings(manager)
        if router is None:
            from llm_providers import LLMRouter

            router = LLMRouter(
                settings=lambda: self.working, store=store, secrets=secrets
            )
        self.router = router
        self.store = store if store is not None else router.store
        self.jobs = BackgroundJobs(self, name="llm-settings")
        self.status_var = tk.StringVar(master=self)
        self.rows: Dict[str, Dict[str, Any]] = {}
        self._build(palette.get("BG"))
        for p in PROVIDERS:
            self._show_provider(p)
        self._show_fallbacks()
        self._show_signal_rows()

    # ---- helpers ----

    def secrets(self):
        if self._secrets is None:
            import pt_secrets

            self._secrets = pt_secrets
        return self._secrets

    def key_hint(self, provider: str) -> str:
        source = self.router.key_source(provider)
        if source == "environment":
            names = ", ".join(self.secrets().env_var_names(provider))
            return f"The key comes from {names}, which is used before a saved key."
        if source == "keyring":
            return "A key is saved. Leave the box empty to keep it."
        return (
            "No key is saved. It is stored in the operating system's credential "
            "store when you press Save."
        )

    def model_in_use(self, provider: str) -> str:
        chosen = self.working["providers"][provider]["model"]
        return chosen or (self.router.recommended(provider) or "")

    # ---- layout ----

    def _build(self, bg: Optional[str]) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        viewport = ttk.Frame(self)
        viewport.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, highlightthickness=0, bd=0)
        if bg:
            canvas.configure(bg=bg)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def fit(_event=None) -> None:
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)
            if bbox and bbox[3] - bbox[1] > canvas.winfo_height() + 1:
                scroll.grid()
            else:
                scroll.grid_remove()
                canvas.yview_moveto(0)

        def resize(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)
            fit()

        body.bind("<Configure>", fit, add="+")
        canvas.bind("<Configure>", resize, add="+")

        def wheel(event) -> None:
            if scroll.winfo_ismapped():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.focus_set(), add="+")
        canvas.bind("<MouseWheel>", wheel, add="+")
        body.columnconfigure(0, weight=1)
        self.body = body

        r = 0
        r = self._build_providers(body, r)
        ttk.Separator(body, orient="horizontal").grid(
            row=r, column=0, sticky="ew", pady=10
        )
        r += 1
        r = self._build_order(body, r)
        ttk.Separator(body, orient="horizontal").grid(
            row=r, column=0, sticky="ew", pady=10
        )
        r += 1
        r = self._build_signals(body, r)

        ttk.Label(
            self, textvariable=self.status_var, wraplength=WRAP, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=8
        )

    def _build_providers(self, body: ttk.Frame, r: int) -> int:
        ttk.Label(body, text="Providers", style="Header.TLabel").grid(
            row=r, column=0, sticky="w"
        )
        r += 1
        grid = ttk.Frame(body)
        grid.grid(row=r, column=0, sticky="ew", pady=(4, 0))
        grid.columnconfigure(2, weight=1)
        gap = ui_tokens.SPACE["sm"]
        for i, p in enumerate(PROVIDERS):
            row = 2 * i
            ttk.Label(grid, text=provider_name(p), style="Header.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, gap), pady=(gap, 0)
            )
            status = ttk.Label(grid, width=16)
            status.grid(row=row, column=1, sticky="w", padx=(0, gap), pady=(gap, 0))
            model_var = tk.StringVar(master=self)
            model_box = ttk.Combobox(
                grid, textvariable=model_var, state="readonly", width=40
            )
            model_box.grid(row=row, column=2, sticky="ew", padx=(0, gap), pady=(gap, 0))
            model_box.bind(
                "<<ComboboxSelected>>", lambda _e, p=p: self._model_picked(p)
            )
            refresh = ttk.Button(
                grid, text="Refresh models", command=lambda p=p: self.refresh_models(p)
            )
            refresh.grid(row=row, column=3, sticky="w", padx=(0, gap), pady=(gap, 0))
            ttk.Button(
                grid, text="Set up...", command=lambda p=p: self.open_setup(p)
            ).grid(row=row, column=4, sticky="w", padx=(0, gap), pady=(gap, 0))
            test = ttk.Button(
                grid,
                text="Test connection",
                command=lambda p=p: self.test_connection(p),
            )
            test.grid(row=row, column=5, sticky="w", pady=(gap, 0))
            detail = ttk.Label(
                grid, style="Muted.TLabel", wraplength=WRAP, justify="left"
            )
            detail.grid(row=row + 1, column=1, columnspan=5, sticky="w")
            self.rows[p] = {
                "status": status,
                "model_var": model_var,
                "model_box": model_box,
                "refresh": refresh,
                "test": test,
                "detail": detail,
            }
        return r + 1

    def _build_order(self, body: ttk.Frame, r: int) -> int:
        gap = ui_tokens.SPACE["sm"]
        ttk.Label(body, text="Order", style="Header.TLabel").grid(
            row=r, column=0, sticky="w"
        )
        r += 1
        top = ttk.Frame(body)
        top.grid(row=r, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(top, text="Preferred provider:").pack(side="left", padx=(0, gap))
        self.preferred_var = tk.StringVar(
            master=self, value=provider_name(self.working["preferred"])
        )
        self.preferred_box = ttk.Combobox(
            top,
            textvariable=self.preferred_var,
            values=[provider_name(p) for p in PROVIDERS],
            state="readonly",
            width=16,
        )
        self.preferred_box.pack(side="left")
        self.preferred_box.bind(
            "<<ComboboxSelected>>", lambda _e: self._preferred_picked()
        )
        r += 1
        ttk.Label(
            body,
            text="When the preferred provider does not answer its health check in time, "
            "the fallbacks are asked in this order.",
            style="Muted.TLabel",
            wraplength=WRAP,
            justify="left",
        ).grid(row=r, column=0, sticky="w", pady=(gap, 0))
        r += 1
        holder = ttk.Frame(body, height=150)
        holder.grid(row=r, column=0, sticky="ew", pady=(4, 0))
        holder.pack_propagate(False)
        self.fallback_table = ui_table.DataTable(
            holder,
            ("order", "provider", "cost"),
            {"order": "#", "provider": "Provider", "cost": "Cost"},
            numeric=("order",),
            sortable=False,
            empty_text="No fallbacks",
            height=4,
            selectmode="browse",
        )
        self.fallback_table.pack(fill="both", expand=True)
        r += 1
        bar = ttk.Frame(body)
        bar.grid(row=r, column=0, sticky="w", pady=(gap, 0))
        self.add_var = tk.StringVar(master=self)
        self.add_box = ttk.Combobox(
            bar, textvariable=self.add_var, state="readonly", width=14
        )
        self.add_box.pack(side="left", padx=(0, gap))
        ttk.Button(bar, text="Add", command=self.add_fallback).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Move up", command=lambda: self.move_fallback(-1)).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Move down", command=lambda: self.move_fallback(1)).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Remove", command=self.remove_fallback).pack(side="left")
        r += 1
        times = ttk.Frame(body)
        times.grid(row=r, column=0, sticky="w", pady=(gap, 0))
        self.health_var = tk.StringVar(
            master=self, value=_number_text(self.working["health_timeout_s"])
        )
        self.answer_var = tk.StringVar(
            master=self, value=_number_text(self.working["request_timeout_s"])
        )
        ttk.Label(times, text="Health check timeout (s):").pack(
            side="left", padx=(0, 4)
        )
        ttk.Entry(times, textvariable=self.health_var, width=6).pack(
            side="left", padx=(0, gap * 2)
        )
        ttk.Label(times, text="Answer timeout (s):").pack(side="left", padx=(0, 4))
        ttk.Entry(times, textvariable=self.answer_var, width=6).pack(side="left")
        return r + 1

    def _build_signals(self, body: ttk.Frame, r: int) -> int:
        gap = ui_tokens.SPACE["sm"]
        ttk.Label(body, text="Signals in trading", style="Header.TLabel").grid(
            row=r, column=0, sticky="w"
        )
        r += 1
        top = ttk.Frame(body)
        top.grid(row=r, column=0, sticky="w", pady=(4, 0))
        ttk.Label(top, text="LLM signals:").pack(side="left", padx=(0, gap))
        self.mode_var = tk.StringVar(
            master=self, value=SIGNAL_MODE_NAMES[self.working["signal_mode"]]
        )
        self.mode_box = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            values=[SIGNAL_MODE_NAMES[m] for m in SIGNAL_MODES],
            state="readonly",
            width=26,
        )
        self.mode_box.pack(side="left")
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: self._show_mode_help())
        r += 1
        self.mode_help = ttk.Label(body, wraplength=WRAP, justify="left")
        self.mode_help.grid(row=r, column=0, sticky="w", pady=(gap, 0))
        r += 1
        ttk.Label(
            body,
            text=NO_SIGNAL_HELP,
            style="Muted.TLabel",
            wraplength=WRAP,
            justify="left",
        ).grid(row=r, column=0, sticky="w", pady=(2, 0))
        r += 1
        times = ttk.Frame(body)
        times.grid(row=r, column=0, sticky="w", pady=(gap, 0))
        self.wait_var = tk.StringVar(
            master=self, value=_number_text(self.working["signal_timeout_s"])
        )
        self.reuse_var = tk.StringVar(
            master=self, value=_number_text(self.working["signal_reuse_minutes"])
        )
        ttk.Label(times, text="Wait for a signal at an entry (s):").pack(
            side="left", padx=(0, 4)
        )
        ttk.Entry(times, textvariable=self.wait_var, width=6).pack(
            side="left", padx=(0, gap * 2)
        )
        ttk.Label(times, text="Use a coin's signal again for (min):").pack(
            side="left", padx=(0, 4)
        )
        ttk.Entry(times, textvariable=self.reuse_var, width=6).pack(side="left")
        r += 1
        t = self.training
        ttk.Label(
            body,
            text=(
                f"Gate: a provider, model and prompt version may confirm or veto "
                f"entries once at least {t['holdout_min_signals']} of the signals it "
                f"made in paper trading are scored and at least "
                f"{t['holdout_min_hit_rate']:.0%} of them won after fees (Settings, "
                "Training). Live trading uses only those that passed in paper trading."
            ),
            style="Muted.TLabel",
            wraplength=WRAP,
            justify="left",
        ).grid(row=r, column=0, sticky="w", pady=(gap, 0))
        r += 1
        holder = ttk.Frame(body, height=190)
        holder.grid(row=r, column=0, sticky="ew", pady=(4, 0))
        holder.pack_propagate(False)
        cols = ("provider", "model", "prompt", "scored", "hit_rate", "gate", "use")
        self.signal_table = ui_table.DataTable(
            holder,
            cols,
            {
                "provider": "Provider",
                "model": "Model",
                "prompt": "Prompt",
                "scored": "Scored",
                "hit_rate": "Hit rate",
                "gate": "Gate",
                "use": "Use in trading",
            },
            key="llm_settings.signal_gate",
            numeric=("scored", "hit_rate"),
            empty_text="No provider or model yet",
            height=5,
            selectmode="browse",
        )
        self.signal_table.pack(fill="both", expand=True)
        r += 1
        ttk.Button(
            body, text="Use in trading / Stop using", command=self.toggle_use
        ).grid(row=r, column=0, sticky="w", pady=(gap, 0))
        self._show_mode_help()
        return r + 1

    # ---- providers ----

    def _show_provider(self, p: str) -> None:
        row = self.rows[p]
        state = self.router.state(p)
        text = (
            state.state
            if not state.message or state.state == "not tested"
            else (
                f"{state.state}: {state.message}"
                if state.state == "error"
                else state.state
            )
        )
        row["status"].configure(
            text=text, style=STATE_STYLES.get(state.state, "TLabel")
        )
        cfg = self.working["providers"][p]
        ids = self.router.cached_models(p)
        rec = self.router.recommended(p)
        values = _model_choices(rec, ids, cfg["model"])
        row["model_box"].configure(values=values)
        row["model_var"].set(cfg["model"] or values[0])
        row["detail"].configure(text=self._detail(p))

    def _detail(self, p: str) -> str:
        cfg = self.working["providers"][p]
        parts = []
        if not cfg["enabled"]:
            parts.append("Not used")
        if p in KEYED:
            source = self.router.key_source(p)
            parts.append(
                {
                    "environment": "key from an environment variable",
                    "keyring": "key in the OS credential store",
                }.get(source, "no API key")
            )
        if p in BASE_URL_SET_UP:
            parts.append(cfg["base_url"])
        if p not in PAID:
            parts.append("free: runs on this computer")
        else:
            model = self.model_in_use(p)
            price = llm_settings.price_of(self.working, p, model) if model else None
            parts.append(
                f"${price['input']:g} in, ${price['output']:g} out per million tokens"
                if price
                else "price not set"
            )
            cap = cfg["monthly_cap_usd"]
            if cap is not None:
                try:
                    spent = self.store.month_spend(p)
                except Exception:
                    spent = 0.0
                parts.append(f"${spent:,.2f} of ${cap:,.2f} spent this month")
        parts.append(f"{cfg['requests_per_minute']:g} requests a minute")
        return "; ".join(parts)

    def _model_picked(self, p: str) -> None:
        value = self.rows[p]["model_var"].get()
        self.working["providers"][p]["model"] = (
            "" if value.startswith(RECOMMENDED) else value
        )
        self.rows[p]["detail"].configure(text=self._detail(p))
        self._show_signal_rows()

    def provider_changed(self, p: str, message: str = "") -> None:
        self._show_provider(p)
        self._show_signal_rows()
        if message:
            self.status_var.set(message)

    def refresh_models(self, p: str) -> None:
        row = self.rows[p]
        row["refresh"].state(["disabled"])
        self.status_var.set(f"Fetching {provider_name(p)}'s models...")

        def done(models) -> None:
            row["refresh"].state(["!disabled"])
            self._show_provider(p)
            self.status_var.set(f"{provider_name(p)}: {len(models)} models")

        def failed(exc) -> None:
            row["refresh"].state(["!disabled"])
            self.status_var.set(f"{provider_name(p)}: no model list ({exc})")

        self.jobs.submit(lambda: self.router.list_models(p), done, failed)

    def test_connection(self, p: str) -> None:
        row = self.rows[p]
        row["test"].state(["disabled"])
        self.status_var.set(f"Testing {provider_name(p)}...")

        def done(result) -> None:
            row["test"].state(["!disabled"])
            self._show_provider(p)
            word = "connected" if result.ok else "error"
            self.status_var.set(f"{provider_name(p)}: {word} ({result.message})")

        def failed(exc) -> None:
            row["test"].state(["!disabled"])
            self.status_var.set(f"{provider_name(p)}: error ({exc})")

        self.jobs.submit(lambda: self.router.test_connection(p), done, failed)

    def open_setup(self, p: str) -> ProviderSetup:
        return ProviderSetup(self, p)

    # ---- order ----

    def _preferred_picked(self) -> None:
        p = llm_settings.provider_id(self.preferred_var.get())
        self.working["preferred"] = p
        self.working["fallbacks"] = [f for f in self.working["fallbacks"] if f != p]
        self._show_fallbacks()

    def _show_fallbacks(self) -> None:
        tree = self.fallback_table.tree
        tree.delete(*tree.get_children())
        for i, p in enumerate(self.working["fallbacks"], start=1):
            cost = "paid" if p in PAID else "free: this computer"
            tree.insert("", "end", iid=p, values=(i, provider_name(p), cost))
        listed = {self.working["preferred"], *self.working["fallbacks"]}
        left = [provider_name(p) for p in PROVIDERS if p not in listed]
        self.add_box.configure(values=left)
        self.add_var.set(left[0] if left else "")

    def add_fallback(self) -> None:
        p = llm_settings.provider_id(self.add_var.get())
        if (
            p in PROVIDERS
            and p != self.working["preferred"]
            and p not in self.working["fallbacks"]
        ):
            self.working["fallbacks"].append(p)
            self._show_fallbacks()

    def _selected_fallback(self) -> Optional[str]:
        selection = self.fallback_table.tree.selection()
        return selection[0] if selection else None

    def move_fallback(self, step: int) -> None:
        p = self._selected_fallback()
        order = self.working["fallbacks"]
        if p not in order:
            return
        i = order.index(p)
        j = max(0, min(len(order) - 1, i + step))
        order[i], order[j] = order[j], order[i]
        self._show_fallbacks()
        self.fallback_table.tree.selection_set(p)

    def remove_fallback(self) -> None:
        p = self._selected_fallback()
        if p in self.working["fallbacks"]:
            self.working["fallbacks"].remove(p)
            self._show_fallbacks()

    # ---- signals ----

    def _mode(self) -> str:
        shown = self.mode_var.get()
        for mode, name in SIGNAL_MODE_NAMES.items():
            if name == shown:
                return mode
        return llm_settings.DEFAULT_SIGNAL_MODE

    def _show_mode_help(self) -> None:
        self.mode_help.configure(text=MODE_HELP[self._mode()])

    def signal_keys(self) -> List[tuple]:
        """The provider/model/prompt versions shown: every one with signals, and each
        provider's model in use with the signal prompt in use."""
        keys = []
        try:
            keys.extend(self.store.keys())
        except Exception:
            pass
        try:
            version = self.store.active_version("signal") or 1
        except Exception:
            version = 1
        for p in llm_settings.order(self.working):
            model = self.model_in_use(p)
            if model and (p, model, version) not in keys:
                keys.append((p, model, version))
        return keys

    def _show_signal_rows(self) -> None:
        tree = self.signal_table.tree
        tree.delete(*tree.get_children())
        for p, model, version in self.signal_keys():
            try:
                gate = llm_gate.gate_status(
                    self.store, p, model, version, self.training
                )
                rate = gate.hit_rate
                scored, rate_text, gate_text = (
                    str(gate.scored),
                    "" if rate is None else f"{rate:.0%}",
                    "passed" if gate.passed else "not passed",
                )
            except Exception:
                scored, rate_text, gate_text = "", "", ""
            use = "yes" if self.working["signal_use"].get(use_key(p, model)) else "no"
            tree.insert(
                "",
                "end",
                iid=f"{p}|{model}|{version}",
                values=(
                    provider_name(p),
                    model,
                    f"v{version}",
                    scored,
                    rate_text,
                    gate_text,
                    use,
                ),
            )

    def toggle_use(self) -> None:
        selection = self.signal_table.tree.selection()
        if not selection:
            self.status_var.set("Select a provider and model first.")
            return
        p, model, _version = selection[0].split("|", 2)
        key = use_key(p, model)
        if self.working["signal_use"].get(key):
            self.working["signal_use"].pop(key, None)
        else:
            self.working["signal_use"][key] = True
        self._show_signal_rows()
        if self.signal_table.tree.exists(selection[0]):
            self.signal_table.tree.selection_set(selection[0])

    # ---- save ----

    def collect(self) -> Dict[str, Any]:
        values = copy.deepcopy(self.working)
        values["health_timeout_s"] = _parse(
            self.health_var.get(), "Health check timeout", 0.5, 30
        )
        values["request_timeout_s"] = _parse(
            self.answer_var.get(), "Answer timeout", 5, 600
        )
        values["signal_timeout_s"] = _parse(
            self.wait_var.get(), "Wait for a signal", 1, 60
        )
        values["signal_reuse_minutes"] = _parse(
            self.reuse_var.get(), "Use a coin's signal again", 0, 1440
        )
        values["signal_mode"] = self._mode()
        return values

    def save(self) -> bool:
        try:
            values = self.collect()
        except ValueError as exc:
            self.status_var.set(str(exc))
            self._box.showerror(TITLE, str(exc), parent=self)
            return False
        if not llm_settings.save_llm_settings(values, self._factory()):
            message = "The LLM settings could not be saved."
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        if self._on_saved is not None:
            self._on_saved()
        self.destroy()
        return True


def summary_line(settings: Optional[dict] = None) -> str:
    """Settings' LLM Providers line: the order and the signal mode."""
    s = settings or llm_settings.read_llm_settings()
    names = [provider_name(p) for p in llm_settings.order(s)]
    order = names[0] + (", then " + ", ".join(names[1:]) if names[1:] else "")
    return f"{order}. LLM signals: {SIGNAL_MODE_NAMES[s['signal_mode']].lower()}."
