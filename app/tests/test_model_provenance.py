"""FDS-MDL Phase 2: model artifact provenance (addendum section 4.1).

* ``pt_paths.strategy_models_dir()``: a sibling of the trainer root, created lazily; a
  model_id equal to a coin symbol never resolves into a coin folder; an overlapping
  trainer root is refused.
* Every training run publishes its model with a manifest: relative paths only, every
  file's SHA-256, the window, the data, the seed, the code and validation metrics from a
  separate fit on the first 80% of the span the bars cover, scored on the last 20%
  (never on data after train_end; checked against hand-computed values). The model_id
  covers all of it.
* Loaders refuse a missing or mismatched manifest (acceptance 4) and log an ERROR; a
  model folder copied to another POWERTRADER_HOME still loads (acceptance 14).
* The legacy neural runner uses a coin's model only when a published manifest matches
  it, and prints the model_id and train_end it uses.
* ``pattern_model`` reproduces the thinker's per-timeframe predictions exactly (checked
  against the real ``pt_thinker.step_coin``).

All candles are synthetic; the network is blocked here and in every child."""

import json
import logging
import hashlib
import math
import os
import posixpath
import shutil
import sys
import time
import types
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_candles as hc  # noqa: E402
import helpers_thinker as hth  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import model_store  # noqa: E402
import pattern_model  # noqa: E402
import pt_paths  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from market_data import candles  # noqa: E402
from market_data.timeframes import candle_timeframe_seconds  # noqa: E402
from test_pattern_trainer import FakeKlines  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a Monday
HOURS = 1680
END = START + timedelta(hours=HOURS)
PAIR = "BTCUSDT"


@pytest.fixture(autouse=True)
def guarded(monkeypatch, tmp_path, isolated_user_dirs):
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


def seed(hourly=None, n=HOURS, seed_=1, pair=PAIR, frames=None):
    if frames is None:
        hourly = hc.synthetic_hourly(n, START, seed=seed_) if hourly is None else hourly
        frames = hc.all_timeframes(hourly)
    hc.seed_cache(candles.cache_dir_default(), pair, frames)
    return frames


def run_main(folder, coin="BTC", start=START, end=END, extra=("--offline",)):
    """The trainer's main() in ``folder`` (offline, explicit window); its exit code."""
    os.makedirs(folder, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(folder)
    try:
        return ppt.main(
            [coin, "--train-start", start.isoformat(), "--train-end", end.isoformat(),
             *extra]
        )  # fmt: skip
    finally:
        os.chdir(cwd)


def train_main(folder, coin="BTC", start=START, end=END, extra=("--offline",)):
    """run_main, which must succeed; returns the training summary."""
    assert run_main(folder, coin, start, end, extra) == 0
    path = pt_paths.data_file(
        "training_results", f"{coin.lower()}_training_results.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def manifest_of(summary):
    return model_store.read_manifest(model_store.model_dir(summary["model_id"]))


def strings_in(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from strings_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v)
    elif isinstance(value, str):
        yield value


@pytest.fixture
def published(tmp_path):
    """A trained, published BTC model: (summary, model folder, coin folder)."""
    seed()
    folder = str(tmp_path / "coin")
    summary = train_main(folder)
    return summary, model_store.model_dir(summary["model_id"]), folder


def write_gui_settings(data):
    pt_paths.write_private_text(pt_paths.gui_settings_file(), json.dumps(data))


# --- the store's place -------------------------------------------------------------------


def test_the_store_is_a_sibling_of_the_trainer_root_and_created_lazily():
    store = pt_paths.strategy_models_dir(create=False)
    assert store == os.path.join(pt_paths.hub_dir(), "strategy_models")
    assert os.path.dirname(store) == os.path.dirname(pt_paths.models_dir())
    assert not pt_paths.paths_overlap(store, pt_paths.models_dir())
    pt_paths.ensure_dirs()
    assert not os.path.exists(store)  # only publishing creates it
    assert pt_paths.trainer_root() == pt_paths.models_dir(create=False)


def test_a_model_id_equal_to_a_coin_symbol_stays_in_the_store():
    for coin in ("ETH", "BTC", "eth"):
        path = model_store.model_dir(coin)
        assert os.path.dirname(path) == os.path.realpath(
            pt_paths.strategy_models_dir(create=False)
        )
        root = pt_paths.neural_dir()
        for folder in (root, os.path.join(root, coin)):
            assert not pt_paths.paths_overlap(path, folder)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        ".",
        "..",
        "a/b",
        "a\\b",
        "../x",
        "C:x",
        " x",
        "x" * 129,
        None,
        7,
        "-x",
        ".x",
        "x\n",
        "BTC-20240311T0000Z-000000000000\n",
    ],
)
def test_a_model_id_that_is_not_a_plain_name_is_refused(bad, caplog):
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError):
            model_store.model_dir(bad)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


@pytest.mark.parametrize(
    "root",
    [
        lambda: pt_paths.hub_dir(),  # contains the store
        lambda: pt_paths.strategy_models_dir(create=False),  # is the store
        lambda: os.path.join(pt_paths.strategy_models_dir(create=False), "x"),  # inside
    ],
    ids=["root-contains-store", "root-is-store", "root-inside-store"],
)
def test_an_overlapping_trainer_root_is_refused(published, root, caplog):
    summary, _, folder = published
    write_gui_settings({"main_neural_dir": root()})
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError, match="overlaps"):
            model_store.load(summary["model_id"])
        with pytest.raises(model_store.ModelStoreError, match="overlaps"):
            model_store.find_published(folder)
    assert any("overlaps" in r.getMessage() for r in caplog.records)


def test_the_provenance_step_refuses_an_overlapping_trainer_root(tmp_path, caplog):
    seed(pair="ETHUSDT")
    write_gui_settings({"main_neural_dir": pt_paths.hub_dir()})  # contains the store
    folder = tmp_path / "eth"  # outside the store: only the root check can refuse
    with caplog.at_level(logging.ERROR, logger="model_store"):
        assert run_main(str(folder), coin="ETH") == 1
    assert any("overlaps" in r.getMessage() for r in caplog.records)
    with open(folder / "trainer_status.json", encoding="utf-8") as f:
        assert json.load(f)["state"] == "ERROR"
    assert not (folder / "trainer_last_training_time.txt").exists()
    assert not os.path.exists(pt_paths.strategy_models_dir(create=False))


@pytest.mark.parametrize("platform, overlap", [("darwin", True), ("linux", False)])
def test_overlap_ignores_letter_case_on_macos_only(monkeypatch, platform, overlap):
    """POSIX path functions (no case folding of their own, unlike Windows'), so the
    macOS rule is what decides, wherever the test runs."""
    with monkeypatch.context() as m:  # scoped: the guard's own patches stay in place
        m.setattr(pt_paths, "os", types.SimpleNamespace(path=posixpath))
        m.setattr(pt_paths.sys, "platform", platform)
        found = pt_paths.paths_overlap(
            "/Volumes/data/powertraderai/hub_data",
            "/Volumes/data/PowerTraderAI/hub_data/strategy_models",
        )
    assert found is overlap


def test_a_trainer_root_beside_the_store_is_accepted(published, tmp_path):
    summary, _, _ = published
    write_gui_settings({"main_neural_dir": str(tmp_path / "elsewhere")})
    assert model_store.load(summary["model_id"]).model_id == summary["model_id"]


# --- what a training run publishes ---------------------------------------------------------


def test_every_training_run_publishes_its_model_with_a_manifest(published):
    summary, model_folder, coin_folder = published
    model_id = summary["model_id"]
    assert model_id.startswith("BTC-20240311T0000Z-")
    manifest = model_store.verify_folder(model_folder)
    for key in model_store.REQUIRED_FIELDS:
        assert key in manifest, key
    assert manifest["symbol"] == "BTCUSDT" and manifest["coin"] == "BTC"
    assert manifest["timeframes"] == list(ppt.TF_CHOICES)
    assert (manifest["train_start"], manifest["train_end"]) == (
        "2024-01-01T00:00:00Z",
        "2024-03-11T00:00:00Z",
    )
    assert manifest["upstream_commit"] == "ba62130"
    assert manifest["trainer_path"] == "app/pt_pattern_trainer.py"
    assert manifest["seed"] == 0
    assert sorted(manifest["candle_file_sha256"]) == sorted(hc.TRAINER_TFS)
    assert sorted(manifest["code_sha256"]) == sorted(ppt.CODE_FILES)
    for name in ppt.CODE_FILES:  # LF line endings: what git stores, on any checkout
        with open(os.path.join(APP_DIR, name), "rb") as f:
            text = f.read().replace(b"\r\n", b"\n")
        assert manifest["code_sha256"][name] == hashlib.sha256(text).hexdigest(), name
    assert (
        manifest["trainer_sha256"] == manifest["code_sha256"]["pt_pattern_trainer.py"]
    )
    assert manifest["validation"]["status"] == "ok"
    # the published files are the coin folder's, byte for byte
    assert manifest["files"] == model_store.folder_file_hashes(coin_folder)
    # no absolute path anywhere: none starts one, and none holds the home or data folder
    assert model_store._absolute_paths(manifest) == []
    folders = [os.path.expanduser("~"), pt_paths.data_dir()]
    folders = [f for f in folders if os.path.dirname(f) != f]  # not a bare root ("/")
    for text in strings_in(manifest):
        for folder in folders:
            assert os.path.normcase(folder) not in os.path.normcase(text), text


@pytest.mark.parametrize("own", [True, False], ids=["own-checkout", "other-repo"])
def test_the_git_checks_run_locally_and_report_uncommitted_code(
    monkeypatch, tmp_path, own
):
    top = pt_paths.install_dir() if own else str(tmp_path)  # another repository's top
    seen = []

    def fake_run(argv, **kwargs):
        seen.append(argv)
        out = {
            ("rev-parse", "--show-toplevel"): top + "\n",
            ("rev-parse", "HEAD"): "a" * 40 + "\n",
            ("status", "--porcelain"): " M pattern_model.py\n",
        }[tuple(argv[4:6])]
        return types.SimpleNamespace(returncode=0, stdout=out)

    with monkeypatch.context() as m:  # scoped: the guard's own patches stay in place
        m.setattr(ppt.subprocess, "run", fake_run)
        commit, dirty = ppt._git_commit(), ppt._git_dirty()
    # inside some other repository nothing is recorded
    assert (commit, dirty) == (("a" * 40, True) if own else (None, None))
    # no optional index lock (never blocks the user's own git), in the program folder
    for argv in seen:
        assert argv[:4] == ["git", "--no-optional-locks", "-C", ppt.current_dir]
    if own:
        assert seen[-1][4:] == ["status", "--porcelain", "--", *ppt.CODE_FILES]
        monkeypatch.setattr(ppt, "_own_checkout", lambda: True)
        for output, expected in (("", False), (None, None)):
            monkeypatch.setattr(ppt, "_git", lambda *a, o=output: o)
            assert ppt._git_dirty() is expected


def test_code_hashes_are_the_same_for_crlf_and_lf_checkouts(tmp_path):
    crlf, lf = tmp_path / "crlf.py", tmp_path / "lf.py"
    crlf.write_bytes(b"x = 1\r\ny = 2\r\n")
    lf.write_bytes(b"x = 1\ny = 2\n")
    assert ppt._text_sha256(str(crlf)) == ppt._text_sha256(str(lf))
    assert ppt._text_sha256(str(lf)) == hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()


def test_the_candle_hashes_identify_the_bars_used():
    frames = seed()
    loader = ppt.BarLoader(PAIR, START, END, offline=True)
    loader.bars("1hour")
    assert loader.reports["1h"]["sha256"] == ppt.candle_sha256(frames["1h"])
    # more bars in the shared cache, same window: same hash
    seed(n=HOURS + 200)
    again = ppt.BarLoader(PAIR, START, END, offline=True)
    again.bars("1hour")
    assert again.reports["1h"]["sha256"] == loader.reports["1h"]["sha256"]


def test_validation_scores_a_separate_fit_on_the_last_20_percent(published):
    summary, model_folder, _ = published
    manifest = model_store.read_manifest(model_folder)
    v = manifest["validation"]
    cut = START + (END - START) * 0.8  # 2024-02-26T00:00Z, on the hour
    assert (v["fit_start"], v["fit_end"]) == (
        "2024-01-01T00:00:00Z",
        cut.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    assert (v["holdout_start"], v["holdout_end"]) == (
        v["fit_end"],
        "2024-03-11T00:00:00Z",
    )
    assert v["holdout_candles"]["1h"]["bars"] == int(
        (END - cut).total_seconds() // 3600
    )
    # the fit's bars all close by the cut; the scored bars all open at or after it
    for tf in hc.TRAINER_TFS:
        step = timedelta(seconds=candle_timeframe_seconds(tf))
        fitted = v["fit_candles"][tf]
        assert pd.Timestamp(fitted["last_open"]) + step <= cut, tf
        held = v["holdout_candles"].get(tf)
        if held is not None:
            assert pd.Timestamp(held["first_open"]) >= cut, tf
    metrics = manifest["validation_metrics"]
    assert sorted(metrics) == sorted(ppt.TF_CHOICES)
    one_hour = metrics["1hour"]
    assert one_hour["scored_pairs"] == v["holdout_candles"]["1h"]["bars"] - 1
    assert set(pattern_model.METRIC_DEFINITIONS) <= set(one_hour)
    assert manifest["metric_definitions"] == pattern_model.METRIC_DEFINITIONS


def test_validation_never_reads_data_after_train_end(tmp_path):
    frames = seed(n=HOURS + 200)
    a = train_main(str(tmp_path / "a"))
    poisoned = {}
    for tf, frame in frames.items():
        frame = frame.copy()
        late = frame["open_time"] + pd.Timedelta(seconds=candle_timeframe_seconds(tf))
        late = late > pd.Timestamp(END)
        frame.loc[late, ["open", "high", "low", "close"]] *= 1000.0
        poisoned[tf] = frame
    ma = model_store.read_manifest(model_store.model_dir(a["model_id"]))
    seed(frames=poisoned)
    shutil.rmtree(model_store.model_dir(a["model_id"]))  # make the rerun publish again
    b = train_main(str(tmp_path / "b"))
    mb = model_store.read_manifest(model_store.model_dir(b["model_id"]))
    assert b["model_id"] == a["model_id"]  # same files, same window
    assert mb["validation_metrics"] == ma["validation_metrics"]
    assert mb["candle_file_sha256"] == ma["candle_file_sha256"]
    assert mb["validation"]["holdout_candles"] == ma["validation"]["holdout_candles"]


def test_the_validation_fit_never_sees_the_held_out_bars(tmp_path):
    frames = seed()
    cut = ppt.validation_cut(START, END)
    clean_window, clean = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    poisoned = {}
    for tf, frame in frames.items():
        frame = frame.copy()
        held = frame["open_time"] >= pd.Timestamp(cut)
        # every held-out bar reversed (open and close swapped): not a rescaling, which
        # the %-based scores would hardly see
        frame.loc[held, ["open", "close"]] = frame.loc[held, ["close", "open"]].values
        poisoned[tf] = frame
    seed(frames=poisoned)
    dirty_window, dirty = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    # validate()'s own fit: the same bars, the same model files
    assert dirty_window["fit_candles"] == clean_window["fit_candles"]
    assert dirty_window["fit_files_sha256"] == clean_window["fit_files_sha256"]
    # the reversed bars are what it scored
    assert dirty_window["holdout_candles"] != clean_window["holdout_candles"]
    assert dirty["1hour"] != clean["1hour"]


def test_the_metrics_are_what_their_definitions_say():
    """score_timeframe on six hand-made hourly bars, with the expected values worked
    out by hand from METRIC_DEFINITIONS. The model has two memories, both predicting
    +1% close, +2% high and -1% low: body 0% (matches only a 0% body) and body 2% (with
    threshold 100: bodies of about 0.67% to 6%). So a falling bar matches nothing."""
    model = pattern_model.TimeframeModel(
        "100.0",
        "0.0 1.0{}2.0{}-1.0~2.0 1.0{}2.0{}-1.0",
        "1.0 1.0",
        "1.0 1.0",
        "1.0 1.0",
    )
    t0 = pd.Timestamp("2024-01-01", tz="UTC")
    bars = pd.DataFrame(
        {
            "open_time": [t0 + pd.Timedelta(hours=h) for h in (0, 1, 2, 3, 4, 6)],
            "open": [100.0, 100.0, 102.0, 100.5, 102.0, 103.0],
            "high": [101.0, 103.0, 102.5, 102.6, 103.5, 104.0],
            "low": [99.0, 99.5, 100.0, 100.2, 101.5, 102.0],
            "close": [100.0, 102.0, 100.5, 102.0, 103.0, 103.5],
        }
    )
    m = pattern_model.score_timeframe(model, bars, 3600)
    # pairs (0,1) (1,2) (2,3) (3,4); (4,5) spans a missing hour and is skipped. Bar 2
    # fell (-1.47%), matches neither memory: pair (2,3) is scored but not active.
    assert (m["scored_pairs"], m["active_pairs"]) == (4, 3)
    assert m["active_share"] == 0.75
    # actual moves from bar j's close, for the active pairs (0,1), (1,2), (3,4)
    move = [2.0, (100.5 - 102.0) / 102.0 * 100, (103.0 - 102.0) / 102.0 * 100]
    high = [3.0, (102.5 - 102.0) / 102.0 * 100, (103.5 - 102.0) / 102.0 * 100]
    low = [-0.5, (100.0 - 102.0) / 102.0 * 100, (101.5 - 102.0) / 102.0 * 100]
    assert m["direction_considered"] == 3
    assert m["direction_hit_rate"] == pytest.approx(2 / 3)  # up, down, up: +1 each time
    assert m["up_share_of_considered"] == pytest.approx(2 / 3)
    assert m["predicted_up_share_of_considered"] == 1.0
    assert m["close_move_mae_pct"] == pytest.approx(sum(abs(1 - a) for a in move) / 3)
    assert m["high_move_mae_pct"] == pytest.approx(sum(abs(2 - a) for a in high) / 3)
    assert m["low_move_mae_pct"] == pytest.approx(sum(abs(-1 - a) for a in low) / 3)
    # bands [99, 102], [100.98, 104.04], [100.98, 104.04] against closes 102, 100.5,
    # 103: two of the three active pairs (not of the four scored)
    assert m["next_close_within_band_share"] == pytest.approx(2 / 3)
    assert set(m) == set(pattern_model.METRIC_DEFINITIONS)


def test_a_pair_listed_late_is_validated_on_the_bars_it_has(tmp_path, monkeypatch):
    """Online (the hub's way), a pair listed after train_start trains on what it has;
    its validation splits the span its bars cover, so the 80% fit has data."""
    listed = START + timedelta(weeks=4)
    hourly = hc.synthetic_hourly(HOURS - 4 * 168, listed, seed=3)
    fake = FakeKlines({"NEWUSDT": hc.all_timeframes(hourly)})
    monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: fake)
    monkeypatch.delenv(ppt.ENV_CANDLES_OFFLINE, raising=False)
    summary = train_main(str(tmp_path / "new"), coin="NEW", extra=())
    assert summary["offline"] is False
    v = manifest_of(summary)["validation"]
    cut = ppt.validation_cut(listed, END)
    assert v["status"] == "ok"
    assert (v["fit_start"], v["fit_end"]) == (ppt._iso(listed), ppt._iso(cut))
    assert v["holdout_end"] == ppt._iso(END)


def test_a_pair_whose_bars_stop_early_is_validated_on_the_bars_it_has(
    tmp_path, monkeypatch
):
    """Online, bars that stop three weeks before train_end (a suspended pair): the
    holdout is the last 20% of the bars there are, not of the window."""
    hourly = hc.synthetic_hourly(HOURS - 3 * 168, START, seed=3)
    last_close = START + timedelta(hours=HOURS - 3 * 168)
    fake = FakeKlines({"OLDUSDT": hc.all_timeframes(hourly)})
    monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: fake)
    monkeypatch.delenv(ppt.ENV_CANDLES_OFFLINE, raising=False)
    summary = train_main(str(tmp_path / "old"), coin="OLD", extra=())
    assert summary["candles"]["1h"]["missing_at_end"] == 3 * 168
    v = manifest_of(summary)["validation"]
    cut = ppt.validation_cut(START, last_close)
    assert v["status"] == "ok"
    assert (v["fit_end"], v["holdout_end"]) == (ppt._iso(cut), ppt._iso(last_close))
    one_hour = manifest_of(summary)["validation_metrics"]["1hour"]
    assert (
        one_hour["scored_pairs"] == int((last_close - cut).total_seconds() // 3600) - 1
    )


def test_validation_with_nothing_scored_is_marked_unavailable(monkeypatch):
    seed()

    def nothing(model, bars, step_seconds):
        return {"scored_pairs": 0}

    with monkeypatch.context() as m:
        m.setattr(pattern_model, "score_timeframe", nothing)
        window, _ = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    assert window["status"] == "unavailable"
    assert window["reason"] == "no held-out bar pair could be scored"
    window, _ = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    assert window["status"] == "ok" and "reason" not in window


def test_a_run_whose_validation_fit_cannot_train_is_published_without_metrics(
    tmp_path, monkeypatch
):
    seed()

    def no_fit(*args, **kwargs):
        raise ppt.TrainerError("too few bars before the cut")

    monkeypatch.setattr(ppt, "validate", no_fit)
    folder = tmp_path / "coin"
    summary = train_main(str(folder))
    manifest = manifest_of(summary)
    assert manifest["validation"]["status"] == "unavailable"
    assert manifest["validation"]["reason"] == "too few bars before the cut"
    assert all(
        m
        == {
            "scored_pairs": 0,
            "error": "no validation fit: too few bars before the cut",
        }
        for m in manifest["validation_metrics"].values()
    )
    assert (folder / "trainer_last_training_time.txt").exists()


def test_validation_folders_of_stopped_runs_are_cleared_and_never_read(tmp_path):
    seed()
    clean, _ = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    parent = os.path.join(pt_paths.cache_dir(), "pt-validation-BTC")
    assert os.listdir(parent) == []  # its own run folder removed (the parent stays)
    # another window's real model files, left untouched for two hours by terminated
    # runs: loose in the coin's folder (where a single shared folder would read them)
    # and in a run folder of their own...
    other = tmp_path / "other"
    train_main(str(other), end=END - timedelta(days=7))
    stale_run = os.path.join(parent, "stopped")
    os.makedirs(stale_run)
    stale = []
    for name in pattern_model.model_file_names():
        for target in (parent, stale_run):
            shutil.copyfile(other / name, os.path.join(target, name))
            stale.append(os.path.join(target, name))
    old = time.time() - 2 * 3600
    for path in stale + [stale_run]:
        os.utime(path, (old, old))
    # ...and a live run's folder, written to just now
    live = os.path.join(parent, "running")
    os.makedirs(live)
    with open(os.path.join(live, "memories_1hour.txt"), "w", encoding="utf-8") as f:
        f.write("a fit in progress")
    again, _ = ppt.validate("BTC", START, END, 0, True, log=lambda *a: None)
    assert (
        again["fit_files_sha256"] == clean["fit_files_sha256"]
    )  # stale files not read
    assert os.listdir(parent) == ["running"]  # only the live run's folder is left


def test_the_model_id_covers_the_seed_and_the_newest_match_is_reported(tmp_path):
    seed()
    a = train_main(str(tmp_path / "a"), extra=("--offline", "--seed", "0"))
    b = train_main(str(tmp_path / "b"), extra=("--offline", "--seed", "7"))
    # the seed changes nothing in the files, but the manifest records it: another id
    assert manifest_of(a)["files"] == manifest_of(b)["files"]
    assert a["model_id"] != b["model_id"]
    assert manifest_of(b)["seed"] == 7
    # the newest of the two matches, whichever way the ids sort
    for older, newer in ((a, b), (b, a)):
        _rewrite_manifest(
            model_store.model_dir(older["model_id"]), created_at="2000-01-01T00:00:00Z"
        )
        _rewrite_manifest(
            model_store.model_dir(newer["model_id"]), created_at="2100-01-01T00:00:00Z"
        )
        found = model_store.find_published(str(tmp_path / "a"), coin="BTC")
        assert found["model_id"] == newer["model_id"]


def test_find_published_reads_only_the_newest_models_of_the_coin(tmp_path, monkeypatch):
    """Its cost does not grow with the store: only the coin's models are read, newest
    train_end first, and the search stops at the first window with a match."""
    seed(n=HOURS + 96)
    old = train_main(str(tmp_path / "old"))
    new = train_main(str(tmp_path / "new"), end=END + timedelta(hours=48))
    seed(n=HOURS + 96, pair="ETHUSDT")  # ETH's model is newer than both BTC models
    eth = train_main(str(tmp_path / "eth"), coin="ETH", end=END + timedelta(hours=96))
    read = []
    peek = model_store._peek_manifest
    monkeypatch.setattr(
        model_store,
        "_peek_manifest",
        lambda f: read.append(os.path.basename(f)) or peek(f),
    )
    found = model_store.find_published(str(tmp_path / "new"), coin="BTC")
    assert found["model_id"] == new["model_id"]
    assert read == [new["model_id"]]  # stops at the newest window, which matches
    read.clear()
    found = model_store.find_published(str(tmp_path / "old"), coin="BTC")
    assert found["model_id"] == old["model_id"]
    assert read == [new["model_id"], old["model_id"]]  # goes on to older windows
    assert eth["model_id"] not in read


def test_validation_metrics_change_with_the_data(tmp_path):
    seed(seed_=1)
    a = train_main(str(tmp_path / "a"))
    seed(seed_=2)
    b = train_main(str(tmp_path / "b"))
    ma = model_store.read_manifest(model_store.model_dir(a["model_id"]))
    mb = model_store.read_manifest(model_store.model_dir(b["model_id"]))
    assert a["model_id"] != b["model_id"]
    assert ma["validation_metrics"] != mb["validation_metrics"]


def test_a_rerun_on_the_same_data_reuses_the_published_model(published, tmp_path):
    summary, model_folder, _ = published
    manifest_path = os.path.join(model_folder, model_store.MANIFEST)
    before = (model_store.read_manifest(model_folder), os.stat(manifest_path))
    time.sleep(1.1)  # a republished manifest would have another created_at and mtime
    again = train_main(str(tmp_path / "again"))
    assert again["model_id"] == summary["model_id"]
    assert sorted(os.listdir(pt_paths.strategy_models_dir())) == [summary["model_id"]]
    # left as it was, not replaced
    assert model_store.read_manifest(model_folder) == before[0]
    assert os.stat(manifest_path).st_mtime_ns == before[1].st_mtime_ns


def test_a_failed_publish_ends_the_run_with_an_error_and_no_stamp(tmp_path):
    seed()
    store = pt_paths.strategy_models_dir(create=False)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    with open(store, "w", encoding="utf-8") as f:
        f.write("not a folder")
    folder = tmp_path / "coin"
    folder.mkdir()
    cwd = os.getcwd()
    os.chdir(folder)
    try:
        code = ppt.main(["BTC", "--offline", "--train-start", START.isoformat(),
                         "--train-end", END.isoformat()])  # fmt: skip
    finally:
        os.chdir(cwd)
    assert code == 1
    with open(folder / "trainer_status.json", encoding="utf-8") as f:
        assert json.load(f)["state"] == "ERROR"
    assert not (folder / "trainer_last_training_time.txt").exists()


# --- loaders refuse (acceptance 4) --------------------------------------------------------


def test_a_published_model_loads(published):
    summary, _, _ = published
    loaded = model_store.load(summary["model_id"])
    assert loaded.train_end == "2024-03-11T00:00:00Z"
    assert sorted(loaded.model.timeframes) == sorted(ppt.TF_CHOICES)


def _rewrite_manifest(folder, **changes):
    path = os.path.join(folder, "manifest.json")
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest.update(changes)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


@pytest.mark.parametrize(
    "damage, message",
    [
        (lambda d: os.remove(os.path.join(d, "manifest.json")), "no manifest.json"),
        (
            lambda d: open(os.path.join(d, "memories_1hour.txt"), "a").write(
                "~1 2{}3{}4"
            ),
            "does not match its manifest",
        ),
        (
            lambda d: os.remove(os.path.join(d, "memory_weights_1day.txt")),
            "files do not match",
        ),
        (
            lambda d: open(os.path.join(d, "memories_extra.txt"), "w").write("x"),
            "files do not match",
        ),
        (lambda d: _rewrite_manifest(d, model_id="someone-else"), "does not match"),
        (lambda d: _rewrite_manifest(d, trainer_path="C:/abs/trainer.py"), "absolute"),
        (lambda d: _rewrite_manifest(d, notes="/srv/models/x"), "absolute"),
        (lambda d: _rewrite_manifest(d, manifest_version=99), "manifest version"),
        (
            lambda d: (
                os.remove(os.path.join(d, "memories_1hour.txt")),
                os.mkdir(os.path.join(d, "memories_1hour.txt")),
            ),
            "unreadable model files",
        ),
        (
            lambda d: open(os.path.join(d, "manifest.json"), "w").write("{not json"),
            "unreadable manifest",
        ),
    ],
    ids=[
        "no-manifest",
        "changed-file",
        "missing-file",
        "extra-file",
        "other-model-id",
        "absolute-trainer-path",
        "absolute-path-anywhere",
        "version",
        "unreadable-file",
        "unreadable",
    ],
)
def test_a_missing_or_mismatched_manifest_is_refused(
    published, damage, message, caplog
):
    summary, model_folder, _ = published
    damage(model_folder)
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError, match=message):
            model_store.load(summary["model_id"])
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_an_unknown_model_id_is_refused(caplog):
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError, match="not found"):
            model_store.load("BTC-20240311T0000Z-000000000000")


def _link_folder(link, target):
    """A directory junction (Windows) or symlink at ``link`` to ``target``; False when
    the system refuses to make one."""
    try:
        if os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, AttributeError, ImportError):
        return False
    return True


def test_a_model_folder_linked_from_outside_the_store_is_refused(
    published, tmp_path, caplog
):
    """A valid model folder elsewhere, linked into the store under its own id, is not
    loaded: model ids resolve inside the store only (realpath)."""
    _, model_folder, _ = published
    outside = tmp_path / "outside" / "linked-model"
    shutil.copytree(model_folder, outside)
    _rewrite_manifest(outside, model_id="linked-model")
    link = os.path.join(pt_paths.strategy_models_dir(), "linked-model")
    if not _link_folder(link, outside):
        pytest.skip("this system refuses to create a folder link")
    try:
        assert model_store.verify_folder(str(outside))["model_id"] == "linked-model"
        with caplog.at_level(logging.ERROR, logger="model_store"):
            with pytest.raises(model_store.ModelStoreError, match="outside the model"):
                model_store.load("linked-model")
        assert any("outside the model store" in r.getMessage() for r in caplog.records)
    finally:
        (
            os.rmdir(link) if os.name == "nt" else os.unlink(link)
        )  # the link, not its target


def test_a_model_folder_copied_to_another_home_still_loads(
    published, tmp_path, monkeypatch
):
    summary, model_folder, _ = published
    other = tmp_path / "other_home"
    monkeypatch.setenv("POWERTRADER_HOME", str(other))
    target = os.path.join(pt_paths.strategy_models_dir(), summary["model_id"])
    shutil.copytree(model_folder, target)
    loaded = model_store.load(summary["model_id"])
    assert os.path.normcase(loaded.folder) == os.path.normcase(os.path.realpath(target))


def test_a_model_published_meanwhile_by_another_run_is_reused(
    published, tmp_path, monkeypatch
):
    summary, model_folder, coin_folder = published
    manifest = model_store.read_manifest(model_folder)
    other_run = tmp_path / "other_run"
    shutil.copytree(model_folder, other_run)
    shutil.rmtree(model_folder)  # absent when publish looks, present when it installs
    install = model_store._install

    def racing(staging, final):
        shutil.copytree(other_run, final)
        install(staging, final)

    monkeypatch.setattr(model_store, "_install", racing)
    assert model_store.publish(coin_folder, manifest, trainer_root=None) == model_folder
    assert model_store.verify_folder(model_folder)["files"] == manifest["files"]
    store = pt_paths.strategy_models_dir()
    assert sorted(os.listdir(store)) == [summary["model_id"]]  # no staging left


def test_publishing_retries_a_folder_rename_a_scanner_holds_up(published, monkeypatch):
    summary, model_folder, coin_folder = published
    manifest = model_store.read_manifest(model_folder)
    shutil.rmtree(model_folder)
    calls = []
    replace = model_store._replace

    def held_twice(staging, final):
        calls.append(final)
        if len(calls) <= 2:
            raise PermissionError(13, "in use by another process")
        replace(staging, final)

    monkeypatch.setattr(model_store, "_replace", held_twice)
    monkeypatch.setattr(model_store.time, "sleep", lambda seconds: None)
    assert model_store.publish(coin_folder, manifest, trainer_root=None) == model_folder
    assert len(calls) == 3
    assert model_store.verify_folder(model_folder)["files"] == manifest["files"]


def test_staging_never_lengthens_a_path_and_a_failed_copy_is_refused(
    published, monkeypatch, caplog
):
    """Windows refuses paths of 260 characters or more: the staging folder's name is
    no longer than the model's own, and a copy that fails anyway is a logged refusal
    that leaves nothing behind."""
    summary, model_folder, coin_folder = published
    manifest = model_store.read_manifest(model_folder)
    shutil.rmtree(model_folder)
    made = []
    mkdtemp = model_store.tempfile.mkdtemp

    def recording(*args, **kwargs):
        made.append(mkdtemp(*args, **kwargs))
        return made[-1]

    with monkeypatch.context() as m:
        m.setattr(model_store.tempfile, "mkdtemp", recording)
        model_store.publish(coin_folder, manifest, trainer_root=None)
    assert len(os.path.basename(made[0])) <= len(summary["model_id"])
    shutil.rmtree(model_folder)

    def path_too_long(src, dst):
        raise FileNotFoundError(2, "No such file or directory", dst)

    with monkeypatch.context() as m:
        m.setattr(model_store.shutil, "copyfile", path_too_long)
        with caplog.at_level(logging.ERROR, logger="model_store"):
            with pytest.raises(model_store.ModelStoreError, match="could not copy"):
                model_store.publish(coin_folder, manifest, trainer_root=None)
    assert any("could not copy" in r.getMessage() for r in caplog.records)
    assert os.listdir(pt_paths.strategy_models_dir()) == []


def test_publishing_other_files_under_an_existing_id_is_refused(published, tmp_path):
    summary, model_folder, coin_folder = published
    manifest = model_store.read_manifest(model_folder)
    with open(
        os.path.join(coin_folder, "memories_1hour.txt"), "a", encoding="utf-8"
    ) as f:
        f.write("~1 2{}3{}4")
    manifest["files"] = model_store.folder_file_hashes(coin_folder)
    with pytest.raises(model_store.ModelStoreError, match="already published"):
        model_store.publish(coin_folder, manifest, trainer_root=None)


# --- the legacy neural runner ------------------------------------------------------------


def thinker_decisions(times, price=None):
    return [
        {"time": int(t.timestamp()), "price": price or 100.0, "sweeps": 1}
        for t in times
    ]


def test_find_published_matches_a_coin_folder_byte_for_byte(published, caplog):
    summary, _, coin_folder = published
    assert model_store.find_published(coin_folder)["model_id"] == summary["model_id"]
    with open(
        os.path.join(coin_folder, "memories_2hour.txt"), "a", encoding="utf-8"
    ) as f:
        f.write(" ")
    with caplog.at_level(logging.ERROR, logger="model_store"):
        assert model_store.find_published(coin_folder) is None
    assert any("no published manifest" in r.getMessage() for r in caplog.records)


def test_find_published_refuses_another_coins_model(published, tmp_path, caplog):
    summary, model_folder, coin_folder = published
    eth = tmp_path / "ETH"
    eth.mkdir()
    for name in pattern_model.model_file_names():
        shutil.copyfile(os.path.join(coin_folder, name), eth / name)
    found = model_store.find_published(str(eth), coin="BTC")
    assert found["model_id"] == summary["model_id"]
    with caplog.at_level(logging.ERROR, logger="model_store"):
        assert model_store.find_published(str(eth), coin="ETH") is None
    assert any("no published manifest" in r.getMessage() for r in caplog.records)
    # a model not named like the trainer's is read too, and its coin still checked
    renamed = os.path.join(os.path.dirname(model_folder), "hand-named")
    shutil.copytree(model_folder, renamed)
    _rewrite_manifest(renamed, model_id="hand-named")
    with caplog.at_level(logging.ERROR, logger="model_store"):
        assert model_store.find_published(str(eth), coin="ETH") is None
    assert any("trained for BTC, not ETH" in r.getMessage() for r in caplog.records)


def test_the_thinker_prints_the_model_it_uses_and_refuses_an_unpublished_one(tmp_path):
    frames = seed(n=HOURS + 200)
    folder = pt_paths.neural_dir()  # BTC's coin folder, as the thinker resolves it
    summary = train_main(folder)
    bars = hth.bars_from_frames(frames)
    times = [END + timedelta(hours=h) for h in (1, 2)]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive_ok"), "BTC", bars, thinker_decisions(times)
    )
    assert code == 0, out[-3000:]
    assert (
        f"Model for BTC: {summary['model_id']}, trained 2024-01-01T00:00:00Z .. 2024-03-11T00:00:00Z"
        in out
    )
    # checked once: rewriting the thresholds unchanged (every step) is not a change
    assert out.count("Model for BTC") == 1
    assert records[-1]["tf_choice_index"] == 0 and records[-1]["perfects"]

    with open(os.path.join(folder, "memories_1hour.txt"), "a", encoding="utf-8") as f:
        f.write("~1 2{}3{}4")
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive_bad"), "BTC", bars, thinker_decisions(times)
    )
    assert code == 0, out[-3000:]
    assert "ERROR: BTC: no published model manifest matches the model files" in out
    assert "Model for BTC" not in out
    # held like an untrained coin: nothing stepped, zero signals written
    assert all(r["tf_choice_index"] == 0 for r in records)
    assert records[-1]["high_tf_prices"][0] == 99999999999999999
    assert records[-1]["signals_dca_spread.txt"] == "0"


def test_the_thinker_rechecks_model_files_changed_without_a_new_stamp(tmp_path):
    frames = seed(n=HOURS + 200)
    folder = pt_paths.neural_dir()
    train_main(folder)
    bars = hth.bars_from_frames(frames)
    decisions = thinker_decisions([END + timedelta(hours=h) for h in (1, 2)])
    # between the decisions a model file changes; the training stamp does not
    memories = os.path.join(folder, "memories_1hour.txt")
    decisions[1]["append"] = [[memories, "~1 2{}3{}4"]]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive"), "BTC", bars, decisions
    )
    assert code == 0, out[-3000:]
    assert out.index("Model for BTC") < out.index(
        "ERROR: BTC: no published model manifest matches the model files"
    )
    assert all(bar is not None for bar in records[0]["served"].values())
    # held from the change on: no bar fetched, nothing stepped, zero signals
    assert all(bar is None for bar in records[1]["served"].values())
    assert records[1]["signals_dca_spread.txt"] == "0"
    assert records[1]["signals_dca_single.txt"] == "0"


def test_the_thinker_refuses_another_coins_model(tmp_path):
    frames = seed(n=HOURS + 200)
    btc = pt_paths.neural_dir()
    train_main(btc)
    eth = os.path.join(btc, "ETH")  # ETH's coin folder, as the thinker resolves it
    os.makedirs(eth)
    for name in pattern_model.model_file_names() + ["trainer_last_training_time.txt"]:
        shutil.copyfile(os.path.join(btc, name), os.path.join(eth, name))
    bars = hth.bars_from_frames(frames)
    times = [END + timedelta(hours=h) for h in (1, 2)]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive"), "ETH", bars, thinker_decisions(times)
    )
    assert code == 0, out[-3000:]
    assert "ERROR: ETH: no published model manifest matches the model files" in out
    assert "Model for ETH" not in out
    assert all(bar is None for r in records for bar in r["served"].values())
    assert records[-1]["signals_dca_spread.txt"] == "0"


# --- pattern_model reproduces the thinker --------------------------------------------------


def same(a, b):
    """Equal floats, or both NaN (a NaN weight gives NaN prices in the thinker too)."""
    return a == b or (math.isnan(a) and math.isnan(b))


def assert_thinker_equivalence(records, models):
    """Every timeframe of every recorded sweep: the thinker's prediction (high and low
    prices, active, training issue) equals pattern_model's for the bar it was served."""
    checked = 0
    for r in records:
        for i, tf in enumerate(ppt.TF_CHOICES):
            t, o, h, lo, c = r["served"][tf]
            p = models[tf].predict(o, c)
            assert r["perfects"][i] == ("active" if p.active else "inactive"), (tf, t)
            assert r["training_issues"][i] == (1 if p.training_issue else 0), (tf, t)
            assert same(r["high_tf_prices"][i], p.high_price), (tf, t)
            assert same(r["low_tf_prices"][i], p.low_price), (tf, t)
            checked += 1
    return checked


def test_pattern_model_predicts_what_the_thinker_predicts(tmp_path):
    frames = seed(n=HOURS + 400)
    folder = pt_paths.neural_dir()
    train_main(folder)
    models = pattern_model.PatternModel.from_folder(folder).timeframes
    bars = hth.bars_from_frames(frames)
    times = [END + timedelta(hours=h) for h in range(1, 400, 7)]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive"), "BTC", bars, thinker_decisions(times)
    )
    assert code == 0, out[-3000:]
    assert assert_thinker_equivalence(records, models) == 7 * len(times)
    active = sum(p == "active" for r in records for p in r["perfects"])
    assert 0 < active < 7 * len(times)  # both outcomes occur


def crafted_files():
    """Hand-built files per timeframe, each exercising one branch of the thinker."""
    ones = lambda n: " ".join(["1.0"] * n)  # noqa: E731
    mem = "~".join(
        [
            "0.0 0.5{}1.0{}-1.0",
            "-0.3 -0.2{}0.4{}-0.6",
            "0.3 0.25{}0.9{}-0.4",
            "1.5 -1.0{}0.2{}-2.0",
            "-1.2 0.8{}1.5{}-0.3",
        ]
    )
    return {
        # matches anything: plain averages, led by high moves that cancel (1e16, 1,
        # -1e16: Python's sum gives the 1, numpy's would not); a "nan" memory parses
        # but never matches
        "1hour": (
            "1000000000.0",
            "0.1 0.2{}1e18{}-1.0~0.2 0.1{}100.0{}-1.0~0.3 0.1{}-1e18{}-1.0~"
            + mem
            + "~nan 0.1{}0.2{}-0.2",
            ones(9),
            ones(9),
            ones(9),
        ),
        # a wide threshold (the 0.3 memory matches bodies of about +0.06% to +2.1%,
        # and zero-sum pairs match); that memory's high weight is NaN, so a match
        # averages in a NaN: active, with a NaN high price
        "2hour": ("150.0", mem, ones(5), "1.0 1.0 nan 1.0 1.0", ones(5)),
        # every move weight 0: nothing to average, so inactive without an issue
        "4hour": ("1000000000.0", mem, " ".join(["0.0"] * 5), ones(5), ones(5)),
        # an empty memory file: a training data issue
        "8hour": ("1.0", "", "", "", ""),
        # a memory without its high/low fields: an issue only once it matches
        "12hour": ("1000000000.0", "0.1 0.2~0.3 0.4{}1{}-1", ones(2), ones(2), ones(2)),
        # weights shorter than the memories: an issue when the last one matches
        "1day": ("1000000000.0", mem, ones(3), ones(5), ones(5)),
        # threshold 0: only exact (or zero-sum) bodies match; mixed weights
        "1week": ("0.0", mem, "2.0 1.0 0.0 1.0 0.5", "1.0 0.0 1.0 1.0 1.0", ones(5)),
    }


def test_pattern_model_matches_the_thinker_on_crafted_edge_cases(tmp_path):
    frames = seed(n=HOURS + 400)
    folder = pt_paths.neural_dir()
    for tf, texts in crafted_files().items():
        for kind, text in zip(pattern_model.FILE_KINDS, texts):
            with open(
                os.path.join(folder, f"{kind}_{tf}.txt"), "w", encoding="utf-8"
            ) as f:
                f.write(text)
    files = model_store.folder_file_hashes(folder)
    manifest = {
        "manifest_version": model_store.MANIFEST_VERSION,
        "model_id": "crafted-edge-cases",
        "trainer_path": "app/tests/test_model_provenance.py",
        "trainer_git_commit": None,
        "upstream_commit": "ba62130",
        "symbol": PAIR,
        "coin": "BTC",
        "timeframes": list(ppt.TF_CHOICES),
        "train_start": "2024-01-01T00:00:00Z",
        "train_end": "2024-03-11T00:00:00Z",
        "candle_file_sha256": {},
        "params": {},
        "seed": 0,
        "created_at": "2026-10-06T00:00:00Z",
        "validation_metrics": {},
        "files": files,
    }
    model_store.publish(folder, manifest, trainer_root=None)
    with open(os.path.join(folder, "trainer_last_training_time.txt"), "w") as f:
        f.write(str(int(datetime.now(timezone.utc).timestamp())))
    models = pattern_model.PatternModel.from_folder(folder).timeframes
    bars = hth.bars_from_frames(frames)
    times = [END + timedelta(hours=h) for h in range(1, 400, 5)]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive"), "BTC", bars, thinker_decisions(times)
    )
    assert code == 0, out[-3000:]
    assert assert_thinker_equivalence(records, models) == 7 * len(times)
    by_tf = {
        tf: {(r["perfects"][i], r["training_issues"][i]) for r in records}
        for i, tf in enumerate(ppt.TF_CHOICES)
    }
    assert by_tf["1hour"] == {("active", 0)}
    i2 = ppt.TF_CHOICES.index("2hour")
    assert any(
        r["perfects"][i2] == "active" and math.isnan(r["high_tf_prices"][i2])
        for r in records
    ), "no bar matched the NaN-high-weight memory"
    assert by_tf["4hour"] == {("inactive", 0)}
    assert by_tf["8hour"] == {("inactive", 1)}
    assert ("inactive", 1) in by_tf["12hour"]
    assert ("inactive", 1) in by_tf["1day"]
