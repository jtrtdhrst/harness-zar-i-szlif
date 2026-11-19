"""Positive and negative tests for root-owned, credential-isolated socket broker."""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import unittest

import harness_coolify_readonly_mcp_layout as layout

class BrokerLayoutTests(unittest.TestCase):
    def fixture(self, base):
        root = base / "package"
        entry = root / layout.ENTRY
        entry.parent.mkdir(parents=True)
        entry.write_bytes(b"harmless pinned module")
        wrapper = base / "wrapper.sh"
        unix_socket = base / "agent.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.bind(str(unix_socket))
        unix_socket.chmod(0o600)
        unit = base / "broker.service"
        wrapper.write_text(
            "#!/bin/bash\nCOOLIFY_MCP_REQUIRE_HUMAN='on'\n"
            'TOKEN_FILE="$CREDENTIALS_DIRECTORY/readonly"\n'
            f"exec /usr/bin/node {entry}\n")
        wrapper.chmod(0o755)
        unit.write_text(
            "[Service]\nUser=multica-zar\nGroup=multica-zar\n"
            "NoNewPrivileges=yes\nProtectSystem=strict\n"
            "CapabilityBoundingSet=\nUMask=0077\n"
            "LoadCredential=readonly:/tmp/fixture-not-read\n"
            f"ExecStart=/usr/bin/socat UNIX-LISTEN:{unix_socket},fork,unlink-early,mode=0600 EXEC:{wrapper}\n")
        return dict(root=root, wrapper=wrapper, unit=unit,
                    socket_path=unix_socket,
                    expected_sha=hashlib.sha256(entry.read_bytes()).hexdigest(),
                    owner=os.getuid(), socket_owner=os.getuid()), entry

    def test_exact_layout_and_invariants(self):
        with tempfile.TemporaryDirectory() as temp:
            opts, entry = self.fixture(Path(temp))
            self.assertEqual(layout.verify_layout(**opts)["status"], "PASS")
            entry.write_bytes(b"changed")
            with self.assertRaisesRegex(layout.LayoutError, "package_entry_digest_drift"):
                layout.verify_layout(**opts)
            entry.write_bytes(b"harmless pinned module")
            opts["socket_path"].chmod(0o666)
            with self.assertRaisesRegex(layout.LayoutError, "unsafe_agent_socket_mode"):
                layout.verify_layout(**opts)
            opts["socket_path"].chmod(0o600)
            opts["unit"].write_text(opts["unit"].read_text().replace(
                "LoadCredential=readonly:", "LoadCredential=wrong:"))
            with self.assertRaisesRegex(layout.LayoutError, "systemd_socket_or_sandbox_wiring_drift"):
                layout.verify_layout(**opts)

    def test_symlink_escape_and_unsafe_wrapper(self):
        with tempfile.TemporaryDirectory() as temp:
            opts, _ = self.fixture(Path(temp))
            (opts["root"] / "escape").symlink_to("/etc/passwd")
            with self.assertRaisesRegex(layout.LayoutError, "package_symlink_escape"):
                layout.verify_layout(**opts)
            (opts["root"] / "escape").unlink()
            opts["wrapper"].chmod(0o777)
            with self.assertRaisesRegex(layout.LayoutError, "writable_by_other_actor"):
                layout.verify_layout(**opts)

if __name__ == "__main__":
    unittest.main()
