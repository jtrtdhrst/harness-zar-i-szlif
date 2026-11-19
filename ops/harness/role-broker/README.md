# ZARI-213: Role-scoped Codex broker — preproduction candidate

This directory implements a deliberately constrained OAuth-aware model transport bridge for Hermes v0.22.5. It is not a completed credential isolation deployment; ZARI-213 and ZARI-240 remain BLOCKED.

## Verified original defect

The native CHO run 01a1f40a-ca05-71a1-bea5-86ceeda8fe9b confirmed that own-profile opens were allowed, foreign CTO profile and shared Git mirror opens were denied, **but global Hermes auth.json and .env could still be opened by the agent**. No secret bytes were read. Hermes OAuth credential_pool uses shared rotating refresh-token chains; copying this account into 14 independent profile files is unsafe.

## Candidate mechanism

The broker runs outside the task sandbox, resolves Codex OAuth from the trusted global store using Hermes's native refresh logic, and forwards only the pinned Responses endpoint. Only a known role's private bearer can call /p/<role>/v1/responses. Wrong/missing role token is denied; requested model is allowlisted; store=false and stream=true are enforced; max body is 1 MiB. The broker drops client authorization/headers, pins https://chatgpt.com/backend-api/codex/responses, prohibits redirects, and sanitizes upstream errors. Listener is loopback 127.0.0.1 only. The broker enforces at most one active request per role and three active requests overall, plus eight admitted calls per 60 seconds per role; rejected unauthenticated calls do not consume quota. These counters are process-local and reset on restart, not an independently audited billing/budget ledger. No secret is committed to Git.

## Tests on 2026-11-19 (operator-observed)

- Initial 11/11 unit cases PASS in local Python and on VPS; after independent CTO review found key-path TOCTOU, the broker was hardened with descriptor-relative O_NOFOLLOW opens, verified service UID, private root/role/key inode checks, and FD-only reads. The expanded 13/13 unit cases PASS on VPS in the actual Hermes virtualenv as root and UID 997 (multica-zar). New tests verify 0700 role directories and a symlink swap after file open still reads the original validated inode. Negative checks cover foreign/missing bearer, unsupported route/model/protocol, symlink/private-file mode, no upstream call on denied request, no client header forwarding, no secrets in error.
- Expanded capacity tests: **16/16 PASS** as UID 997 in the actual Hermes virtualenv using GitHub blob-identical source/test files; new tests include same-role concurrent denial, 8-per-minute limit with other-role independence, and no quota consumption by wrong-role requests.
- A separate synthetic-only **named custom provider** (`custom:rolebroker`, `api_mode: codex_responses`) caused a real unprivileged Hermes Gateway worker to call `/p/cho/v1/responses` with stream=true/store=false and, with a complete fake Responses event stream, return **exit 0** and output `OK`. No real model credential was used. This proves Hermes worker/transport compatibility against a fake endpoint, not real native Multica agent -> broker OAuth.
- Disposable VPS broker staging: anonymous -> HTTP 401, COO bearer on CHO route -> 401, CHO bearer on CHO route -> 200. No persistent service/profile change.
- Direct real GPT-6 Luna request via disposable broker returned HTTP 200, valid completed SSE, output OK, about 3.1 seconds. This is proof of the broker data-plane, not full agent runtime.
- Disposable Hermes gateway-backed one-shot -z exited 2 with an unknown execution outcome; it never reached the broker's Responses route. The real-key direct-client diagnostic was blocked by execution safeguards. A separate unprivileged synthetic-only Hermes chat -q test using a fake Responses server and NONSECRET test bearer returned 'Worker execution is unknown' (exit 1) before reaching /responses. No real credentials were used. The cause of this synthetic CLI failure is undetermined. This observation shows only that the test client did not invoke /responses; it does not establish a production session-ingress or ACP defect. Native Hermes client -> broker E2E remains NOT_VERIFIED.

## Mandatory gates before role migration or release

1. Independent exact-source SHA review and regression tests; fix any review failures.
2. Native two-role agent test for positive own broker calls and negative cross-role calls; no secret bytes exposed. Do not rely only on URL role labels for authorization.
3. Prove a direct (not nested gateway agent) Hermes Responses runtime call via custom provider, without global auth.json or .env access. Preserve tool behavior and avoid double agent execution.
4. Bounded concurrency and per-role request rate limits are implemented and tested; independently enforce role/account billing budgets and exercise real SSE/upstream failure paths before enabling a long-lived production service.
5. Use a restricted service identity and role key path, no public listener. Capture source/blob/digest, CI, release owner, live positive and negative canaries and rollback.
6. Remove Landlock global auth.json/.env grants only after approved model-broker replacement successfully handles every migrated role; fail closed, do not copy shared refresh tokens to individual profiles.
7. Native ZARI-213 and full ZARI-240 Done gates remain enforced. A partial RepoWise deployment observation alone never constitutes a successful full release.

## Rollback

This source-only PR leaves the Multica daemon, Hermes role profiles, global OAuth store, and RepoWise unchanged. Roll back by reverting the candidate PR. No new systemd service has been installed or activated.
