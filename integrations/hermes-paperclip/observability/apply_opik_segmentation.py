#!/usr/bin/env python3
"""Fail-closed, source-pinned Opik role segmentation for Hermes plugin copies.

Apply to a *staged* plugin tree before constructing the reviewed Gateway image.
Never patch a running container. A shared plugin fallback intentionally emits no
agent role: model identity or prompt text is not proof of an agent's identity.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

BASE_SHA256 = "b029684c8c24703013126b90527f9b43ee7593c6acdd8afa8ffa13c442738a7a"
IMPORT_ANCHOR = "import datetime\n"
META_ANCHOR = '        "source": "hermes",\n'
KWARGS_ANCHOR = '        "tags": tags(),\n'
KNOWN_ROLES = frozenset({
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer", "email-creative",
    "engineer", "harness-engineer", "lifecycle-ops", "mascot-designer",
    "mcp-engineer", "ui-qa",
})

ROLE_HELPER = '''
def _verified_role_from_plugin_path(plugin_file: str) -> str:
    """Return the only role authenticated by the selected profile plugin path.

    The expected Hermes layout is /opt/data/profiles/<role>/plugins/opik/lifecycle.py.
    A generic/shared plugin is intentionally unclassified.
    """
    parts = Path(plugin_file).parts
    for i in range(len(parts) - 4):
        if (parts[i] == "profiles"
                and parts[i + 2:i + 4] == ("plugins", "opik")
                and parts[i + 4] == "lifecycle.py"
                and parts[i + 1] in _KNOWN_OPIK_ROLES):
            return parts[i + 1]
    return ""


_KNOWN_OPIK_ROLES = frozenset(%r)

''' % (tuple(sorted(KNOWN_ROLES)),)

def transform(original: str) -> str:
    """Pure, pinned transformation; preserves existing trace create/upsert lifecycle."""
    def replace_once(s: str, old: str, new: str) -> str:
        if s.count(old) != 1:
            raise ValueError("Opik plugin anchor drift detected; refusing to patch")
        return s.replace(old, new, 1)

    code = replace_once(original, IMPORT_ANCHOR,
                        IMPORT_ANCHOR + "from pathlib import Path\n")
    code = replace_once(code, "\ndef start_root_trace(\n",
                        "\n" + ROLE_HELPER + "def start_root_trace(\n")
    code = replace_once(code, "    metadata = {\n",
                        "    role = _verified_role_from_plugin_path(__file__)\n"
                        "    metadata = {\n")
    code = replace_once(code, META_ANCHOR,
                        META_ANCHOR +
                        '        "service": "hermes-gateway",\n'
                        '        "component": "agent-turn",\n')
    code = replace_once(code, "    # Build the create payload once and keep it:",
                        '    if role:\n'
                        '        metadata["agent_role"] = role\n'
                        '        metadata["memory_bank"] = f"hermes-{role}"\n'
                        '    # Build the create payload once and keep it:')
    code = replace_once(code, KWARGS_ANCHOR,
                        '        "tags": tags() + (["agent:" + role] if role else []),\n')
    ast.parse(code)
    return code

def prepare(path: Path) -> str:
    original = path.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    if sha != BASE_SHA256:
        raise ValueError("Opik lifecycle source SHA mismatch; no changes applied")
    return transform(original.decode("utf-8"))

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lifecycle_py", type=Path)
    parser.add_argument("--check", action="store_true", help="validate only; never write")
    args = parser.parse_args()
    result = prepare(args.lifecycle_py)
    if not args.check:
        args.lifecycle_py.write_text(result, encoding="utf-8")
    print("validated source-pinned Opik role segmentation" +
          (" (no write)" if args.check else " (staged write)"))

if __name__ == "__main__":
    main()
