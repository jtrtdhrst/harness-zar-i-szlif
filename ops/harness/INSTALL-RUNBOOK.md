# Harness delivery gate — OPERATOR-ONLY installation runbook

Status: **source-side contract, not installed.** This document describes the one
privileged step that is deliberately outside agent authority: replacing the
hold-blind controller that `harness-image-delivery.timer` runs every 120 s with
the reviewed admission-gated delivery path, and pointing the unit's `ExecStart`
at it. No agent may perform any step here (no sudo, no `systemctl`, no root file
writes, no hold changes, no deploy).

Until steps 1-9 are completed and read back, the live behaviour is unchanged and
the release lane stays `BLOCKED`: the installed controller still promotes a
merged `main` SHA without consulting `ops/release-lanes.json`, the per-UUID
grant, the independent exact-SHA approval or the root-owned local-CI attestation.

## What gets installed

| source (from the exact approved SHA) | installed path | mode |
|---|---|---|
| `scripts/harness_release_admission.py` | `/usr/local/libexec/harness_release_admission.py` | `0644 root:root` |
| `scripts/harness_local_ci_attest.py` | `/usr/local/libexec/harness_local_ci_attest.py` | `0644 root:root` |
| `scripts/harness_delivery_controller.py` | `/usr/local/libexec/harness_delivery_controller.py` | `0644 root:root` |
| `scripts/harness_native_delivery.py` | `/usr/local/libexec/harness_native_delivery.py` | `0644 root:root` |
| `ops/systemd/harness-image-delivery.service` | `/etc/systemd/system/harness-image-delivery.service` | `0644 root:root` |
| operator-written source range | `/var/lib/harness-image-delivery/source-range.env` | `0600 root:root` |
| operator-authored policy | `/etc/paperclip-gitops/harness-ci-policy.json` | `0600 root:root` |
| operator-authored HMAC key | `/etc/paperclip-gitops/harness-attestation.key` | `0600 root:root` |

`harness-image-delivery.timer` is **not** replaced: the cadence (120 s, oneshot)
is unchanged. Only the service unit's `ExecStart` changes, and it must run:

```
/usr/bin/python3 /usr/local/libexec/harness_native_delivery.py --mode deploy --auto \
  --artifact-dir /var/lib/harness-image-delivery/gates \
  --attestation-key /etc/paperclip-gitops/harness-attestation.key \
  --state-dir /var/lib/harness-image-delivery/delivery
```

with `WorkingDirectory=/var/lib/harness-image-delivery/checkout`.

`scripts/harness_install_preflight.py --sha <approved-sha> --plan` prints the
same list with the immutable expected `sha256` of each module and of the unit
computed from git at that SHA, refuses to emit a plan while a precondition fails,
and reports `delivery_unit_wired` / `delivery_unit_matches_approved_sha` for the
*installed* unit: it re-parses that unit's `ExecStart` with the adapter's own
argparse, so an invocation the adapter would reject (the previous
`harness_image_delivery.py --auto` did exactly that and exited 2) can never be
reported ready.

## Why `--auto`, and what it does not do

A 120-second timer cannot know a merge SHA in advance. The adapter therefore
takes the exact pair from the unit's `EnvironmentFile`,
`/var/lib/harness-image-delivery/source-range.env` (`0600 root:root`):

```
HARNESS_BASE_SHA=<previous delivered main SHA>
HARNESS_SOURCE_SHA=<approved main SHA>
```

The operator (or the existing mechanism that advances the checkout) refreshes
that file when `main` moves. The adapter **does not reconstruct** the range: an
absent, partial or malformed file denies the cycle with `auto_source_range_missing`
or `invalid_base_sha`/`invalid_source_sha`, zero docker calls and zero Coolify
calls. There is no delivery baseline, no scheduler and no extra state store —
`--auto` only says where to read the two SHAs, and every service still needs its
own request, per-UUID grant, independent exact-SHA review and HMAC-verified
attestation bound to that exact SHA.

## Preconditions (all must be green before step 1)

- `harness-image-delivery.timer` and `harness-image-delivery.service` **inactive**
  (stopping the timer is the separately owned emergency task; coordinate, do not
  race it).
- The exact approved SHA is known and its CTO approval names that SHA.
- `/usr/local/libexec/harness_image_delivery.py` still exists and its `sha256` is
  recorded in the backup step (currently
  `3bc7234cd05139d9c3654b8976264eaf123de855a57e485435160d6745336ef5`).
- No delivery run in flight (`/var/lib/harness-image-delivery/delivery.lock`
  unheld) and no Coolify deployment running.
- `scripts/harness_install_preflight.py --sha <sha> --plan` exits 0 when its
  actual safety blockers are clear. Before installation, missing policy, key,
  runtime directory, source-range file and old unit replacement appear under
  `pending` (the plan creates or installs them). Any existing insecure file,
  running service, unauthorized principal or mismatched partially installed
  module is a hard `blocker` and suppresses the plan. After step 6, including
  source-range setup, require `ready: true` with empty `blockers` and `pending`. 
- `/var/lib/harness-image-delivery/checkout` is a clean git checkout of this
  repository that the operator advances to `main` before each cycle (or an
  existing scheduler does); `verify_source` refuses a dirty worktree or a
  foreign HEAD, so the build can only ever run on the reviewed tree.
- `/var/lib/harness-image-delivery/source-range.env` holds the exact
  `HARNESS_BASE_SHA` / `HARNESS_SOURCE_SHA` pair for the cycle to run. Without it
  the unit fails closed; it is operator input, not something this code derives.

## Steps

1. **Stop the timer and the oneshot service.**
   `systemctl stop harness-image-delivery.timer && systemctl stop harness-image-delivery.service`
   Read back `systemctl is-active` for both = `inactive`.
2. **Back up the hold-blind controller and the current unit.**
   First create the root-private backup directory:
   `install -o root -g root -m 0700 -d /var/lib/harness-image-delivery/backups`.
   Then run `install -o root -g root -m 0600 /usr/local/libexec/harness_image_delivery.py /var/lib/harness-image-delivery/backups/harness_image_delivery-<sha12>.py`
   `install -o root -g root -m 0600 /etc/systemd/system/harness-image-delivery.service /var/lib/harness-image-delivery/backups/harness-image-delivery.service-<sha12>.bak`
   `sha256sum` every file and record the digests in the issue.
3. **Stage the four reviewed modules** from the exact SHA, not from a branch head:
   `git -C <approved checkout> show <sha>:scripts/<module> | install -o root -g root -m 0644 /dev/stdin /usr/local/libexec/<module>`
4. **Verify the four staged modules** against the expected digests printed by
   preflight (step 0). Do not verify the replacement systemd unit yet: it is
   deliberately installed in step 6. Any mismatch = stop and roll back.
5. **Install the policy and key** you authored: per-service fixed argv commands,
   `repo_root`, `out_dir`, `run_as_uid`/`run_as_gid` (never 0), key path. The
   attester refuses uid 0 test execution and any non-root-owned policy/key.
6. **Install the reviewed unit and reload systemd.**
   `git -C <approved checkout> show <sha>:ops/systemd/harness-image-delivery.service | install -o root -g root -m 0644 /dev/stdin /etc/systemd/system/harness-image-delivery.service`
   Verify the installed unit's SHA-256 against the digest from preflight,
   **before** `systemctl daemon-reload` or any future timer activation.
   `systemctl daemon-reload`
   `systemctl cat harness-image-delivery.service | sed -n '/^ExecStart=/p'` —
   verify `harness_native_delivery.py --mode deploy --auto`. Create the
   runtime directories it references:
   `install -o root -g root -m 0700 -d /var/lib/harness-image-delivery/checkout /var/lib/harness-image-delivery/gates /var/lib/harness-image-delivery/delivery`
   Then write the first cycle's source range (operator input, never generated by
   the controller or an agent):
   `printf 'HARNESS_BASE_SHA=%s\nHARNESS_SOURCE_SHA=%s\n' <previous-main> <approved-main> > /var/lib/harness-image-delivery/source-range.env`
   `chown root:root /var/lib/harness-image-delivery/source-range.env && chmod 0600 /var/lib/harness-image-delivery/source-range.env`.
   Only **now**, once the unit, policy, key, directories and range exist,
   rerun `scripts/harness_install_preflight.py --sha <sha>` and require
   `ready: true` with no `blockers` and no `pending`.
7. **Negative canaries before re-enabling anything** (root, no secrets printed):
   - `harness_delivery_controller.py --plan` on a **held** lane → `denied`,
     `release_lane_on_hold`, and **zero** docker build/push and zero Coolify
     PATCH/POST in the log.
   - unattested merge → `local_ci_attestation_missing`; wrong UUID →
     `coolify_uuid_mismatch`; stale attestation → `attestation_stale_source_sha`;
     expired/revoked grant → `grant_expired` / `grant_revoked`; a request for
     SHA A presented while promoting SHA B → `admission_source_sha_mismatch`.
   - a **forged** attestation that merely claims `signature_verified: true`, or a
     deploy run without `--attestation-key` → `attestation_signature_invalid` /
     `attestation_key_missing`, with zero docker and zero Coolify calls.
   - `harness_native_delivery.py --mode plan --auto` with the EnvironmentFile
     present → the intended range and decisions, with zero docker/Coolify calls;
     with the file removed → denied `auto_source_range_missing`, still zero calls.
   - Confirm the service that is currently running still runs its previous image
     digest (nothing was promoted by the denied attempts).
8. **Re-enable only after every negative canary denies**: start the timer, watch
   one cycle, confirm `--mode deploy` refuses an unapproved `main` change and
   that an authorized lane (approved SHA + attestation + per-UUID grant) promotes
   with digest/health readback recorded. Attested `local_ci` must appear in
   `multica-release-status --sha <sha>`.
9. **Rollback** if any of the above fails: stop the timer and service, restore
   the backed-up controller and unit, and `systemctl daemon-reload`. **Leave the
   timer stopped**. The legacy controller bypasses HOLD and must never be
   automatically reactivated by rollback. Record restored digests and verify
   `systemctl is-active harness-image-delivery.timer` remains `inactive`.
   A new production activation requires a separately approved safe controller.

## Rollback

1. `systemctl stop harness-image-delivery.timer`
2. `install -o root -g root -m 0755 /var/lib/harness-image-delivery/backups/harness_image_delivery-<sha12>.py /usr/local/libexec/harness_image_delivery.py`
3. `install -o root -g root -m 0644 /var/lib/harness-image-delivery/backups/harness-image-delivery.service-<sha12>.bak /etc/systemd/system/harness-image-delivery.service`
4. `systemctl daemon-reload`
5. `systemctl is-active harness-image-delivery.timer` must report `inactive`.
6. Record restored digests and disabled timer state; keep the release lane `BLOCKED`.

Restoring the backup reinstates the **hold-blind code on disk**, but keeping
its timer stopped prevents the rollback itself from reactivating that unsafe
release path. Never restart it without an independently approved replacement.

## Not claimed by the source change

- Nothing here is installed, started, or verified by an agent.
- The absence of `local_ci` in release status is expected until step 7 passes.
- A merged PR, green tests or an approved SHA are not production evidence; only
  the step 8 readback is.
- The checkout this unit builds from, and the `source-range.env` SHA pair, must
  be maintained by an operator or an existing scheduler; this change installs no
  fetcher, no new timer, no baseline state and no SHA reconstruction.
