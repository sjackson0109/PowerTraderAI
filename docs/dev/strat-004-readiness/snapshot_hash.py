"""The proposed STRAT-004 observation's frozen settings and their SHA-256, computed with
strategy_lab.observation's own snapshot() and digest(). Sandbox only: the inputs are
written here in full; no real settings file is read."""

import copy
import hashlib
import json
import os
import sys

for var in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
    assert "p4-sbx" in os.environ.get(var, ""), var

from pt_settings_manager import DEFAULT_SETTINGS
from signal_fusion import settings as fs
from strategies.catalogue import create, get_entry
from strategy_lab import observation as obs

COINS = [
    "BTC",
    "ETH",
    "XRP",
    "DOGE",
    "SOL",
    "ZEC",
    "DASH",
    "ADA",
    "AVAX",
    "LINK",
    "LTC",
]

config = copy.deepcopy(DEFAULT_SETTINGS)  # a fresh install's pt_config.json
config["strategy"] = {
    "engine": "catalogue",
    "active_id": "STRAT-004",
    "timeframe": "1d",
    "params": {},  # Settings > Strategy saves only values that differ from the defaults
    "overlays": [],  # no stop, no OVL-REGIME
}
config["llm"] = {"signal_mode": "off"}  # not frozen by snapshot(); shown for the plan
gui = {  # pt_hub.DEFAULT_SETTINGS for the frozen keys, with the observation's coins
    "coins": COINS,
    "paper_coins_mode": "inherit",
    "paper_coins": [],
    "start_allocation_pct": 1.0,
    "max_coin_allocation_pct": 10.0,
    "min_order_margin_pct": 2.0,
    "trade_start_level": 3,
    "dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0],
    "dca_multiplier": 2.0,
    "max_dca_buys_per_24h": 2,
    "pm_start_pct_no_dca": 5.0,
    "pm_start_pct_with_dca": 2.5,
    "trailing_gap_pct": 0.5,
}

snap_a = obs.snapshot(config, gui)
print("A: signal_fusion absent (never saved)")
print(json.dumps(snap_a, sort_keys=True, indent=1))
print(
    "canonical:", json.dumps(snap_a, sort_keys=True, separators=(",", ":"), default=str)
)
print("A sha256:", obs.digest(snap_a))

config_b = copy.deepcopy(config)
config_b["signal_fusion"] = fs.normalise({})  # saved by Settings > Strategy, all Off
snap_b = obs.snapshot(config_b, gui)
print("B signal_fusion:", json.dumps(config_b["signal_fusion"], sort_keys=True))
print("B sha256:", obs.digest(snap_b))

# what Reconcile replays from the frozen snapshot
print("spec_of:", obs.spec_of(snap_a))
# the parameter hash each trade record carries (pt_trader._strategy_fields)
params = dict(create("STRAT-004").params)
canonical = json.dumps(
    params, sort_keys=True, separators=(",", ":"), ensure_ascii=False
)
print("params:", canonical, "version", get_entry("STRAT-004")["version"])
print("params sha256:", hashlib.sha256(canonical.encode("utf-8")).hexdigest())
