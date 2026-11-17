# Delivery contract — one path from commit to confirmed production

Status: as verified on 2026-11-17 against harness `main` `3c8da46902d2fd488b4bb1edc41fcf70a3c6fa6d`.
This file is the single index for the harness lane. Policy detail stays in
`docs/RELEASE-POLICY.md`; the privileged install steps stay in
`ops/harness/INSTALL-RUNBOOK.md`.

The rule behind the whole document: **one stage, one PASS condition, and a FAIL
stops the next stage.** A stage that did not run is FAIL, never "skipped".

| # | Stage | Owner | PASS condition |
|---|-------|-------|----------------|
| 1 | Code | Multica producer agent | A PR is open from a feature branch in the owning repo, built from the isolated task workspace. No direct push to `main`. |
| 2 | Tests | GitHub Actions (self-hosted `local-build`) | Both guarding checks, `validate-release-lanes` and `validate-paperclip-mcp`, report `success` on the exact PR head SHA. (Server-side branch protection is not verified: the rulesets API answers 403 on this plan, so this is process, not an unbypassable gate.) |
| 3 | Deploy | root delivery controller (`harness-image-delivery.timer`) | `delivery.json` records `source_sha` equal to the merged `main` SHA and an immutable `image_digest`; the running container's image ID equals that digest. |
| 4 | Acceptance | independent reviewer / operator | Live readback of the running container: image ID, OCI `org.opencontainers.image.revision`, Docker health, and the previous-image identifier retained for rollback. |

## 1. Code

- Branch and worktree are created by the runtime per task; agents do not create
  branches by hand.
- Delivery to a protected branch goes through a PR only. Merge is never done by
  the author.
- PASS = the PR contains exactly the intended source change and its head SHA is
  the one later reviewed and delivered.

## 2. Tests

`.github/workflows/release-lanes-policy.yml` and
`.github/workflows/paperclip-mcp-ci.yml` both run on
`[self-hosted, linux, x64, local-build]`. GitHub-hosted minutes are blocked by
account billing, so a job that "was not started because recent account payments
have failed" is a **FAIL**, never a pass and never a reason to merge.

Failure modes that must stop the pipeline:

| Symptom | Meaning |
|---|---|
| check conclusion `failure` with a billing annotation | the job never ran; the SHA is untested |
| check conclusion `failure` with `EACCES ... unlink .../.git/objects/...` | the runner workspace has root-owned files; fix ownership on the host, then re-run |
| no check run at all for the head SHA | CI was not triggered; push a new commit rather than assuming green |

Local equivalent of the same checks, for pre-push sanity (never a substitute for
the recorded check run):

```
python scripts/check-release-lanes.py --self-test
python3 -m unittest discover -s scripts -p test_non_mcp_build_guard.py -v
cd multica-mcp && npm test
```

## 3. Deploy

Every service needs three artefacts plus a manifest entry for the exact source
SHA before any Docker or Coolify mutation happens:

1. `request` — service, changed paths, PR head SHA, merge SHA and an
   independent review (`reviewer_agent_id` different from
   `producer_agent_id`, `approved_sha` equal to the PR head, reviewer role equal
   to the manifest's `reviewer_role`, `base_ref` = `main`).
2. `grant` — per Coolify UUID, naming that exact SHA, revocable. **This is what
   lifts HOLD for one cycle.** `ops/release-lanes.json` keeps
   `promotion_state: "hold"` for these services permanently; a held lane with a
   valid grant proceeds, a held lane without one denies
   `release_lane_on_hold`, and the hold is checked before any artefact.
3. `attestation` — root-signed HMAC over the test evidence, bound to the SHA and
   the image digest; produced by `harness_local_ci_attest.py` from commands in
   `/etc/paperclip-gitops/harness-ci-policy.json`.

Note: that policy currently declares tests for **`ubuntu-mcp` only**. Until a
service has an entry there, its attestation cannot be produced and the lane
cannot be admitted, no matter how good its PR is.

The timer runs every 120 s:

```
/usr/bin/python3 /usr/local/libexec/harness_native_delivery.py --mode deploy --auto \
  --artifact-dir /var/lib/harness-image-delivery/gates \
  --attestation-key /etc/paperclip-gitops/harness-attestation.key \
  --state-dir /var/lib/harness-image-delivery/delivery
```

`--auto` reads `HARNESS_BASE_SHA` / `HARNESS_SOURCE_SHA` **from the environment**
loaded by `EnvironmentFile=/var/lib/harness-image-delivery/source-range.env`.
A manual run must export the same two variables, otherwise it denies with
`auto_source_range_missing` even though the file exists.

Dry evaluation that performs zero Docker and zero Coolify calls:

```
cd /var/lib/harness-image-delivery/checkout
sudo env HARNESS_BASE_SHA=<previous-main> HARNESS_SOURCE_SHA=<main> \
  python3 /usr/local/libexec/harness_native_delivery.py --mode plan --auto \
  --artifact-dir /var/lib/harness-image-delivery/gates \
  --attestation-key /etc/paperclip-gitops/harness-attestation.key \
  --state-dir /var/lib/harness-image-delivery/delivery
```

Expected shape: `{"admitted": ["<service>"], "deployed": null, "mode": "plan"}`.

Denials verified on 2026-11-17 in plan mode, each with no mutation:

| Tampered input | Denial |
|---|---|
| missing `--attestation-key` | `attestation_key_missing` |
| altered image digest in attestation | `attestation_signature_invalid` |
| grant marked `revoked` | `grant_revoked` |
| grant naming another SHA | `grant_source_sha_mismatch` |
| no request/attestation artefacts | `request_unavailable` |
| `--auto` without the two SHA env vars | `auto_source_range_missing` |

## 4. Acceptance

Read the live system, not the pipeline's own claim:

```
docker ps --filter name=<service> --format '{{.Names}} {{.Image}} {{.Status}}'
docker inspect <image> --format '{{.Id}} | {{index .Config.Labels "org.opencontainers.image.revision"}}'
cat /var/lib/harness-image-delivery/delivery/delivery.json
```

PASS requires all of:

- the running image ID equals `delivery.json.image_digest`;
- the OCI revision label equals `delivery.json.source_sha`;
- the container reports `healthy`;
- the previous image digest is recorded, so a rollback target exists.

Observed on 2026-11-17 for `ubuntu-mcp` at `main` `3c8da469`:
image ID and `delivery.json.image_digest` both
`sha256:b0bc9a052358a95e1f8068225cf4ccfa558f7d718c94f8e6ba835e58f71ebb52`,
OCI revision `3c8da46902d2fd488b4bb1edc41fcf70a3c6fa6d`, container `healthy`.

`multica-release-status --sha <sha>` covers the product lanes (panel, host MCP,
Coolify deployment) only. A harness SHA legitimately reports
`live_anywhere: false` there; use the three commands above for harness services.

## ## What still needs a human — the honest part

**Nothing advances the checkout or the source range on its own.** No timer,
cron or service runs `git fetch`/`reset` on `/var/lib/harness-image-delivery/checkout`
or rewrites `source-range.env`; the reflog shows manual `reset --hard`. After a
merge to `main`, an operator must do both before the timer can deliver:

```
git -C /var/lib/harness-image-delivery/checkout fetch origin main
git -C /var/lib/harness-image-delivery/checkout reset --hard <merged-main-sha>
printf 'HARNESS_BASE_SHA=%s\nHARNESS_SOURCE_SHA=%s\n' <previous-delivered-sha> <merged-main-sha> \
  > /var/lib/harness-image-delivery/source-range.env
chown root:root /var/lib/harness-image-delivery/source-range.env
chmod 0600 /var/lib/harness-image-delivery/source-range.env
```

That is one deliberate manual step, by design: the controller refuses to derive
the range. Automating it is a policy decision, not a bug fix.

## Known gaps — do not paper over

1. **Runner trust.** PR checks run on the host runner with Docker access. Any
   branch can therefore execute code on the host as the runner user. Fixing this
   needs either GitHub-hosted minutes (billing) or an isolated runner; until
   then, treat every PR as privileged code (ZARI-213).
2. **Rollback restores, but does not verify.** `Transport.rollback` snapshots the
   previous Compose before the first mutation and PATCHes it back once, then
   posts `/deploy` — with no health or digest readback afterwards. The previous
   digest is recorded for audit, not proven serving. It has never been exercised
   on a real service; `docs/RELEASE-POLICY.md` still marks it NOT VERIFIED.
   PR #123 adds the missing post-restore verification.
3. **Code review is not automated.** Stage 1 → stage 2 needs a reviewer separate
   from the author; CI green never substitutes for that decision.
