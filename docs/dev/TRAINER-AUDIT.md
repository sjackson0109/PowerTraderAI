# Trainer audit (FDS-MDL Phase 0)

| | |
|---|---|
| Spec | `docs/dev/specs/FDS-MDL-trained-model-strategy.md` section 3, as amended by `FDS-MDL-A-addendum-after-108a.md` (v3) section 5 |
| New base | `main` at `7a84250` (`app/` identical on `feat/model-strategy-1`); pre-FDS-108a side: `858a0eb` |
| Date | 2026-10-05 |
| Issue | Closes #136 (trainer tests that don't exercise the real launch); see section 8 |
| Evidence | `docs/dev/trainer-audit-evidence.json`, written by `app/tests/audit_trainer_evidence.py` (section 10) |
| Port verdict | Section 11 (2026-10-06): the four checks re-run against the ported trainer, `app/pt_pattern_trainer.py`; static, determinism and data dependence pass; reported metrics (held out) fail; to be re-run after Phase 2 |

Line numbers are as of `7a84250` (after the Black reformat) unless a commit is given; each citation also names the
function or symbol. "Static" means read from the code; "executed" means observed in the evidence runs; "INFERRED" marks a
conclusion traced through code but not run.

## Verdict

### Gating verdict: STUB

**The script the hub launches on the new base, `app/pt_trainer.py` (blob `c85fc4c`), is a stub.** Its outputs are not
learned from data. This is the verdict that gates Phase 1 (addendum 5.3).

| Check (FDS-MDL 3.3) | Result | Evidence |
|---|---|---|
| Static | **FAIL** | `time.sleep(0.5)` in the epoch loop; accuracy is a formula of the loop counters; `"final_accuracy": 95.0` is a literal; weights are unseeded `random.uniform`; market data is never parsed (section 3.1) |
| Determinism | **FAIL as launched** | The trainer has no seed. Two runs on the same data differ in 28 of 35 model files. They are identical (0 of 35) only when Python's `random` is seeded from outside the trainer (section 3.2, executed) |
| Data dependence | **FAIL** | With the RNG pinned, four different prices fed through the real data provider, and a different coin, give byte-identical model files (section 3.3, executed) |
| Reported metrics | **FAIL** | Nothing is held out. The accuracy the hub shows is `70.0 + epoch*2.5 + i*0.5`; the saved `final_accuracy` is 95.0 in every run, for every input (section 3.4) |

Static, data dependence and reported metrics fail outright. Determinism as the spec words it ("with a fixed seed")
cannot be run through the trainer, which has no seed; as launched, it fails.

### The MIXED question and the Phase 1 route: the owner's decision

- **By the spec's definitions, not MIXED.** FDS-MDL calls a trainer REAL when all the 3.3 checks pass, and MIXED when the
  hub launches a stub "but a real trainer exists elsewhere". The only genuine learner in the tree,
  `app/pt_neural_network.py` (`ModelTrainer`), fails the determinism and held-out checks on reading (static only: it
  cannot run in the project environment, because `torch`, `scikit-learn` and `ta` are not installed), and it writes
  nothing the thinker reads (section 6).
- **By the looser rule in the owner's note ("a genuine learner that nothing launches"), MIXED.** `ModelTrainer` does
  real gradient descent, and nothing launches it.
- **Either way, Phase 1 is a choice:** (A) wire in `pt_neural_network.py`, or (B) port the upstream pattern-matching
  trainer, which survives in this repo's history (section 6).
- **Recommendation: B.** Phase 3 must reproduce the legacy thinker's LONG/SHORT decisions bar for bar (FDS-MDL acceptance
  7), and those decisions are built from the memories, weights and threshold files only an upstream-style trainer writes.
  An LSTM regression model cannot reproduce that rule, so route A would make Phase 3 log BLOCKED unless the spec changes.
  Route A would also need `torch`, `scikit-learn` and `ta` added to `requirements.txt` (which this spec must not edit),
  a seed, a `train_end` window, an honest held-out split and a thinker-format writer: most of a rewrite.

### Not BLOCKED, for default settings

The hub's trainer is identified with certainty for default settings (section 1). The setting is free text: every
**tracked** file it could point at is a stub or not a trainer (section 4). The owner's own settings file was not
opened; confirming that `script_neural_trainer` there is `pt_trainer.py` (or another tracked path) is the remaining
precondition for the owner's install (section 1.4).

### For the release notes

By static trace (not executed): **the thinker never weighed these files.** For a trained coin, `step_coin` loops
forever in its candle fetch, because the data provider returns a single candle; the model files are read only after
that loop (section 2.1, section 7 item 1). Had it got through, every timeframe would have been INACTIVE (the files do not
parse, section 3.6), and since `4fc3834` the trader does not read the thinker's signal files anyway (section 7 item 2).
The accuracy shown during training is the stub's formula. Only paper mode has ever run.

### Scope of Phase 0 changes

No production code was changed. Phase 0 adds and replaces tests only, to close #136: the kickoff assigns #136 to Phase 0,
#136's proposal is to delete the two no-op tests "as part of the trainer audit", and addendum 5.3 requires the
determinism and data-dependence checks to execute real training. It also adds this document and its evidence file.

---

## 1. What the hub launches (FDS-MDL 3.1; addendum 5.1)

### 1.1 The script

| Step | Code |
|---|---|
| Default setting | `DEFAULT_SETTINGS["script_neural_trainer"] = "pt_trainer.py"` (`app/pt_hub.py:600`) |
| Settings file | `PowerTraderHub._load_settings` reads `pt_paths.gui_settings_file()`, i.e. `<config>/gui_settings.json`, shallow-merged over the defaults (`app/pt_hub.py:2570-2584`) |
| Resolution | `PowerTraderHub._refresh_trainer_path`: `self.proc_trainer_path = os.path.abspath(os.path.join(self.project_dir, self.settings["script_neural_trainer"]))` (`app/pt_hub.py:2629-2639`), with `self.project_dir = pt_paths.program_dir()` (`:2010`), the `app/` folder |
| When resolved | In `__init__` (`app/pt_hub.py:2076`) and on every Settings save (`:8602`). Nothing else sets it |
| Resolved value (defaults) | `<checkout>/app/pt_trainer.py` |
| Where it can be changed | The Settings field "pt_trainer.py path:" (`app/pt_hub.py:7497-7499`, `:7713`), saved to `gui_settings.json`. The value is not validated: a relative path such as `ETH/pt_trainer.py` resolves inside `app/`, and an absolute path is used as it is |

### 1.2 How it is started

`PowerTraderHub.start_trainer_for_selected_coin` (`app/pt_hub.py:5615`), reached from `train_selected_coin`,
`train_all_coins` and the auto-retrain timer:

1. Stops the neural runner (`stop_neural`).
2. Working folder: `coin_cwd = self.coin_folders.get(coin, self.settings["main_neural_dir"])` (`:5632`).
3. Deletes `trainer_last_training_time.txt`, `trainer_status.json`, `trainer_last_start_time.txt`, `killer.txt`,
   `memories_*.txt`, `memory_weights_*.txt` and `neural_perfect_threshold_*.txt` from that folder (`:5657-5685`; the
   addendum's `pt_hub.py:5655` is stale after Black).
4. Environment: a copy of `os.environ` plus `POWERTRADER_HUB_DIR`, `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`
   (`:5690-5694`).
5. Command: `cmd_args = [sys.executable, "-u", "-W", "ignore", info.path, coin]` (`:5699`), where `info.path` is
   `trainer_path = self.proc_trainer_path` (`:5638`); `subprocess.Popen(cmd_args, cwd=coin_cwd, ...)` (`:5705`).

The new tests confirm, from inside the child process (section 8), the command line, working folder, `POWERTRADER_HOME`,
`POWERTRADER_HUB_DIR`, keyring backend and the absence of credential variables, and that a stale memories file is
removed; asserted for BTC and ETH.

### 1.3 Trainer root and coin folders

- **Root:** `self.settings["main_neural_dir"] = pt_paths.neural_dir(self.settings.get("main_neural_dir"))`
  (`app/pt_hub.py:2014`). `pt_paths.neural_dir` (`app/pt_paths.py:233`) uses
  `user_dir_setting(configured, models_dir(), "main_neural_dir")` (`:206`): blank means `models_dir()`; a relative value
  is joined to `data_dir()`; a value inside the install folder is refused with a warning and the default is used.
- **Default root:** `models_dir()` = `<data>/hub_data/models` (`app/pt_paths.py:200`), i.e.
  `%LOCALAPPDATA%\SJackson\PowerTraderAI\hub_data\models` on Windows, or `<POWERTRADER_HOME>/data/hub_data/models`.
- **Overrides:** the `main_neural_dir` key in `gui_settings.json` (Settings "Main neural folder:", saved at `:8483`), and
  `POWERTRADER_HOME`, which moves the whole data folder. The thinker and trader read `main_neural_dir` from the file
  named by `POWERTRADER_GUI_SETTINGS` when that variable is set; the hub always uses `pt_paths.gui_settings_file()`.
- **Coin folders:** `build_coin_folders` (`app/pt_hub.py:752`): BTC is the root itself (`:764`); every other coin is
  `<root>/<SYM>`. `_ensure_alt_coin_folders_and_trainer_on_startup` only creates the alt folders; nothing is copied.
- **Training results moved:** at `858a0eb` the summary went to `os.path.join(os.path.dirname(__file__), "..", "data")`
  (`858a0eb:app/pt_trainer.py:199`): `<repo>/data` for BTC and `app/data` for alts, inside the install tree. On the new
  base it is `pt_paths.data_file("training_results", f"{coin.lower()}_training_results.json")`
  (`app/pt_trainer.py:203-205`), i.e. `<data>/training_results/`. Nothing reads that file.

### 1.4 Certainty of identification

- With default settings the hub runs `app/pt_trainer.py` for every coin (above; asserted by the new tests).
- Every tracked file the setting could resolve to is a stub or not a trainer (section 4). An absolute or untracked path
  cannot be ruled out without the owner's settings file, which was not opened (addendum section 10). **Owner action:**
  confirm that `script_neural_trainer` in your `gui_settings.json` is `pt_trainer.py`.
- Corroboration, limited to the file name: the most recent training summaries at the pre-FDS-108a paths in the main
  checkout (`data/btc_training_results.json` and `app/data/{bnb,doge,eth,xrp}_training_results.json`, written
  2026-10-02 08:48) all hold `"timeframes": 7, "final_accuracy": 95.0`. Only the `f0c5fc4`/`c85fc4c` trainer writes a
  `"timeframes"` key, and the paths match its `dirname(__file__)/../data`. At `858a0eb` the hub used only the base name
  of the setting (`858a0eb:app/pt_hub.py:5575-5577`), so this proves the name was `pt_trainer.py`, not the full value.
  (Read by an audit agent; these are training summaries, not config.)

## 2. What the trainer writes and the thinker reads (FDS-MDL 3.2)

### 2.1 Files

| File (in the coin folder unless stated) | Written by `pt_trainer.py` | Read by | Compatible? |
|---|---|---|---|
| `neural_perfect_threshold_<tf>.txt` | One float, `max(0.8, final_accuracy/100*1.5)`, i.e. 1.425 to 1.470 (`:41-47`) | Thinker: `perfect_threshold = float(file.read())` (`app/pt_thinker.py:752`), the largest % difference at which a memory counts as a match. The thinker also **rewrites** the file on every step with `str(perfect_threshold)` (`:934-938`), so its bytes can change (`1.470` becomes `1.47`) | Parses, but the value comes from the mock accuracy |
| `memories_<tf>.txt` | 50 comma-joined floats (`:88`) | Thinker: commas stripped, then `.split("~")` (`:759-767`); each entry's pattern is `split("{}")[0]` split on spaces, its first value compared with the current candle and its last value taken as the move (`:820-832`); the high and low % come from `split("{}")[1]` and `[2]`, only for matching memories (`:852-877`) | **No.** One token remains, and `float()` raises `ValueError` (executed reproduction, section 3.6) |
| `memory_weights_<tf>.txt`, `memory_weights_high_<tf>.txt`, `memory_weights_low_<tf>.txt` | 50 comma-joined floats each (`:100-106`) | Thinker: read and split on spaces, one weight per memory (`:771-805`) | **No**, same reason: the files are read and split, but their float conversions are never reached because the memories parse fails first |
| `trainer_last_training_time.txt` | `str(time.time())` at the end of a successful run (`:210-212`) | Hub `_coin_is_trained`; thinker `_coin_is_trained` (14-day freshness gate) | Yes |
| `<data>/training_results/<coin, lower case>_training_results.json` | `coin`, `timestamp`, `timeframes`, `"final_accuracy": 95.0`, `status` (`:194-207`) | Nothing | — |

Timeframe names match: the trainer writes `1week … 1hour` (`app/pt_trainer.py:148`), the thinker reads the same seven
(`app/pt_thinker.py:477`). The thinker reads from `coin_folder(sym)` under `BASE_DIR = pt_paths.neural_dir(...)`
(`app/pt_thinker.py:397`), the same folder the hub starts the trainer in.

**Effect (static trace).** With the current data provider, `step_coin` never leaves its candle loop for a trained coin
(`app/pt_thinker.py:713-737`: one candle gives `len(history_list) == 1`, so it sleeps 0.2 s and retries for ever), so no
model file is read and no neural signal is written. Only if the provider returned two or more candles would the files be
read; then every timeframe would become `inactive` with `training_issues = 1` (`:926`), shown as
`INACTIVE (training data issue)` (`:1132`).

**The format the thinker expects is upstream's** (input to Phase 1 item 5, "keep the output format the thinker already
reads"): memories are `~`-joined entries `"<space-separated pattern>{}<high %>{}<low %>"`, where each entry records the
high and low % move that followed the pattern; weights are space-joined, one per memory (`b4522b0:pt_trainer.py:160-176`,
`:1549-1558`). Upstream also writes `trainer_status.json`, `trainer_last_start_time.txt` and
`trainer_last_training_time.txt` (`b4522b0:pt_trainer.py:252`, `:610-624`). The stub's comma format is **not** that format
and must not be preserved.

### 2.2 What the trainer reads

- `app/data_provider_config.json` (program folder; it has no `data_provider_settings` key, so the defaults apply).
- In `DataProvider`: `POWERTRADER_USER_REGION` (`app/pt_data_provider.py:48-50`), which matters only if no trading config
  loads (`app/pt_multi_exchange.py:314-316`).
- In `pt_multi_exchange`: `<config>/trading_config.json`, or the shipped `app/trading_config.example.json`; and, for every
  exchange in that file, credentials from `POWERTRADER_*` environment variables and the keyring
  (`_fill_credentials` → `pt_secrets.get_credentials`, `app/pt_multi_exchange.py:56`, `:159`; again per enabled exchange
  in `initialize`, `:332`). In the test runs the keyring is the "fail" backend, so no entry is read, and the credential
  variables are removed.
- Market data: `DataProvider.get_kline_data`, which returns **a string holding one synthetic candle** built from the live
  ticker price, whatever timeframe or `limit` is asked for:
  `kline_data = f"[[{current_time}, {price}, {price}, {price}, {price}, 1000]]"` (`app/pt_data_provider.py:226`).

### 2.3 Other side effects of a run

- Importing `pt_multi_exchange` creates the config folder (module-level `MultiExchangeManager()`,
  `app/pt_multi_exchange.py:504`, then `pt_paths.config_dir()`, `:96`).
- The hub, started without `-B` (`start_powertrader.bat`), writes `app/__pycache__` for its own imports. Its children do
  not get `PYTHONDONTWRITEBYTECODE` (`app/pt_hub.py:5690-5694`), so a hub-started trainer can add `pt_data_provider`'s
  `.pyc` (INFERRED; the tests disable bytecode writing). See section 7 item 9.
- Write inventory of the executed runs (evidence `home_files_added` / `home_files_changed`): the 35 model files and the
  stamp in the coin folder, and `data/training_results/<coin>_training_results.json`; nothing else was added or changed
  under the home folder. No file in the program folder, and no trainer output anywhere in the install folder, changed
  (bytecode caches excluded; bytecode writing disabled in the child).

## 3. Checks (FDS-MDL 3.3; addendum 5.3)

### 3.1 Static

All in `app/pt_trainer.py` at `7a84250` (blob `c85fc4c`); the same training code is at `858a0eb` (blob `f0c5fc4`) apart
from paths and imports.

- **Sleep in the epoch loop** (`NeuralTrainer.train`): `epochs = 10` / `for epoch in range(1, epochs + 1):` /
  `time.sleep(0.5)  # Reduced time per epoch` (`:173-175`): 7 timeframes x 10 x 0.5 s = 35 s, plus `time.sleep(1)` before
  exit (`:291`, `:297`). History: the sleep-loop stub first replaced the real trainer in `10e190e` (2026-02-25: 20 epochs
  x `time.sleep(2)` plus `time.sleep(5)`, no model files; its message says "Extended training duration to 45 seconds to
  maintain GUI status"). The current multi-timeframe version with random model files arrived in `49a2c92` (2026-03-16,
  "Add project management system", no message body).
- **Accuracy is not computed:** `accuracy = (70.0 + epoch * 2.5 + i * 0.5)  # Mock increasing accuracy per timeframe`
  (`:176-178`); the comment above the loop reads `# Simulate neural network training for this timeframe` (`:172`), while
  the method docstring says `"""Perform actual neural network training for the specified coin"""` (`:109`).
- **Literal accuracy:** `"final_accuracy": 95.0,` (`:198`).
- **`random` for weights and memories, never seeded** (`NeuralTrainer._create_neural_files_for_timeframe`):
  `import random` (`:38`); weights `0.5 + (final_accuracy/100.0) * 0.3 + random.uniform(-0.1, 0.1)` (`:92`), high and low
  `± random.uniform(0.05, 0.15)` (`:95-96`); fallback prices `base_price + (i * 10) + random.uniform(-100, 100)` with
  `base_price = 50000.0` for every coin (`:61-73`); memory padding `random.uniform(-2.0, 2.0)` (`:84`).
- **Market data is never parsed:** `for candle in historical_data[-100:]:` (`:53`) iterates the provider's **string**
  character by character; neither the list nor the dict branch matches, so `prices` stays empty and the random fallback
  always runs. Executed corroboration, in all 10 runs that used the real provider: the "price points" count
  (`:138`) equals the length of the provider's string (63 for the 8-character price 63742.07, 59 for the 7-character
  prices in X2-X5), and `Latest price data: ]` (`:140`) is its last character. (The two counterfactual runs used a list
  provider and print 100.)

### 3.2 Determinism (executed)

The trainer has no seed parameter or setting, so the spec's "fixed seed" cannot be given through its own interface.
Every run had `PYTHONHASHSEED=0`, so the only difference between the pairs below is whether Python's `random` was seeded.

| Runs | Setup | Model files that differ (of 35) |
|---|---|---|
| D1, D2 | BTC, BTC fixture, as launched (no seed) | **28**: every `memories_*`, `memory_weights_*`, `memory_weights_high_*`, `memory_weights_low_*`; the 7 thresholds are identical |
| D3, D4 | Same, with Python's `random` seeded to 0 before the trainer starts (instrumentation) | 0 |

**FAIL as launched**: two runs on the same data give different models. The seeded pair shows the output is a deterministic
function of the global RNG state, which the trainer does not let anyone set.

### 3.3 Data dependence (executed)

All runs with Python's `random` seeded to 0 and `PYTHONHASHSEED=0`, so any difference would have to come from the data.
The real data provider passes the trainer one value per request, a price, so each run was fed a different price: the
last close of the chosen fixture rows.

| Run | Coin | Fixture rows (only the last close is served) | Price served | Model files that differ from X1 (of 35) |
|---|---|---|---|---|
| X1 | BTC | `BTCUSDT_1h.csv`, all rows | 63742.07 | — |
| X2 | BTC | `ETHUSDT_1h.csv`, all rows | 1882.59 | **0** |
| X3 | BTC | `BTCUSDT_1h.csv`, rows 0-755 | 64198.0 | **0** |
| X4 | BTC | `BTCUSDT_1h.csv`, rows 756-1511 | 63600.0 | **0** |
| X5 | ETH | `ETHUSDT_1h.csv`, all rows | 1882.59 | **0** |

Each run made the same 8 price requests (the 1-hour call and one per timeframe), all answered from its fixture and parsed
by the real `BinanceExchange.get_current_price`.

**FAIL.** Four different prices, which is all the real provider can pass on, and a different coin give byte-identical
model files. The only output that changes is the stdout "price points" count (the string length).

### 3.4 Reported metrics

- The accuracy the hub shows in the Trainers pane is the trainer's stdout (`self._drain_queue_to_text(lp.log_q,
  self.trainer_text)`, `app/pt_hub.py:6468`): `  {timeframe} - Epoch {epoch}/{epochs} - Accuracy: {accuracy:.1f}%`, the
  formula above. The printed lines are identical across all 12 executed runs apart from the coin prefix, whatever the
  data, seed or provider.
- `final_accuracy` in the saved summary is 95.0 in all 12 runs.
- No data is held out; no split exists. **FAIL.**

### 3.5 Counterfactual (does not decide the verdict)

C1 and C2 replace `pt_data_provider` with a fixture provider that returns 1-hour candles in the list form the trainer
parses (and nothing for the other timeframes, so the trainer reuses the 1-hour candles for them); no exchange code runs.
With BTC (C1) and ETH (C2) candles and the same seed, **only the memories change**; weights and thresholds stay
identical. In both runs all 7 memories files are the same: the first 50 one-step % changes of the last 100 closes
(checked against each fixture), i.e. a copy of the data, not a fitted quantity. So fixing the data provider alone would
not make this trainer learn.

### 3.6 The thinker cannot read the output (reproduction)

The thinker's own parse expressions from `step_coin` (`app/pt_thinker.py:759-767`, `:820-832`), applied to run T1's
`memories_1hour.txt`, raise `ValueError: could not convert string to float` on the commas-stripped run of 50 values (the
exact text is in the evidence). The harness checks that both the thinker's source and the function it runs contain those
expressions. The same first-memory parse accepts an upstream-format sample. The thinker itself was not run.

## 4. Every trainer file, both sides (addendum 5.3)

SHA-256 is over the committed content (`git cat-file blob <id> | sha256sum`; LF line endings as stored). Working-tree
files have CRLF (`core.autocrlf=true`) and hash differently.

**Launched by** uses the addendum's categories, applied mechanically, plus one: *hub* = started by
`start_trainer_for_selected_coin` with default settings; *config* (added) = started by the hub only if Settings are
changed (the script path, or at `858a0eb` the main neural folder); *CLI* = has a `__main__` block that runs it by hand;
*nothing* = no launcher. At `7a84250` any `.py` file under `app/` is reachable through the free-text script setting.
**Verdict** uses REAL, STUB or MIXED for trainer scripts; the two neural modules are marked "not REAL" (a learner that
fails the 3.3 checks on reading) and "n/a" (not a trainer).

| Script | Commit | Git blob | SHA-256 | Launched by | Verdict |
|---|---|---|---|---|---|
| `app/pt_trainer.py` | `858a0eb` | `f0c5fc4aa9d8` | `0ade973af54458f716d0451eb5ad754890e0a09687c52a9998ffe512b45e45a6` | hub (BTC, cwd `app/`); CLI | STUB |
| `app/{BNB,DOGE,ETH,XRP}/pt_trainer.py` | `858a0eb` | `f0c5fc4aa9d8` | `0ade973a…45e45a6` (same) | hub (alts: the hub copies `<BTC folder>/<base name of the setting>` over this path, then runs it); CLI | STUB |
| `app/BTC/pt_trainer.py` | `858a0eb` | `6c11e9729bd1` | `0de9a60f94a25261c2a49bdeaeedaf98f2abc9b725dd2043c1c5a5eaad0a19e9` | config (main neural folder set to `app/BTC`; BTC's script is never re-copied); CLI | STUB |
| `app/pt_trainer_standalone.py` | `858a0eb` | `c29fdc5b4770` | `c02603da9de5f4f6749fdca8ca6b67c820727b4b99fb5cb544e874d412fbdab8` | config (script setting); CLI | STUB |
| `app/{BNB,BTC,DOGE,ETH,XRP}/pt_trainer_standalone.py` | `858a0eb` | `34b0d9501ecb` | `5f70dae541626cd7eea8529ed0916b5ef733489d11ad541132981f178edd1a2b` | config (main neural folder set to that folder, with the standalone script; for alts the hub copies the root copy over it first); CLI | STUB |
| `app/pt_neural_network.py` | `858a0eb` | `387e058d9526` | `919f45c6a7b74f1ec6acb8d8ebcc735b111beb94825ebb4cba8da869e163f481` | config and CLI (both only run a dependency check); imported by `pt_neural_processor.py` and a test | not REAL (static; section 6) |
| `app/pt_neural_processor.py` | `858a0eb` | `902b26e369ba` | `0093cb01a1863ff7d076e00aa6a2b3bbf3bc2f686dd3e9d6e4ea4094ef660974` | config and CLI (a demo); imported by demos and a test | n/a (not a trainer) |
| **`app/pt_trainer.py`** | **`7a84250`** | **`c85fc4c82edc`** | **`d0a04f3cc099a29ab0c1f67bbaf0a1eed97f92d1e2c78667da2d04c6982bd3ee`** | **hub (every coin)**; CLI | **STUB (gating)** |
| `app/{BNB,DOGE,ETH,XRP}/pt_trainer.py` | `7a84250` | `f0c5fc4aa9d8` | `0ade973a…45e45a6` (stale copies) | config (e.g. `ETH/pt_trainer.py`); CLI | STUB |
| `app/BTC/pt_trainer.py` | `7a84250` | `6c11e9729bd1` | `0de9a60f…19e9` | config; CLI | STUB |
| `app/pt_trainer_standalone.py` | `7a84250` | `66330cb099d7` | `5724211bb93721b15b50e922e2893db3b8ac21fba22b0914a1685272070c6954` | config; CLI | STUB |
| `app/{BNB,BTC,DOGE,ETH,XRP}/pt_trainer_standalone.py` | `7a84250` | `34b0d9501ecb` | `5f70dae5…1a2b` | config; CLI | STUB |
| `app/pt_neural_network.py` | `7a84250` | `4e2dc76c48df` | `f3ec7f2e186ea853211fe3ffacf593852442f780cbdd23694c8d1d9c3d6d70cf` | config and CLI (dependency check only); imported by `pt_neural_processor.py` and a test | not REAL (static; section 6) |
| `app/pt_neural_processor.py` | `7a84250` | `1dbd8faaac2f` | `50171096d6bcef3b81deb8ae41ab18b20501af83c2ec7781dce6d73cca872acb` | config and CLI (a demo); imported by demos and a test | n/a (not a trainer) |

Static evidence for the other stubs: `app/BTC/pt_trainer.py` runs `time.sleep(2)` per epoch with
`accuracy = 85.0 + epoch * 0.5  # Mock increasing accuracy` and `"final_accuracy": 95.0`, and writes no model files
(`:62-74`); `app/pt_trainer_standalone.py` runs `time.sleep(1)  # Simulate training time` with
`accuracy = 85.0 + epoch * 2.5  # Mock increasing accuracy` and `"final_accuracy": 97.5`, and writes no model files
(`7a84250:…:55-67`). At `858a0eb` the per-coin standalone copies differ from the root copy only in the results path (one
more `..`) and a whitespace line; at `7a84250` the root copy also adds the `pt_paths` import and results path. The per-coin
`app/<SYM>/pt_trainer*.py` copies stay in place (addendum section 6); removing them is a later chore.

## 5. The pre-FDS-108a side, `858a0eb` (addendum 5.2)

- **Launch:** the root was `app/` when `main_neural_dir` was blank or not an existing folder (a relative value resolved
  against `app/`; `858a0eb:app/pt_hub.py:1984-1990`). BTC ran `<root>/pt_trainer.py`, i.e. `app/pt_trainer.py`. For an
  alt, the hub copied `<BTC folder>/<base name of the setting>` to `app/<SYM>/<base name>` (`:5575-5592`,
  `shutil.copy2`), i.e. over `app/<SYM>/pt_trainer.py` with default settings, and ran it there: working folder
  `coin_cwd = self.coin_folders.get(coin, self.project_dir)` (`:5572`), passed as `cwd=coin_cwd` (`:5665`).
- **Known facts, confirmed:** `app/{BNB,DOGE,ETH,XRP}/pt_trainer.py` were byte-identical to `app/pt_trainer.py` (blob
  `f0c5fc4`); `app/BTC/pt_trainer.py` differs (blob `6c11e97`) and was never launched by the hub with default settings
  (`build_coin_folders` skips a `BTC` subfolder, `858a0eb:app/pt_hub.py:754`; that rule dates from upstream `b4522b0`);
  every `app/<SYM>/pt_trainer_standalone.py` (blob `34b0d95`) differs from `app/pt_trainer_standalone.py` (blob
  `c29fdc5`).
- **Commit `dae9b3e`:** its message does **not** say "the legacy neural trainer is a mock"; it says "legacy_neural is
  labelled UNTRAINED in the hub". The commit adds "mock" in four places: the docstring of
  `PowerTraderHub._refresh_signals_note` (`app/pt_hub.py:6478`), comments in `app/pt_settings_manager.py` and
  `app/pt_trader.py`, and `docs/technical/ARCHITECTURE.md`, which names only `pt_trainer_standalone.py` and the per-coin
  copies as mocks and leaves out `app/pt_trainer.py`. Tested as a claim: confirmed by sections 3.1 to 3.4.
- **Running `858a0eb` is not needed:** `app/pt_trainer.py` differs only in paths and imports (the `current_dir`
  `sys.path` entry, the `pt_paths` import and results path, `_leave_program_dir`), and `app/pt_data_provider.py` is the same
  blob (`9912421`) at both commits. The exchange layer that supplies the ticker price changed (`pt_multi_exchange.py`,
  `pt_exchanges.py`, `pt_exchange_abstraction.py`), but runs X1-X5 show the price has no effect on the model files, and
  the verdict-deciding code (sleep, formula, literal, random, string iteration) is identical (INFERRED for `858a0eb`'s
  behaviour).

## 6. Is there a real trainer anywhere else? (the MIXED question)

A search of the tree for fitting code (`.fit(`, `.backward(`, `optim.`, `train_test_split`, `sklearn`, `torch`, `keras`,
`xgboost`, `perfect_threshold`, `class …Trainer`) finds only the files in section 4, the hub, the thinker, migration
pattern lists, `pt_model_evaluation.py` (metric formulas only), `app/install_optional_deps.py` (an optional installer that
offers scikit-learn, not torch or ta) and tests.

**`app/pt_neural_network.py`: a genuine learner, not a usable trainer** (static reading; it was not executed, because
`torch`, `scikit-learn` and `ta` are not installed in the project environment and are in neither `requirements.txt` nor
`app/requirements.txt`):

- It learns: PyTorch `TradingLSTM` / `TradingTransformer`; `ModelTrainer.train_model` runs `loss.backward()` and
  `optimizer.step()` (`:462-464`).
- Not deterministic: no seed anywhere, and `DataLoader(train_dataset, batch_size=batch_size, shuffle=True)` (`:432`).
- Not honest on held-out data: the scaler is fitted on all the data (`self.scaler.fit_transform(data)`, `:360`) before
  `train_test_split` (`:368`); validation loss, the learning-rate schedule and the best checkpoint are chosen on the test
  set (`:474-481`); and the reported metrics, including `directional_accuracy` (`:551`), come from that same set.
- No `train_end`, and nothing the thinker reads: it saves a `.pth` regression model to `models_dir()/best_model.pth`
  (`:303`), i.e. inside BTC's default trainer folder. `pt_neural_processor.py` loads `<sym>_neural_model.pth` from the
  same place, a file nothing writes.
- Nothing launches it: `pt_neural_processor.py` imports `TradingLSTM` and `FeatureEngineering` from it, and only a broken
  test (`app/test_phase1_phase2_integration.py`, wrong constructor signature) calls `ModelTrainer`.

**`app/pt_neural_processor.py`** is inference and heuristics only. Not a trainer.

**The full-size pattern-matching trainer exists only in history** (port sources for route B):

| Commit | Path | Blob | Lines | Note |
|---|---|---|---|---|
| `b4522b0` (2025-12-28, Stephen Hughes, "Add files via upload") | `pt_trainer.py` | `e02bd5b` | 1,607 | Upstream upload; KuCoin `Market` |
| `ba62130` (2026-01-08, Stephen Hughes) | `pt_trainer.py` | `0369182` | 1,625 | Last upstream-authored version |
| `3407fe7` | `app/pt_trainer.py` | `5be6534` | 2,239 | Last full version on `main`'s ancestry; calls a `DataProvider.get_historical_data` that did not exist yet |

`10e190e` (2026-02-25) replaced it with a 121-line sleep-loop stub (blob `1db5296`; its message says "Created standalone
pt_trainer.py that performs actual neural network training"). Whether `ba62130` is upstream's current tip needs a network
check, so Phase 1 must confirm the upstream commit hash before recording it.

## 7. Findings outside the trainer (recorded, not fixed in Phase 0)

1. **The data provider returns a single synthetic candle, as a string**, for any `get_kline_data` /
   `get_historical_data` call (`app/pt_data_provider.py:101`, `:130`, `:226`), whatever window is asked for. Even a real
   trainer would have been fed one candle. Callers:
   - live (hub-launched): `app/pt_trainer.py` (`:132`, `:159`) and `app/pt_thinker.py` (`:604`, `:720`, `:1030`,
     `:1410`). By static trace the thinker's candle loop needs two candles and retries for ever for a trained coin,
     calling the exchange price API about every 0.2 s plus the request time;
   - not launched: the per-coin `app/<SYM>/pt_trainer*.py` copies, `app/pt_trainer_standalone.py`,
     `app/pt_neural_processor.py` (demos only), `app/pt_hub_chart_components.py` (imported nowhere),
     `app/demo_phase3_features.py`, `app/phase3_live_demo.py`.

   Phase 1 takes its data from `app/market_data/candles.py`, as the spec says.
2. **The trader reads signal files nothing writes.** Since `4fc3834` (2026-03-06) the thinker writes
   `signals_dca_spread.txt` / `signals_dca_single.txt` (`app/pt_thinker.py:1382`, `:1396`), while the trader reads
   `long_dca_signal.txt` / `short_dca_signal.txt` (`app/pt_trader.py:880`, `:902`). In `legacy_neural` mode no legacy entry
   or neural DCA can fire, whatever the trainer does, unless a stale `long_dca_signal.txt` from before `4fc3834` is present
   (the migration carries such files forward, `app/pt_migrate.py:125-126`; the trader has no age check). Relevant to
   FDS-MDL acceptance 7.
3. **Correction to FDS-MDL section 2:** the upstream trainer does not write predicted high/low bands. Each memory entry
   carries the high and low % move that followed its pattern (`b4522b0:pt_trainer.py:1552`), and the **thinker** weights
   these into bands (`app/pt_thinker.py:852-894`, `:944-951`).
4. `pt_multi_exchange` reads environment and keyring credentials for every exchange in the config, enabled or not, when it
   loads it (`app/pt_multi_exchange.py:56`, `:159`); creates the config folder on import (`:504`); and, when `initialize`
   is given a region, which `DataProvider` always does (`app/pt_data_provider.py:48-51`), replaces an unreadable
   `trading_config.json` with defaults (`app/pt_multi_exchange.py:314-316`), contrary to `load_config`'s docstring
   (`:109`).
5. `trainer_status.json` is read by the hub but never written: `_write_training_status` is never called (and would
   write BTC's status into `<root>/BTC`).
6. Auto-retrain: `cancel_all_auto_retrains` calls `self.master.after_cancel` on a `Tk` root whose `master` is None, so
   cancelling silently fails (INFERRED); a coin removed in Settings that still has a timer would retrain in BTC's folder
   and delete BTC's model files (INFERRED).
7. `docs/technical/ARCHITECTURE.md` "Real Machine Learning Implementation" (`:36`) and "Enhanced Trainer System"
   (`:56-57`) are contradicted by the code: no `*/neural_trainer.py` exists, and no hub-launched or per-coin trainer imports
   torch. Its FDS-121 section (`:129-141`) names the wrong signal files and leaves out `app/pt_trainer.py`.
8. `pt_paths.models_dir()`'s docstring ("one `<model_id>/` folder per model") is stale; the addendum schedules the fix
   for Phase 1.
9. The program folder is written at runtime: the hub (started without `-B`) writes `app/__pycache__` for its own imports,
   and its trainer children may add more (INFERRED), contrary to `pt_paths.program_dir()`'s "read-only at runtime".
10. The thinker rewrites `neural_perfect_threshold_<tf>.txt` on every step (`app/pt_thinker.py:934-938`), so hashes of
    legacy coin folders are not stable while the thinker runs (relevant to Phase 2 manifests).

## 8. Issue #136: trainer tests that exercise the real launch

#136's acceptance: (a) removing the `_refresh_trainer_path()` call from `PowerTraderHub.__init__` makes a test fail;
(b) no test under `app/` contains a hard-coded user path.

**What changed (tests only):**

- `app/tests/helpers_trainer.py` (new):
  - `build_real_hub` builds the hub with its **real** `__init__`. It hides the window, switches off the optional heavy
    features through their module flags (their tabs become placeholder labels; the exchange system and API server are not
    started) and records message boxes. Nothing replicates `__init__`. It skips only when Tk itself cannot start; an
    error after Tk has started fails the test.
  - `guard_trainer_children` puts a fail-closed `sitecustomize.py` on `PYTHONPATH`, so every process the hub starts blocks
    Python-level TCP connects, UDP sends and name resolution; refuses to run without an absolute `POWERTRADER_HOME` and
    the "fail" keyring backend; records its command line, working folder and environment; and (when asked) answers the
    Binance ticker from a recorded candle file.
- `app/tests/test_trainer_launch.py` (rewritten). Every test builds the real hub and starts **real processes** through
  `start_trainer_for_selected_coin`; no `Popen` is patched, and the CWD is a temp folder, so a script resolved against the
  CWD would not be found.
  - `test_every_coin_runs_the_program_folder_trainer_in_its_user_data_folder`: `proc_trainer_path` was set by `__init__`;
    the BTC and ETH children saw exactly `[python, -u, -W, ignore, <program dir>/pt_trainer.py, COIN]`, their user-data coin
    folder, the per-test `POWERTRADER_HOME`, the hub folder, the fail keyring and no credential variables; a stale
    memories file was cleared; no script was copied in.
  - `test_a_launch_runs_to_completion_with_the_ticker_served_from_a_fixture`: the real trainer runs to exit 0 with the
    network blocked, the Binance ticker answered with the last close of the recorded ETH candles; the model files, stamp
    and summary land in the user data folder; no file in the program folder, and no trainer output anywhere in the
    install folder, changes. This replaces the old test that only parsed `pt_trainer.py` with `ast`; the results path is
    now checked by a real run, for ETH (the code path does not depend on the coin).
  - `test_a_trainer_script_saved_in_settings_is_used_by_the_next_launch`: the real Settings window saves a new script
    path and coin list; the next launches (BTC, and SOL, added in the same save) run the saved script without a restart.
- `app/tests/test_no_hard_coded_user_paths.py` (new): scans `app/conftest.py`, `app/test_*.py` and everything under
  `app/tests/` for Windows-profile paths (with or without a drive), `/home/<name>`, `/Users/<name>` and `/root`, with a
  self-check that the patterns catch them and pass placeholders and environment lookups.
- **Deleted:** `app/test_hub_trainer.py` and `app/test_subprocess_trainer.py`. Neither imported the hub, neither asserted
  anything, and between them they held the only hard-coded user paths
  (`C:\Users\Administrator\PowerTrader\PowerTrader_AI\app...`, `test_hub_trainer.py:76`,
  `test_subprocess_trainer.py:37`, `:39`).

**How each criterion is met:**

- **(a)** Demonstrated with the guard on, in a scratch clone with the one line `self._refresh_trainer_path()` removed from
  `__init__` (the Settings-save call left in place): all 3 tests in the new `test_trainer_launch.py` **fail** with
  `AttributeError: '_tkinter.tkapp' object has no attribute 'proc_trainer_path'`, and pass again with the line restored.
  The previous `test_trainer_launch.py` (with `make_hub`) **passes 4 of 4** against the same broken hub, which is the gap
  #136 describes. (a) is enforced wherever Tk can start: `run_suite.py` and local pytest on Windows. CI does not collect
  `app/tests` at all (`.github/workflows/ci-cd.yml` runs `pytest app/test_*.py`).
- **(b)** `test_no_test_under_app_contains_a_hard_coded_user_path` passes after the deletion, and failed before it on
  exactly those three lines.

**Effect on the suite compare:** `app/test_hub_trainer.py` and `app/test_subprocess_trainer.py` show as GONE (1 "passed"
each, with no assertions); `app/tests/test_trainer_launch.py` goes from 4 to 3 tests; `test_no_hard_coded_user_paths.py`
is NEW (2 tests).

**Tk start-up on Windows:** creating a Tk root right after a hub that started a child process occasionally fails with
"Can't find a usable init.tcl" (the same flake behind the known `test_graceful_degradation` flip). `build_real_hub`
retries only that start-up failure, which leaves nothing behind because creating the root is the first line of
`__init__`. Measured over 64 builds: every build succeeded; 3 needed a second attempt.

## 9. Inputs for Phase 1

- **Route** (owner's decision, section "The MIXED question"): A, wire in `pt_neural_network.py`; or B, port the upstream
  trainer from the history sources in section 6. Recommendation: B.
- For route B: write the **upstream** file format (section 2.1), with data from `app/market_data/candles.py`. Code facts to
  plan for:
  - the timeframe names differ (trainer and thinker `1hour`, `2hour`, …, `1week`; candles `1h`, `2h`, …), so the port
    needs a name map; `candles.py` has no `1w` (`app/market_data/timeframes.py:3-16`), so `1w` must be added or the weekly
    model dropped explicitly;
  - `get_candles(..., closed_only=True)` filters on `close_time <= now` (`app/market_data/candles.py:255-257`), not on
    `end`, so pass `now=train_end` as well as `end=train_end` to keep bars that close after `train_end` out.
- The determinism and data-dependence tests (FDS-MDL acceptance 3) belong with the new trainer, which will have a seed
  and a training window to pass; this audit's harness and helpers are the starting point.
- `allow_mock_trainer` goes in `pt_config.json` (addendum section 6); the hub does not consult any such setting today.
- The thinker rewrites the threshold files while it runs (section 7 item 10): Phase 2 manifests should hash the copies
  in `strategy_models_dir()`, not the live coin folders.

## 10. Method and reproduction

- **Read-only fact-finding:** six parallel agents (hub launch, thinker, static checks, data path, tests and guard,
  history) and a completeness critic, using git and grep reads only; then an adversarial review of this document, its
  evidence and the tests by six more read-only reviewers, whose findings were applied. Process deviations are listed in
  the run log.
- **Executed checks:** `app/tests/audit_trainer_evidence.py`, 12 training runs through the real hub, under the isolation
  guard (`app/tests/conftest.py`), with the test venv recorded in `docs/dev/RUN-LOG-model-1.md`, from a scratch clone
  that nothing else wrote to (PowerShell):

  ```
  $env:PT_AUDIT_OUT = '<evidence.json>'
  $env:POWERTRADER_HOME = '<scratch>\dev-home'
  $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.fail.Keyring'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  python -m pytest app/tests/audit_trainer_evidence.py -p no:cacheprovider --timeout=900 -q
  ```

- In the 10 runs D1-D4, X1-X5 and T1, the child ran the real `pt_trainer.py`, `DataProvider`, `MultiExchangeManager` and
  `BinanceExchange` (stdout shows `Data provider initialized: Multi-exchange (binance)`), and only the Binance price
  response came from the fixture: 8 ticker requests per run. C1 and C2 replace `pt_data_provider` with the fixture candle
  provider (8 candle calls, no exchange code). Every other connection attempt would have been blocked and recorded; none
  were. Fixtures: `app/tests/fixtures/BTCUSDT_1h.csv` (git blob content SHA-256
  `c1a297b8fa111bf6f75f032dec6f7b10ea7bc544be86db3eec3f7bcd9672c7dc`) and `ETHUSDT_1h.csv`
  (`ab15e5592c18caae1948bce47a3254e509c20d8111cf15f85ceb30e0dd8c4dd9`); the evidence file records their working-tree
  hashes and git blob IDs.
- **Evidence file:** `docs/dev/trainer-audit-evidence.json`. Per run: exit code, duration, what the child itself reported
  (command line, folder, environment, seed, fixture, price), every request served, every model file's SHA-256, the five
  1-hour files' contents, the summary without its timestamp, the relevant stdout lines, files added, changed or removed
  under the home folder, and whether the program folder changed. It also records which tests passed, and the SHA-256 and
  git blob ID of the harness, `helpers_trainer.py` and `pt_trainer.py` that produced it. The harness itself replaces
  machine-specific path prefixes with `<pytest-tmp>`, `<repo>`, `<venv>`, `<tmp>` and `<home>`, and refuses to write the
  file if a user-profile path is left.

## 11. Port verdict (after FDS-MDL Phase 1)

| | |
|---|---|
| Script | `app/pt_pattern_trainer.py` at `03f489e` (blob `f34e6ab`), the hub's default trainer since FDS-MDL Phase 1 |
| Date | 2026-10-06 |
| Evidence | `docs/dev/trainer-port-evidence.json`, written by `app/tests/audit_port_evidence.py` (method in 11.7) |

The four Phase 0 checks (FDS-MDL 3.3) re-run against the ported trainer, through the hub's real launch path, with the
Phase 0 isolation. Line numbers in this section are as of `03f489e`. Issues #149 (weights never saved) and #151 (matching
sees only memories flushed to disk) are the upstream behaviours the port keeps on purpose; they shape what follows.

### 11.1 Result: static, determinism and data dependence pass; reported metrics fail

| Check (FDS-MDL 3.3) | Result | Evidence |
|---|---|---|
| Static | **PASS** | No fixed delay in any training loop (the only `time.sleep` is a 0.2 s retry, reached only when a model-file write raises `PermissionError`); no `random` draw; no accuracy value of any kind (11.2) |
| Determinism | **PASS** | The same fixture twice with seed 7: 0 of 35 model files differ. Also 0 with a different `PYTHONHASHSEED`, and 0 as launched with no seed set (11.3, executed) |
| Data dependence | **PASS** | Different bars give different model files, and the differences trace to the bars: every memory entry differs, and memories are recomputed exactly from each timeframe's own bars. Beyond the copied bar values, which steps match (and so which memories are kept) changes with the data, and on three years of real bars the written 1-hour and 2-hour thresholds do too. The same bars under another coin name give byte-identical files (11.4, executed) |
| Reported metrics | **FAIL** | The trainer computes and reports no metric, held out or otherwise (11.5) |

**Verdict: not REAL, by the spec's definition.** FDS-MDL 3.4 calls a trainer REAL only when all four checks pass, and
the reported-metrics check fails: nothing is held out and nothing measures how well the model predicts.

It is not a STUB in the spec's sense either ("fails in a way that shows outputs are not learned from data"): the matching
and, on long windows, the threshold respond to the data (11.4). But what the model adjusts is limited, and the
data-dependence pass should be read with that in mind:

- **On the 9-week fixtures, nothing is fitted.** Every weight is 1.0 (#149); every threshold equals 1.0 plus 0.01 per
  step of its last pass, because no step ever matched more than 20 memories; and the memories are per-bar % values
  taken from the bars, the pattern Phase 0 section 3.5 called "a copy of the data". The one data-dependent output beyond
  the copied values is which steps of the 1-hour timeframe's last pass matched a memory instead of storing a new one:
  162 against 160 on the same number of BTC and ETH bars.
- **On three years of real Binance bars**, matching acts in passes 1-2 of every timeframe, on that timeframe's own bars,
  and the written threshold falls below its step counter in the 1-hour and 2-hour timeframes, differently for BTC and
  ETH. That threshold is the only adjusted parameter the evidence shows. In the 4-hour to 1-week timeframes the written
  threshold is still a step counter.

**Re-run after Phase 2.** Phase 2 adds `validation_metrics`: a separate fit on the first 80% of the window, scored on the
last 20%, while the published model is refit on the whole window (owner decision, 2026-10-06). The metrics will then be
held out for the fit that produced them, not for the published model, which has seen that slice wherever it trains on
it: pass 2 of the `1day` and `1week` timeframes walks from the middle of the window to its last bar (pass 1 stops at the
first quarter; the intraday timeframes and every pass 0 use only the older half). The check should be re-run then, and
judged on those terms. The harness reads only the training summary, so it needs extending to read the Phase 2 manifest.
Done: see 11.8 (sections 11.1 to 11.7 stay as the verdict on the trainer at `03f489e`).

### 11.2 Static

`app/pt_pattern_trainer.py` (blob `f34e6ab`), read with Python's `ast` by the harness (`test_static_checks`):

- **Sleep:** one call, `time.sleep(0.2)` (`:398`) in `_write_text`, inside its `except PermissionError` handler: the
  retry when Windows briefly locks a file that is being replaced. The harness asserts it sits in that handler. Training
  writes go through `_write_text`, so a step waits only if a write fails. There are no epochs.
- **`random`:** one use, `random.seed(seed)` (`:707`) in `train` (deviation 9). Nothing draws from the RNG, so weights
  and memories cannot be random. Upstream `ba62130` has no `random` at all.
- **Accuracy:** no variable, key or assignment mentions accuracy. The only string that does is the module docstring
  saying the port removed upstream's "Bounce Accuracy" statistic (printed only, never used, not held out).
- **Market data is parsed:** bars come from `app/market_data/candles.py` (`BarLoader._load`); `pt_data_provider` is not
  imported (the Phase 1 test `test_the_trainer_reads_candles_only_through_the_candle_layer` checks this too). The
  harness records every import: `argparse`, `datetime`, `json`, `market_data.candles`, `market_data.timeframes`, `os`,
  `pandas`, `pt_paths`, `random`, `sys`, `time`, `traceback`.

The detector looks for `time.sleep` and `random.<name>` written that way. It is a reading of this one file, which has no
aliased or `from` imports of either module and no other RNG.

### 11.3 Determinism (executed)

| Runs | Setup | Model files that differ (of 35) |
|---|---|---|
| D1, D2 | BTC fixture, `POWERTRADER_TRAIN_SEED=7`, `PYTHONHASHSEED=0` (the spec's check) | **0** |
| D1, D3 | Same, but D3 with `PYTHONHASHSEED=12345` | **0** |
| D1, D4 | D4 as launched: no seed set, so the trainer's default seed 0 | **0** |

D1's and D2's training summaries (per-pass statistics, thresholds and memory counts) are identical too. The seed is
recorded but changes nothing, because the trainer draws no random numbers. **PASS.**

Determinism is per window: as launched without `POWERTRADER_TRAIN_START`/`_END`, the hub's trainer trains on the three
years up to the last full hour, so two launches an hour apart train on different windows. Each summary records the window
it used.

### 11.4 Data dependence (executed)

All runs with seed 7 and `PYTHONHASHSEED=0`, so any difference has to come from the data.

| Run | Coin | Data |
|---|---|---|
| X1 | BTC | `BTCUSDT_1h.csv`, all 1,513 bars (2026-06-10 to 2026-08-12), resampled to 2h-1w |
| X2 | BTC | `ETHUSDT_1h.csv`, all 1,512 bars, served as BTC's candles |
| X3 | BTC | `BTCUSDT_1h.csv`, bars 0-755 |
| X4 | BTC | `BTCUSDT_1h.csv`, bars 756-1512 (no overlap with X3) |
| X5 | ETH | `ETHUSDT_1h.csv`, all bars |
| L1 | BTC | Binance BTCUSDT bars for all 7 timeframes, 2023-01-01 to 2026-01-01 (the fetched cache, 11.7) |
| L2 | ETH | Binance ETHUSDT bars, same window |

Model files that differ (of 35):

| | X2 | X3 | X4 | X5 |
|---|---|---|---|---|
| X1 | 10 | 35 | 35 | 10 |
| X2 | | 35 | 35 | **0** |
| X3 | | | 11 | 35 |
| X4 | | | | 35 |

L1 and L2 differ in 30 of 35 files.

In every run the harness checks, from the cache files alone, that each timeframe trained on its own bars: the bar count
the summary reports per timeframe equals the count in the cache for the window (X1: 1,513 1h, 756 2h, 378 4h, 189 8h, 126
12h, 63 1d, 8 1w bars), and the 1-hour older half the trainer used (757 bars for X1) equals the harness's own computation.

**What depends on the data, on the fixtures:**

- **The memories' contents.** Between X1 and X2, and between X3 and X4, every entry differs from the entry at the same
  position, in all 7 timeframes, over all the positions both files have (the shorter file's count: for example 575
  compared in `memories_1hour.txt`, where X1 holds 575 entries and X2 577). Most entries of the 2h-1w files come from
  pass 0, which is the same walk over 1-hour bars in every timeframe.
- **They trace to the bars.** For each run the harness recomputes two memories from the bars in the cache:
  - the 1-hour pass-0 memory that every timeframe stores first: the body % of bar 9 of the older half, then the close,
    high and low moves % from bar 9's close to bar 10 (X1:
    `0.11978147471269857 0.08339455455568094{}0.19737526440883071{}-0.299242161156432`);
  - for each timeframe, the first memory pass 2 stores, from that timeframe's own bars, at the position the summary's
    counts give. This applies wherever passes 0 and 1 stayed under the 200-step flush, so nothing could have matched
    first: all 7 timeframes in X1, X2, X4 and X5, and 6 in X3, whose weekly pass 2 is skipped (3 weekly bars).

  Every recomputed memory equals the stored entry. The harness asserts this.
- **Matching.** In the 1-hour timeframe's last pass, the only pass on these fixtures long enough to reach upstream's
  200-step flush (#151), X1 and X2 use the same number of bars (757) and take 380 steps each. The summary counts 162 and
  161 matched steps; a pass's last step never learns, and X2's matched, so 162 and 160 steps matched instead of storing a
  memory. X1 therefore stores 217 new memories in that pass and X2 219: 575 against 577 in total. The harness asserts
  that these counts differ on equal bar counts, which a trainer that only copied the bars would fail.
- **The coin's name does not matter, the bars do:** X2 (ETH bars as BTC) and X5 (ETH bars as ETH) are byte-identical.

**What does not depend on the data, on the fixtures:**

- **Thresholds.** In every fixture run, every timeframe's final threshold equals 1.0 plus 0.01 per step of its last pass
  (the harness replays the rule and records the comparison): no step ever matched more than 20 memories, so the threshold
  only rose. All 7 threshold files are identical between X1 and X2.
- **Weights.** Every weight in every run is 1.0 (#149), so a weight file differs only when its memory count does. The 10
  files that differ between X1 and X2 are the 7 memories files and the three 1-hour weight files (575 against 577
  entries).
- **X3 against X4** (11 files): the 7 memories files, plus the four 1-week files, which differ because X3's window holds 3
  complete Monday weeks (its passes 1-2 are skipped) and X4's holds 4. That difference is the calendar, not the prices.
  No step matches in X3 or X4: no pass reaches the 200-step flush.

**What depends on the data, on three years of real bars (L1, L2):**

| Timeframe | BTC threshold | ETH threshold | Step counter | Matched steps per pass, BTC / ETH |
|---|---|---|---|---|
| 1hour | **28.55** | **28.07** | 66.77 | 2993, 3279, 6495 / 2993, 3279, 6489 |
| 2hour | **27.04** | **24.84** | 33.90 | 2993, 1552, 3235 / 2993, 1538, 3237 |
| 4hour | 17.46 | 17.46 | 17.46 | 2993, 713, 1600 / 2993, 727, 1594 |
| 8hour | 9.24 | 9.24 | 9.24 | 2993, 302, 766 / 2993, 299, 773 |
| 12hour | 6.50 | 6.50 | 6.50 | 2993, 172, 489 / 2993, 166, 490 |
| 1day | 6.49 | 6.49 | 6.49 | 2993, 150, 492 / 2993, 152, 479 |
| 1week | 1.79 | 1.79 | 1.79 | 2993, 7, 11 / 2993, 8, 12 |

- **Matching** acts in passes 1-2 of every timeframe, which run on that timeframe's own bars (the harness asserts this
  for both coins), and the counts differ between BTC and ETH there, except in 1-hour pass 1: it replays pass 0's bars
  against the memories pass 0 stored from them, so every step matches for both coins. Pass 0 is the same 1-hour walk in
  every timeframe, so its numbers repeat down the column; that BTC and ETH both end it on 2,993 matched steps is a
  coincidence (their walks differ along the way).
- **The written threshold** falls below its step counter only in the 1-hour and 2-hour timeframes, where some steps of
  the last pass matched more than 20 memories, and it ends differently for each coin. The pass-0 threshold adapts in
  every timeframe (the run's progress lines show it below the counter part-way through), but every pass starts again at
  1.0, and in the 4-hour to 1-week timeframes no step of the last pass matched more than 20 memories.
- Weights are still all 1.0.

**PASS**, as the spec words the check: the outputs differ in a way that traces to the data. What responds to the data is
which steps match; the only adjusted parameter the evidence shows is the written 1-hour and 2-hour threshold on
three-year windows.

### 11.5 Reported metrics

- No metric is computed. Every key of the training summary
  (`<data>/training_results/<coin>_training_results.json`), as the harness lists them: `coin`, `trainer`, `upstream`
  (`repo`, `commit`, `blob`), `train_start`, `train_end`, `seed`, `offline`, `sources` (`train_start`, `train_end`,
  `seed`, `offline`), `timeframes.<tf>` (`final_threshold`, `memories`, and per pass `pass`, `data_tf`,
  `bars_in_window`, `bars_used`, `steps`, `matched_steps`, `new_memories`, `unlearned_steps`, `skipped`), and
  `candles.<tf>` (`bars`, `first_open`, `last_open`, `window_first_open`, `window_last_open`, `missing_at_start`,
  `missing_at_end`, `gaps`). The summary also holds the wall-clock fields `started_at`, `finished_at` and
  `runtime_seconds`, which the harness drops before comparing. None is a metric.
- Nothing is printed as one: the harness searches every output line of every run (not only the lines it keeps) for
  accuracy and other metric words, and finds none.
- What the summary reports is not constant across inputs: the four distinct inputs give four distinct sets of final
  thresholds and memory counts (X2 and X5 are the same bars). The differences come from window length (X1 and X2 against
  X3 and X4), the weekly bar count (X3 against X4) and, in one place, the prices (the 1-hour memory count, X1 against X2).
  None of it is a measure of predictive skill.
- **FAIL.** See 11.1 for the re-run after Phase 2.

### 11.6 The thinker can read the output (supplementary)

Run T1 (BTC fixture, seed 7): the thinker's own parse expressions (`thinker_reads` in
`app/tests/test_pattern_trainer.py`, copied from `pt_thinker.py`'s `step_coin`) accept all 7 timeframes: every threshold
parses, every memory entry has its 2 values and 2 `{}` fields, and each weight list has one entry per memory. The
harness first checks that `pt_thinker.py` still contains the expressions the copy uses. The thinker itself was not run
(its candle loop never ends with the current data provider: #141).

### 11.7 Method and reproduction

- **Executed checks:** `app/tests/audit_port_evidence.py`, 12 training runs through the real hub: a hub built by its real
  `__init__` calls `start_trainer_for_selected_coin`, which launches the default `pt_pattern_trainer.py` (the harness
  asserts the command line `-u -W ignore <program folder>\pt_pattern_trainer.py <COIN>`) in the coin's folder. The
  guarded child (`helpers_trainer.CHILD_SITE`) blocks the network and records its command line, folder and environment;
  no connection was attempted in any run, and the program folder did not change.
- **Isolation, as in Phase 0:** a scratch clone that nothing else wrote to, `POWERTRADER_HOME=<scratch>\dev-home` (each
  test also gets its own per-test home from the guard), the fail keyring backend, `PYTHONDONTWRITEBYTECODE=1`, and
  `PYTHONHASHSEED` pinned in every child. Command (PowerShell):

  ```
  $env:PT_AUDIT_OUT = '<evidence.json>'
  $env:PT_AUDIT_LONG_CACHE = '<scratch>\model1-home\cache\candles'
  $env:POWERTRADER_HOME = '<scratch>\dev-home'
  $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.fail.Keyring'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  python -m pytest app/tests/audit_port_evidence.py -p no:cacheprovider --timeout=3600 -q
  ```

- **Fixture data (D, X, T runs):** the recorded Binance fixtures used in Phase 0 (`app/tests/fixtures/BTCUSDT_1h.csv`,
  blob `32dcea1`; `ETHUSDT_1h.csv`, blob `fd4a95f`), resampled to 2h-1w by `helpers_candles.resample` (complete bars
  only; weekly bars open on Monday, as Binance's do), written to the candle cache under the per-test home, and read
  offline over the fixture's window. With 9 weeks of data the weekly timeframe has 8 bars, so its pass 1 is skipped and
  recorded ("fewer than 10 bars").
- **Three-year data (L runs):** the candle cache that `docs/dev/run_backtest_model1.py fetch` wrote in Phase 1 (public
  Binance klines, all 7 timeframes, 2023-01-01 to 2026-01-01), copied into the per-test home and read offline. Without
  `PT_AUDIT_LONG_CACHE` these two runs are skipped, and the evidence says so. The evidence records each cache file's
  SHA-256 (BTCUSDT_1h.csv `736539ae…`, ETHUSDT_1h.csv `69b99216…`); the prefixes `fetch` printed are recorded in
  `docs/dev/RUN-LOG-model-1.md` (Phase 1 follow-up).
- **Evidence file:** per run, the exit code, duration, what the child reported (command line, folder, environment),
  every model file's SHA-256, each memories file's entry count and first entry, the harness's expectations from the
  cache (bars per timeframe, the 1-hour older half, the recomputed memories), the thresholds and their step-counter
  comparison, matched steps that learned, whether every weight is 1.0, the status and stamp, the training summary
  without its wall-clock fields, the relevant output lines and every output line that looks like a metric, files added,
  changed or removed under the home folder, and whether the program folder changed. Also which harness tests passed
  (the reported-metrics test passes by confirming the FAIL), and the SHA-256 and git blob ID of the harness, both helpers
  modules, the trainer and the fixtures. The SHA-256 values are of the scratch clone's checkout, which has CRLF line
  endings on Windows; the blob IDs identify the committed content. Path prefixes are replaced as in Phase 0.

### 11.8 Re-run after FDS-MDL Phase 2

| | |
|---|---|
| Script | `app/pt_pattern_trainer.py` as committed with FDS-MDL Phase 2 (blob `3792be9`), which now scores with `app/pattern_model.py` and publishes through `app/model_store.py` (both new) |
| Date | 2026-10-06 |
| Evidence | `docs/dev/trainer-port-evidence-phase2.json`, written by `app/tests/audit_port_evidence.py` (blob `91ef43d`) |

The 12 runs of 11.3 to 11.6, through the hub's real launch path, with the isolation and the command of 11.7, from a
scratch clone holding the Phase 2 code: all 6 harness tests passed (pytest reported 326 s; the run log records it).
Every run published its model with a manifest; the harness verified each manifest the way a loader does and read its
validation window and metrics. Each manifest also records the SHA-256 of the three code files the metrics come from
(`code_sha256`: the trainer, `pattern_model.py` and `model_store.py`).

**Verdict: REAL by FDS-MDL 3.4 (all four checks pass), with no skill above the up-rate base rate: held-out 1-hour
direction hit rate against the share of closes that rose, on the same pairs, BTC 50.3% vs 50.4% (n = 5,257 pairs) and
ETH 51.3% vs 51.0% (n = 5,257 pairs).** Each base rate lies inside its hit rate's 95% interval (BTC 48.9–51.6%, ETH
50.0–52.7%), and any skill these data could hide is small: a 95% bound on the paired difference (hit rate minus up
share, on the same pairs) allows at most 1.2 points for BTC and 2.0 for ETH. Those pairs are the last 20% of three years of real Binance bars (2025-05-26 19:00 to 2026-01-01 UTC), scored
by a separate fit on the first 80%.

| Check (FDS-MDL 3.3) | Result | Evidence |
|---|---|---|
| Static | **PASS** | A reading of the trainer file, as in 11.2: still no fixed delay in a loop (the only `time.sleep` is the 0.2 s retry in `_write_text`'s `PermissionError` handler), no `random` draw (only `random.seed`), no accuracy value. New imports: `hashlib`, `shutil`, `tempfile`, `subprocess` (local `git rev-parse` and `git status` only), `pattern_model`, `model_store`. Of those two, only `app/model_store.py` sleeps: 0.2 s between retries when a `PermissionError` holds up the rename of a published model's folder, after training |
| Determinism | **PASS** | 0 of 35 files differ between D1 and D2 (seed 7), D3 (another `PYTHONHASHSEED`) and D4 (no seed). D1 to D3 publish one model_id; D4 publishes another, because the id also covers the seed (0 by default), which never changes the files |
| Data dependence | **PASS** | As in 11.4: different bars give different files (10 to 35 of 35 per pair of runs), and the same bars under two coin names (X2, X5) give identical files |
| Reported metrics | **PASS** (FAIL in 11.5) | Every run publishes validation metrics from a separate fit on the first 80% of its window, scored frozen on the last 20%. For the seven X and L runs the harness asserts that the fit's last bar closes by the cut and the first scored bar opens at or after it; in all 12 runs' records both fall exactly on the cut. The four distinct inputs give four distinct metric sets; the same bars (X2, X5) give identical ones. The training summary still holds no metric. Each run prints one line that matches a metric word, the trainer's `validation: fitting ...` line (the evidence lists those of the X and L runs) |

**What REAL means here, and what it does not.** It is the spec's term: the trainer learns from data, in the limited
sense of 11.1 and 11.4 (every weight stays 1.0, #149; the only adjusted parameter the evidence shows is the written
1-hour and 2-hour threshold on three-year windows), and it reports metrics measured on data its fit did not see. It says
nothing in the model's favour:

- **No detectable skill in any timeframe.** The held-out direction metrics of the three-year runs (L1, L2). "n" counts
  the scored pairs where both the predicted and the actual close move are non-zero; the interval is a 95% Wilson
  interval for the hit rate; the up share is the base rate of the verdict line; the best constant is "always up", or
  "always down" where fewer closes rose; "chance at the model's mix" is the hit rate of guesses that carry no
  information but have the model's own up/down proportions (predicted up × up share + predicted down × down share).

  | Coin | Timeframe | Scored pairs | n | Hit rate (hits) | 95% interval | Up share | Best constant | Predicted up | Chance at the model's mix | Best constant inside the interval |
  |---|---|---|---|---|---|---|---|---|---|---|
  | BTC | 1hour | 5,260 | 5,257 | 50.3% (2,644) | 48.9–51.6% | 50.4% | 50.4% | 77.2% | 50.2% | yes |
  | BTC | 2hour | 2,629 | 2,627 | 52.0% (1,365) | 50.0–53.9% | 50.8% | 50.8% | 73.8% | 50.4% | yes |
  | BTC | 4hour | 1,314 | 1,313 | 51.5% (676) | 48.8–54.2% | 50.3% | 50.3% | 64.1% | 50.1% | yes |
  | BTC | 8hour | 656 | 653 | 51.6% (337) | 47.8–55.4% | 51.6% | 51.6% | 60.8% | 50.3% | yes |
  | BTC | 12hour | 437 | 431 | 43.9% (189) | 39.2–48.6% | 50.3% | 50.3% | 55.5% | 50.0% | **no** (the hit rate is below it) |
  | BTC | 1day | 218 | 218 | 45.0% (98) | 38.5–51.6% | 49.5% | 50.5% | 49.5% | 50.0% | yes |
  | BTC | 1week | 29 | 17 | 58.8% (10) | 36.0–78.4% | 35.3% | 64.7% | 52.9% | 49.1% | yes |
  | ETH | 1hour | 5,260 | 5,257 | 51.3% (2,697) | 50.0–52.7% | 51.0% | 51.0% | 62.1% | 50.2% | yes |
  | ETH | 2hour | 2,629 | 2,624 | 51.3% (1,346) | 49.4–53.2% | 51.6% | 51.6% | 78.1% | 50.9% | yes |
  | ETH | 4hour | 1,314 | 1,308 | 50.5% (661) | 47.8–53.2% | 51.6% | 51.6% | 65.0% | 50.5% | yes |
  | ETH | 8hour | 656 | 655 | 51.5% (337) | 47.6–55.3% | 53.6% | 53.6% | 53.0% | 50.2% | yes |
  | ETH | 12hour | 437 | 427 | 51.1% (218) | 46.3–55.8% | 51.8% | 51.8% | 53.9% | 50.1% | yes |
  | ETH | 1day | 218 | 215 | 53.0% (114) | 46.4–59.6% | 50.2% | 50.2% | 52.6% | 50.0% | yes |
  | ETH | 1week | 29 | 9 | 66.7% (6) | 35.4–87.9% | 33.3% | 66.7% | 66.7% | 44.4% | yes |

  - In 13 of the 14 rows the best constant guess lies inside the hit rate's interval, and so does chance at the model's
    mix. In the other row the hit rate is the lower one: BTC 12-hour predictions do worse than a constant guess, 43.9%
    against 50.3% (n = 431), and worse than uninformed guesses at the model's mix (50.0%; z = −2.6, p ≈ 0.01). Taken
    alone that is significant, but not after correcting for the 14 rows looked at (Bonferroni p ≈ 0.14, a conservative
    figure because the rows are correlated), and all 14 come from one held-out period, one market regime. So it is not
    read as a finding either way. Against chance at the mix, every other row is within 1.63 standard errors.
  - The model's calls are not a constant. Depending on the timeframe and the coin, it predicts a rise for 49.5% to
    78.1% of the n pairs (BTC 77.2% and ETH 62.1% at 1 hour), and in 13 of the 14 rows its hit rate lands where guesses
    at that mix would.
  - In the weekly rows most closes fell, so the up share there (35.3% and 33.3%) lies below the hit rate's interval;
    "always down" lies inside it. Those rows rest on 17 and 9 pairs and say nothing either way.
- **Held out for the sibling fit, not for the published model** (owner decision, 2026-10-06; see 11.1). The published
  model is refit on the whole window, and pass 2 of its `1day` and `1week` timeframes walks through the held-out slice.
  The sibling fit's own 1-hour timeframe, like every intraday timeframe and every pass 0, learns only from the older half
  of its 80% span (L1: the oldest 10,522 of 21,042 hourly bars, to about mid-March 2024), some 14 months before the first
  scored bar. The 1-hour figures above test those memories.
- **The fixture runs** (X, D, T) score 151 to 302 held-out 1-hour pairs each. They show that the metrics change with the
  data and repeat for the same data; they are not used for the skill finding.
- **Every validation metric is new in Phase 2** (the trainer computed none before, 11.5). The predicted-up share
  (`predicted_up_share_of_considered`) is among them so that a hit rate equal to the up share can be told apart from a
  model that always predicts a rise.

**For FDS-MDL Phase 4.** This finding is an input to the pre-declared verdict rule in `BACKTEST-REPORT-model-1.md`,
which will be written and committed before any backtest runs.
