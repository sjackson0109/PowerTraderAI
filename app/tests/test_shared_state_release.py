"""Two pieces of process-wide state that made app/tests/test_suite.py fail when run on its
own (it passed in the full suite only because earlier tests had set them up):

* ExchangeFactory knew no exchange until something imported pt_exchanges, whose
  connectors register themselves on import;
* the global order manager and its database could not be released: SQLite kept the
  file open (Windows could not delete it) and the monitoring thread kept running.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import subprocess
import sys
import time

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def test_the_exchange_factory_lists_its_exchanges_without_a_prior_import(tmp_path):
    """In a fresh process: no module but pt_exchange_abstraction is imported first."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from pt_exchange_abstraction import ExchangeFactory, ExchangeType; "
        "print(len(ExchangeFactory.get_available_exchanges())); "
        "print(ExchangeFactory.get_exchange_class(ExchangeType.BINANCE).__name__)"
    )
    env = dict(os.environ, POWERTRADER_HOME=str(tmp_path / "home"))
    result = subprocess.run(
        [sys.executable, "-c", code, APP_DIR],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    count, binance = result.stdout.split()[-2:]
    assert int(count) > 0 and binance == "BinanceExchange"


def test_shutting_down_order_management_releases_its_database(tmp_path):
    from order_management_integration import (
        initialize_order_management_for_powertrader,
        shutdown_order_management,
    )

    shutdown_order_management()  # none left over from another test
    db = tmp_path / "orders.db"
    manager = initialize_order_management_for_powertrader(f"sqlite:///{db}")
    try:
        assert manager.is_available and manager.is_monitoring
        thread = manager.condition_check_thread
    finally:
        start = time.monotonic()
        shutdown_order_management()
    assert time.monotonic() - start < 3  # no waiting out the 5 s check interval
    assert not thread.is_alive()
    for path in tmp_path.glob("orders.db*"):  # the database and its WAL files
        os.remove(path)  # Windows refuses while a connection holds it
    assert not list(tmp_path.glob("orders.db*"))
