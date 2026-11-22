# ArkCodexImageGen gpt-image-2.5 compatibility patch

This reproducible patch is based on `Hishamahmer/comfyui-arkennemasis` commit
`9fea8c02d6937189f31fab4bf85744e8e38a39c5`. Its upstream
`codex_provider/nodes.py` SHA-256 is
`07fb23a93a30c2197953df4811853b7d0a9d7b08fe812347fd58ec89696fee7c`.

It preserves the installed `gpt-image-2.5` image model as a one-line overlay and
removes `reasoning.effort=low` only from the `ArkCodexImageGen` Responses payload.
The LLM route and model selection are untouched. Check and test with:

```sh
python3 comfy-mcp/tests/test_arkennemasis_image_reasoning_patch.py /path/to/comfyui-arkennemasis
```

The test requires the exact pinned commit and source-file hash, applies both
overlays to a temporary copy, asserts `IMAGE_MODEL == "gpt-image-2.5"`, and
inspects the generated image-route wire payload AST to ensure it cannot contain
a `reasoning` field or `HOST_EFFORT`. This is a source regression check; it does
not replace a real backend probe or production rollout.

The owner reported the installed volume file SHA-256 as
`5b869128443d88a7eb8f874a2a2cc6fca81269b92fdc82b50e55380497108bdf`, which is
different from the pinned upstream file above because production uses CRLF and
the reviewed model overlay; the owner verified there are no other semantic
differences. Build from the pinned source with both documented overlays; do not
hot-edit the production volume. The deployed ComfyUI image must be built from the pinned, patched
source and published with its digest, then promoted through the authorized
review/deploy path with rollback and live prompt-id/PNG readback.

## Versioned startup overlay and safe rollback (KOMAA-1599)

The candidate `comfy-mcp/Dockerfile.comfyui` copies the versioned
`patches/arkcodex_image_compat.py` into its image and invokes `apply`
before ComfyUI starts. `custom_nodes` is a separate persisted Docker
volume: a patch copied into an image alone does not reach its runtime.

The script accepts only the exact verified production original `nodes.py`
SHA256 `5b869128443d88a7eb8f874a2a2cc6fca81269b92fdc82b50e55380497108bdf`.
It removes image-only `reasoning.effort`, preserves `gpt-image-2.5`,
checks Python syntax and atomically replaces only that one volume file.
A 0600 backup of the original bytes is placed in the existing persistent
`/app/user/.arkcodex-compat/KOMAA-1599/nodes.py.original`.
Unknown digests, corrupt backups and symlinked targets fail closed.

BEFORE a production release, build from the independently approved exact
merged SHA, record the image digest and previous image, and test with a
COPY of `custom_nodes`, not a mount of the production data volume.
Prove the updated `ArkCodexImageGen` is importable in a real isolated
ComfyUI server via `/object_info`. After the versioned image is deployed
through existing Coolify service, run a minimal real image prompt and
capture the exact prompt_id, output PNG SHA and health readback.
AST/import success does not prove an authorized image render.

Rollback must restore the separately mounted plugin SOURCE before
switching back to the previous Docker image: run the image's
`arkcodex_image_compat.py rollback` against the existing volume
(from an isolated helper using the exact approved image if it cannot start),
confirm original SHA, restore the previous image through Coolify and
verify production health. Image rollback alone does not revert the volume.

Reproducible source and negative tests:

```sh
python3 comfy-mcp/tests/test_arkennemasis_image_reasoning_patch.py /path/to/pinned/upstream
python3 comfy-mcp/tests/test_arkcodex_image_compat.py /path/to/pinned/upstream
```

Both are executed by `.github/workflows/comfy-arkcodex-compat.yml`.
Do not close KOMAA-1599 before reviewed SHA, production prompt/PNG
and actual rollback + readback have passed.
