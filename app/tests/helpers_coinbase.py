"""Shared fixtures for the Coinbase tests. Everything here is synthetic: keys are
generated on the fly and no test may reach the network."""

from __future__ import annotations

import contextlib
import json
from typing import Callable, List, Optional, Tuple
from unittest import mock

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

KEY_NAME = "organizations/00000000-test-org/apiKeys/11111111-test-key"


def make_ec_pem(label: str = "EC") -> str:
    """A throw-away P-256 key, PEM. ``label='EC'`` is SEC1 (BEGIN EC PRIVATE KEY),
    anything else is PKCS#8 (BEGIN PRIVATE KEY)."""
    key = ec.generate_private_key(ec.SECP256R1())
    fmt = (
        serialization.PrivateFormat.TraditionalOpenSSL
        if label == "EC"
        else serialization.PrivateFormat.PKCS8
    )
    return key.private_bytes(
        serialization.Encoding.PEM, fmt, serialization.NoEncryption()
    ).decode()


def make_ed25519_pem() -> str:
    key = ed25519.Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def make_response(status: int, body=None, raw: Optional[bytes] = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = raw if raw is not None else json.dumps(body if body is not None else {}).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp


class HttpRecorder:
    """Intercepts ``requests.sessions.Session.request`` - the funnel under
    ``requests.get/post/...`` and every Session - and blocks raw sockets, so a
    test sees every HTTP request the code under test tries to make and nothing
    can leave the machine."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, dict]] = []
        self._responder: Callable[[str, str], object] = lambda m, u: make_response(200, {})

    def respond(self, responder) -> None:
        """``responder(method, url)`` returns a Response or raises."""
        self._responder = responder

    def respond_with(self, status: int, body=None, raw: Optional[bytes] = None) -> None:
        self.respond(lambda m, u: make_response(status, body, raw))

    def raise_on_request(self, exc: Exception) -> None:
        def _raise(m, u):
            raise exc

        self.respond(_raise)

    # -- views --
    @property
    def methods(self) -> List[str]:
        return [m for m, _, _ in self.calls]

    @property
    def urls(self) -> List[str]:
        return [u for _, u, _ in self.calls]

    def order_like(self) -> List[Tuple[str, str]]:
        """Requests that look like order traffic: any non-GET, or any URL that
        mentions orders / preview."""
        return [
            (m, u)
            for m, u, _ in self.calls
            if m.upper() != "GET" or "order" in u.lower() or "preview" in u.lower()
        ]


@contextlib.contextmanager
def recorded_http():
    rec = HttpRecorder()

    def fake_request(session, method, url, **kwargs):
        rec.calls.append((str(method).upper(), str(url), kwargs))
        return rec._responder(str(method), str(url))

    def no_socket(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    with mock.patch.object(
        requests.sessions.Session, "request", autospec=True, side_effect=fake_request
    ), mock.patch("socket.create_connection", side_effect=no_socket), mock.patch(
        "socket.socket.connect", side_effect=no_socket
    ):
        yield rec
