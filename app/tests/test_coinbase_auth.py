"""Coinbase CDP key authentication: JWT shape, signature, and pasted-key handling.

Keys are generated per test; nothing here touches the network.
"""

import base64
import json
import os
import sys
import unittest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: E402
    encode_dss_signature,
)

import coinbase_auth  # noqa: E402
from coinbase_auth import CoinbaseCredentialError  # noqa: E402
from helpers_coinbase import KEY_NAME, make_ec_pem, make_ed25519_pem  # noqa: E402

try:
    import jwt as pyjwt
except ImportError:  # optional cross-check only
    pyjwt = None

HOST = "api.coinbase.com"
PATH = "/api/v3/brokerage/accounts"


def b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def split(token: str):
    head, payload, sig = token.split(".")
    return json.loads(b64d(head)), json.loads(b64d(payload)), b64d(sig), f"{head}.{payload}"


class TestJwt(unittest.TestCase):
    def setUp(self):
        self.key = ec.generate_private_key(ec.SECP256R1())

    def token(self, **kw):
        return coinbase_auth.build_jwt(KEY_NAME, self.key, "GET", HOST, PATH, **kw)

    def test_header_matches_documented_fields(self):
        header, _, _, _ = split(self.token(nonce="abc123"))
        self.assertEqual(
            header, {"alg": "ES256", "typ": "JWT", "kid": KEY_NAME, "nonce": "abc123"}
        )

    def test_payload_matches_documented_claims(self):
        _, payload, _, _ = split(self.token(now=1_700_000_000))
        self.assertEqual(
            payload,
            {
                "sub": KEY_NAME,
                "iss": "cdp",
                "nbf": 1_700_000_000,
                "exp": 1_700_000_120,  # valid for two minutes
                "uri": "GET api.coinbase.com/api/v3/brokerage/accounts",
            },
        )

    def test_uri_claim_has_no_scheme_and_follows_method_and_path(self):
        self.assertEqual(
            coinbase_auth.build_uri_claim("get", HOST, "/api/v3/brokerage/key_permissions"),
            "GET api.coinbase.com/api/v3/brokerage/key_permissions",
        )
        _, payload, _, _ = split(
            coinbase_auth.build_jwt(KEY_NAME, self.key, "POST", HOST, "/x/y")
        )
        self.assertEqual(payload["uri"], "POST api.coinbase.com/x/y")

    def test_query_strings_are_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            coinbase_auth.build_uri_claim("GET", HOST, PATH + "?limit=5")

    def test_signature_is_raw_r_s_and_verifies(self):
        token = self.token()
        _, _, sig, signing_input = split(token)
        self.assertEqual(len(sig), 64)  # JWS ES256: r||s, not DER
        r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
        self.key.public_key().verify(
            encode_dss_signature(r, s), signing_input.encode(), ec.ECDSA(hashes.SHA256())
        )

    def test_tampering_or_wrong_key_fails_verification(self):
        token = self.token()
        _, _, sig, signing_input = split(token)
        der = encode_dss_signature(
            int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
        )
        with self.assertRaises(InvalidSignature):
            self.key.public_key().verify(
                der, (signing_input + "x").encode(), ec.ECDSA(hashes.SHA256())
            )
        other = ec.generate_private_key(ec.SECP256R1()).public_key()
        with self.assertRaises(InvalidSignature):
            other.verify(der, signing_input.encode(), ec.ECDSA(hashes.SHA256()))

    def test_fresh_nonce_and_token_per_request(self):
        a, b = self.token(), self.token()
        self.assertNotEqual(split(a)[0]["nonce"], split(b)[0]["nonce"])
        self.assertNotEqual(a, b)

    @unittest.skipIf(pyjwt is None, "PyJWT not installed")
    def test_independent_library_accepts_the_token(self):
        public_pem = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        claims = pyjwt.decode(
            self.token(),
            public_pem,
            algorithms=["ES256"],
            issuer="cdp",
            options={"verify_aud": False},
        )
        self.assertEqual(claims["sub"], KEY_NAME)
        self.assertEqual(claims["exp"] - claims["nbf"], 120)


class TestNormalisation(unittest.TestCase):
    def setUp(self):
        self.pem = make_ec_pem()
        self.canonical = coinbase_auth.normalise_private_key(self.pem)

    def assertLoads(self, text):
        key = coinbase_auth.load_private_key(text)
        self.assertIsInstance(key, ec.EllipticCurvePrivateKey)
        self.assertEqual(coinbase_auth.normalise_private_key(text), self.canonical)

    def test_plain_multiline_pem(self):
        self.assertLoads(self.pem)

    def test_surrounding_whitespace_and_quotes(self):
        self.assertLoads(f'  "{self.pem}"  \n\n')

    def test_literal_backslash_n_as_in_the_downloaded_json(self):
        self.assertLoads(self.pem.strip().replace("\n", "\\n"))

    def test_crlf_line_endings(self):
        self.assertLoads(self.pem.replace("\n", "\r\n"))

    def test_body_flattened_onto_one_line(self):
        lines = self.pem.strip().splitlines()
        self.assertLoads(f"{lines[0]} {''.join(lines[1:-1])} {lines[-1]}")

    def test_pkcs8_label_also_works(self):
        pem = make_ec_pem(label="PKCS8")
        self.assertIn("BEGIN PRIVATE KEY", pem)
        self.assertIsInstance(coinbase_auth.load_private_key(pem), ec.EllipticCurvePrivateKey)
        self.assertIn("BEGIN PRIVATE KEY", coinbase_auth.normalise_private_key(pem))

    def test_output_is_wrapped_pem_with_markers(self):
        lines = self.canonical.splitlines()
        self.assertEqual(lines[0], "-----BEGIN EC PRIVATE KEY-----")
        self.assertEqual(lines[-1], "-----END EC PRIVATE KEY-----")
        self.assertTrue(all(len(line) <= 64 for line in lines[1:-1]))

    def test_rejections_are_specific_and_never_echo_the_input(self):
        body = "".join(self.pem.strip().splitlines()[1:-1])
        cases = {
            "": "empty",
            body: "BEGIN",
            "-----BEGIN EC PRIVATE KEY-----\n-----END EC PRIVATE KEY-----": "no content",
            "-----BEGIN EC PRIVATE KEY-----\nQUJD\n-----END EC PRIVATE KEY-----": "parsed",
            make_ed25519_pem(): "Ed25519",
        }
        for text, expect in cases.items():
            with self.subTest(expect=expect):
                with self.assertRaises(CoinbaseCredentialError) as cm:
                    coinbase_auth.load_private_key(text)
                self.assertIn(expect, str(cm.exception))
                self.assertNotIn(body[:30], str(cm.exception))

    def test_wrong_curve_is_rejected(self):
        key = ec.generate_private_key(ec.SECP384R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode()
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.load_private_key(pem)
        self.assertIn("P-256", str(cm.exception))

    def test_encrypted_key_is_rejected(self):
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"pw"),
        ).decode()
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.load_private_key(pem)
        self.assertIn("passphrase", str(cm.exception))


class TestKeyName(unittest.TestCase):
    def test_accepts_documented_format(self):
        self.assertEqual(coinbase_auth.validate_key_name(f"  {KEY_NAME}\n"), KEY_NAME)

    def test_rejects_other_shapes(self):
        for bad in ("", "a1b2c3d4e5f6", "organizations/x", "organizations/x/apiKeys/",
                    "organizations/x/apiKeys/y/z", "keys/abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(CoinbaseCredentialError):
                    coinbase_auth.validate_key_name(bad)

    def test_legacy_error_mentions_retirement(self):
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.validate_key_name("abcdef123456")
        self.assertIn("retired", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
