"""FDS-SR-001 milestone M5b: "Model evidence..." (sections 5.8, 6.6 and 12).

* STRAT-001's recorded findings are copied verbatim from FDS-SIG-004's development
  report, and kept apart: prediction, then trading, then economic.
* A strategy with no evaluated model says so.
* A declared experiment's sealed results are shown with its strategy only; results
  that changed are not shown, and are never overwritten.
* The words state facts only.

No candles, no network."""

from __future__ import annotations

import json
import os

import pytest
from test_strategy_experiments import declaration
from test_strategy_settings_ui import Box, folder, manager, root  # noqa: F401

import strategy_lab_ui as ui
import strategy_settings_ui as ssui
from strategy_lab import evidence, experiment

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(os.path.dirname(APP), "docs", "dev", "SIG4-REPORT-dev.md")
BANNED = ("FDS", "STRAT-", "OVL-", "F_P", "Binance", "KuCoin", "_len", "_pct")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
    return tmp_path / "strategy_lab"


class TestRecorded:
    def test_strat_001s_findings_are_the_reports_and_kept_apart(self, lab):
        lines = evidence.lines_for("STRAT-001")
        assert [line.kind for line in lines] == [
            "prediction",
            "prediction",
            "trading",
            "trading",
            "economic",
        ]
        with open(REPORT, encoding="utf-8") as f:
            report = f.read()
        for line in lines:
            verbatim = line.text.split(" (385 trades")[0]
            assert verbatim in report, line.text
            assert line.recorded.endswith("development only")

    def test_a_strategy_without_evidence_says_so(self, root, lab):  # noqa: F811
        assert evidence.lines_for("STRAT-004") == []
        win = ui.EvidenceWindow(root, "STRAT-004")
        win.withdraw()
        assert not win.table.tree.get_children()
        assert win.table.is_empty_shown()
        assert ui.NO_EVIDENCE == "No model has been evaluated with this strategy."
        win.destroy()

    def test_the_words_state_facts_only(self):
        texts = list(ui.EVIDENCE_HEADINGS.values()) + [ui.NO_EVIDENCE]
        for line in evidence.RECORDED:
            texts += [line.model, line.text, line.period, line.recorded]
        for text in texts:
            for banned in BANNED:
                assert banned not in text, (banned, text)


class TestDeclared:
    def test_sealed_results_show_with_their_strategy_only(self, lab):
        experiment.freeze("e1", declaration())
        mine = evidence.Line(
            "STRAT-004",
            "Price-only filter",
            "trading",
            "Too few trades to tell",
            "dev",
            "now",
        )
        evidence.write_results("e1", [mine])
        assert evidence.lines_for("STRAT-004") == [mine]
        assert len(evidence.lines_for("STRAT-001")) == 5
        with pytest.raises(experiment.ExperimentError, match="already has results"):
            evidence.write_results("e1", [mine])

    def test_changed_results_are_not_shown(self, lab):
        experiment.freeze("e2", declaration())
        evidence.write_results(
            "e2",
            [evidence.Line("STRAT-004", "m", "economic", "Not shown", "dev", "now")],
        )
        path = evidence.results_path("e2")
        data = json.loads(open(path, encoding="utf-8").read())
        data["lines"][0]["text"] = "Profitable"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        assert evidence.lines_for("STRAT-004") == []

    def test_an_unknown_kind_is_refused(self, lab):
        experiment.freeze("e3", declaration())
        with pytest.raises(experiment.ExperimentError, match="kind"):
            evidence.write_results(
                "e3", [evidence.Line("STRAT-004", "m", "profit", "x", "dev", "now")]
            )


class TestStrategyWindow:
    def test_the_button_opens_the_highlighted_strategys_evidence(
        self, root, folder, lab
    ):  # noqa: F811
        win = ssui.StrategySettingsWindow(
            root,
            manager_factory=lambda: manager(folder),
            messagebox=Box(),
            coins_factory=list,
        )
        win.withdraw()
        win.list_table.tree.selection_set("OVL-ATR")
        win._on_list_select()
        assert win.evidence_button.instate(["disabled"])
        assert win.open_evidence() is None
        win.list_table.tree.selection_set("STRAT-001")
        win._on_list_select()
        assert win.evidence_button.instate(["!disabled"])
        shown = win.open_evidence()
        shown.withdraw()
        assert len(shown.table.tree.get_children()) == 5
        win.destroy()
