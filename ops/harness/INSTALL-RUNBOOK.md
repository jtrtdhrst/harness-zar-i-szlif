# Harness delivery gate — OPERATOR-ONLY installation runbook

Status: **source-side contract, not installed.** This document describes the one
privileged step that is deliberately outside agent authority: replacing the
hold-blind controller that `harness-image-delivery.timer` runs every 120 s with
the reviewed admission-gated delivery path. No agent may perform any step here
(no sudo, no `systemctl`, no root file writes, no hold changes, no deploy).

Until steps 1-7 are completed and read back, the live behaviour is unchanged and
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
| operator-authored policy | `/etc/paperclip-gitops/harness-ci-policy.json` | `0600 root:root` |
| operator-authored HMAC key | `/etc/paperclip-gitops/harness-attestation.key` | `0600 root:root` |

`scripts/harness_install_preflight.py --sha <approved-sha> --plan` prints the
same list with the immutable expected `sha256` of each module computed from git
at that SHA, and refuses to emit a plan while a precondition fails.

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
- `scripts/harness_install_preflight.py --sha <sha> --plan` exits 0.

## Steps

1. **Stop the timer and the oneshot service.**
   `systemctl stop harness-image-delivery.timer && systemctl stop harness-image-delivery.service`
   Read back `systemctl is-active` for both = `inactive`.
2. **Back up the hold-blind controller.**
   `install -o root -g root -m 0600 /usr/local/libexec/harness_image_delivery.py /var/lib/harness-image-delivery/backups/harness_image_delivery-<sha12>.py`
   `sha256sum` both files and record the digests in the issue.
3. **Stage the four reviewed modules** from the exact SHA, not from a branch head:
   `git -C <approved checkout> show <sha>:scripts/<module> | install -o root -g root -m 0644 /dev/stdin /usr/local/libexec/<module>`
4. **Verify** each staged file against the expected digest printed by the
   preflight (step 0). Any mismatch = stop and roll back, do not continue.
5. **Install the policy and key** you authored: per-service fixed argv commands,
   `repo_root`, `out_dir`, `run_as_uid`/`run_as_gid` (never 0), key path. The
   attester refuses uid 0 test execution and any non-root-owned policy/key.
6. **Negative canaries before re-enabling anything** (root, no secrets printed):
   - `harness_delivery_controller.py --plan` on a **held** lane → `denied`,
     `release_lane_on_hold`, and **zero** docker build/push and zero Coolify
     PATCH/POST in the log.
   - unattested merge → `local_ci_attestation_missing`; wrong UUID →
     `coolify_uuid_mismatch`; stale attestation → `attestation_stale_source_sha`;
     expired/revoked grant → `grant_expired` / `grant_revoked`.
   - `harness_native_delivery.py --mode prepare` on a held lane → denied and no
     `docker build`, no `docker push`.
   - Confirm the service that is currently running still runs its previous image
     digest (nothing was promoted by the denied attempts).
7. **Re-enable only after every negative canary denies**: start the timer, watch
   one cycle, confirm `--mode deploy` refuses an unapproved `main` change and
   that an authorized lane (approved SHA + attestation + per-UUID grant) promotes
   with digest/health readback recorded. Attested `local_ci` must appear in
   `multica-release-status --sha <sha>`.

## Rollback

1. `systemctl stop harness-image-delivery.timer`
2. Restore the backup:
   `install -o root -g root -m 0755 /var/lib/harness-image-delivery/backups/harness_image_delivery-<sha12>.py /usr/local/libexec/harness_image_delivery.py`
3. Remove the staged reviewed modules from `/usr/local/libexec/` if you are
   reverting the whole change.
4. `systemctl start harness-image-delivery.timer`
5. Record: restored digest, `systemctl is-active`, and the next fire time.

Restoring the backup returns the host to the **hold-blind** behaviour, which is
why the lane must be re-marked `BLOCKED` in the issue if a rollback happens.

## Not claimed by the source change

- Nothing here is installed, started, or verified by an agent.
- The absence of `local_ci` in release status is expected until step 6 passes.
- A merged PR, green tests or an approved SHA are not production evidence; only
  the step 7 readback is.
