"""Fail-closed structural inventory of all Harness Coolify build roots.

This is only a source-layout assertion, not image build / release proof.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "ops" / "service-build-roots.json"
# Fail closed on local Docker COPY/ADD instructions escaping the build context.
# A literal "\\s" in this pattern would silently disable the guard.
PARENT_CONTEXT_COPY_RE = re.compile(r"(?im)^\s*(?:ADD|COPY)\s+[^\n]*\.\./")

class HarnessBuildRootsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.rows = cls.data["resources"]

    def test_exactly_15_in_repo_build_root_resources(self):
        self.assertEqual(self.data["schema_version"], 1)
        self.assertEqual(self.data["repo"], "jtrtdhrst/harness-zar-i-szlif")
        self.assertEqual(len(self.rows), 15)
        self.assertEqual(len({r["id"] for r in self.rows}), 15)
        self.assertEqual(len({r["uuid"] for r in self.rows}), 15)

    def test_every_source_root_is_non_root_and_explicit(self):
        for r in self.rows:
            with self.subTest(service=r["id"]):
                self.assertRegex(r["uuid"], r"^[a-z0-9]{24}$")
                path = r["source_root"]
                self.assertNotIn(path, ("", ".", "/"))
                self.assertNotIn("..", Path(path).parts)
                self.assertFalse(Path(path).is_absolute())
                self.assertTrue(path.strip())
                self.assertTrue(r.get("source_build_ready") is True or r.get("source_build_ready") is False)
                if not r["source_build_ready"]:
                    self.assertGreater(len(r.get("reason", "")), 30)

    def test_ready_dockerfiles_exist_inside_owned_context(self):
        ready = [r for r in self.rows if r["source_build_ready"]]
        self.assertGreaterEqual(len(ready), 10)
        for r in ready:
            with self.subTest(service=r["id"]):
                folder = (ROOT / r["source_root"]).resolve()
                dockerfile = (ROOT / r["build_dockerfile"]).resolve()
                self.assertTrue(folder.is_dir())
                self.assertTrue(dockerfile.is_file())
                self.assertTrue(dockerfile.is_relative_to(folder))
                source = dockerfile.read_text(encoding="utf-8")
                self.assertNotRegex(source, PARENT_CONTEXT_COPY_RE)

    def test_parent_context_guard_rejects_real_dockerfile_syntax(self):
        for offending in (
            "COPY ../private.env /app/private.env",
            "   ADD  ../state /state",
            'COPY ["../outside", "/app/outside"]',
            "COPY --chown=1000:1000 ../internal /app/internal",
        ):
            with self.subTest(instruction=offending):
                self.assertRegex(offending, PARENT_CONTEXT_COPY_RE)
        for safe in (
            "COPY --from=builder /app/dist ./dist",
            "COPY src ./src",
            "ADD assets /app/assets",
        ):
            with self.subTest(instruction=safe):
                self.assertNotRegex(safe, PARENT_CONTEXT_COPY_RE)

    def test_exact_fourteen_source_ready_and_unreleased_coolify(self):
        approved = {
            "github-ops-mcp", "hermes-gateway", "multica-mcp",
            "repowise-deployment-publisher-staging", "emailens-mcp",
            "plasmic-mcp", "supabase-mcp", "ubuntu-mcp",
            "mantic-mcp", "playwright-mcp", "comfy-mcp",
            "coolify-mcp", "hindsight-mcp", "opik-mcp",
        }
        ready = {row["id"] for row in self.rows if row["source_build_ready"]}
        self.assertEqual(ready, approved)
        coolify = next(row for row in self.rows if row["id"] == "coolify-mcp")
        self.assertEqual(coolify["source_root"], "mcp/coolify-mcp")
        self.assertEqual(coolify["build_dockerfile"], "mcp/coolify-mcp/Dockerfile")
        # PR #221 source is now in main; production release parity remains unverified.
        self.assertTrue(coolify["source_build_ready"])

    def test_staging_compose_has_owned_context_without_mount_drift(self):
        """A safe staged migration never silently changes active Compose or host mounts."""
        folder = ROOT / "ops" / "repowise"
        active = (folder / "compose.publisher.coolify.yaml").read_text(encoding="utf-8")
        owned = (folder / "compose.publisher.owned.yaml").read_text(encoding="utf-8")
        self.assertIn("      context: ./ops/repowise", active.splitlines())
        self.assertIn("      context: .", owned.splitlines())
        self.assertNotIn("context: ./ops/repowise", owned)
        self.assertIn("      dockerfile: Dockerfile.publisher", owned)
        self.assertIn("base_directory=/ops/repowise", owned)
        self.assertIn("docker_compose_location=/compose.publisher.owned.yaml", owned)
        # The only Compose configuration difference is the relative build
        # context. This prevents unnoticed data/volume/auth changes at cutover.
        def non_comment_lines(text):
            return [line for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(non_comment_lines(owned),
                         non_comment_lines(active.replace(
                             "      context: ./ops/repowise", "      context: .")))
        self.assertTrue((folder / "Dockerfile.publisher").is_file())

    def test_missing_or_external_sources_are_never_marked_as_ready(self):
        for service in ("plasmic",):
            row = next(r for r in self.rows if r["id"] == service)
            self.assertFalse(row["source_build_ready"], service)
        self.assertTrue(next(r for r in self.rows if r["id"] == "github-ops-mcp")["source_build_ready"])
        self.assertTrue(next(r for r in self.rows if r["id"] == "multica-mcp")["source_build_ready"])

LIVE_COOLIFY_UUIDS = {
    "t09dqe2eppn2eiqmhzlf8xzp", "o968ndolpcfecgswerjjeg6j",
    "sf67p2qio3qf31dwvkp5gcfw", "2sganhxhhnioiqh4an9g2f4k",
    "g0xdkztpmjnhgwms7qelzxqd", "5o4edyfjo0wftfg08mtkknir",
    "oea9obpkhzbgkmipxwqmz2hj", "gl8bvfjtw2af8hkox4mguzzr",
    "cs847jiwtuq5rlm8ntjeohgf", "e8rnh91jkim7cladg7lqdmfu",
    "xevk2uwgf7lgbnflyvwkaoqp", "z4ikllc2j5zvhjr2tyloovmg",
    "k0vwdsjazxguvgmh4qixjgxn", "mzmlcorgkfgdy44hqfmmtxgw",
    "hjda7ckq5z4luhd1vpdepi0r", "aglen8ervlo2lpi30oz8iii9",
    "s7a4rwqbij7w4fxlnauriblo", "8byf8qjxdixpwp7lsnr8zpto",
    "r2gnunvpkqwmuew1tupbf7lx", "egasedqaofxnzcqppuxi805h",
    "16qnapdkj0qqqmeokepdechk", "a6ci2beifbinzckfnneiqnjd",
    "f7smgdueq8frlex9lfhp9iji", "a4zgmthjspz8hwvyu6llr8dh",
    "tjit4c8m0kjh8brkmdhyvkde", "eciprwgeyol4znmdd0dpu3xc",
    "kkhfw0napmeaqewgdirwhc1h", "26aqp0flyvdinjn6dklxnb1c",
    "lcnjb3vreec7saihkhan6akh", "hdn0rl4wznbvaoizna61bbyy",
    "3byzyvjxsycixyzcpxbujzev", "ra0iy2xs7abgms1r0phx4iqg",
    "g16yynrbdpkab4hnmaoj7vxk", "bioufw4uxwuhmr51ueyahf0u",
    "9e4fzsodixl4qzzap4zg0ntp", "6ihjnudsifbcvklz5hqxdldc",
    "vwe5lv4bniosxug34uhyf0ag", "lecwi3emh9hjxir7gphmalie",
}
PIN_RE = re.compile(r"^[^@\s]+@sha256:[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")


def inventory_errors(data, registry, root):
    errors = []
    inventory = data.get("coolify_inventory", {})
    entries = inventory.get("resources", [])
    ids = [row.get("uuid") for row in entries]
    expected = {row["uuid"]: row for row in registry["resources"]}
    source_roots = {row["uuid"]: row for row in data.get("resources", [])}
    if len(entries) != 38 or len(set(ids)) != 38 or set(ids) != LIVE_COOLIFY_UUIDS:
        errors.append("live_uuid_coverage_mismatch")
    if set(ids) != set(expected):
        errors.append("registry_uuid_coverage_mismatch")
    for row in entries:
        reference = expected.get(row.get("uuid"))
        if not reference:
            continue
        for field in ("name", "type", "source"):
            if row.get(field) != reference.get(field):
                errors.append("registry_metadata_mismatch:" + str(row.get("uuid")))
        kind = row.get("provenance_kind")
        roots_row = source_roots.get(row.get("uuid"))
        if kind != "owned-source" and row.get("source_root"):
            errors.append("non_owned_source_root_forbidden:" + row["uuid"])
        if kind != "owned-source" and row.get("source_build_ready") is not False:
            errors.append("non_owned_source_must_not_build:" + row["uuid"])
        if kind == "owned-source":
            if reference["source"] not in {"owned-code", "non-mcp-custom-code"}:
                errors.append("owned_source_misclassified:" + row["uuid"])
            if not roots_row:
                errors.append("owned_source_missing_build_root:" + row["uuid"])
                continue
            for field in ("source_root", "build_dockerfile", "source_build_ready"):
                if row.get(field) != roots_row.get(field):
                    errors.append("owned_source_manifest_mismatch:" + row["uuid"])
                    break
            source_root = (root / roots_row["source_root"]).resolve()
            dockerfile = (root / roots_row["build_dockerfile"]).resolve()
            if not source_root.is_dir():
                errors.append("owned_source_root_missing:" + row["uuid"])
            if not dockerfile.is_file() or not dockerfile.is_relative_to(source_root):
                errors.append("owned_source_dockerfile_missing_or_outside_root:" + row["uuid"])
        elif kind == "vendor-image":
            pins = row.get("pinned_images", [])
            configured = set(row.get("configured_images", []))
            pinned_config = {x.get("configured_ref") for x in pins}
            if reference["source"] != "vendor-image" or row.get("source_build_ready") is not False:
                errors.append("vendor_image_misclassified:" + row["uuid"])
            if (not pins or configured != pinned_config or
                    any(not PIN_RE.fullmatch(x.get("pinned_ref", "")) for x in pins)):
                errors.append("vendor_image_missing_digest_pin:" + row["uuid"])
        elif kind == "upstream-pinned":
            if (reference["source"] != "upstream-git" or
                    not row.get("source_repository") or
                    not COMMIT_RE.fullmatch(row.get("source_commit", ""))):
                errors.append("upstream_source_missing_exact_commit:" + row["uuid"])
        elif kind == "external-repo-pin":
            if (reference["source"] != "other-repository" or
                    not row.get("source_repository") or
                    not COMMIT_RE.fullmatch(row.get("source_commit", ""))):
                errors.append("external_repo_missing_exact_commit:" + row["uuid"])
        elif kind == "unknown-local-image":
            if (reference["source"] != "local-image-unknown-source" or
                    row.get("source_build_ready") is not False or
                    row.get("release_eligible") is not False or
                    row.get("source_root") or row.get("build_dockerfile")):
                errors.append("unknown_local_image_must_not_build_or_release:" + row["uuid"])
        elif kind == "owned-image-pin":
            pins = row.get("pinned_images", [])
            origin = row.get("origin_root")
            configured = set(row.get("configured_images", []))
            pinned_config = {x.get("configured_ref") for x in pins}
            if (reference["source"] != "owned-image" or not origin or
                    not (root / origin).is_dir() or not pins or configured != pinned_config or
                    any(not PIN_RE.fullmatch(x.get("pinned_ref", "")) for x in pins)):
                errors.append("owned_image_missing_verified_origin_or_digest:" + row["uuid"])
        else:
            errors.append("unknown_provenance_kind:" + str(row.get("uuid")))
        if row.get("release_eligible") is not False:
            errors.append("inventory_release_not_authorized:" + row["uuid"])
    return errors


class FullCoolifyInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "ops" / "coolify-service-registry.json").read_text(encoding="utf-8"))

    def test_all_38_live_application_and_service_uuids_are_classified(self):
        rows = self.data["coolify_inventory"]["resources"]
        self.assertEqual(len(rows), 38)
        self.assertEqual(len({row["uuid"] for row in rows}), 38)
        self.assertEqual({row["uuid"] for row in rows}, LIVE_COOLIFY_UUIDS)
        self.assertEqual(sum(row["type"] == "application" for row in rows), 13)
        self.assertEqual(sum(row["type"] == "service" for row in rows), 25)
        self.assertEqual(inventory_errors(self.data, self.registry, ROOT), [])

    def test_missing_uuid_fails_closed(self):
        broken = json.loads(json.dumps(self.data))
        broken["coolify_inventory"]["resources"].pop()
        self.assertIn("live_uuid_coverage_mismatch", inventory_errors(broken, self.registry, ROOT))

    def test_owned_source_without_existing_root_or_dockerfile_fails_closed(self):
        broken = json.loads(json.dumps(self.data))
        owned = next(row for row in broken["coolify_inventory"]["resources"]
                     if row["provenance_kind"] == "owned-source")
        owned["source_root"] = "missing-owned-root"
        source_row = next(row for row in broken["resources"] if row["uuid"] == owned["uuid"])
        source_row["source_root"] = "missing-owned-root"
        source_row["build_dockerfile"] = "missing-owned-root/Dockerfile"
        errors = inventory_errors(broken, self.registry, ROOT)
        self.assertTrue(any(error.startswith("owned_source_root_missing:") for error in errors))
        self.assertTrue(any(error.startswith("owned_source_dockerfile_missing_or_outside_root:")
                            for error in errors))

    def test_vendor_image_without_digest_pin_fails_closed(self):
        broken = json.loads(json.dumps(self.data))
        vendor = next(row for row in broken["coolify_inventory"]["resources"]
                      if row["provenance_kind"] == "vendor-image")
        vendor["pinned_images"] = []
        self.assertTrue(any(error.startswith("vendor_image_missing_digest_pin:")
                            for error in inventory_errors(broken, self.registry, ROOT)))

    def test_unknown_local_image_cannot_be_build_ready_or_release_eligible(self):
        broken = json.loads(json.dumps(self.data))
        unknown = next(row for row in broken["coolify_inventory"]["resources"]
                       if row["provenance_kind"] == "unknown-local-image")
        unknown["source_build_ready"] = True
        unknown["release_eligible"] = True
        self.assertTrue(any(error.startswith("unknown_local_image_must_not_build_or_release:")
                            for error in inventory_errors(broken, self.registry, ROOT)))


if __name__ == "__main__":
    unittest.main()
