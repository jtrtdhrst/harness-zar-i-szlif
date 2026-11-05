# Hermes → Hindsight/Vectorize → Opik: privacy-safe observability overlay

> **Stacked change.** This branch is based on PR #39 (`fix/opik-role-segmentation-20261104`). The current production Gateway has **not** adopted that prerequisite or this privacy overlay. Source/control-plane production readback, signed user authorization and real agent run correlation are separate release gates.

## Failure reproduced from production

The active Hermes v0.22.5 Opik plugin captures raw LLM prompts, tool arguments, Hindsight recall/retain contents, provider error bodies, subagent summaries and the last user message. Its generic serializer truncates strings but does not redact token/secret-named fields. The public ChatGPT Opik MCP has been separately secured with Cloudflare Access + origin JWT; **that does not prevent private data from being ingested into the Opik backend by Hermes**.

In a sample of 45 native `hermes` traces, `agent_role`, `memory_bank`, `paperclip_run_id` and trace cost were absent in 45/45. PR #39 addresses verified profile role and configured bank attribution but remains unmerged at the time of this change. Real native Hindsight tool spans already exist, so the Opik runtime instrumentation has a usable starting point.

## Implementation

- `apply_opik_segmentation.py` (PR #39) must transform the exact original `lifecycle.py` hash `b029684c8c24703013126b90527f9b43ee7593c6acdd8afa8ffa13c442738a7a` first.
- `apply_opik_telemetry_privacy.py` requires the resulting segmentation SHA `d25ba46c79f80e9d8c34157b73636bb2ddebdfdf46f0fe74679db24141c8ffec` and exact original `hooks.py` SHA `8fb15f3f78fa8c078748f7ec39b4d1242e63a11e5c38048d726e97d690151a0a`, rejecting unexpected drift before changing a file. Its CLI is **read-only**; writes are performed only through the journaled rollout.
- `privacy_rollout.py` checks all 14 role profiles before any writes, backs up original files root-only, uses exclusive locking with the prerequisite PR #39 rollout, atomically writes both source files per profile while preserving UID/GID/mode, verifies the exact SHA for all 28 outputs, and restores backups on errors.
- Final lifecycle SHA: `e5c9464e94fcddbd075bc25403829e967936b28214b5ab513f5e9b3298f9471c`. Final hooks SHA: `d4a222be6571c955e901560f7197809bfc984453993c97c22b1d52a071597f08`.
- Root traces have constant names, redacted input/output and verified profile-scoped metadata. LLM spans keep model, provider, durations, fresh/cache-write/cache-read/reasoning usage and an explicit `cost_status` (unverified provider estimate or unknown). Tool spans keep safe category, elapsed time and **reported** machine-readable outcome, with a configured memory bank labelled `profile_config_only_not_call_proof`. Tool calls lacking typed status remain `unverified`.
- For errors, provider message/traceback and untrusted status text are replaced by non-content categories. Dynamic tool names, subagent summary text and tool ID values are not exported. A short digest of the tool ID is retained for correlation.

## Evidence (isolated replay of exact production source, 2026-11-05)

- Staged copy of the genuine active Hermes profile plugin; PR #39 transform produced the previously recorded `d25ba46…` checksum.
- 3/3 tests passed in a `--network none` container using actual patched plugin hook handlers with a fake Opik SDK, including private memory strings and synthetic nested fake credentials: no marker strings escaped, LLM token breakdown preserved, `hindsight_recall` status and configured bank preserved, root trace redacted, failed LLM error redacted. These were **not** live production traces.
- 6/6 independent source/denial tests passed on Ubuntu. GitHub workflow runs this suite on every PR commit.
- Isolated clone of all 14 actual active profile source files: PR #39 segmentation applied to 14/14; privacy overlay applied to 28/28 files and read back exact SHA for every file; privacy rollback restored 28 files; PR #39 rollback restored 14; final baseline bytes matched originals. Drift rejection passed.
- No active production Hermes profile, agent binding or banking data was altered by these tests.

## Review and real E2E acceptance

1. Independent CTO review of the composed PR #39 + this PR source/manifest and an immutable candidate. Do not merge directly into `main` ahead of the prerequisite without explicitly rebasing/changing target.
2. Do not use `rollout apply` on a live Gateway. Drain/stop executions, make verified backup, assert no in-flight runs, stage a single canary profile, apply PR #39 then privacy rollout in a controlled environment, restart the candidate only.
3. Make a **real Paperclip-issued Hermes run** with a permitted Named MCP Wiki/Skills call plus native Hindsight `retain` and a subsequent `recall` in the correct bank. Reject wrong-agent and foreign-bank attempts.
4. Read the resulting Opik trace with `paperclip_run_id`, verified `agent_role`, configured `memory_bank`, LLM and tool spans, cache/fresh/reasoning usage and explicit unknown cost. Validate no prompt/memory/secrets in new trace outputs. A snapshot of a Hindsight bank is not proof of a memory call.
5. Prove ChatGPT MCP OAuth positive `tools/list` and `tools/call` after reauthorization; the earlier 401/403 negatives do not constitute authenticated success.
6. Promote only the reviewed candidate by immutable digest under the per-service GitHub→Coolify release policy, read production back, then migrate any agents cohort-wise. **Never** reopen an anonymous MCP endpoint or change all 14 Hermes profiles solely because the unit tests pass.

## Usage (on an isolated copied profile tree only)

```bash
python3 apply_opik_telemetry_privacy.py /stage/profiles/cho/plugins/opik/lifecycle.py /stage/profiles/cho/plugins/opik/hooks.py --check
python3 privacy_rollout.py status --root /stage
python3 privacy_rollout.py apply --root /stage
python3 privacy_rollout.py status --root /stage
python3 privacy_rollout.py rollback --root /stage --batch-id <batch-id>
```

**Rollback order:** privacy first, segmentation second. A privacy-patched lifecycle hash is intentionally incompatible with the PR #39 baseline rollback until the privacy layer is rolled back.

**Limitations:** bank ID comes from a validated local profile config, *not* a cryptographically proven operation target. Existing provider billing may be incomplete. This patch reduces prospective capture of private data; it does **not** purge historic trace contents. A separate retention/redaction procedure must be reviewed and applied to existing Opik data without erasing needed audit evidence.
