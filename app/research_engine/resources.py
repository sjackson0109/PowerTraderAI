"""
The workstation's resources and the research engine's operating modes.

``inventory()`` reports what the machine has, as the operating system reports it:
nothing is assumed. GPU names come from the OS (Windows: ``Win32_VideoController``);
an accelerator is listed only when an installed framework can use it (CUDA, DirectML
or MPS through torch). None of them is required.

**Operating modes** (``limits_for``). Research must never starve the trader, so
every mode keeps cores and memory free and runs jobs below normal priority:

| Mode | Workers | Kept free | Job priority |
|---|---|---|---|
| ``max_throughput`` | physical cores - 1 | max(4 GiB, 15% of memory) | below normal |
| ``balanced`` (default) | half the physical cores | max(4 GiB, 25% of memory) | below normal |
| ``low_resource`` | 1 | max(4 GiB, 40% of memory) | idle |

A job gets an equal share of the memory left after the reserve, and is stopped when
it uses more. A lower priority lets the operating system run the trader first; it
cannot guarantee the trader's timing.

**Energy.** No sensor is read: Windows does not expose the processor's power to
programs without a driver. When the owner sets the watts one busy core draws, a
job's energy is estimated as CPU-seconds x watts per core, and its cost from the
tariff the owner sets. Without those settings no energy or cost is reported.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Optional, Tuple

GIB = 1024**3
MODES = ("max_throughput", "balanced", "low_resource")
DEFAULT_MODE = "balanced"
_RESERVE_SHARE = {"max_throughput": 0.15, "balanced": 0.25, "low_resource": 0.40}
_MIN_RESERVE = 4 * GIB
_PRIORITY = {
    "max_throughput": "below_normal",
    "balanced": "below_normal",
    "low_resource": "idle",
}


@dataclass(frozen=True)
class Inventory:
    cpu_name: str
    physical_cores: int
    logical_cores: int
    memory_total_bytes: int
    memory_available_bytes: int
    gpus: Tuple[str, ...]
    accelerators: Tuple[str, ...]
    disk_free_bytes: int
    python: str
    platform: str

    def to_dict(self) -> dict:
        return asdict(self)


def _windows_hardware_names() -> Dict[str, object]:
    """The processor's and the GPUs' names, from Windows' CIM classes."""
    command = (
        "@{cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1).Name;"
        " gpus=@((Get-CimInstance Win32_VideoController).Name)} | ConvertTo-Json"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    data = json.loads(out.stdout or "{}")
    gpus = data.get("gpus") or []
    if isinstance(gpus, str):
        gpus = [gpus]
    return {"cpu": str(data.get("cpu") or "").strip(), "gpus": [str(g) for g in gpus]}


def hardware_names() -> Dict[str, object]:
    """``{"cpu": name, "gpus": [names]}`` as the OS reports them; empty when the OS
    cannot be asked (then the CPU falls back to ``platform.processor()``)."""
    names: Dict[str, object] = {"cpu": "", "gpus": []}
    if sys.platform == "win32":
        try:
            names = _windows_hardware_names()
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if not names.get("cpu"):
        names["cpu"] = platform.processor() or platform.machine()
    return names


def accelerators() -> Tuple[str, ...]:
    """The accelerators an installed framework can use. torch is imported only when
    it is installed; none of them is required."""
    found = []
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch

            if torch.cuda.is_available():
                found.append("cuda")
            mps = getattr(torch.backends, "mps", None)
            if mps is not None and mps.is_available():
                found.append("mps")
        except Exception:  # a broken torch install must not stop the inventory
            pass
    if importlib.util.find_spec("torch_directml") is not None:
        found.append("directml")
    return tuple(found)


def inventory(
    path: Optional[str] = None,
    names: Optional[Callable[[], Dict[str, object]]] = None,
    accelerator_probe: Optional[Callable[[], Tuple[str, ...]]] = None,
) -> Inventory:
    """What this machine has. ``path`` is where research data is kept (its disk's
    free space is reported); the probes can be replaced in tests."""
    import psutil

    hw = (names or hardware_names)()
    memory = psutil.virtual_memory()
    logical = psutil.cpu_count(logical=True) or os.cpu_count() or 1
    physical = psutil.cpu_count(logical=False) or logical
    return Inventory(
        cpu_name=str(hw.get("cpu") or ""),
        physical_cores=int(physical),
        logical_cores=int(logical),
        memory_total_bytes=int(memory.total),
        memory_available_bytes=int(memory.available),
        gpus=tuple(str(g) for g in (hw.get("gpus") or [])),
        accelerators=tuple((accelerator_probe or accelerators)()),
        disk_free_bytes=int(shutil.disk_usage(path or os.getcwd()).free),
        python=platform.python_version(),
        platform=platform.platform(),
    )


@dataclass(frozen=True)
class Limits:
    mode: str
    workers: int
    threads_per_worker: int
    memory_reserve_bytes: int
    memory_per_job_bytes: int
    priority: str

    def to_dict(self) -> dict:
        return asdict(self)


def limits_for(mode: str, inv: Inventory) -> Limits:
    """The limits of operating mode ``mode`` on machine ``inv`` (the module's table)."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; use one of {MODES}")
    physical = max(1, inv.physical_cores)
    workers = {
        "max_throughput": max(1, physical - 1),
        "balanced": max(1, physical // 2),
        "low_resource": 1,
    }[mode]
    reserve = max(_MIN_RESERVE, int(inv.memory_total_bytes * _RESERVE_SHARE[mode]))
    usable = max(0, inv.memory_total_bytes - reserve)
    # numerical libraries' threads, so the workers together stay within the cores
    threads = (
        max(1, (inv.logical_cores - 2) // workers) if mode != "low_resource" else 1
    )
    return Limits(
        mode=mode,
        workers=workers,
        threads_per_worker=threads,
        memory_reserve_bytes=reserve,
        memory_per_job_bytes=usable // workers if usable else 0,
        priority=_PRIORITY[mode],
    )


@dataclass(frozen=True)
class EnergyModel:
    """The owner's figures; None means not set, and then nothing is estimated."""

    watts_per_busy_core: Optional[float] = None
    tariff_per_kwh: Optional[float] = None
    currency: str = ""

    METHOD = "estimate: CPU-seconds x watts per busy core (set by the owner)"

    def energy_wh(self, cpu_seconds: float) -> Optional[float]:
        if self.watts_per_busy_core is None:
            return None
        return float(cpu_seconds) * float(self.watts_per_busy_core) / 3600.0

    def cost(self, cpu_seconds: float) -> Optional[float]:
        wh = self.energy_wh(cpu_seconds)
        if wh is None or self.tariff_per_kwh is None:
            return None
        return wh / 1000.0 * float(self.tariff_per_kwh)
