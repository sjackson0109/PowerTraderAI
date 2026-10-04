"""pt_secrets: the only place credentials are read or written (FDS-108a)."""

import json
import logging
import os
import pickle
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import keyring  # noqa: E402
import keyring.backends.fail  # noqa: E402
import keyring.backends.null  # noqa: E402
from keyring.backend import KeyringBackend  # noqa: E402

import pt_secrets  # noqa: E402

SERVICE = "SJackson.PowerTraderAI"
KEY_NAME = "organizations/11111111-2222-3333-4444-555555555555/apiKeys/66666666-7777-8888-9999-000000000000"


def ec_pem_sec1():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


def ec_pem_pkcs8():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(pt_secrets, "_warned_both", set())
    for name in list(os.environ):
        if name.startswith("POWERTRADER_") and name != "POWERTRADER_HOME":
            monkeypatch.delenv(name)


def user_files(isolated_user_dirs):
    found = []
    for root, _, files in os.walk(isolated_user_dirs["home"]):
        found += [os.path.join(root, f) for f in files]
    return found


# --- storage --------------------------------------------------------------------


def test_round_trip_uses_service_and_entry_names(memory_keyring):
    pt_secrets.set_secret("coinbase", "key_name", KEY_NAME)
    pt_secrets.set_secret("coinbase", "private_key", "pem-value")
    assert memory_keyring.entries == {
        (SERVICE, "coinbase:key_name"): KEY_NAME,
        (SERVICE, "coinbase:private_key"): "pem-value",
    }
    assert pt_secrets.get_secret("coinbase", "key_name").reveal() == KEY_NAME
    assert pt_secrets.has_credentials("coinbase")


def test_credentials_map_fields_to_connector_arguments(memory_keyring):
    pt_secrets.set_credentials("coinbase", {"key_name": KEY_NAME, "private_key": "pem"})
    creds = pt_secrets.get_credentials("coinbase")
    assert dict(creds) == {"api_key": KEY_NAME, "api_secret": "pem"}
    assert creds.source == "keyring"
    pt_secrets.set_credentials(
        "kucoin", {"api_key": "k", "api_secret": "s", "passphrase": "p"}
    )
    assert dict(pt_secrets.get_credentials("kucoin")) == {
        "api_key": "k",
        "api_secret": "s",
        "passphrase": "p",
    }


def test_passphrase_is_optional_but_key_and_secret_are_required(memory_keyring):
    pt_secrets.set_secret("binance", "api_key", "k")
    assert not pt_secrets.has_credentials("binance")
    assert pt_secrets.get_credentials("binance") is None
    pt_secrets.set_secret("binance", "api_secret", "s")
    assert dict(pt_secrets.get_credentials("binance")) == {
        "api_key": "k",
        "api_secret": "s",
    }


def test_empty_value_deletes_and_delete_reports(memory_keyring):
    pt_secrets.set_secret("kraken", "api_key", "k")
    pt_secrets.set_secret("kraken", "api_key", "")
    assert memory_keyring.entries == {}
    pt_secrets.set_secret("kraken", "api_key", "k")
    assert pt_secrets.delete_secret("kraken", "api_key") is True
    assert pt_secrets.delete_secret("kraken", "api_key") is False


def test_unknown_field_is_refused(memory_keyring):
    with pytest.raises(pt_secrets.UnknownSecretField):
        pt_secrets.set_secret(
            "coinbase", "api_secret", "x"
        )  # coinbase uses private_key
    with pytest.raises(pt_secrets.UnknownSecretField):
        pt_secrets.get_secret("binance:x", "api_key")


# --- precedence --------------------------------------------------------------------


def test_environment_wins_over_keyring_and_the_source_is_logged(
    memory_keyring, monkeypatch, caplog
):
    pt_secrets.set_credentials(
        "coinbase", {"key_name": "keyring-key", "private_key": "keyring-pem"}
    )
    monkeypatch.setenv("POWERTRADER_COINBASE_API_KEY", "env-key-value")
    monkeypatch.setenv("POWERTRADER_COINBASE_API_SECRET", "env-pem-value")
    with caplog.at_level(logging.WARNING, logger="pt_secrets"):
        creds = pt_secrets.get_credentials("coinbase")
    assert creds.source == "environment"
    assert dict(creds) == {"api_key": "env-key-value", "api_secret": "env-pem-value"}
    assert pt_secrets.credential_source("coinbase") == "environment"
    text = caplog.text
    assert "environment" in text and "coinbase" in text
    for value in ("env-key-value", "env-pem-value", "keyring-key", "keyring-pem"):
        assert value not in text


def test_an_incomplete_environment_set_is_not_mixed_with_the_keyring(
    memory_keyring, monkeypatch
):
    pt_secrets.set_credentials("binance", {"api_key": "kr-k", "api_secret": "kr-s"})
    monkeypatch.setenv("POWERTRADER_BINANCE_API_KEY", "env-k")
    creds = pt_secrets.get_credentials("binance")
    assert creds.source == "keyring"
    assert dict(creds) == {"api_key": "kr-k", "api_secret": "kr-s"}


def test_environment_alone_works_without_any_keyring(monkeypatch):
    keyring.set_keyring(keyring.backends.fail.Keyring())
    monkeypatch.setenv("POWERTRADER_KRAKEN_API_KEY", "k")
    monkeypatch.setenv("POWERTRADER_KRAKEN_API_SECRET", "s")
    creds = pt_secrets.get_credentials("kraken")
    assert creds.source == "environment" and dict(creds) == {
        "api_key": "k",
        "api_secret": "s",
    }


def test_robinhood_private_key_env_name_and_alias(monkeypatch):
    monkeypatch.setenv("POWERTRADER_ROBINHOOD_API_KEY", "rk")
    monkeypatch.setenv("POWERTRADER_ROBINHOOD_API_SECRET", "alias")
    assert pt_secrets.get_secret("robinhood", "private_key").reveal() == "alias"
    monkeypatch.setenv("POWERTRADER_ROBINHOOD_PRIVATE_KEY", "primary")
    assert pt_secrets.get_secret("robinhood", "private_key").reveal() == "primary"
    assert dict(pt_secrets.get_credentials("robinhood")) == {
        "api_key": "rk",
        "api_secret": "primary",
    }


def test_env_var_table_is_complete_for_every_exchange():
    assert pt_secrets.env_var_names("coinbase") == (
        "POWERTRADER_COINBASE_API_KEY",
        "POWERTRADER_COINBASE_API_SECRET",
    )
    assert pt_secrets.env_var_names("kucoin") == (
        "POWERTRADER_KUCOIN_API_KEY",
        "POWERTRADER_KUCOIN_API_SECRET",
        "POWERTRADER_KUCOIN_PASSPHRASE",
    )
    assert pt_secrets.env_var_names("aave") == ("POWERTRADER_AAVE_PRIVATE_KEY",)


# --- no usable backend: refuse, no plaintext ------------------------------------------


@pytest.mark.parametrize(
    "backend",
    [keyring.backends.fail.Keyring(), keyring.backends.null.Keyring()],
    ids=["fail", "null"],
)
def test_no_backend_refuses_and_writes_no_file(
    backend, isolated_user_dirs, tmp_path, monkeypatch
):
    keyring.set_keyring(backend)
    monkeypatch.chdir(tmp_path)
    before = set(os.listdir(tmp_path))
    assert not pt_secrets.keyring_available()
    with pytest.raises(pt_secrets.KeyringUnavailable) as err:
        pt_secrets.set_secret("coinbase", "private_key", "plaintext-must-not-land")
    message = str(err.value)
    assert (
        "POWERTRADER_COINBASE_API_KEY" in message
        and "POWERTRADER_COINBASE_API_SECRET" in message
    )
    assert "paper mode" in message
    assert "plaintext-must-not-land" not in message
    with pytest.raises(pt_secrets.KeyringUnavailable):
        pt_secrets.set_credentials("binance", {"api_key": "k", "api_secret": "s"})
    assert set(os.listdir(tmp_path)) == before
    assert user_files(isolated_user_dirs) == []
    assert pt_secrets.get_secret("coinbase", "private_key") is None


from jaraco.classes import properties  # noqa: E402
from keyring.backends.chainer import ChainerBackend  # noqa: E402


class PlaintextKeyring(KeyringBackend):
    """Stand-in for keyrings.alt.file.PlaintextKeyring (never auto-selected)."""

    stored = {}

    @properties.classproperty
    def priority(cls):
        raise RuntimeError("test-only backend")

    def get_password(self, service, username):
        return self.stored.get((service, username))

    def set_password(self, service, username, password):
        self.stored[(service, username)] = password

    def delete_password(self, service, username):
        self.stored.pop((service, username), None)


def test_plaintext_file_backends_are_refused():
    PlaintextKeyring.__module__ = "keyrings.alt.file"
    keyring.set_keyring(PlaintextKeyring())
    assert not pt_secrets.keyring_available()
    with pytest.raises(pt_secrets.KeyringUnavailable):
        pt_secrets.set_secret("kraken", "api_key", "k")
    assert PlaintextKeyring.stored == {}


class FakeChain(ChainerBackend):
    """A chainer with explicit members (the real one asks the system)."""

    def __init__(self, members):
        self._members = members

    @property
    def backends(self):
        return self._members


def test_a_chained_backend_never_falls_through_to_a_refused_member(memory_keyring):
    PlaintextKeyring.__module__ = "keyrings.alt.file"
    chain = FakeChain([PlaintextKeyring(), memory_keyring])
    keyring.set_keyring(chain)
    try:
        assert pt_secrets._backend() is memory_keyring
        pt_secrets.set_secret("kraken", "api_key", "k")
        assert memory_keyring.entries == {(SERVICE, "kraken:api_key"): "k"}
        assert PlaintextKeyring.stored == {}
    finally:
        keyring.set_keyring(memory_keyring)


# --- redaction ---------------------------------------------------------------------------


def test_secret_never_shows_itself():
    s = pt_secrets.Secret("super-secret-value")
    for shown in (repr(s), str(s), f"{s}", "%s" % s, format(s, ">30")):
        assert "super-secret-value" not in shown
    assert s.reveal() == "super-secret-value"
    with pytest.raises(TypeError):
        json.dumps(s)
    with pytest.raises(TypeError):
        pickle.dumps(s)
    with pytest.raises(AttributeError):
        s._value = "x"


def test_credentials_repr_is_redacted(memory_keyring):
    pt_secrets.set_credentials(
        "binance", {"api_key": "visible-key-1234", "api_secret": "hidden-secret-5678"}
    )
    creds = pt_secrets.get_credentials("binance")
    for shown in (repr(creds), str(creds), f"{creds}", repr([creds])):
        assert "visible-key-1234" not in shown and "hidden-secret-5678" not in shown
    assert creds["api_secret"] == "hidden-secret-5678"


def test_values_never_reach_the_logs(memory_keyring, caplog, monkeypatch):
    with caplog.at_level(logging.DEBUG):
        pt_secrets.set_credentials(
            "binance", {"api_key": "log-key-value", "api_secret": "log-secret-value"}
        )
        pt_secrets.get_credentials("binance")
        monkeypatch.setenv("POWERTRADER_BINANCE_API_KEY", "env-log-key")
        monkeypatch.setenv("POWERTRADER_BINANCE_API_SECRET", "env-log-secret")
        pt_secrets.get_credentials("binance")
        pt_secrets.delete_credentials("binance")
    for value in ("log-key-value", "log-secret-value", "env-log-key", "env-log-secret"):
        assert value not in caplog.text


def test_a_failing_backend_error_carries_no_value(memory_keyring, monkeypatch):
    def boom(service, username, password):
        raise RuntimeError(f"backend echoed {password}")

    monkeypatch.setattr(memory_keyring, "set_password", boom)
    with pytest.raises(pt_secrets.SecretsError) as err:
        pt_secrets.set_secret("kraken", "api_secret", "leaky-value-123")
    assert "leaky-value-123" not in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__


def test_redact_helper():
    assert pt_secrets.redact("key=abcd1234 ok", ["abcd1234"]) == "key=*** ok"


# --- size limit (Windows Credential Manager: 2,560 bytes, UTF-16) --------------------------


@pytest.mark.parametrize("make_pem", [ec_pem_sec1, ec_pem_pkcs8], ids=["sec1", "pkcs8"])
def test_a_realistic_coinbase_pem_fits_and_round_trips(memory_keyring, make_pem):
    pem = make_pem()
    assert len(pem.encode("utf-16-le")) < pt_secrets.MAX_SECRET_BYTES
    pt_secrets.set_credentials("coinbase", {"key_name": KEY_NAME, "private_key": pem})
    assert pt_secrets.get_secret("coinbase", "private_key").reveal() == pem
    assert pt_secrets.get_secret("coinbase", "key_name").reveal() == KEY_NAME


def test_robinhood_ed25519_seed_fits(memory_keyring):
    import base64

    seed_b64 = base64.b64encode(os.urandom(32)).decode()
    pt_secrets.set_credentials(
        "robinhood", {"api_key": "rh-key", "private_key": seed_b64}
    )
    assert pt_secrets.get_secret("robinhood", "private_key").reveal() == seed_b64


def test_oversized_value_is_refused_with_a_clear_error(memory_keyring):
    too_big = "A" * (pt_secrets.MAX_SECRET_BYTES // 2 + 1)
    with pytest.raises(pt_secrets.SecretTooLarge) as err:
        pt_secrets.set_secret("coinbase", "private_key", too_big)
    message = str(err.value)
    assert "coinbase:private_key" in message and "2560" in message
    assert too_big not in message
    assert memory_keyring.entries == {}
    # largest value that fits is accepted
    pt_secrets.set_secret(
        "coinbase", "private_key", "A" * (pt_secrets.MAX_SECRET_BYTES // 2)
    )


def test_set_credentials_checks_every_size_before_writing(memory_keyring):
    with pytest.raises(pt_secrets.SecretTooLarge):
        pt_secrets.set_credentials(
            "binance",
            {"api_key": "fine", "api_secret": "B" * pt_secrets.MAX_SECRET_BYTES},
        )
    assert memory_keyring.entries == {}
