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

if __name__ == "__main__":
    unittest.main()
