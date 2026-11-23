# ZARI-213 — Hermes task Landlock role ACL

This directory holds the exact root-owned task launcher source deployed on the Żar i Szlif VPS. It is **not** a stand-alone MCP service. It is used by the existing `multica-zar-daemon.service` override as `MULTICA_HERMES_PATH`.

## Current observed host state (2026-11-18)

- Host executable: `/usr/local/libexec/zari213-hermes-task-landlock`.
- Deployed SHA-256: `59c1f62570b8de4d28c57b32fcdd100a8ab0c52853330d01c1e35b31cd9dcfca`.
- Exact Git blob: `15e19075072b0b1bde6130583386a4db32f59e13`.
- Previous SHA-256: `6e3f40be426b184771f08e6e0b86030e6a4e9833f34221877570e9a57de1040d`.
- Previous root-only backup: `/usr/local/libexec/zari213-hermes-task-landlock.backup-20261118-role-acl`.

The urgent host policy patch was installed by the owner-authorized operator **before independent source review**. This PR captures immutable source for review and reproducibility; it does **not** claim full ZARI-213 completion or authorize other release lanes to bypass HOLD.

## Why

Prior runtime Landlock granted `READ` to **all** of `/srv/multica-zar/.hermes`. Real unprivileged CTO task canary proved this accidentally allowed reading CHO's role profile (same Unix uid), while checkout/mirror isolation otherwise denied access. The patch limits `READ` to the role obtained from verified `HERMES_HOME` session scope, exact bootstrap files and installs. It denies global `state.db` and foreign profiles.

## Actual operator canaries

Run under the same `multica-zar` Unix principal and task Landlock rules, not as root:

| Probe | Expected | Observed |
|---|---|---|
| Own CTO profile | read allowed | PASS |
| Foreign CHO profile | EACCES | PASS |
| Own CHO profile | read allowed | PASS |
| Foreign CTO profile | EACCES | PASS |
| Global shared Hermes state DB | EACCES | PASS |
| Shared Git bare mirror | EACCES | PASS |
| Other task root | EACCES | PASS |
| Task-owned disposable file write/read/delete | allowed | PASS |
| DNS and public unauthenticated HTTPS TLS | reachable (HTTP 404 is expected) | PASS |
| `python3 -m py_compile` | exit 0 | PASS |

No paid render, agent code changes, credential values, or model inference were used in these canaries. Production daemon remained active and was not restarted; last `systemctl --failed` count was zero.

## Rollback / safety

Only if new evidence shows a regression, the authorized root operator can restore the saved prior version with:

```sh
sudo install -m 0755 -o root -g root \
  /usr/local/libexec/zari213-hermes-task-landlock.backup-20261118-role-acl \
  /usr/local/libexec/zari213-hermes-task-landlock
```

Verify SHA, run the same positive/negative Landlock canaries and collect subsequent native run output. Do not broaden `chmod`, disable Landlock, edit shared agent profiles or restart other services to work around a failed test.

## Remaining blockers — NOT DONE (OpenCode-only source, install not yet approved)

OpenCode-only source policy has **no shared Codex OAuth grants**: it validates all 14 explicit role providers and role-private `.env`, while the sandbox must deny global `auth.json` and every profile `auth.json` symlink. The **currently installed host launcher is older and still grants shared OAuth to six stale Codex-labeled roles**. This source change does not fix the installed policy until independently reviewed, trusted exact-SHA CI passes and a controlled root-owned rollout with rollback is verified. No shared OAuth token copying or privilege expansion is permitted. An actual two-role native Multica task/tool canary, independent CTO review, approved root installation pipeline, and tested rollback are not yet proven. The failed CTO PR #183 review also logged `admitted_turn_failed` / model-provider `APIConnectionError` despite separate DNS/HTTPS reachability checks. Do not equate those failed agent turns with a security E2E PASS.
