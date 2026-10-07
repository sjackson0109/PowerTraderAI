# Issue drafts and release notes: FDS-MDL Phase 1

These drafts were filed on 2026-10-06 as #141 to #151 on `sjackson0109/PowerTraderAI` (the table gives each number; B1a and B1b were merged into B1 first, by owner decision). Each issue's body is its draft below, with references between drafts replaced by issue numbers (D1's mention of D2 is worded by description), and a footer saying where the drafts and audit live. Each body uses the headings of `.github/ISSUE_TEMPLATE/bug_report.yml`. Notes on scope and fixes sit inside those headings, because the bug form has no field for them.

E1 and E2 were added on 2026-10-07: two behaviours of the legacy neural runner found in FDS-MDL Phase 3, whose STRAT-003 reproduces the runner's rule. They follow the same base, evidence and label rules. Their numbers are in the table once filed.

- **Base:** `main` at `7a84250`. Line numbers are at that commit unless a draft says otherwise. Files added by FDS-MDL Phase 1 (`app/pt_pattern_trainer.py`, `app/trainer_guard.py`) are cited by symbol.
- **Evidence:** every claim was checked against the code with `git show 7a84250:<path>`, `git grep` and `git log -S`. Anything traced through the code but not run is marked INFERRED. The Phase 0 evidence is `docs/dev/TRAINER-AUDIT.md` and `docs/dev/trainer-audit-evidence.json`.
- **Labels:** existing labels only (checked with `gh label list` before filing): `bug` or `documentation`, `needs-triage`, and `component-trading` where the draft suggested it. Priority and phase labels are left to triage.

| Draft | Issue | Title (short) | Fixed by FDS-MDL? |
|---|---|---|---|
| [A1](#a1) | #141 | DataProvider returns one synthetic candle as a string | No (owner decision: the legacy handoff is not repaired) |
| [A2](#a2) | #142 | `signals_dca_*` written, `long/short_dca_signal` read | No (same) |
| [A3](#a3) | #143 | Thinker cannot parse the mock trainers' files | Mostly: the default trainer is now the port; the mocks are refused unless allowed |
| [B1](#b1) | #144 | Market-data path reads every exchange's credentials; unreadable `trading_config.json` silently replaced | No |
| [B2](#b2) | #145 | `trainer_status.json` writer is dead code with the wrong BTC path | Partly: the port writes the file; trimmed to what is left |
| [B3](#b3) | #146 | Auto-retrain timers survive Stop All; a removed coin retrains in BTC's folder | No |
| [B4](#b4) | #147 | `ARCHITECTURE.md` trainer, signal-file and default claims don't match the code | No |
| [B5](#b5) | #148 | Hub writes `app/__pycache__` at runtime | No |
| [D1](#d1) | #149 | Pattern trainer never saves its weight updates | No (kept on purpose: faithful port) |
| [D2](#d2) | #150 | Pattern trainer's close-weight test multiplies a percentage by 100 | No (same) |
| [D3](#d3) | #151 | Pattern trainer matches only flushed memories and re-reads them every step | No (same) |
| [E1](#e1) | not yet filed | Runner's bound remap drops repeats; with two inactive timeframes later ones use a neighbour's bounds | No (STRAT-003 reproduces it on purpose; the Phase 4 backtest counts the decisions where it applies) |
| [E2](#e2) | not yet filed | Runner's gap pass loops for ever on two zero bounds | No (STRAT-003 holds `BOUNDS_NOT_CONVERGED` instead; the Phase 4 backtest counts these) |

Section [C](#c-release-notes) is the release-notes paragraph.

## Notes for the owner

1. **The handoff breaks (A1–A3) are separate issues on purpose,** as asked. A1 hides A3 today: the runner never reaches the parse.
2. **History behind the release-note wording.**
   - The thinker has not produced signals for a trained coin since 2026-02-22. `2d7a0f2` introduced the one-candle string. `b7f563a` switched the thinker to `get_historical_data`, which `DataProvider` only gained in `4fc3834` (2026-03-06); until then the call raised `AttributeError` and was retried every 3.5 s.
   - The stub trainer arrived in `10e190e` (2026-02-25).
   - The fork's commits from 2026-02-19 to 2026-02-22 ran upstream's KuCoin pipeline and were not audited. So the release note says "since February 2026" and "since 25 February 2026", not "never".
3. **"Only paper mode has ever run"** (audit, Verdict) has no evidence cited, so the release note leaves it out.
4. **B1 holds two `pt_multi_exchange` bugs** (credentials for every exchange; an unreadable config silently replaced). They need separate fixes, but are filed as one issue (owner decision, 2026-10-06).
5. **B2 was re-checked after the port** and trimmed: the port writes `trainer_status.json` itself.
6. **Found while checking, not in the audit:** B3's last part (every auto-retrain stops the neural runner and nothing restarts it), and B4's `STRAT-000` row.
7. **D1–D3 are upstream behaviour kept on purpose** (owner decision: faithful port). They are drafted so the decision to change the model's output is a separate, visible one. D2 only matters once D1 is fixed.
8. **The thinker's threshold rewrite** (audit section 7 item 10) is not drafted. It cannot be reached today, it is upstream's behaviour, and the port writes `str(float)`, which the thinker writes back unchanged (checked by `test_the_output_is_what_the_thinker_reads`). It is in A3's checklist instead.
9. **The desktop installer script is stale.** `.github/scripts/create_desktop_installer.py` lists a handful of modules and misses `pt_paths`, `market_data/` and most of `app/`. Phase 1 only added the new trainer files and changed its default trainer name. Not drafted; worth a task if the installer is still used.
10. **E1 and E2 come from reproducing the legacy runner** for STRAT-003 (FDS-MDL Phase 3). Both are latent on main (#141, #143). STRAT-003 keeps E1 on purpose and stops E2 after 100,000 steps; the Phase 4 backtest header counts both per symbol and timeframe (owner decision, 2026-10-07). Both drafts cite `feat/model-strategy-1`, which is not yet published, for STRAT-003's tests and the recorded fixture.

---

## A1

**Filed as:** #141 (https://github.com/sjackson0109/PowerTraderAI/issues/141), labels `bug`, `needs-triage`, `component-trading`

**Title:** `[Bug]: DataProvider returns one synthetic candle (as a string) for any kline/history request, so the neural runner stalls on the first trained coin`

**Suggested labels:** `bug`, `needs-triage` (optional: `component-trading`)

### What happened?

`DataProvider.get_kline_data()` and `get_historical_data()` (`app/pt_data_provider.py:101`, `:130`) ignore the timeframe and `limit` they are given. Both end in `_get_multi_exchange_kline`, which fetches the current ticker price and returns one made-up candle as a string:

```python
# app/pt_data_provider.py:220-227
price = self.multi_exchange.get_current_price(normalized_symbol)
...
current_time = int(time.time() * 1000)
kline_data = f"[[{current_time}, {price}, {price}, {price}, {price}, 1000]]"
return kline_data
```

The code's own comment says so: `# For now, get current price and create a simple kline-like response` (`:214`).

**Effect on the neural runner** (static trace, not run). For a trained coin, `step_coin` needs at least two candles and retries until it gets them:

```python
# app/pt_thinker.py:732-737
history_list = history.split("], [")
# KuCoin can occasionally return an empty/short kline response.
# Guard against history_list[1] raising IndexError.
if len(history_list) < 2:
    time.sleep(0.2)
    continue
```

One candle always gives `len(history_list) == 1`, so the loop that starts at `:713` never exits. As a result:

- No model file is read and no signal is written.
- The runner calls the exchange price endpoint about every 0.2 s plus request time.
- The runner never reports ready. Start All waits for that (`app/pt_hub.py:5210-5217`), so **Start All never starts the trader** once every coin is trained (INFERRED).
- Untrained coins return early (`app/pt_thinker.py:649-678`), so the stall only appears after training.

**Callers**

- Started by the hub: the neural runner (`app/pt_thinker.py:604`, `:720`, `:1030`, `:1410`). Before FDS-MDL the default trainer `app/pt_trainer.py` (`:132`, `:159`) also called it. Since FDS-MDL Phase 1 that trainer is a mock the hub launches only with `allow_mock_trainer`, and the default trainer (`app/pt_pattern_trainer.py`) reads `app/market_data/candles.py` instead.
- Not started by anything: the per-coin `app/<SYM>/pt_trainer*.py` copies, `app/pt_trainer_standalone.py`, `app/pt_neural_processor.py`, `app/pt_hub_chart_components.py`, `app/demo_phase3_features.py`, `app/phase3_live_demo.py`.

**History.** The single synthetic candle has been there since `2d7a0f2` (2026-02-22). The thinker has called `get_historical_data` since `b7f563a` (also 2026-02-22). `DataProvider` only gained that method in `4fc3834` (2026-03-06).

**Scope.** Out of scope for FDS-MDL (trained-model strategy): STRAT-003 is evaluated through the strategy runtime, not the thinker. See `docs/dev/TRAINER-AUDIT.md` section 2.1 and section 7 item 1.

### What did you expect to happen?

Either the candles asked for (timeframe and window), in the shape the callers parse, or an error.

Notes for a fix:
- The thinker parses `history_list[1]` as the last closed candle, with open at index 1 and close at index 2 (`app/pt_thinker.py:738-743`). That is KuCoin's newest-first `[time, open, close, high, low, ...]`, which upstream fetched with `market.get_kline` (`b4522b0:pt_thinker.py:556-574`).
- The synthetic row uses Binance order `[time, open, high, low, close, volume]` (comment at `app/pt_data_provider.py:222`).
- A fix has to settle on one shape. `app/market_data/candles.py` (Binance, cached, closed bars) already exists and is what the pattern trainer uses.

### Steps to reproduce

1. Offline, in plain Python (no app import), using the thinker's own expressions:
   ```python
   raw = "[[1700000000000, 63742.07, 63742.07, 63742.07, 63742.07, 1000]]"  # shape from pt_data_provider.py:226
   history = raw.replace("]]", "], ").replace("[[", "[")
   print(len(history.split("], [")))  # 1 -> step_coin's `if len(history_list) < 2: continue` repeats forever
   ```
2. In the hub (paper mode, scratch `POWERTRADER_HOME`), with `allow_mock_trainer` set and the trainer path set to `pt_trainer.py`, train BTC. The Trainers pane prints `Successfully retrieved 63 price points`, where 63 is the length of the string, and `Latest price data: ]`.
3. Start the Neural Runner. The log stops after `Processing BTC...`, and Start All never starts the trader. This step is the expected result from reading the code; it was not run.

### Trading mode
Paper (the code path is the same in Live)

### Exchange
Not applicable (any exchange; the audit's runs used Binance, the default primary)

### Area
Market data

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
3.13 (audit test venv, for the executed trainer runs)

### Logs
```shell
[BTC] Successfully retrieved 63 price points for BTCUSDT
[BTC] Latest price data: ]
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## A2

**Filed as:** #142 (https://github.com/sjackson0109/PowerTraderAI/issues/142), labels `bug`, `needs-triage`, `component-trading`

**Title:** `[Bug]: Neural runner writes signals_dca_spread/single.txt but the trader and hub read long_dca_signal.txt/short_dca_signal.txt`

**Suggested labels:** `bug`, `needs-triage` (optional: `component-trading`)

### What happened?

Since `4fc3834` (2026-03-06) the thinker writes its DCA signal counts under new names:

```python
# app/pt_thinker.py:1382-1383, :1396-1397 (also the zeroing for untrained coins at :656-659)
with open("signals_dca_spread.txt", "w+") as f:
    f.write(str(longs))
...
with open("signals_dca_single.txt", "w+") as f:
    f.write(str(shorts))
```

The readers still use the old names:
- Trader: `path = os.path.join(folder, "long_dca_signal.txt")` (`app/pt_trader.py:880`) and `"short_dca_signal.txt"` (`:902`). A missing file reads as 0 (`:886-887`).
- Hub: the chart overlay (`app/pt_hub.py:1227-1229`), `read_short_signal` (`:845-850`) and the neural tiles (`:7168-7179`).

Nothing in `app/` writes the old names; `git grep` finds only the readers and the migration list. So with `strategy.engine = legacy_neural`:
- **The trader never opens a trade.** The entry gate is `if not (buy_count >= start_level and sell_count == 0)` (`app/pt_trader.py:2361-2369`), and `buy_count` is always 0.
- **The trader never takes a neural DCA.** `neural_level_now = self._read_long_dca_signal(symbol)` (`:2214`) is always 0. Hard-% DCA and trailing-profit sells still work, because they don't read signals.
- **The hub's neural tiles and chart show 0.**

The default engine, `catalogue`, does not read these files (`app/pt_trader.py:2037-2041`, `:2349-2358`).

**Stale-file risk (INFERRED).**
- The migration carries the old files forward: `"long_dca_signal.txt"` and `"short_dca_signal.txt"` are in `NEURAL_PATTERNS` (`app/pt_migrate.py:125-126`).
- Afterwards nothing overwrites or deletes them. The thinker writes the new names, the hub's pre-training cleanup leaves them out (`app/pt_hub.py:5658-5666`), and the trader has no age check (`app/pt_trader.py:880-887`).
- So a copied `long_dca_signal.txt` holding 3 or more, with the short file at 0 or missing, would let the legacy trader open trades and take neural DCAs on a value of unknown age.
- The copies tracked in git before `4fc3834` held 0.

Renamed in the same commit: `futures_profit_margin_spread.txt` and `_single.txt` (`:1380`, `:1394`). Nothing in `app/` reads either the old or the new names.

**Scope.** Out of scope for FDS-MDL: STRAT-003 goes through the strategy runtime, not these files. See `docs/dev/TRAINER-AUDIT.md` section 7 item 2.

### What did you expect to happen?

The thinker, trader and hub share one file name, and an old or stale signal file is ignored or removed rather than traded on.

Notes for a fix: choose one name; decide what happens to migrated old-name files; consider an age check in `_read_long_dca_signal` and `_read_short_dca_signal`.

### Steps to reproduce

1. `git grep -n -E "long_dca_signal|short_dca_signal|signals_dca_" -- app ":!app/tests"`. Writers use only `signals_dca_*`; readers use only the old names.
2. Stale risk (scratch `POWERTRADER_HOME`, paper mode, `strategy.engine = legacy_neural`): write `5` to `<coin folder>/long_dca_signal.txt` and start the trader. It should open a paper trade for that coin whatever the thinker does. This is the expected result from reading the code; it was not run.

### Trading mode
Paper (the same code runs in Live with `legacy_neural`)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
n/a (found by reading the code)

### Logs
```shell
None: found by reading the code.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## A3

**Filed as:** #143 (https://github.com/sjackson0109/PowerTraderAI/issues/143), labels `bug`, `needs-triage`

**Title:** `[Bug]: Neural runner cannot parse the mock trainers' model files; every timeframe becomes "INACTIVE (training data issue)"`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

The hub's default trainer at `7a84250`, `app/pt_trainer.py`, writes its model files as comma-joined floats:

```python
# app/pt_trainer.py:87-88 (weights the same way, :99-106)
with open(f"memories_{timeframe}.txt", "w", encoding="utf-8") as f:
    f.write(",".join(memories[:50]))
```

The thinker expects upstream's format: `~`-joined entries `"<space-separated pattern>{}<high %>{}<low %>"`, with weights joined by spaces. It strips every comma before splitting:

```python
# app/pt_thinker.py:760-767
memory_list = (
    file.read()
    .replace("'", "")
    .replace(",", "")
    ...
    .split("~")
)
```

What follows:
1. The 50 values fuse into one token.
2. `float(memory_pattern[check_dex])` (`:832`) raises `ValueError`.
3. The `except` at `:924-931` sets `training_issues[...] = 1` and marks the timeframe inactive.
4. The log shows `"INACTIVE (training data issue) on "...` (`:1131-1132`).

With every timeframe inactive, `_is_printing_real_predictions` (`:513-522`) never finds `WITHIN`, `LONG` or `SHORT`, so the runner never reports ready (INFERRED). Today A1 hides this, because the runner never reaches the parse. Every other tracked trainer script is also a stub, and some write no model files at all (audit section 4).

**Since FDS-MDL Phase 1.**
- The hub's default trainer is `app/pt_pattern_trainer.py`, a port of upstream `ba62130`. It writes the `~` / `{}` / space format, and a test runs the thinker's own parse expressions on its output (`app/tests/test_pattern_trainer.py::test_the_output_is_what_the_thinker_reads`).
- The 12 stubs stay in the repo with a `MOCK - DO NOT USE FOR DECISIONS` header. The hub refuses to launch a marked script unless `allow_mock_trainer` is `true` in `pt_config.json` (`app/trainer_guard.py`).
- So this bug now affects only someone who sets that flag and points `script_neural_trainer` at a stub, or whose saved `gui_settings.json` still names `pt_trainer.py` and who then sets the flag. Removing the stubs is a planned chore after FDS-MDL (addendum section 6).

**What remains to verify end to end once A1 is fixed** (FDS-MDL does not test the thinker process reading the files):
- [ ] The thinker parses the pattern trainer's memories and its three weight files, and each weight list has one entry per memory (`weight_list[mem_ind]`, `:880`, `:890`, `:893`). The parse expressions are covered by the test above; the running thinker is not.
- [ ] On real candles at least one timeframe becomes `active` and `runner_ready` reaches `ready: true` (`:1348-1361`), so Start All starts the trader (`app/pt_hub.py:5210-5217`).
- [ ] Timeframe names match `1hour` … `1week` (`app/pt_thinker.py:477`).
- [ ] The threshold file rewrite is byte-identical: the thinker rewrites it with `str(perfect_threshold)` on every step (`:934-938`), and the pattern trainer writes `str(float)`.
- [ ] Signals reach the trader. This is blocked by A2.

**Scope.** Out of scope for FDS-MDL beyond the default switch and the refusal: STRAT-003 goes through the strategy runtime. See `docs/dev/TRAINER-AUDIT.md` sections 2.1 and 3.6.

### What did you expect to happen?

The trainer the hub launches writes files the thinker can read. A file in the wrong format is reported clearly, naming the file and the expected format, instead of quietly turning every timeframe into a "training data issue".

### Steps to reproduce

Offline, in plain Python, using the thinker's own expressions:

```python
text = ",".join(["-0.273418", "-0.014439", "0.182522"])  # as app/pt_trainer.py:88 writes
memory_list = text.replace("'", "").replace(",", "").replace('"', "").replace("]", "").replace("[", "").split("~")
pattern = memory_list[0].split("{}")[0].split(" ")
float(pattern[0])  # ValueError: could not convert string to float: '-0.273418-0.0144390.182522'
```

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
3.13 (audit reproduction)

### Logs
```shell
ValueError: could not convert string to float: '-0.273418-0.0144390.182522-0.1614840.338668-0.036205-0.007515-0.015862-0.1315340.331...
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## B1

**Filed as:** #144 (https://github.com/sjackson0109/PowerTraderAI/issues/144), labels `bug`, `needs-triage`

**Title:** `[Bug]: pt_multi_exchange reads every exchange's credentials for public market data, and silently replaces an unreadable trading_config.json`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

Two problems in the configuration path that the market-data code goes through (`DataProvider`, `app/pt_data_provider.py:44-51`, which only needs public prices). They need separate fixes; they are filed together by owner decision.

**1. Credentials are read for every exchange in `trading_config.json`, enabled or not.**

```python
# app/pt_multi_exchange.py:122-125 (load_config)
exchanges = [
    self._exchange_from_file(ex, path)
    for ex in data.get("exchanges", [])
]
# :158-159 (_exchange_from_file)
ex = ExchangeConfig(**settings)
_fill_credentials(ex)
```

- `_fill_credentials` (`:56-64`) calls `pt_secrets.get_credentials`, which reads both the environment and the OS keyring (`app/pt_secrets.py:579-582`).
- `initialize` reads them again for each enabled exchange (`app/pt_multi_exchange.py:332`, `_get_exchange_credentials` at `:492-500`) and passes them to `add_exchange` (`:342`).
- `DataProvider` is created at import by the neural runner (`app/pt_thinker.py:33`) and by the mock trainer (`app/pt_trainer.py:117`).

So with the shipped template, where only Binance is enabled (`app/trading_config.example.json`), a process that only reads public prices still loads any stored Robinhood, Coinbase, Kraken or KuCoin credentials into memory. Nothing is logged or written; this is a least-privilege problem, not a leak.

Also: importing the module creates the config folder. The module-level `multi_exchange_manager = MultiExchangeManager()` (`:504`) leads to `pt_paths.config_dir()` (`:96`), which creates the folder by default (`app/pt_paths.py:178-179`). A script or test that imports it without `POWERTRADER_HOME` creates the real user config folder.

**2. An unreadable `trading_config.json` is silently replaced with defaults.**

`load_config`'s docstring promises not to replace an unreadable file:

```python
# app/pt_multi_exchange.py:108-110
config to edit; the real file is only created by ``save_config``. A
real file that exists but cannot be read is NOT replaced by the example
(that would hide the problem and a later save would overwrite it).
```

`load_config` keeps that promise: it prints the error and returns `None` (`:135-137`). `initialize` then does this:

```python
# app/pt_multi_exchange.py:314-316
config = self.config_manager.load_config()
if not config and user_region:
    config = self.config_manager.create_default_config(user_region)
```

`create_default_config` ends with `self.save_config(config)` (`:245`), which writes `trading_config.json` (`:179`). `DataProvider` always passes a region (`config.get("user_region", os.environ.get("POWERTRADER_USER_REGION", "GLOBAL"))`, `app/pt_data_provider.py:48-51`). So starting the neural runner (or the mock trainer) with a damaged `trading_config.json` overwrites it.

- The `GLOBAL` replacement enables Binance, Kraken and KuCoin (`app/pt_multi_exchange.py:232-239`). The shipped template enables only Binance.
- The user's exchange choices are lost, and the only trace is `Error loading config: ...` in the log.
- Credentials are not affected: they live in the keyring or environment, and the default config carries none, so `save_config` writes no keyring entry (`:181-191`).

**Scope.** Not fixed by FDS-MDL. FDS-MDL needs no credentials, and its trainer does not import `DataProvider` or `pt_multi_exchange` (an AST test checks this: `test_the_trainer_reads_candles_only_through_the_candle_layer`). See `docs/dev/TRAINER-AUDIT.md` section 2.2 and section 7 item 4.

### What did you expect to happen?

1. Market-data code reads no credentials, since it uses public endpoints. Code that needs credentials reads them only for the exchange it is about to use. Importing the module has no file-system side effects.
2. An unreadable `trading_config.json` is left untouched, and initialisation fails with a clear error naming the file, as the docstring says. If defaults are ever written, the original is kept as a backup.

### Steps to reproduce

PowerShell, scratch folder, keyring disabled, dummy values. Not run for this report.

Part 1:

```powershell
$env:POWERTRADER_HOME = "$env:TEMP\pt-scratch"
$env:PYTHON_KEYRING_BACKEND = "keyring.backends.fail.Keyring"
$env:POWERTRADER_COINBASE_API_KEY = "dummy"; $env:POWERTRADER_COINBASE_API_SECRET = "dummy"
cd app
python -c "import pt_multi_exchange as m; c = m.ExchangeConfigManager().load_config(); print([(e.exchange_type, e.enabled, e.credential_source) for e in c.exchanges])"
```

Expected from the code: `('coinbase', False, 'environment')`, meaning credentials were loaded for a disabled exchange.

Part 2:

```powershell
$env:POWERTRADER_HOME = "$env:TEMP\pt-scratch"
$env:PYTHON_KEYRING_BACKEND = "keyring.backends.fail.Keyring"
New-Item -ItemType Directory -Force "$env:POWERTRADER_HOME\config" | Out-Null
Set-Content "$env:POWERTRADER_HOME\config\trading_config.json" "{ not json"
cd app
python -c "import pt_data_provider; pt_data_provider.DataProvider()"
Get-Content "$env:POWERTRADER_HOME\config\trading_config.json"
```

The file now holds the `GLOBAL` default config. The overwrite (`:245`) happens before the connection loop (`:324-351`), so it happens even with the network blocked.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable (every configured exchange)

### Area
Exchange connection

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
n/a (found by reading the code)

### Logs
```shell
Part 2 prints: Error loading config: <JSON error>   (pt_multi_exchange.py:136; not captured)
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## B2

**Filed as:** #145 (https://github.com/sjackson0109/PowerTraderAI/issues/145), labels `bug`, `needs-triage`

**Title:** `[Bug]: Hub's _write_training_status is dead code with the wrong BTC path, and a killed trainer leaves trainer_status.json at TRAINING`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

Re-checked after FDS-MDL Phase 1. The hub reads `trainer_status.json` to tell whether a coin is mid-training:
- In `_coin_is_trained` (`app/pt_hub.py:5262-5265`): `st = _safe_read_json(os.path.join(folder, "trainer_status.json"))`, then `== "TRAINING": return False`.
- In `_running_trainers`, for "Trainers launched elsewhere" (`:5298-5324`). This feeds the training-status icons in `_training_status_map` (`:5344-5357`).

The hub deletes the file before each training run (`:5660`).

**What FDS-MDL changed.** At `7a84250` nothing wrote the file. The pattern trainer now writes it in the coin folder, as upstream did: `TRAINING` at the start, then `FINISHED` (before the stamp) or `ERROR` with the message (`app/pt_pattern_trainer.py`, `_write_status` and `main`). A test checks the `FINISHED` and `ERROR` cases. So the readers above now work for the default trainer.

**What is left.**
1. The hub defines a writer and never calls it: `self._write_training_status = _write_training_status` (`:2007`) is the only other reference. If it were called, it would put BTC's status in the wrong folder:
   ```python
   # app/pt_hub.py:1999-2002
   coin_dir = os.path.join(self.settings["main_neural_dir"], coin)
   if os.path.exists(coin_dir):
       status_path = os.path.join(coin_dir, "trainer_status.json")
   ```
   BTC's folder is the root itself (`out["BTC"] = main_dir`, `:763-764`), not `<root>/BTC`.
2. A trainer that is killed (Stop, Stop All, a crash of the interpreter) cannot write `ERROR`, so the file stays at `TRAINING`. A trainer started from a terminal then shows as running in every hub until the next launch for that coin deletes the file (INFERRED from the readers above).
3. The mock trainers still write no status file.

**Scope.** FDS-MDL fixed the missing writer for the default trainer. See `docs/dev/TRAINER-AUDIT.md` section 7 item 5.

### What did you expect to happen?

The unused helper is removed (or fixed and used), and a status left at `TRAINING` by a process that no longer runs is recognised as stale (for example by recording the PID, or by an age limit).

### Steps to reproduce

1. `git grep -n -E "trainer_status|_write_training_status" -- app ":!app/tests"`. This shows the reads at `pt_hub.py:5263` and `:5306`, the delete at `:5660`, the helper at `:1988-2007` with no call, and the writes in `pt_pattern_trainer.py`.
2. Scratch `POWERTRADER_HOME`: start `python app\pt_pattern_trainer.py ETH` from a terminal and kill it with Ctrl+Break during training. `<root>\ETH\trainer_status.json` still says `TRAINING`. This is the expected result from reading the code; it was not run.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Hub GUI

### PowerTraderAI version or commit
7a84250 (re-checked on feat/model-strategy-1 after Phase 1)

### Operating system
Windows (not OS-specific)

### Python version
n/a (found by reading the code)

### Logs
```shell
None: found by reading the code.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## B3

**Filed as:** #146 (https://github.com/sjackson0109/PowerTraderAI/issues/146), labels `bug`, `needs-triage`

**Title:** `[Bug]: Auto-retrain timers survive "Stop All", and a removed coin's timer retrains in BTC's folder`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

All of this is INFERRED from the code; none of it was run.

**1. Cancelling does nothing.**

```python
# app/pt_hub.py:6139-6145
for coin, timer_id in self.auto_retrain_timers.items():
    try:
        self.master.after_cancel(timer_id)
        ...
    except Exception:
        pass
self.auto_retrain_timers.clear()
```

- `PowerTraderHub` is the Tk root (`class PowerTraderHub(tk.Tk)`, `:1945`), and tkinter sets `self.master = None` on a Tk root (`Tk.__init__`).
- Each `after_cancel` therefore raises `AttributeError`, which is swallowed. The timer IDs are then dropped, but the timers still fire.
- `stop_all_scripts` relies on this function (`:6161-6162`). It is the stop side of the Start/Stop All toggle (`:5178-5184`).
- Scheduling works, because it uses `self.master or self.winfo_toplevel()` (`:5797`).
- Once the IDs are cleared, `_schedule_auto_retrain` can no longer cancel a coin's old timer (`:5806-5810`), so a coin can have two pending timers. A second start is ignored while that coin's trainer is still running (`:5650-5655`).

**2. A removed coin retrains in BTC's folder.**

- Nothing cancels a coin's timer when the coin is removed in Settings.
- When the timer fires, the working folder is `coin_cwd = self.coin_folders.get(coin, self.settings["main_neural_dir"])` (`:5632`).
- `coin_folders` is rebuilt from the new coin list (`:6922-6927`), so the removed coin falls back to the root, which is BTC's folder.
- The hub then deletes BTC's `memories_*`, `memory_weights_*` and `neural_perfect_threshold_*` files and training stamp (`:5657-5675`). It runs the removed coin's trainer there, so BTC's model is replaced by that coin's.

**3. Every auto-retrain stops the neural runner (not in the audit).** Every launch first calls `self.stop_neural()` (`:5625`), and nothing restarts the runner afterwards: `_monitor_trainer_process` only schedules the next retrain (`:5758-5766`). With the defaults (`"training_auto_interval_hours": 6`, `"training_auto_enabled": True`, `:605-607`), the neural runner is stopped 6 hours after a manual training and stays stopped.

**Scope.** Not fixed by FDS-MDL. See `docs/dev/TRAINER-AUDIT.md` section 7 item 6.

### What did you expect to happen?

- Stop All cancels pending retrains.
- Removing a coin cancels its timer.
- A trainer never runs in another coin's folder; the hub refuses to train a coin that is not configured.
- After an auto-retrain the runner is restarted, or the user is told it was stopped.

### Steps to reproduce

Scratch `POWERTRADER_HOME`, paper mode. Not run for this report.

1. In `<home>\config\gui_settings.json` set `"training_auto_interval_hours": 0.01` (36 s). The setting is not in the Settings window.
2. Train ETH and wait for `DEBUG: Scheduled auto-retrain for ETH` in the console.
3. Then try either of these:
   - Start the Neural Runner, then click Start/Stop All, which stops while the runner is running. An ETH trainer still starts within 36 s.
   - Remove ETH in Settings and save. When the timer fires, `DEBUG: Working directory:` prints the root (BTC's folder), and BTC's model files are replaced.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
n/a (found by reading the code)

### Logs
```shell
None: found by reading the code.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## B4

**Filed as:** #147 (https://github.com/sjackson0109/PowerTraderAI/issues/147), labels `documentation`, `needs-triage`

**Title:** `[Bug]: docs/technical/ARCHITECTURE.md describes trainers, signal files and defaults that don't match the code`

**Suggested labels:** `documentation`, `needs-triage`. This could also go on the task form (Type: Documentation, label `task`).

### What happened?

| `docs/technical/ARCHITECTURE.md` at 7a84250 | What the code shows |
|---|---|
| `:29` "Individual Trainers (*/neural_trainer.py)" | No `neural_trainer.py` exists. The trainers are `app/pt_trainer.py`, `app/pt_trainer_standalone.py` and the per-coin copies (`git ls-tree`), all mocks, and since FDS-MDL Phase 1 the default `app/pt_pattern_trainer.py`. |
| `:36` "Replaced completely simulated "neural networks" (using `time.sleep()` with fake accuracy) with real PyTorch implementations." | The old default `app/pt_trainer.py` runs `time.sleep(0.5)` per epoch and prints `accuracy = (70.0 + epoch * 2.5 + i * 0.5)` (`:175-178`). `torch` is not in `requirements.txt` or `app/requirements.txt`. |
| `:46-48` `ModelTrainer(model, feature_eng)` / `trainer.train(market_data, epochs=100)` | The real signature is `def __init__(self, model_type: str = "lstm", device: str = None)` (`app/pt_neural_network.py:311`), and the method is `train_model` (`:412`). Nothing launches it. |
| `:57` "All coin-specific trainers (`BTC/neural_trainer.py`, `ETH/neural_trainer.py`, etc.) have been completely rewritten to use real PyTorch training" | The per-coin files are `app/<SYM>/pt_trainer.py` and `pt_trainer_standalone.py`. None imports torch. In `app/`, `git grep torch` matches only `app/pt_neural_network.py` and `app/pt_neural_processor.py` (neither is launched by anything) and two integration tests (`app/test_phase1_phase2_integration.py`, `app/test_phase3_integration.py`). |
| `:132-134` names only `pt_trainer_standalone.py` and the per-coin `pt_trainer.py` copies as mocks, and says the thinker writes `long_dca_signal.txt` and `short_dca_signal.txt` | The hub launched `app/pt_trainer.py`, which is also a stub (TRAINER-AUDIT section 3). Since `4fc3834` the thinker writes `signals_dca_spread.txt` and `signals_dca_single.txt` (issue A2). |
| `:151` "`strategy.active_id` (default `STRAT-000`, ...)" | `DEFAULT_ACTIVE_ID = "STRAT-001"` (`app/strategies/settings.py:25`; also `app/pt_settings_manager.py`). The module docstring (`settings.py:5`) has the same stale default. Not in the audit; found while checking. |

Why it matters: FDS-MDL Phase 3 is told to reproduce the legacy thinker's rule "exactly as documented in `ARCHITECTURE.md` (the "Signal Path" section from FDS-121)" (FDS-MDL section 6 item 2). Where the doc and the code differ, the code should win. See `docs/dev/TRAINER-AUDIT.md` section 7 item 7.

### What did you expect to happen?

The document matches the code:
- it names the trainer the hub launches (`pt_pattern_trainer.py`) and says which trainers are mocks;
- it removes or qualifies the "real PyTorch trainers" claims;
- it fixes the signal file names (or links A2), the `ModelTrainer` example and the default strategy.

### Steps to reproduce

1. `git ls-tree -r --name-only HEAD | grep -i neural_trainer` prints nothing.
2. Compare each cited line with the code location in the table.

### Trading mode
Not sure (documentation; not mode-related)

### Exchange
Not applicable

### Area
Other

### PowerTraderAI version or commit
7a84250

### Operating system
Windows (not OS-specific)

### Python version
n/a

### Logs
```shell
None.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## B5

**Filed as:** #148 (https://github.com/sjackson0109/PowerTraderAI/issues/148), labels `bug`, `needs-triage`

**Title:** `[Bug]: Hub writes app/__pycache__ at runtime, contrary to the "read-only program folder" rule`

**Suggested labels:** `bug`, `needs-triage` (low priority)

### What happened?

`pt_paths` says "The program directory is read-only at runtime" (`app/pt_paths.py:32`), and `program_dir()` says "Read-only at runtime: no component writes here" (`:154-155`). In practice:

- `start_powertrader.bat:12` runs `.venv\Scripts\python.exe app\pt_hub.py` without `-B`.
- Nothing in `app/` or the launcher sets `PYTHONDONTWRITEBYTECODE` or `sys.pycache_prefix` (`git grep`).
- So CPython writes `app/__pycache__/*.pyc` for every app module the hub imports.
- Child processes get an unchanged copy of the environment (`app/pt_hub.py:3855-3856`, `:5420-5421`, `:5690-5694`), so the runner, trader and trainer can add more files (INFERRED).
- The FDS-108a check doesn't catch this, because it skips `__pycache__` (`SKIP_DIRS`, `app/tests/test_program_dir_read_only.py:15`).

Impact is low. In a git checkout `__pycache__/` is ignored (`.gitignore:2`). In a truly read-only install, CPython quietly skips writing bytecode, so nothing breaks. It is a gap between the documented guarantee and what happens: the install folder is written to wherever that is allowed.

**Scope.** Not fixed by FDS-MDL. See `docs/dev/TRAINER-AUDIT.md` section 2.3 and section 7 item 9.

### What did you expect to happen?

Either nothing is written to the program folder, or the exception is documented. Ways to stop the writes: start with `-B` or `PYTHONDONTWRITEBYTECODE=1`, or point `PYTHONPYCACHEPREFIX` / `sys.pycache_prefix` at a folder under `pt_paths.cache_dir()` and pass it to child processes. Otherwise, document bytecode caches as the one exception in `pt_paths` and `ARCHITECTURE.md`.

### Steps to reproduce

1. In a checkout, delete `app\__pycache__`.
2. Set `POWERTRADER_HOME` to a scratch folder, start the hub with `start_powertrader.bat`, then close it.
3. `app\__pycache__\*.pyc` exists again.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Other

### PowerTraderAI version or commit
7a84250

### Operating system
Windows

### Python version
n/a

### Logs
```shell
None.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## D1

**Filed as:** #149 (https://github.com/sjackson0109/PowerTraderAI/issues/149), labels `bug`, `needs-triage`, `component-trading`

**Title:** `[Bug]: Pattern trainer never saves its weight updates, so every saved memory weight is 1.0`

**Suggested labels:** `bug`, `needs-triage` (optional: `component-trading`)

### What happened?

`app/pt_pattern_trainer.py` is a faithful port of upstream `pt_trainer.py` at `ba62130` (owner decision, FDS-MDL Phase 1), and keeps this upstream bug on purpose.

On every step, `run_pass` re-reads the flushed weight files into local lists (`weight_list`, `high_weight_list`, `low_weight_list`) and, when memories matched, adjusts the matched entries by ±0.25 on those local lists. The lists are then dropped. `ModelFiles.flush` writes the in-RAM cache (`mem["weight_list"]` and so on), which only ever receives `"1.0"` for each new memory. Upstream does the same: the updates at `ba62130:pt_trainer.py:1529-1534` go to the lists re-read at `:851-859`, and `flush_memory` (`:152-179`) writes the cache.

Effects:
- Every value in `memory_weights_<tf>.txt`, `memory_weights_high_<tf>.txt` and `memory_weights_low_<tf>.txt` is `1.0`. `test_default_mode_keeps_upstreams_output_and_adds_the_unflushed_tail` asserts this.
- The thinker's weighting (`moves.append(move * weight)`, `app/pt_thinker.py:883-893`) is an unweighted average, and its "skip weight 0" rule never applies.
- Any statement that the model "learns weights" is wrong for this trainer; what it learns is the memory list and the match threshold.

**Scope.** Kept by FDS-MDL on purpose. Fixing it changes the model's output, so the equivalence test against upstream (`test_the_port_writes_the_same_model_files_as_upstream`) would need a separate upstream-compatible mode, as `--upstream-flush-only` is for the flush schedule. D2 starts to matter once this is fixed.

### What did you expect to happen?

Weight updates are applied to the cached lists that get saved, so the saved weights reflect how well each memory predicted. Or, if the weights are not meant to change, the update code is removed and the files are documented as constant.

### Steps to reproduce

1. Offline: `python -m pytest app/tests/test_pattern_trainer.py -k unflushed_tail` (synthetic candles, network blocked). It asserts every saved weight is `1.0`.
2. Or train any coin and open `memory_weights_1hour.txt`: every entry is `1.0`, although the summary's `matched_steps` shows memories matched on many steps.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
feat/model-strategy-1 (FDS-MDL Phase 1); upstream ba62130

### Operating system
Windows (not OS-specific)

### Python version
3.13

### Logs
```shell
None.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## D2

**Filed as:** #150 (https://github.com/sjackson0109/PowerTraderAI/issues/150), labels `bug`, `needs-triage`

**Title:** `[Bug]: Pattern trainer's close-weight test compares a percentage with 100 times a percentage`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

Kept from upstream `ba62130` on purpose (faithful port). In `run_pass` (`app/pt_pattern_trainer.py`), for each matched memory:

```python
var3 = moves[indy] * 100            # moves: close move % (already a percentage) x weight
high_var3 = high_moves[indy] * 100  # high_moves: (high move % / 100) x weight -> a percentage
low_var3 = low_moves[indy] * 100    # low_moves:  (low move % / 100) x weight  -> a percentage
...
if perc_diff_now_actual > var3 + (var3 * 0.1): ...   # perc_diff_now_actual is a percentage
```

`moves` holds the memory's close move in percent (`float(memory_pattern[-1])`), while `high_moves` and `low_moves` were divided by 100 when read. So the high and low tests compare percentages with percentages, but the close test compares a percentage with 100 times a percentage. Upstream: `ba62130:pt_trainer.py:1484-1486` and the reads at `:898-899`.

Effect today: none on the saved files, because D1 discards every weight update. Once D1 is fixed, close weights would move almost entirely by the sign of the predicted move rather than by its accuracy (INFERRED): for a positive predicted move, `var3` is about 100 times the realised move, so the weight falls; for a negative one it rises.

**Scope.** Kept by FDS-MDL on purpose. Fix together with D1.

### What did you expect to happen?

All three tests compare the realised move with the predicted move in the same unit (for example `var3 = moves[indy]`).

### Steps to reproduce

Read `run_pass` in `app/pt_pattern_trainer.py` next to `ba62130:pt_trainer.py:1484-1528`. Found by reading the code.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
feat/model-strategy-1 (FDS-MDL Phase 1); upstream ba62130

### Operating system
Windows (not OS-specific)

### Python version
n/a (found by reading the code)

### Logs
```shell
None: found by reading the code.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## D3

**Filed as:** #151 (https://github.com/sjackson0109/PowerTraderAI/issues/151), labels `bug`, `needs-triage`

**Title:** `[Bug]: Pattern trainer matches each candle only against memories flushed to disk, and re-reads them on every step`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

Kept from upstream `ba62130` on purpose (faithful port). On every step, `run_pass` (`app/pt_pattern_trainer.py`) re-reads the four model files from disk with `ModelFiles.read_list` and matches the current candle against what they hold. New memories go to the in-RAM cache and reach the files only at the batch flush every 200 steps (`FLUSH_EVERY`). Upstream: `ba62130:pt_trainer.py:846-859` (reads), `:1541` and `:1564` (flushes every 200 loops).

Effects:
- **Memories made since the last flush are invisible to matching.** A pattern seen twice within 200 steps is stored twice instead of matching. At the start of each timeframe no file exists yet, so the first 200 steps cannot match and each stores a new memory. On BTC 2023–2025 every pass 0 shows 3,279 steps, 2,993 matched and 286 new memories, 200 of them from those first steps.
- **Cost.** Each step parses every flushed memory from text again, so a pass costs about steps × memories string splits and float conversions. A full BTC run on 2023–2025 1h data takes about 60 s (`docs/dev/RUN-LOG-model-1.md`). Under cProfile (99 s with profiling overhead), `ModelFiles.read_list` took 23% of the time (cumulative) and `_strip` 18% (cumulative; 14.3 million calls, almost all from the matching loop; the two overlap slightly because `read_list` also calls `_strip`). The rest is mostly the per-memory comparison loop itself.

**Scope.** Kept by FDS-MDL on purpose. Matching against the cache instead changes the model's output (more matches, fewer duplicate memories) and needs the same kind of upstream-compatible mode as D1.

### What did you expect to happen?

Each step matches against every memory learned so far, held in memory, and the files are written at the end (or periodically, for progress) without being read back.

### Steps to reproduce

1. Train any coin and read `<data>/training_results/<coin>_training_results.json`. In every timeframe's pass 0 (201 steps on the 10-week test fixture, 3,279 on 2023–2025 data), `new_memories` is at least 200 and `matched_steps` is at most `steps - 200`.
2. Profile a run: most of the time is in `ModelFiles.read_list` and the matching loop.

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
feat/model-strategy-1 (FDS-MDL Phase 1); upstream ba62130

### Operating system
Windows (not OS-specific)

### Python version
3.13

### Logs
```shell
None.
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

### Also noted, not drafted

Two more upstream behaviours are kept and documented in the trainer's header and the run log rather than drafted, because they are design choices rather than defects:
- pass 0 of every timeframe trains on 1-hour bars (`tf_list = ['1hour', tf_choice, tf_choice]`, `ba62130:pt_trainer.py:365`);
- intraday timeframes, and pass 0 of every timeframe, use only the older half of the window (the owner decided to keep this; the trainer prints and records the counts).

---

## E1

**Filed as:** not yet filed

**Title:** `[Bug]: Neural runner's bound remap drops repeats: with two inactive timeframes, later timeframes use a neighbour's bounds`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

At the end of each sweep, `step_coin` rebuilds each timeframe's low and high bound: its predicted low and high moved 0.5% outwards, or the placeholders `0.01` and `99999999999999999` when the timeframe is inactive (`7a84250:app/pt_thinker.py:1184-1203`). It sorts both lists for the gap pass (`:1205-1207`) and then maps the sorted values back to timeframe order. The mapping records where each sorted value came from with `list.index`, which returns the first match, and the remap skips any index it cannot find:

```python
# 7a84250:app/pt_thinker.py:1212-1218
while True:
    og_low_index_list.append(
        low_bound_prices.index(new_low_bound_prices[og_index])
    )
    og_high_index_list.append(
        high_bound_prices.index(new_high_bound_prices[og_index])
    )
```

```python
# 7a84250:app/pt_thinker.py:1299-1311
while True:
    try:
        low_bound_prices.append(
            new_low_bound_prices[og_low_index_list.index(og_index)]
        )
    except:
        pass
    try:
        high_bound_prices.append(
            new_high_bound_prices[og_high_index_list.index(og_index)]
        )
    except:
        pass
```

When two timeframes share a value, `list.index` maps both to the first one, so the second one's index never appears. The remap's bare `except: pass` skips it, and every later bound is appended one place early. The lists come back one entry short per repeat and are saved that way (`:1443-1444`). At the next end of sweep, `_pad_to_len` (`:992-999`, applied at `:1004-1005`) fills the tail with the placeholders, and the SHORT and LONG tests (`:1053-1056`, `:1090-1093`) read the bounds by position.

The usual repeat is two or more inactive timeframes, whose placeholders are identical. When the second inactive timeframe comes before 1week:
- each active timeframe after it is judged on a later timeframe's band (one place on per repeat), so it can signal where its own band would not, or the reverse;
- the last timeframes get the padded placeholders. For a coin priced at $0.01 or more (all the default coins), `current > 99999999999999999` and `current < 0.01` are never true, so an active 1week never signals (with three inactive timeframes, 1day neither). For a coin priced below $0.01, `current < 0.01` is always true, so the padded slot is LONG on every sweep instead;
- 1hour always keeps its own bounds, and inactive timeframes stay silent anyway (their predicted high equals their low: `:957-961`, `:1055`, `:1092`).

Two active timeframes with exactly equal predicted lows (or highs) trigger it too, in that list only. That needs equal predicted prices as floats, which is unlikely from a trained model (INFERRED).

**Measured on a recording of the real runner.** `app/tests/fixtures/strat003_thinker_record.json` records `step_coin` (blob `97aee15`: main's bound code, unchanged) over 241 hourly decisions on synthetic bars, with a model whose 4hour and 12hour never match and whose 1day matches on some bars (97 decisions have two inactive timeframes, 144 have three). Long / short / none per timeframe, as recorded and with each timeframe on its own bounds (the kept bounds put back on their own timeframes and compared again; the shifted mapping reproduces all 241 recorded rows):

| Timeframe | As recorded | On its own bounds |
|---|---|---|
| 1day | 5 / 52 / 184 | 19 / 22 / 200 |
| 1week | **0 / 0 / 241** | 5 / 183 / 53 |

1hour, 2hour and 8hour are the same in both columns; 4hour and 12hour are inactive. These counts are what the runner writes to `signals_dca_spread.txt` and `signals_dca_single.txt` (`:1382-1383`, `:1396-1397`). For a coin at $0.01 or more with two inactive timeframes before 1week, at most 4 timeframes can be LONG instead of 5, so once #142 is fixed a `legacy_neural` trader could reach only the first neural DCA level (`7a84250:app/pt_trader.py:2212-2218`) (INFERRED).

How often: on three-year BTC and ETH models from the FDS-MDL pattern trainer, 1hour to 1day were each active on 98–100% of the validation fit's held-out bars (`docs/dev/trainer-port-evidence-phase2.json`, runs L1 and L2, on `feat/model-strategy-1`), so two of them inactive at once looks rare (INFERRED, from per-timeframe shares).

**Scope.**
- **Latent on main.** The runner stalls before this code (#141, a static trace). The trainers the hub launches on main write files the runner cannot parse, so every timeframe is inactive and nothing signals either way (#143); only models from the FDS-MDL pattern trainer, or upstream's trainer, reach this code with active timeframes. The runner's counts do not reach the trader (#142).
- **Upstream behaviour:** the same lines are at `ba62130:pt_thinker.py:880-957` (padding at `:747-761`), in the fork since its first upload (`b4522b0`).
- **STRAT-003** (FDS-MDL Phase 3, on `feat/model-strategy-1`, not yet published) reproduces the runner's rule, this quirk included, so its backtest decisions include it; the Phase 4 backtest will count the decisions with two or more inactive timeframes before 1week. Fix the runner and `pattern_model.thinker_bounds` together and re-record the fixture, or keep a legacy-compatible mode for the bar-for-bar test, as #149 suggests for the trainer.

### What did you expect to happen?

Each timeframe keeps its own bounds after the gap pass, and both lists keep all seven entries. Inactive timeframes keep their placeholders and stay silent, which the high ≠ low test already ensures.

A possible fix: build both index orders first (lows descending, highs ascending), run the existing gap pass once on both sorted lists as now, then write each sorted value back to the index it came from. Every index is written once, so ties do not matter, and nothing changes when no value repeats.

### Steps to reproduce

1. Offline, in plain Python, with the runner's own expressions (a coin priced above $0.01):
   ```python
   # 4hour and 12hour inactive (placeholder 0.01); the other bounds are far apart, so the gap pass moves nothing
   low_bound_prices = [98.5, 97.5, 0.01, 93.5, 0.01, 89.5, 79.5]
   new_low_bound_prices = sorted(low_bound_prices)
   new_low_bound_prices.reverse()
   og_low_index_list = [low_bound_prices.index(v) for v in new_low_bound_prices]
   print(og_low_index_list)  # [0, 1, 3, 5, 6, 2, 2]: 4 (12hour) is missing
   kept = []
   for og_index in range(len(new_low_bound_prices)):
       try:
           kept.append(new_low_bound_prices[og_low_index_list.index(og_index)])
       except ValueError:  # the runner has a bare `except: pass`
           pass
   print(kept)  # 6 entries: 12hour's slot holds 1day's bound, 1day's holds 1week's
   print(kept + [0.01] * (7 - len(kept)))  # padded as at :1004; 1week gets 0.01
   ```
   Running the runner's lines `1205-1314` verbatim on these lows, with highs `[101.5, 102.5, 99999999999999999, 106.5, 99999999999999999, 110.5, 120.5]`, gives the same kept lows, and the highs shift the same way.
2. On `feat/model-strategy-1` (not yet on main): `python -m pytest app/tests/test_model_strategy.py -p no:cacheprovider -k "remap_drops_repeated or reproduces_the_recorded_runner"`. The first test asserts the shifted lists; the second checks STRAT-003 against the recording.
3. In the hub (not run; blocked today by #141 and #143): run the neural runner on a coin trained with the pattern trainer (`app/pt_pattern_trainer.py` on `feat/model-strategy-1`), whose model has two timeframes before 1week that match nothing on the current bars. On the next sweep, 1week's line reads `WITHIN on 1week timeframe. Low Boundary: 0.01 High Boundary: 99999999999999999` even though 1week is active (INFERRED).

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
7a84250 (legacy runner); STRAT-003 on feat/model-strategy-1 (FDS-MDL Phase 3, not yet published); upstream ba62130

### Operating system
Windows (not OS-specific)

### Python version
3.13

### Logs
```shell
[0, 1, 3, 5, 6, 2, 2]
[98.5, 97.5, 0.01, 93.5, 89.5, 79.5]
[98.5, 97.5, 0.01, 93.5, 89.5, 79.5, 0.01]
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## E2

**Filed as:** not yet filed

**Title:** `[Bug]: Neural runner's gap pass loops for ever on two zero bounds, so the runner stops processing coins`

**Suggested labels:** `bug`, `needs-triage`

### What happened?

At the end of each sweep the neural runner sorts the timeframes' low and high bounds and runs a "gap pass", which nudges neighbouring bounds apart until each pair is at least 0.25% + 0.25% × position apart (`7a84250:app/pt_thinker.py:1183-1294`). A pair is skipped when either list holds a placeholder (`0.01` or `99999999999999999`, an inactive timeframe) at that position (`:1226-1232`). The pass never ends when a pair it checks holds two zero bounds:

```python
# 7a84250:app/pt_thinker.py:1234-1249, 1267-1277, 1291-1294 (each statement joined onto one line; the file wraps them)
try:
    low_perc_diff = (abs(new_low_bound_prices[og_index] - new_low_bound_prices[og_index + 1]) / ((new_low_bound_prices[og_index] + new_low_bound_prices[og_index + 1]) / 2)) * 100
except:
    low_perc_diff = 0.0
...
if low_perc_diff < 0.25 + gap_modifier or new_low_bound_prices[og_index + 1] > new_low_bound_prices[og_index]:
    new_price = new_low_bound_prices[og_index + 1] - (new_low_bound_prices[og_index + 1] * 0.0005)
    del new_low_bound_prices[og_index + 1]
    new_low_bound_prices.insert(og_index + 1, new_price)
    continue
...
og_index += 1
gap_modifier += 0.25
if og_index >= len(new_low_bound_prices) - 1:
    break
```

1. `0 / 0` raises `ZeroDivisionError`, and the bare `except` sets the difference to 0.0 (`:1248-1249`).
2. 0.0 is below the threshold, so the second bound is nudged: `0 - 0 * 0.0005` is 0 (`:1272-1276`).
3. `continue` (`:1277`) goes back to the top of the loop (`:1225`) without moving `og_index` or `gap_modifier` on (`:1291-1292`), so the next pass sees exactly the same state, for ever. The high list does the same at `:1250-1265` and `:1279-1289`.

Whether the zero pair is checked depends on where it sorts (each case run on a verbatim copy of `:1183-1314` with a pass counter):
- **Low list** (descending): zero lows sort last, below the `0.01` placeholders, and the high list ends with one placeholder per inactive timeframe. So zero lows hang the pass when there are at least two more of them than inactive timeframes. Two zero lows (1hour and 2hour) hang it at position 5 only when all seven timeframes are active; with 1week inactive the pass ends.
- **High list** (ascending): zero highs sort first, so two of them hang the pass at position 0 whenever the two largest low bounds are not placeholders, for example two timeframes whose last candle closed at 0 and at least two other active ones.

A single zero bound ends. On positive bounds in the normal float range the pass always ends; the longest found is 587 passes (seven equal bounds). Two bounds at or below zero also never end when their pair is checked; a bound below zero needs a predicted price below zero.

**How a bound becomes zero.** `distance` is 0.5 (`:476`), so a bound is 0 only when the predicted price, `start_price + start_price * diff` (`:949-951`), is 0: the last candle closed at 0, or the mean of weight × move over the matched memories (`:890-894`, `:911-913`) is exactly −100%. With every saved weight at 1.0 (#149), the second needs every matched memory to have seen a next bar whose low (or high) was 0. Neither was shown on real data (INFERRED). Binance candles should not have zero prices, but nothing checks for them (`app/market_data/candles.py`, the pattern trainer's source, checks only timestamps; the runner's candles come from DataProvider, #141). Hand-made or corrupted model files reach it directly.

**What the runner does while stuck** (INFERRED: traced through the code, not run):
- `step_coin` never returns, so the main loop (`:1522-1525`) stops at this coin: later coins are never processed, the last log line is `Processing <coin>...`, and the gap pass, which has no sleep, keeps one CPU core busy. Nothing after the gap pass runs for this coin (bound files, `runner_ready.json`, `signals_dca_*`, state save: `:1317-1465`), and nothing raises, so the process stays alive. Restarting on the same model and candle hangs again.
- A hang in either of the first two sweeps comes before the runner reports ready (ready needs one earlier rebuild of the bounds, `:1344-1351`). Start All polls until the runner reports ready, exits, or Stop All is pressed (`7a84250:app/pt_hub.py:5200-5223`), so it never starts the trader, even in the default catalogue engine, which does not need the runner. A hang from the third sweep on leaves the runner "ready" while its files stop updating; today the trader reads none of its signal files (#142).

**Scope.**
- **Latent on main.** The runner stalls before this code (#141, a static trace). With the mock trainers' files every timeframe is inactive, so every pair is skipped and the pass cannot hang (#143); the FDS-MDL pattern trainer's files can make it hang.
- **Upstream behaviour:** the same loop is at `b4522b0:pt_thinker.py:911-941`.
- **STRAT-003** (FDS-MDL Phase 3, on `feat/model-strategy-1`, not yet published) reproduces the rule but counts passes. After 100,000 (`GAP_PASS_LIMIT` in `app/pattern_model.py`) it raises `GapPassStuck`, and the strategy holds with reason `BOUNDS_NOT_CONVERGED`; the Phase 4 backtest will report how often that happens (expected never). A single bound far below its neighbours can take more than 100,000 passes to end (a predicted low of −1e30 among lows near 100: about 129,000), so there STRAT-003 holds where the runner would finish; only hand-made files give such a bound. A fix to the runner should change STRAT-003 the same way, or record the difference.

### What did you expect to happen?

The gap pass always ends, and a bad bound does not freeze the runner. For example:
- treat a predicted price of 0 or below (or one that is not finite) as an inactive timeframe before the bounds are built, or skip a pair where either bound is 0 or below, as a placeholder pair is skipped;
- also bound the loop (587 passes is the longest found on positive bounds). If the limit is reached, log the coin, write no new signals for it and go on to the next coin.

### Steps to reproduce

1. Offline, in plain Python, run the gap pass's own statements on one low-list pair at position 0:
   ```python
   def gap_pair(b, og_index=0, gap_modifier=0.0, passes=10):
       for n in range(passes):
           try:
               low_perc_diff = (abs(b[og_index] - b[og_index + 1]) / ((b[og_index] + b[og_index + 1]) / 2)) * 100
           except:
               low_perc_diff = 0.0
           if low_perc_diff < 0.25 + gap_modifier or b[og_index + 1] > b[og_index]:
               b[og_index + 1] = b[og_index + 1] - (b[og_index + 1] * 0.0005)
               continue  # back to the top; og_index and gap_modifier unchanged
           return f"ends after {n} nudges: {b}"
       return f"still looping after {passes} passes: {b}"

   print(gap_pair([99.5, 99.5]))  # ends after 5 nudges
   print(gap_pair([0.0, 0.0]))    # still looping: [0.0, 0.0] never changes
   ```
2. On `feat/model-strategy-1` (not yet on main): `python -m pytest app/tests/test_model_strategy.py -p no:cacheprovider -k gap_pass`. `test_a_gap_pass_that_never_ends_holds` writes model files in which every timeframe is active and 1hour and 2hour predict a −100% low; the rule raises `GapPassStuck`, and the strategy holds with `BOUNDS_NOT_CONVERGED`.
3. The real runner: not run (blocked by #141). Once it can run, on 7a84250, model files in the coin's folder whose 1hour and 2hour memories all record a low move of `-100.0`, with every other timeframe matching and a fresh `trainer_last_training_time.txt` (on `feat/model-strategy-1`, published instead), should stop the log at `Processing <coin>...` at the end of the first sweep (INFERRED).

### Trading mode
Paper (mode-independent)

### Exchange
Not applicable

### Area
Trainer/thinker

### PowerTraderAI version or commit
7a84250 (runner; the same loop is in upstream b4522b0); STRAT-003 on feat/model-strategy-1 (FDS-MDL Phase 3, not yet published)

### Operating system
Windows (not OS-specific)

### Python version
3.13 (the offline runs and the tests)

### Logs
```shell
# output of step 1; the runner itself was not run
ends after 5 nudges: [99.5, 99.2514986256561]
still looping after 10 passes: [0.0, 0.0]
```

### Before you submit
- [x] I have removed any API keys, secrets and personal account details.

---

## C. Release notes

> **Legacy neural pipeline: correction.** The legacy train → think → trade pipeline (the hub's Train buttons, the neural runner and the trader's `legacy_neural` signal mode) has not worked end to end since February 2026. From 25 February 2026 the trainer the hub launched was a placeholder that did not learn from market data: the accuracy shown during training since 25 February 2026 was a formula, not a measurement, and the saved "final accuracy" was always 95.0. Even a real trainer's output would not have reached a trade. Reading the code shows three breaks: the neural runner receives a single price candle and stops making progress at the first trained coin; it cannot read the placeholder's model files; and since March 2026 the trader has looked for signal files under names the runner no longer writes.
>
> This release makes the hub's default trainer `pt_pattern_trainer.py`, a port of the original PowerTrader_AI pattern-matching trainer (upstream commit `ba62130`). It trains on cached Binance candles over a stated window (by default the three years up to the last full hour) and records the window, the seed and every bar count it used. Tests check that, on the same candles and in a test mode that keeps the upstream trainer's save schedule, it writes byte for byte the same model files as the upstream trainer (in normal use it also saves the memories and the final threshold that the upstream trainer lost at the end of each timeframe); that it gives the same output for the same data and different output for different data; and that it never reads a candle that closes after the end of the window. The placeholder trainers remain, labelled as mocks, and the hub refuses to launch them unless `allow_mock_trainer` is set to `true` in `pt_config.json`. If you saved Settings before this release, your `gui_settings.json` may still name `pt_trainer.py`: the hub will then refuse to train and tell you to set the trainer path to `pt_pattern_trainer.py`. STRAT-001 stays the default strategy. The legacy runner-to-trader handoff is not repaired in this release; it is tracked in #141, #142 and #143.

Before publishing:
- **Issue numbers:** #141, #142 and #143 (filed 2026-10-06).
- **"Since February 2026" and "since 25 February 2026" are deliberate qualifiers** (owner decision). The evidence covers every commit since 2026-02-22 (thinker), 2026-02-25 (stub trainer) and 2026-03-06 (file names). The fork's commits from 2026-02-19 to 2026-02-22 ran upstream's pipeline and were not audited.
- **What the code shows versus what was run.** The runner stall is a static trace. The parse failure, the accuracy formula and the 95.0 were observed in executed runs (`docs/dev/trainer-audit-evidence.json`).
- **Model provenance (FDS-MDL Phase 2).** If it lands in the same release, add: every training run now publishes its model to `hub_data/strategy_models/<model_id>/` with a manifest recording the trainer, the window, the candles, the seed and validation metrics (a separate fit on the window's first 80%, scored on its last 20%). The neural runner uses a coin's model only if its files match a published manifest, and prints the model_id it uses. Models trained before this release have no manifest, so retrain each coin once.
- **STRAT-003.** If the strategy and its backtest (FDS-MDL Phases 3 and 4) land in the same release, add one sentence: the trained model is evaluated as strategy STRAT-003 in the catalogue backtester, on data it was not trained on, against buy-and-hold and random entries.
- **Paper mode.** The earlier draft said the project's own runs were in paper mode. That claim has no cited evidence, so it is left out.
