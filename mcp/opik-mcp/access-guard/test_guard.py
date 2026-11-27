import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from guard import verify_assertion

class LocalKeys:
    def __init__(self, public_key):
        self.public_key = public_key
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.public_key)

class TestJwtGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pub = LocalKeys(cls.key.public_key())
        cls.issuer = "https://example.cloudflareaccess.com"
        cls.aud = "access-app-aud-only"
    def token(self, **changes):
        now = datetime.now(timezone.utc)
        c = {"iss": self.issuer, "aud": [self.aud], "iat": now,
             "exp": now + timedelta(minutes=5), "sub": "user", "email": "tester@example.test"}
        c.update(changes)
        return jwt.encode(c, self.key, algorithm="RS256")
    def test_good(self):
        self.assertTrue(verify_assertion(self.token(), self.pub, self.issuer, self.aud))
    def test_no_or_invalid_token(self):
        for t in ("", "a.b.c", "none", "x" * 20000):
            self.assertFalse(verify_assertion(t, self.pub, self.issuer, self.aud))
    def test_wrong_issuer(self):
        self.assertFalse(verify_assertion(self.token(iss="https://evil.example"), self.pub, self.issuer, self.aud))
    def test_wrong_audience(self):
        self.assertFalse(verify_assertion(self.token(aud=["not-this-app"]), self.pub, self.issuer, self.aud))
    def test_expired(self):
        self.assertFalse(verify_assertion(self.token(exp=datetime.now(timezone.utc)-timedelta(minutes=30)), self.pub, self.issuer, self.aud))
    def test_wrong_signature(self):
        evil = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        t = self.token()
        c = jwt.decode(t, options={"verify_signature":False})
        self.assertFalse(verify_assertion(jwt.encode(c, evil, algorithm="RS256"), self.pub, self.issuer, self.aud))
    def test_missing_human_identity(self):
        self.assertFalse(verify_assertion(self.token(email=""), self.pub, self.issuer, self.aud))

    def machine_token(self, client_id="machine-test-123.access", **changes):
        now = datetime.now(timezone.utc)
        claims = {
            "iss": self.issuer, "aud": [self.aud], "iat": now,
            "exp": now + timedelta(minutes=5),
            "sub": "", "service_token_id": client_id,
            "common_name": client_id,
        }
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256")

    def test_machine_denied_by_default(self):
        self.assertFalse(verify_assertion(self.machine_token(), self.pub, self.issuer, self.aud))
        self.assertFalse(verify_assertion(self.machine_token(), self.pub, self.issuer, self.aud, ""))

    def test_exact_service_token_opt_in_and_human_compatibility(self):
        expected = "machine-test-123.access"
        self.assertTrue(verify_assertion(self.machine_token(), self.pub, self.issuer, self.aud, expected))
        self.assertTrue(verify_assertion(self.token(), self.pub, self.issuer, self.aud, expected))

    def test_service_identity_must_match_both_signed_claims(self):
        expected = "machine-test-123.access"
        for kwargs in (
            {"service_token_id": "other-client.access"},
            {"common_name": "other-client.access"},
            {"service_token_id": None},
            {"common_name": None},
            {"sub": "human-user"},
            {"email": "human@example.test"},
            {"email": True},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(verify_assertion(
                    self.machine_token(**kwargs), self.pub, self.issuer, self.aud, expected
                ))
        self.assertFalse(verify_assertion(self.machine_token(), self.pub, self.issuer, self.aud, "other-client.access"))

    def test_service_jwt_signed_claims_remain_mandatory(self):
        expected = "machine-test-123.access"
        for claims in (
            {"iss": "https://wrong.cloudflareaccess.com"},
            {"aud": ["wrong-audience"]},
            {"exp": datetime.now(timezone.utc) - timedelta(minutes=30)},
            {"sub": None},
        ):
            with self.subTest(claims=claims):
                self.assertFalse(verify_assertion(
                    self.machine_token(**claims), self.pub, self.issuer, self.aud, expected
                ))
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged_claims = jwt.decode(self.machine_token(), options={"verify_signature": False})
        forged = jwt.encode(forged_claims, other_key, algorithm="RS256")
        self.assertFalse(verify_assertion(forged, self.pub, self.issuer, self.aud, expected))


if __name__ == "__main__":
    unittest.main()
