"""Portfolio Analytics and Portfolio Optimization (owner, 2026-11-05).

* Portfolio Analytics is gone: no tab, no entry in the tab order, its two modules in
  archive/legacy/.

Real Tk widgets and a real hub, under the isolation guard (app/conftest.py).
"""

import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_DIR = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# ---- acceptance: no Portfolio Analytics tab remains ----


def test_no_portfolio_analytics_tab_remains(monkeypatch):
    import helpers_trainer as ht

    import pt_hub

    hub = ht.build_real_hub(monkeypatch)
    try:
        nb = hub.bottom_notebook
        names = [pt_hub.module_tab_name(nb.tab(t, "text")) for t in nb.tabs()]
        assert "Portfolio Optimization" in names
        assert not [n for n in names if "Analytics" in n]
    finally:
        ht.close_hub(hub)
    assert "Portfolio Analytics" not in pt_hub.MODULE_TAB_ORDER
    assert not hasattr(pt_hub, "PORTFOLIO_ANALYTICS_AVAILABLE")
    assert not hasattr(pt_hub.PowerTraderHub, "_create_portfolio_analytics_tab")
    # the modules: in archive/legacy/, no longer in app/
    for name in ("portfolio_analytics.py", "portfolio_analytics_gui.py"):
        assert not os.path.exists(os.path.join(APP_DIR, name))
        assert os.path.isfile(os.path.join(REPO_DIR, "archive", "legacy", name))
