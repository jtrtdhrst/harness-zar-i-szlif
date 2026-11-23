"""Positive and negative tests for fail-closed OCI reference validation."""
import unittest
import verify_owned_image_digests as guard

class ImageDigestGuardTests(unittest.TestCase):
    def test_accept_exact_immutable_image(self):
        self.assertTrue(guard.validate_ref("ghcr.io/org/image@sha256:" + "a"*64))
        self.assertTrue(guard.validate_ref("registry.example/x:v3@sha256:" + "0"*64))

    def test_reject_mutable_ambiguous_and_missing(self):
        for ref in ("registry:latest", "local/runtime:HEAD", "",
                    "ghcr.io/x@sha256:abc", "sha256:" + "a"*64,
                    "ghcr.io/x@sha256:" + "a"*64 + "\n",
                    "ghcr.io/x@sha256:" + "G"*64):
            with self.subTest(ref=ref):
                self.assertFalse(guard.validate_ref(ref))
        self.assertFalse(guard.validate_ref(None))

    def test_real_registry_requires_unresolved_variables(self):
        errors = guard.check(["opik-mcp"], env={})
        self.assertTrue(any("PINNED_IMAGE_OPIK_MCP" in x for x in errors))
        self.assertTrue(any("unknown resource" in x
                            for x in guard.check(["does-not-exist"], env={})))

if __name__ == "__main__":
    unittest.main()
