---
title: Native Multica → GitHub → local CI → Coolify delivery: verified evidence and gaps
date: 2026-11-18
status: partial-live-proof
scope: harness and product
evidence_rule: exact SHA + real job + deployed immutable revision + negative tests; never extrapolate from a single green step
---

# Development lifecycle evidence — 2026-11-18 (UTC)

## Newer verified state — 2026-11-18, 11:35 UTC (supersedes only the dated snapshots below)

- **Publication into RepoWise is now LIVE PASS**: documentation-only PR
  [#133](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/133)
  merged as GitHub Harness `main=d293903091f60f6d15b5dd2621732e1932efe6cd`.
  `repowise-github-sync.service` staged and checked the exact SHA, passed
  positive harness/product and negative cross-repo MCP smoke, emitted
  `PROMOTE_OK`, `LIVE_CURRENT`, and `LIVE_STATUS_OK`. Live RepoWise MCP
  `list_repos` reported Harness indexed at that SHA and Product at
  `4feef6903dc21be5da0433a77b10549bf0009661`;
  `search_codebase(mode=path)` found this document, and
  `get_context(include=skeleton)` returned its text with `verified=true`.
  This proves **documentation→GitHub→RepoWise index→MCP retrieval**, not
  a new functional Coolify release or model-driven agent E2E.
- **Rootless Product Docker build exists since the earlier preflight**:
  socket `/run/zis-rootless-docker/docker.sock` is owned by
  `actions-zis-product`; with scoped `DOCKER_HOST`, Docker reports
  `name=rootless`. Product PR
  [#183](https://github.com/miloszspyrka-code/zar-i-szlif/pull/183)
  at `6e43015961ed41ead0efd4507f66a364ba4bd4fb` passed
  [Product CI run 44290719173](https://github.com/miloszspyrka-code/zar-i-szlif/actions/runs/44290719173):
  release contract, npm validation, Docker build, source-commit HTTP smoke,
  and negative versionless start. **This is test capability, not safe PR admission**.
  CTO's independent native review (ZARI-251) requested changes: the guard
  against malicious same-repo PRs is embedded in PR-editable workflow YAML.
  Host runner systemd lacks a verified per-job filesystem and network sandbox.
  A same-repository author could delete the guard; neither rootless Docker nor
  a green run proves host confinement. PR is still unmerged; production is
  unchanged. Never enable unrestricted PR execution or force an approval.
- **Harness release-source PR #123 was repaired, not released**:
  head `9f247314fc460f637b9cd443e4bd7e19ee83129a`
  is a two-parent merge with Harness `main=d293903…`.
  Its diff now contains **only six** release controller, installer and test
  paths, no resurrected Paperclip MCP workflow and no broken `ubuntu-latest`
  PR routing. CI for the new SHA is a separate pending/required gate;
  independent CTO exact-SHA review, approved root install, restricted
  per-resource HOLD and controlled deployment/rollback remain necessary.
- **Hermes ZARI-213 is still NO-GO for unrestricted agents**.
  A newer daemon binary was seen active, and a CTO native review run completed,
  but this does not prove task-level Landlock policies, project repo ACL,
  cross-task denial, concurrent tool-use, or verified rollback.

These observations are deliberately **not** retroactively applied to
the 11:16 UTC rootless-preflight table: that table records what was actually
installed and tested at that earlier moment.

This is an **evidence log and troubleshooting runbook**, not an approval to deploy.
RepoWise indexes committed repository facts and reviewed decisions. It does **not**
execute native Multica agents, prove production, or turn a red CI result green.
Use GitHub, live Docker/Coolify, Multica task runs, and local CI attestation as
distinct sources of truth. See `docs/decisions/0002-agent-knowledge-provenance.md`,
`docs/knowledge/AGENT-LOOKUP.md`, and `ops/repowise/README.md`.

## Real evidence (observed on 18 November, not a promise)

| Gate | Result | Evidence and strict limits |
| --- | --- | --- |
| RepoWise private sync | **PASS at inspected snapshot** | `list_repos` reported harness indexed at `1b883292a131f0259add0574c4997a15189f873c` and product `4feef6903dc21be5da0433a77b10549bf0009661`. Host `repowise-github-sync.service` reported `LIVE_CURRENT` / `SYNC_CURRENT` at 11:05:50Z, freshness check exit 0 at 11:05:57Z. This is not a claim of instant freshness for future pushes. |
| Harness self-hosted CI | **PASS for one exact PR SHA** | GitHub Actions [Release Lanes Policy run 44290987130](https://github.com/miloszspyrka-code/harness-zar-i-szlif/actions/runs/44290987130) on `6610a8b90b70dd51e15a03f332f6c5ffa8890bb9`: `actions/checkout@v4`, release-contract validator, and Multica MCP adapter test all succeeded. Other PRs and later runs require their own result. |
| Harness runner HOME isolation bug | **FIXED / positive CI retest** | Run [44289203027](https://github.com/miloszspyrka-code/harness-zar-i-szlif/actions/runs/44289203027) failed at checkout: `EACCES: permission denied, stat '/opt/zis-actions-runner/.gitconfig'`. Harness process ran as `actions-zis` but inherited `HOME=/opt/zis-actions-runner`, owned by `actions-zis-product` with mode 0750. The harness runner's own worktree/.git had no mismatched owners. |
| Harness runner repair | **LIVE installed** | Root-owned systemd drop-in `/etc/systemd/system/actions.runner.miloszspyrka-code-harness-zar-i-szlif.zis-harness-build.service.d/10-harness-home.conf` sets `Environment=HOME=/opt/zis-actions-runner-harness`. An empty `0600 actions-zis:actions-zis` `.gitconfig` exists in that home. Only Harness runner restarted. Listener environment and `actions-zis` read/write tests passed, followed by green checkout in run 44290987130. No Docker group grant, token copying, or access broadening was done. |
| Old HOLD-blind Harness controller | **NEGATIVE PASS for legacy entrypoint only** | `python3 /usr/local/libexec/harness_image_delivery.py --auto` returned exit **78** with `legacy_hold_blind_controller_disabled`; running-container count before/after was unchanged (82 → 82). `harness-image-delivery.timer` was disabled/inactive. This is **not** proof that every alternative deployment credential or path is revoked. |
| Product main → live panel | **PASS for existing release** | GitHub product `main` was `4feef6903dc21be5da0433a77b10549bf0009661`. `https://panel.zariszlif.pl/healthz` returned HTTP 200 (`ok`), `/__release.json` returned that exact commit. Production web and product-MCP containers were `running/healthy`. `multica-release-status --sha 4feef6903dc21be5da0433a77b10549bf0009661` returned an `exit_code=0` local-CI entry (`zis-local-build`) and finished Coolify deployment records. This **does not** prove new Harness code or live ComfyUI generation. |
| Product GitHub-hosted CI | **FAIL / NOT_RUN tests** | Product CI run [44281497056](https://github.com/miloszspyrka-code/zar-i-szlif/actions/runs/44281497056) failed without executed `validate-product` steps; `.github/workflows/product-ci.yml` uses `ubuntu-latest`. GitHub-hosted minutes are blocked by billing in related runs. Do not claim green product GitHub Actions from local production health or local attestation. |
| Safe Docker PR runner | **BLOCKED** | Both runner identities were tested independently: Harness `actions-zis` and Product `actions-zis-product` each received `permission denied` from the root-owned `/var/run/docker.sock` (both exit 1). Neither runner is presently a proven production-equivalent Docker builder. Granting Docker group privileges to untrusted PR jobs would expose host-root-equivalent access; use a genuinely isolated rootless build lane with scoped credentials and its own negative canaries instead. A runner capable of isolated build+test, with no host socket or cross-project file access, remains unverified. |
| Native Hermes task isolation | **NO-GO / ZARI-213** | Linux Landlock **synthetic** negative tests passed, but actual Hermes agent tool-use failed at the shared `.recovery.lock` install path. Project checkout allowlist and cross-task filesystem enforcement are not proven live. Do not silently enable cross-project unrestricted runs or mark this as E2E PASS. |
| New Harness release + rollback | **NOT_RUN, HOLD maintained** | Exact candidate SHA → independent CTO review → trusted CI → COO authorization → Coolify UUID+immutable digest → authenticated positive/negative service probes → actual rollback acceptance remains unproven as a **new** end-to-end release. A green repository check or healthy unrelated product cannot close this gate. |

## Isolated build preflight — 11:16 UTC, read-only

Both runner principals were checked with `runuser -u <user> -- docker info`:
`actions-zis` exit 1; `actions-zis-product` exit 1. Neither could
contact the host's root-owned Docker socket. Neither should be blindly added
to the `docker` group.

A rootless replacement is **not yet available**:
- `dockerd-rootless.sh`, `rootlesskit`, `newuidmap`, and `newgidmap`
  exist; `slirp4netns` and `fuse-overlayfs` were not found.
- Product user has `/etc/subuid` and `/etc/subgid` ranges; Harness user
  has no declared subordinate-ID ranges.
- `kernel.unprivileged_userns_clone=1` and cgroup v2 are present, but
  `kernel.apparmor_restrict_unprivileged_userns=1`.
- `unshare -U true` for Product returned 0, whereas `unshare -Ur true`
  failed writing `/proc/self/uid_map` with `EPERM`. Kernel audit explicitly
  denied `capable sys_admin` in the `unprivileged_userns` profile.
  An unprivileged user namespace **creation** is therefore not the same as
  a working rootless-Docker mapping.

**Decision / NO-GO:** Do not switch off AppArmor globally, widen access to
`/var/run/docker.sock`, or declare rootless build E2E PASS. Any replacement
builder needs a narrowly reviewed AppArmor profile plus correct per-runner
subordinate IDs, packaging, an isolated daemon/socket, clean disposable workspace,
restricted secrets/egress and both positive build and negative host-access tests.
Run this in a separate scoped release lane, not as a quick global sysctl
change on production. These are requirements, **not installed changes**.

## Operational repair and rollback: Harness runner HOME

**Reproduce without changing state:** inspect `systemctl show <runner.service> -p User -p Environment`,
the corresponding `Runner.Listener` `/proc/<pid>/environ` HOME value,
`namei -l /opt/zis-actions-runner/.gitconfig`, and the failed job's *exact*
checkout step. Verify the owner/permissions of the worktree; do not recursively
chown it without evidence.

**Reviewed minimal host-side fix, already installed:** harness-only systemd
drop-in `[Service]\nEnvironment=HOME=/opt/zis-actions-runner-harness`,
one private harness-owned `.gitconfig`, daemon reload, Harness runner restart.
Use `systemctl is-active`, the Listener's actual `HOME`, and an
`actions-zis` Git config read/write probe to verify. Then require a fresh
GitHub Actions job on an exact SHA whose checkout and substantive tests pass.

**Rollback if the change regresses:** stop only the Harness runner; back up and
remove **only** the named `10-harness-home.conf` drop-in, reload systemd and
restart the same service. Preserve the original service and product runner.
Before rollback, verify this will not recreate the known EACCES failure and
do not overwrite unrelated drop-ins. No broad chmod and no Docker membership.

## Release admission / quality contract

The release is **done** only when this chain is tied to one approved source SHA:

1. Authorized scoped branch/PR, exact head SHA and reviewed diff; independent reviewer on that SHA.
2. Trusted CI on the correct SHA, with **executed** tests (a workflow `success` elsewhere is irrelevant). Docker/container tests require isolated build authority.
3. Explicit per-Coolify-resource HOLD-aware admission and owner authorization; never trigger the disabled legacy controller or re-enable old credentials.
4. Actual release deployment UUID, immutable running image digest, provenance to SHA, health and *authenticated* feature checks plus negative auth checks.
5. Verified rollback to previously recorded healthy digest; independently inspect the restored runtime. Multica issue DONE only after this readback, not after PR merge.

**Unfinished specific blockers:** ZARI-213 (Hermes task/repo isolation);
ZARI-240 (full new-change lifecycle); ZARI-214 (Harness exact-SHA
release admission); draft PR
[#123](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/123)
(immutable digests / rollback / unsafe PR-runner routing).
PR #123 at inspected head `05a24a9908401f67b335f67dd9bfb3c442c22c26`
also touched a now-deleted `.github/workflows/paperclip-mcp-ci.yml`
and proposed `ubuntu-latest` for PR checks despite hosted-billing refusal;
do not merge without rebase, independent review and a working isolated test
execution path. This finding was posted in PR conversation comment
[#6976425346](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/123#issuecomment-6976425346).

## Repeatable non-mutating verification

```sh
# GitHub Actions: check the actual new PR SHA / job steps using the GitHub API/UI.
systemctl is-active actions.runner.miloszspyrka-code-harness-zar-i-szlif.zis-harness-build.service
systemctl show actions.runner.miloszspyrka-code-harness-zar-i-szlif.zis-harness-build.service -p User -p Environment
systemctl is-enabled harness-image-delivery.timer
systemctl is-enabled product-native-promotion.timer
systemctl status repowise-github-sync.service --no-pager
systemctl status repowise-freshness-check.service --no-pager
curl -fsS https://panel.zariszlif.pl/healthz
curl -fsS https://panel.zariszlif.pl/__release.json
multica-release-status --sha 4feef6903dc21be5da0433a77b10549bf0009661
```

Running these probes proves only their explicitly stated scope.
Do **not** call an endpoint with live write credentials or trigger a paid
ComfyUI image generation merely to green-light documentation. The RepoWise
GitHub sync reads **main**, not unmerged PRs: a PR draft of this file is
not yet published to the live indexed knowledge until an authorized reviewed
merge, successful sync, and MCP readback.
