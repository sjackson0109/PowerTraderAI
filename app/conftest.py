"""Test isolation for every test under app/ (FDS-108a). The guard itself is
tests/isolation.py, shared with .github/scripts/conftest.py: loading it sets
``POWERTRADER_HOME``, the keyring backends and the blocked real folders before
any test module is imported, and its autouse fixture isolates every test.
"""

import importlib.util
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _load_isolation():
    """tests/isolation.py, loaded once per session under one name."""
    name = "powertrader_test_isolation"
    if name not in sys.modules:
        path = os.path.join(APP_DIR, "tests", "isolation.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


_isolation = _load_isolation()
RealLocationTouched = _isolation.RealLocationTouched
real_platform_dirs = _isolation.real_platform_dirs
isolated_user_dirs = _isolation.isolated_user_dirs
memory_keyring = _isolation.memory_keyring


def _no_request_pacing():
    """Connectors pace their requests to each exchange's limit (rate_limits.py);
    tests that stand in for the network would only wait. Off for the whole
    session (a thread left running between tests never waits either);
    test_rate_limits.py switches it on where it tests it."""
    import rate_limits

    rate_limits.ENABLED = False


_no_request_pacing()


def _no_llm_requests():
    """The trader's LLM signal hook (llm_gate) asks a provider for a signal at every
    entry in its default mode ("log only"), Ollama on this computer included, which
    the isolation guard lets through. No trader test may do that: off for the whole
    session; test_llm_gate.py switches it on with a fake provider."""
    import llm_gate

    llm_gate.REQUESTS_ENABLED = False


_no_llm_requests()


def _trainer_gate_not_enforced():
    """The trainer publishes a model only when it passes the entry gate (deviation 13).
    A model trained on a test's fixture candles has no reason to pass, and most tests
    are about training, publishing and loading, so the gate is still run and recorded
    but not enforced for the session; test_entry_gate.py switches it on."""
    import pt_pattern_trainer

    pt_pattern_trainer.ENFORCE_GATE = False


_trainer_gate_not_enforced()
