"""FDS-SR-001 milestone M2b: the strategy list in Settings > Strategy (sections 5.3,
5.8 and 12).

* The list shows every strategy, then every stop, with its ID, name, kind, family,
  candles, what it may be used for, whether it is enabled for research and whether it
  is in use.
* Each entry has a trading switch for the trading mode the settings name. It starts
  as the entry's authorisation; switching one on that its authorisation does not clear
  asks first. "Use for trading" switches the entry on (asking the same way) and
  chooses it. A strategy switched off leaves the Strategy list and Save refuses until
  another is chosen; a stop switched off is unticked. The switches are saved as
  ``strategy.trading_allowed`` only when one changed, and only where they differ from
  the authorisation.
* The research ticks are saved as ``strategy.research_enabled`` only when one changed,
  so a file nobody changed stays as it was.
* Its words state facts only. The ID column is the one place an ID is shown: it names
  each entry as the reports do.

The window runs under the isolation guard (app/conftest.py) with a hidden root, and
saves to a pt_config.json in a temporary folder."""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest
from test_strategy_settings_ui import Box, folder, manager, on_disk, root  # noqa: F401

import strategy_settings_ui as ui
from strategies import catalogue as cat
from strategies import descriptions as words
from strategies.settings import (
    DEFAULT_RESEARCH_ENABLED,
    read_research_enabled,
    read_strategy_settings,
)

BANNED = ("FDS", "STRAT-", "OVL-", "Binance", "KuCoin", "_len", "_pct")


def open_window(root, folder, saved=None, trading=None, box=None):  # noqa: F811
    if trading is not None or saved is not None:
        path = os.path.join(folder, "pt_config.json")
        data = {}
        if trading is not None:
            data["trading"] = trading
        if saved is not None:
            data["strategy"] = saved
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    win = ui.StrategySettingsWindow(
        root, manager_factory=lambda: manager(folder), messagebox=box or Box()
    )
    win.withdraw()
    return win


def rows(win):
    tree = win.list_table.tree
    return {iid: tree.item(iid, "values") for iid in tree.get_children()}


def highlight(win, sid):
    win.list_table.tree.selection_set(sid)
    win._on_list_select()


def entry_with(sid, **changes):
    return {sid: dict(cat.CATALOGUE[sid], **changes)}


def test_the_list_shows_every_entry_with_its_use_and_state(root, folder):  # noqa: F811
    win = open_window(root, folder)
    shown = rows(win)
    assert list(shown) == ui.listed_ids()
    assert ui.listed_ids()[:4] == ["STRAT-000", "STRAT-001", "STRAT-002", "STRAT-003"]
    assert shown["STRAT-001"] == (
        "STRAT-001",
        "Trend crossover (DEMA/TEMA)",
        "Strategy",
        "Trend",
        "1 hour",
        "Paper and live",
        "Yes",
        "Yes",
        "Yes",
    )
    assert shown["STRAT-003"] == (
        "STRAT-003",
        "Trained pattern model",
        "Strategy",
        "Trained model",
        "1 hour",
        "Research only",
        "No",
        "No",
        "",
    )
    assert shown["OVL-ATR"] == (
        "OVL-ATR",
        "ATR trailing stop",
        "Stop or filter",
        "Stop or filter",
        "Any",
        "Paper and live",
        "Yes",
        "Yes",
        "",
    )
    win.destroy()


def test_in_use_follows_the_strategy_and_the_stop_ticks(root, folder):  # noqa: F811
    win = open_window(root, folder)
    win.strategy_var.set("Supertrend")
    win.overlay_on["OVL-ATR"].set(True)
    shown = rows(win)
    assert shown["STRAT-002"][8] == "Yes" and shown["STRAT-001"][8] == ""
    assert shown["OVL-ATR"][8] == "Yes"
    win.engine_var.set("legacy_neural")
    assert rows(win)["STRAT-002"][8] == ""
    win.destroy()


def test_use_for_trading_chooses_the_highlighted_strategy(root, folder):  # noqa: F811
    win = open_window(root, folder)
    highlight(win, "STRAT-002")
    assert win.highlight_help_var.get().startswith("Supertrend: ")
    assert win.use_button.instate(["!disabled"])
    win.use_button.invoke()
    assert win.strategy_var.get() == "Supertrend"
    highlight(win, "OVL-PLOCK")
    win.use_button.invoke()
    assert win.overlay_on["OVL-PLOCK"].get()
    assert win.save()
    after = on_disk(folder)
    assert after["active_id"] == "STRAT-002"
    assert [o["id"] for o in after["overlays"]] == ["OVL-PLOCK"]
    assert "research_enabled" not in after  # no research tick changed


def test_a_model_strategy_cannot_be_used_for_trading(root, folder):  # noqa: F811
    win = open_window(root, folder)
    highlight(win, "STRAT-003")
    assert win.use_button.instate(["disabled"])
    assert win.trading_tick.instate(["disabled"])
    assert win.highlight_use_var.get() == words.USE_HELP["research"]
    win.use_button.invoke()  # does nothing
    assert win.strategy_var.get() == "Trend crossover (DEMA/TEMA)"
    assert "Trained pattern model" not in win.strategy_combo.cget("values")
    win.destroy()


def test_a_research_strategy_is_not_offered_and_a_saved_one_is_reported(
    root, folder  # noqa: F811
):
    with mock.patch.dict(
        cat.CATALOGUE, entry_with("STRAT-002", authorisation="research")
    ):
        assert ui.offered_strategies() == ["STRAT-000", "STRAT-001", "STRAT-004"]
        win = open_window(root, folder, saved={"active_id": "STRAT-002"})
        assert (
            win.status_var.get()
            == "The saved strategy 'STRAT-002' is not one of these."
        )
        assert rows(win)["STRAT-002"][5] == "Research only"
        assert rows(win)["STRAT-002"][7] == "No"
        highlight(win, "STRAT-002")
        win.use_button.invoke()  # asked, and the test's answer is no
        assert win._box.questions == [
            "Supertrend is cleared for backtests only. Switch it on for paper "
            "trading?"
        ]
        assert not win.trading_on["STRAT-002"].get()
        assert win.strategy_var.get() == "Trend crossover (DEMA/TEMA)"
        win.destroy()


def test_a_paper_strategy_is_offered_in_paper_but_not_in_live(
    root, folder
):  # noqa: F811
    with mock.patch.dict(cat.CATALOGUE, entry_with("STRAT-002", authorisation="paper")):
        assert "STRAT-002" in ui.offered_strategies("paper")
        assert "STRAT-002" not in ui.offered_strategies("live")
        win = open_window(root, folder, trading={"mode": "live"})
        highlight(win, "STRAT-002")
        assert not win.trading_on["STRAT-002"].get()
        assert win.highlight_use_var.get() == (
            words.USE_HELP["paper"] + " Trading is set to live."
        )
        win.destroy()


def test_a_stop_this_mode_may_not_use_is_not_tickable_or_kept(
    root, folder
):  # noqa: F811
    saved = {"overlays": [{"id": "OVL-ATR", "params": {}}]}
    with mock.patch.dict(
        cat.CATALOGUE, entry_with("OVL-ATR", authorisation="research")
    ):
        win = open_window(root, folder, saved=saved)
        assert not win.overlay_on["OVL-ATR"].get()
        assert "The saved stop ATR trailing stop cannot be used for paper trading." in (
            win.status_var.get()
        )
        highlight(win, "OVL-ATR")
        assert not win.trading_on["OVL-ATR"].get()
        assert win._overlay_ticks["OVL-ATR"].instate(["disabled"])
        assert win.save()
        assert on_disk(folder)["overlays"] == []
        assert "trading_allowed" not in on_disk(folder)


def test_research_ticks_are_saved_only_when_changed(root, folder):  # noqa: F811
    win = open_window(root, folder)
    assert win.research_enabled() == list(DEFAULT_RESEARCH_ENABLED)
    assert win.save()
    assert "research_enabled" not in on_disk(folder)

    win = open_window(root, folder)
    highlight(win, "STRAT-003")
    win.research_tick.invoke()
    assert rows(win)["STRAT-003"][6] == "Yes"
    highlight(win, "OVL-PLOCK")
    win.research_tick.invoke()
    assert rows(win)["OVL-PLOCK"][6] == "No"
    assert win.save()
    wanted = [
        sid
        for sid in ui.listed_ids()
        if (sid in DEFAULT_RESEARCH_ENABLED or sid == "STRAT-003")
        and sid != "OVL-PLOCK"
    ]
    assert on_disk(folder)["research_enabled"] == wanted
    assert list(read_research_enabled(manager(folder))) == wanted


def test_research_ticks_are_saved_with_the_neural_levels_too(
    root, folder
):  # noqa: F811
    win = open_window(root, folder)
    win.engine_var.set("legacy_neural")
    highlight(win, "STRAT-000")
    win.research_tick.invoke()
    assert win.save()
    after = on_disk(folder)
    assert after["engine"] == "legacy_neural"
    assert "STRAT-000" not in after["research_enabled"]


def test_the_timeframes_offered_are_the_strategys_own(root, folder):  # noqa: F811
    with mock.patch.dict(
        cat.CATALOGUE, entry_with("STRAT-002", timeframes_permitted=["4h", "1d"])
    ):
        win = open_window(root, folder)
        win.timeframe_var.set("15 minutes")
        win.strategy_var.set("Supertrend")
        assert list(win.timeframe_combo.cget("values")) == ["4 hours", "1 day"]
        assert win.timeframe_var.get() == "4 hours"  # the strategy's own primary
        win.destroy()


def test_the_lists_words_state_facts_only(root, folder):  # noqa: F811
    win = open_window(root, folder)
    shown = rows(win)
    # the ID column shows each entry's ID, and nothing else does
    assert [row[0] for row in shown.values()] == ui.listed_ids()
    texts = [str(v) for row in shown.values() for v in row[1:]]
    for sid in ui.listed_ids():
        highlight(win, sid)
        texts += [win.highlight_help_var.get(), win.highlight_use_var.get()]
    texts += list(words.FAMILY_NAMES.values()) + list(words.KIND_NAMES.values())
    texts += list(words.USE_NAMES.values()) + list(words.USE_HELP.values())
    for text in texts:
        for banned in BANNED:
            assert banned not in text, (banned, text)
        assert "catalogue" not in text.lower(), text
    win.destroy()


@pytest.mark.parametrize("auth", list(cat.AUTHORISATIONS))
def test_every_authorisation_has_its_words(auth):
    assert words.USE_NAMES[auth] and words.USE_HELP[auth]


def test_every_family_has_its_words():
    assert set(words.FAMILY_NAMES) == set(cat.FAMILIES)


# -- the trading switch ------------------------------------------------------------


def test_switching_the_strategy_in_use_off_needs_another_before_saving(
    root, folder
):  # noqa: F811
    box = Box()
    win = open_window(root, folder, box=box)
    highlight(win, "STRAT-001")
    win.trading_tick.invoke()  # off: no question, nothing is being allowed
    assert box.questions == []
    assert not win.trading_on["STRAT-001"].get()
    assert win.strategy_var.get() == ""
    assert "Trend crossover (DEMA/TEMA)" not in win.strategy_combo.cget("values")
    assert rows(win)["STRAT-001"][7:] == ("No", "")
    assert win.highlight_use_var.get() == (
        words.USE_HELP["live"] + " You switched it off for paper trading."
    )
    assert not win.save()
    assert box.errors == ["Choose a strategy that is switched on for paper trading."]
    assert on_disk(folder) == {}  # nothing saved

    win.strategy_var.set("Supertrend")
    assert win.save()
    after = on_disk(folder)
    assert after["active_id"] == "STRAT-002"
    assert after["trading_allowed"] == {"STRAT-001": {"paper": False}}
    settings = {"trading": {"mode": "paper"}, "strategy": dict(after)}
    settings["strategy"]["active_id"] = "STRAT-001"
    assert read_strategy_settings(settings, "paper").problem == (
        "STRAT-001 is switched off for paper trading in Settings > Strategy"
    )
    assert read_strategy_settings(settings, "live").problem is None


def test_switching_on_a_research_strategy_asks_first(root, folder):  # noqa: F811
    box = Box(answer=False)
    win = open_window(root, folder, box=box)
    highlight(win, "STRAT-005")
    name = words.name_of("STRAT-005")
    win.trading_tick.invoke()
    assert box.questions == [
        f"{name} is cleared for backtests only. Switch it on for paper trading?"
    ]
    assert not win.trading_on["STRAT-005"].get()  # the answer was no
    box.answer = True
    win.trading_tick.invoke()
    assert win.trading_on["STRAT-005"].get()
    assert name in win.strategy_combo.cget("values")
    assert win.highlight_use_var.get() == (
        words.USE_HELP["research"] + " You switched it on for paper trading."
    )
    win.use_button.invoke()  # already on: no second question
    assert len(box.questions) == 2
    assert win.strategy_var.get() == name
    assert win.save()
    after = on_disk(folder)
    assert (after["active_id"], after["timeframe"]) == ("STRAT-005", "1d")
    assert after["trading_allowed"] == {"STRAT-005": {"paper": True}}
    settings = {"strategy": dict(after)}
    assert read_strategy_settings(settings, "paper").problem is None
    assert "STRAT-005 can be used for research only, not live trading" in (
        read_strategy_settings(settings, "live").problem
    )


def test_use_for_trading_in_live_asks_and_names_real_orders(root, folder):  # noqa: F811
    box = Box(answer=True)
    win = open_window(root, folder, trading={"mode": "live"}, box=box)
    assert win.trading_tick.cget("text") == "Enabled for live trading"
    highlight(win, "STRAT-004")
    win.use_button.invoke()
    name = words.name_of("STRAT-004")
    assert box.questions == [
        f"{name} is cleared for paper trading only. Switched on for live trading, "
        "it can place real orders. Switch it on for live trading?"
    ]
    assert win.strategy_var.get() == name
    assert win.save()
    assert on_disk(folder)["trading_allowed"] == {"STRAT-004": {"live": True}}


def test_switches_are_saved_only_when_changed_and_where_they_differ(
    root, folder
):  # noqa: F811
    win = open_window(root, folder)
    assert win.save()
    assert "trading_allowed" not in on_disk(folder)

    # the other mode's switch is kept; switching back to the authorisation drops one
    saved = {"trading_allowed": {"STRAT-005": {"live": True}}}
    win = open_window(root, folder, saved=saved)
    highlight(win, "STRAT-002")
    win.trading_tick.invoke()
    assert win.save()
    assert on_disk(folder)["trading_allowed"] == {
        "STRAT-005": {"live": True},
        "STRAT-002": {"paper": False},
    }
    win = open_window(root, folder, saved=on_disk(folder))
    highlight(win, "STRAT-002")
    win.trading_tick.invoke()  # back on: what it is cleared for, so no question
    assert win._box.questions == []
    assert win.save()
    assert on_disk(folder)["trading_allowed"] == {"STRAT-005": {"live": True}}


def test_a_stop_switched_off_is_unticked_and_not_saved(root, folder):  # noqa: F811
    saved = {"overlays": [{"id": "OVL-ATR", "params": {}}]}
    win = open_window(root, folder, saved=saved)
    assert win.overlay_on["OVL-ATR"].get()
    highlight(win, "OVL-ATR")
    win.trading_tick.invoke()
    assert not win.overlay_on["OVL-ATR"].get()
    assert win._overlay_ticks["OVL-ATR"].instate(["disabled"])
    assert rows(win)["OVL-ATR"][7:] == ("No", "")
    assert win.save()
    after = on_disk(folder)
    assert after["overlays"] == []
    assert after["trading_allowed"] == {"OVL-ATR": {"paper": False}}


def test_unreadable_switches_are_reported_and_saved_again(root, folder):  # noqa: F811
    win = open_window(root, folder, saved={"trading_allowed": ["STRAT-001"]})
    assert (
        "The saved trading switches could not be read, so nothing trades until "
        "they are saved again." in win.status_var.get()
    )
    assert win.trading_on["STRAT-001"].get()  # shown as the authorisation
    assert win.save()
    assert on_disk(folder)["trading_allowed"] == {}


def test_the_switch_words_state_facts_only(root, folder):  # noqa: F811
    box = Box(answer=True)
    win = open_window(root, folder, box=box)
    for sid in ui.listed_ids():
        highlight(win, sid)
        if ui.tradable(sid):
            win.trading_tick.invoke()
            texts = [win.highlight_use_var.get(), win.status_var.get()]
            for text in texts + box.questions:
                for banned in BANNED:
                    assert banned not in text, (banned, text)
                assert "catalogue" not in text.lower(), text
    win.destroy()
