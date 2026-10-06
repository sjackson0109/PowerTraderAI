"""Refuse to launch a mock trainer (FDS-MDL Phase 1 item 6).

The old stub trainer scripts carry ``MOCK_MARKER`` near the top: their "training" is a
sleep loop with a formula for accuracy, and nothing is learned from market data (some
also write random weights; see docs/dev/TRAINER-AUDIT.md).
The hub reads the first bytes of the configured trainer script (it never imports it)
and refuses to launch a marked script unless ``pt_config.json`` in the user config
folder holds ``"allow_mock_trainer": true``. Only JSON ``true`` counts; the default is
false. The setting is read fresh on every launch, the same way as the trading settings
(``trading_mode``).
"""

import logging

MOCK_MARKER = "MOCK - DO NOT USE FOR DECISIONS"
ALLOW_MOCK_TRAINER_KEY = "allow_mock_trainer"
REAL_TRAINER = "pt_pattern_trainer.py"
_HEAD_BYTES = 4096

logger = logging.getLogger(__name__)


def is_mock_trainer(path: str) -> bool:
    """True if the script at ``path`` carries the mock marker in its first 4 KB.
    A file that cannot be read is not judged here (the hub reports it as missing)."""
    try:
        with open(path, "rb") as f:
            head = f.read(_HEAD_BYTES)
    except OSError:
        return False
    return MOCK_MARKER.encode("ascii") in head


def read_allow_mock_trainer(settings=None) -> bool:
    """``allow_mock_trainer`` from pt_config.json (or ``settings``). Fails closed."""
    from trading_mode import lookup_setting, settings_mapping

    value = lookup_setting(settings_mapping(settings), ALLOW_MOCK_TRAINER_KEY, False)
    if value is not True and value not in (False, None):
        logger.warning(
            f"Invalid {ALLOW_MOCK_TRAINER_KEY}={value!r} (must be true or false); "
            "mock trainers stay refused"
        )
    return value is True


def refusal_message(script_path: str) -> str:
    import pt_paths

    return (
        f'The trainer script\n{script_path}\nis marked "{MOCK_MARKER}": it does not '
        "learn from market data (see docs/dev/TRAINER-AUDIT.md).\n\n"
        f'Set Settings > "pt_trainer.py path:" to {REAL_TRAINER} (the real trainer), '
        f'or set "{ALLOW_MOCK_TRAINER_KEY}": true in\n{pt_paths.settings_file()}\n'
        "to run it anyway."
    )
