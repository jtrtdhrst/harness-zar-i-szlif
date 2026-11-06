# ArkCodexImageGen gpt-image-2.5 compatibility patch

This reproducible patch is based on `Hishamahmer/comfyui-arkennemasis` commit
`9fea8c02d6937189f31fab4bf85744e8e38a39c5`. Its upstream
`codex_provider/nodes.py` SHA-256 is
`07fb23a93a30c2197953df4811853b7d0a9d7b08fe812347fd58ec89696fee7c`.

It preserves the installed `gpt-image-2.5` image model as a one-line overlay and
removes `reasoning.effort=low` only from the `ArkCodexImageGen` Responses payload.
The LLM route and model selection are untouched. Check and test with:

```sh
python3 comfyui-mcp/tests/test_arkennemasis_image_reasoning_patch.py /path/to/comfyui-arkennemasis
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
