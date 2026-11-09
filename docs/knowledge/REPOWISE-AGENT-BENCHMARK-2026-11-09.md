# RepoWise vs GitHub — real OpenCode agent A/B (2026-11-09)

**Status:** completed read-only agent trials; **not** a statistical effect-size estimate or a 14-agent Multica rollout.

## Protocol

- Same runner: isolated `opencode run --standalone --agent plan --model opencode-go/deepseek-v4.1-flash --format json`; fresh session for every run.
- Conditions: explicit instructions to use **only RepoWise MCP** or **only GitHub MCP**. OpenCode was read-only for these tasks; no user source or production application files were edited.
- Tasks: (A) identify the canonical backend documentation path, first heading, and count of numbered chapters; (B) locate `validateParentForCreate` and explain missing-parent and cross-company guards, caller and cycle-check behavior.
- GitHub control received the precise repository `miloszspyrka-code/harness-zar-i-szlif`; RepoWise arm received the `harness` alias. A separate exploratory GitHub-only run **without** the repository name is reported separately and is not used in the fair paired comparison.
- Answer grading was checked against the real GitHub source and verified RepoWise symbol ranges. A run with no complete grounded final answer before its 110-second limit counts as timeout.
- Durations use first-to-last OpenCode JSONL event timestamps, which omit a small startup/teardown interval. Tool calls are real emitted `tool_use` events. Token counts are the sum of emitted `step_finish.tokens` fields. Cached input is reported **separately** from noncached input; no currency-cost claim is made.

## Observed results

| Case | Condition | Correct completed answer | Event duration | Tool calls | Noncached input tokens | Cached-read tokens | Output tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| Backend document | RepoWise | YES | 39.7 s | 7 | 68,260 | 222,464 | 1,221 |
| Backend document, exact repo provided | GitHub | YES | 57.3 s | 10 | 57,851 | 296,576 | 1,892 |
| Function/security analysis | RepoWise | YES | 52.9 s | 8 | 65,720 | 248,064 | 1,803 |
| Function/security analysis, exact repo provided | GitHub | NO — timeout (110 s wall) | 102.9 s recorded events | 15 | 50,122 | 517,376 | 1,912 |
| Document discovery, no repo name supplied | GitHub (exploratory) | NO — timeout (110 s wall) | 101.4 s recorded events | 9 | 34,938 | 264,320 | 1,396 |
| Architecture evidence / readiness warning | RepoWise | YES — correctly refused to infer production readiness | 20.3 s | 2 | 26,274 | 47,872 | 1,396 |

### Measured impact

- For the fully completed *same document task*, RepoWise was **30.7% faster by event duration** and used **30% fewer tool calls** (7 vs 10). The GitHub-only control was also correct once given the exact repo. This is **one pair**, not an estimated average improvement.
- Cached-read token count on that same pair was **25.0% lower**, but noncached input tokens were **18.0% higher** with RepoWise. Do not describe this as an unequivocal token or monetary saving.
- On the function/security task, RepoWise answered correctly within 52.9 seconds of events; GitHub-only did not complete within its 110-second wall limit, despite 15 calls. The timeout means **no fair relative latency percentage** can be calculated for this task.
- A third **nonpaired safety/regression case** asked whether the RepoWise architecture score 9.9/10 and 0 detected violations prove production E2E. A real RepoWise-assisted agent answered **NO**, reported 2 checked rules and 9/14 isolated services, and explicitly cited partial graph evidence. It completed in 20.3 s of events with 2 tool calls. This test checks interpretation quality; it is **not** another speed comparison.
- A separate direct source-extraction comparison of the already-known `paperclip-mcp/src/issue-hierarchy.ts` returned **1,088 characters / 23 lines** for the verified RepoWise function range versus **6,786 characters / 180 lines** for the full GitHub file (about **84% less text**). This does not apply when the task actually requires the entire file.
- Across the two paired tasks: grounded completion **2/2 with RepoWise vs 1/2 with GitHub**, in this small single-model test. Tool-use discovery overhead is substantial in both conditions.

### Quality and safety findings

- RepoWise symbol lookup correctly located `paperclip-mcp/src/issue-hierarchy.ts:157-179`, cross-company `PARENT_CROSS_COMPANY`, missing-parent `PARENT_NOT_FOUND`, and the client-side caller. The new-issue variant deliberately does not traverse parent chains for cycles.
- A separate **source-isolation defect** existed in the former production RepoWise index: a harness-only file `scripts/product_native_promotion.py` appeared under `product`. Do not attribute the legacy corpus to true product ownership; an isolated staged index correctly rejected this false path.
- The RepoWise graph remains **partial**, and a high architecture score is not validated production connectivity. Provider, embedder and answer-synthesis functionality are separate from the successful source/path tools.

## Opik provenance

The six actual OpenCode runs (two paired tasks, one unseeded discovery run, one architecture-readiness safety probe) were imported to a **private, metadata-only** native Opik project named `repowise-agent-ab-20261109` (project ID `01a1c2b6-f9d9-75cf-9cb4-a4506d607e7f`). Each trace was created through the self-hosted native private API and verified by GET readback. Import metadata explicitly identifies the event-JSONL origin, model, condition, correctness, token counts, tool calls and raw-log SHA-256; no prompts, full answers, secrets or transcripts were uploaded.

Private raw JSONL evidence remains on the VPS in `/opt/repowise-knowledge/agent-benchmark-20261109/` (root-owned; do not publicly publish or sync). These are **imported benchmark traces**, not evidence of automatic Opik instrumentation of Multica runs.

## Limits and next gates

1. **n = 2** paired task types with one model and one OpenCode `plan` agent. Repeated trials and other models/roles are necessary before treating the figures as a general speed/token advantage.
2. The 14 configured Hermes Gateway profiles do **not** equal 14 executed Multica agents. Production Multica `zar-prod` daemon is still unauthorized and guarded, and may not be promoted without native session authentication; do not bypass it.
3. The user is configuring the RepoWise LLM provider and embedder separately. This benchmark uses exact path/symbol retrieval and makes **no** claim that `get_answer` synthesis or semantic search is available.
4. RepoWise GitHub staging→MCP→production promotion has its own regression check and rollback gate. Never turn a staging-only PASS into a production-release claim.
