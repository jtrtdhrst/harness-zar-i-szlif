"""Make the pinned Hermes plugin-loader concurrent-wait bound operator-tunable at build time.

Pinned source: ``plugins/plugin_loader.py`` from ``nousresearch/hermes-agent`` v0.22.5
(file sha256 ``b4d4e730df8d8163e45d4fb9dd305f61a1c6fb724ed4c3c7768eac880abba320``,
12129 bytes). The Dockerfile pins the base image by manifest digest, so this anchor
cannot drift silently; if it does, the build fails closed instead of patching unknown code.

What this changes, and what it does not
---------------------------------------
v0.22.5 hardcodes ``_CONCURRENT_LOAD_WAIT_SECS = 10.0``. Inside ``bounded_load_wait()``
a caller that must not stall on another thread's in-flight plugin import gives up after
that many seconds, marks the module stalled and returns ``None`` with the warning
``Skipping plugin <name>: another thread's load of it has not finished (import still
running after 10s)``. On a CPU-starved host the first import of a large plugin exceeds
the bound and every concurrent per-turn caller skips that plugin.

This patch only makes the bound readable from ``HERMES_PLUGIN_CONCURRENT_LOAD_WAIT_SECS``.
The default is unchanged (10.0) and any unusable value (non-numeric, non-finite, <= 0)
falls back to it, so merging the patch changes no behaviour; only an explicit operator
env change does. It does not fix host load, container-boot profile reconciliation, MCP
handshake stalls, or the state-db migration lease — those are separate causes.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

TARGET = Path("/opt/hermes/plugins/plugin_loader.py")
EXPECTED_SHA256 = "b4d4e730df8d8163e45d4fb9dd305f61a1c6fb724ed4c3c7768eac880abba320"
ENV_VAR = "HERMES_PLUGIN_CONCURRENT_LOAD_WAIT_SECS"
DEFAULT_SECS = 10.0

_IMPORT_ANCHOR = "import logging\n"
_CONST_ANCHOR = "_CONCURRENT_LOAD_WAIT_SECS = 10.0\n"

_HELPER = '''def _env_seconds(name: str, default: float) -> float:
    """Operator-tunable positive seconds bound; any unusable value keeps the pinned default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        _log.warning("Ignoring non-numeric %s=%r; keeping %.1fs", name, raw, default)
        return default
    if not math.isfinite(value) or value <= 0:
        _log.warning("Ignoring out-of-range %s=%r; keeping %.1fs", name, raw, default)
        return default
    return value


'''


def patch_source(original: str) -> str:
    """Return patched source; raise RuntimeError if the pinned anchors are not exact."""
    code = original

    def once(old: str, new: str) -> None:
        nonlocal code
        count = code.count(old)
        if count != 1:
            raise RuntimeError(f"Pinned Hermes source drift: anchor count {count}")
        code = code.replace(old, new, 1)

    once(_IMPORT_ANCHOR, _IMPORT_ANCHOR + "import math\nimport os\n")
    once(
        _CONST_ANCHOR,
        _HELPER
        + f"_CONCURRENT_LOAD_WAIT_SECS = _env_seconds({ENV_VAR!r}, {DEFAULT_SECS!r})\n",
    )

    ast.parse(code)
    if f"_CONCURRENT_LOAD_WAIT_SECS = {DEFAULT_SECS!r}\n" in code:
        raise RuntimeError("Pinned hardcoded plugin load bound still present")
    if f'_env_seconds({ENV_VAR!r}' not in code:
        raise RuntimeError("Plugin load bound was not made configurable")
    return code


def main() -> None:
    original = TARGET.read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED_SHA256:
        raise SystemExit("Pinned Hermes plugin loader checksum mismatch; bound not patched")
    TARGET.write_text(patch_source(original.decode("utf-8")), encoding="utf-8")
    print(
        "Hermes plugin loader bound installed: "
        f"{ENV_VAR} overrides the {DEFAULT_SECS}s default"
    )


if __name__ == "__main__":
    main()
