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
from cryptography.hazmat.primitives.asymmetric import ec, ed25519  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: E402
    encode_dss_signature,
)

import coinbase_auth  # noqa: E402
from coinbase_auth import CoinbaseCredentialError  # noqa: E402
from helpers_coinbase import (  # noqa: E402
    KEY_NAME,
    make_ec_pem,
    make_ed25519_pem,
    make_ed25519_secret,
)

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
    return (
        json.loads(b64d(head)),
        json.loads(b64d(payload)),
        b64d(sig),
        f"{head}.{payload}",
    )


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
            coinbase_auth.build_uri_claim(
                "get", HOST, "/api/v3/brokerage/key_permissions"
            ),
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
            encode_dss_signature(r, s),
            signing_input.encode(),
            ec.ECDSA(hashes.SHA256()),
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
        self.assertIsInstance(
            coinbase_auth.load_private_key(pem), ec.EllipticCurvePrivateKey
        )
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
            "not a key": "not one Coinbase issues",
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


def raw_public(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


class TestEd25519Keys(unittest.TestCase):
    """Ed25519, the CDP portal's default: one line of base64, seed || public key."""

    def setUp(self):
        self.secret = make_ed25519_secret()
        self.key = coinbase_auth.load_private_key(self.secret)

    def token(self, key=None, **kw):
        return coinbase_auth.build_jwt(
            KEY_NAME, key or self.key, "GET", HOST, PATH, **kw
        )

    def test_the_base64_secret_coinbase_issues_loads(self):
        raw = base64.b64decode(self.secret)
        self.assertEqual(len(raw), 64)
        self.assertIsInstance(self.key, ed25519.Ed25519PrivateKey)
        self.assertEqual(raw_public(self.key), raw[32:])

    def test_a_bare_32_byte_seed_is_rejected(self):
        # Coinbase issues seed || public key; a bare seed (e.g. a Robinhood key
        # pasted into the wrong box) cannot be checked, so it is refused here
        seed = make_ed25519_secret(seed_only=True)
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.load_private_key(seed)
        self.assertIn("not one Coinbase issues", str(cm.exception))
        self.assertNotIn(seed[:20], str(cm.exception))

    def test_an_ec_key_without_its_pem_lines_is_named_as_such(self):
        for label in ("EC", "PKCS8"):
            body = "".join(make_ec_pem(label=label).strip().splitlines()[1:-1])
            with self.subTest(label=label):
                with self.assertRaises(CoinbaseCredentialError) as cm:
                    coinbase_auth.load_private_key(body)
                self.assertIn("ECDSA key without its", str(cm.exception))
                self.assertNotIn(body[:20], str(cm.exception))

    def test_other_key_types_without_pem_lines_are_not_called_ecdsa(self):
        from cryptography.hazmat.primitives.asymmetric import rsa

        for key in (
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            ed25519.Ed25519PrivateKey.generate(),
        ):
            der = key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            body = base64.b64encode(der).decode()
            with self.subTest(key=type(key).__name__):
                with self.assertRaises(CoinbaseCredentialError) as cm:
                    coinbase_auth.load_private_key(body)
                self.assertIn("not one Coinbase issues", str(cm.exception))
                self.assertNotIn("ECDSA key without its", str(cm.exception))

    def test_pasting_quirks_are_tolerated_and_normalised(self):
        s = self.secret
        for label, text in (
            ("whitespace", f"  {s}\n\n"),
            ("quotes", f'"{s}"'),
            ("line break", f"{s[:40]}\n{s[40:]}"),
            ("literal \\n", f"{s}\\n"),
            ("no padding", s.rstrip("=")),
            ("url-safe", s.replace("+", "-").replace("/", "_")),
        ):
            with self.subTest(label):
                key = coinbase_auth.load_private_key(text)
                self.assertEqual(raw_public(key), raw_public(self.key))
                self.assertEqual(coinbase_auth.normalise_private_key(text), s)

    def test_damaged_key_is_rejected_without_echo(self):
        raw = bytearray(base64.b64decode(self.secret))
        raw[40] ^= 1  # a flipped bit in the public half
        damaged = base64.b64encode(bytes(raw)).decode()
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.load_private_key(damaged)
        self.assertIn("halves do not match", str(cm.exception))
        self.assertNotIn(damaged[:20], str(cm.exception))

    def test_wrong_length_is_rejected_without_echo(self):
        for n in (16, 48, 63, 65, 121):
            text = base64.b64encode(os.urandom(n)).decode()
            with self.subTest(bytes=n):
                for call in (
                    coinbase_auth.load_private_key,
                    coinbase_auth.normalise_private_key,
                ):
                    with self.assertRaises(CoinbaseCredentialError) as cm:
                        call(text)
                    self.assertIn("not one Coinbase issues", str(cm.exception))
                    self.assertNotIn(text[:20], str(cm.exception))

    def test_an_ed25519_key_in_pkcs8_pem_also_loads(self):
        key = coinbase_auth.load_private_key(make_ed25519_pem())
        self.assertIsInstance(key, ed25519.Ed25519PrivateKey)

    def test_header_and_claims(self):
        header, payload, _, _ = split(self.token(now=1_700_000_000, nonce="abc"))
        self.assertEqual(
            header, {"alg": "EdDSA", "typ": "JWT", "kid": KEY_NAME, "nonce": "abc"}
        )
        self.assertEqual(
            payload,
            {
                "sub": KEY_NAME,
                "iss": "cdp",
                "nbf": 1_700_000_000,
                "exp": 1_700_000_120,
                "uri": f"GET {HOST}{PATH}",
            },
        )

    def test_signature_is_raw_ed25519_and_verifies(self):
        _, _, sig, signing_input = split(self.token())
        self.assertEqual(len(sig), 64)
        self.key.public_key().verify(sig, signing_input.encode())

    def test_tampering_or_wrong_key_fails_verification(self):
        _, _, sig, signing_input = split(self.token())
        with self.assertRaises(InvalidSignature):
            self.key.public_key().verify(sig, (signing_input + "x").encode())
        other = ed25519.Ed25519PrivateKey.generate().public_key()
        with self.assertRaises(InvalidSignature):
            other.verify(sig, signing_input.encode())

    def test_fresh_nonce_and_token_per_request(self):
        a, b = self.token(), self.token()
        self.assertNotEqual(split(a)[0]["nonce"], split(b)[0]["nonce"])
        self.assertNotEqual(a, b)

    def test_ecdsa_keys_still_sign_es256(self):
        key = coinbase_auth.load_private_key(make_ec_pem())
        self.assertEqual(split(self.token(key=key))[0]["alg"], "ES256")

    def test_unsupported_key_objects_are_refused(self):
        with self.assertRaises(TypeError):
            coinbase_auth.jwt_algorithm("not a key")

    @unittest.skipIf(pyjwt is None, "PyJWT not installed")
    def test_independent_library_accepts_the_token(self):
        public_pem = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        claims = pyjwt.decode(
            self.token(),
            public_pem,
            algorithms=["EdDSA"],
            issuer="cdp",
            options={"verify_aud": False},
        )
        self.assertEqual(claims["sub"], KEY_NAME)
        self.assertEqual(claims["exp"] - claims["nbf"], 120)


class TestKeyName(unittest.TestCase):
    def test_accepts_documented_format(self):
        self.assertEqual(coinbase_auth.validate_key_name(f"  {KEY_NAME}\n"), KEY_NAME)

    def test_accepts_a_bare_uuid_key_id_and_signs_with_it(self):
        key_id = "d2efa49a-369c-43d7-a60e-ae26e28853c2"
        self.assertEqual(coinbase_auth.validate_key_name(f" {key_id} "), key_id)
        key = coinbase_auth.load_private_key(make_ed25519_secret())
        header, payload, _, _ = split(
            coinbase_auth.build_jwt(key_id, key, "GET", HOST, PATH)
        )
        self.assertEqual((header["kid"], payload["sub"]), (key_id, key_id))

    def test_uuid_lookalikes_are_refused(self):
        for bad in (
            "d2efa49a-369c-43d7-a60e-ae26e28853c",  # one short
            "d2efa49a369c43d7a60eae26e28853c2",  # no dashes (a Pro-style key)
            "g2efa49a-369c-43d7-a60e-ae26e28853c2",  # not hex
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(CoinbaseCredentialError):
                    coinbase_auth.validate_key_name(bad)

    def test_rejects_other_shapes(self):
        for bad in (
            "",
            "a1b2c3d4e5f6",
            "organizations/x",
            "organizations/x/apiKeys/",
            "organizations/x/apiKeys/y/z",
            "keys/abc",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(CoinbaseCredentialError):
                    coinbase_auth.validate_key_name(bad)

    def test_legacy_error_mentions_retirement(self):
        with self.assertRaises(CoinbaseCredentialError) as cm:
            coinbase_auth.validate_key_name("abcdef123456")
        self.assertIn("retired", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
