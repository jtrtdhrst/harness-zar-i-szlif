# Paperclip-native reviewed PR publication

One GitHub App installation remains responsible for Git transport.
The independent reviewer lives inside Paperclip, not a second GitHub
identity. No GitHub App Administration privileges or additional PAT.

## Execution
1. Engineer/Harness Engineer executes an assigned issue in its own
   workspace on a feature branch, not main.
2. paperclipGitPush pushes a branch and refreshes the already-linked
   Paperclip PR work product's actual remote HEAD SHA.
3. paperclipGitCreatePR creates or recovers a PR and upserts a real
   Paperclip pull_request work product with canonical URL, branch,
   repository and pinned exact SHA. Missing artifact is not success.
4. CHO/CTO reviews through first-class Paperclip review decisions.
   Changes requested returns the issue to the executor for rework.
5. Only an issue marked DONE by approved native review can pass
   paperclipGitMergePR. Native authorization verifies independent
   review stage, actual PR work product SHA, GitHub head, check-runs
   validate-product or validate-paperclip-mcp and clean merge state.
6. GitHub merge to main triggers existing Coolify app auto deployment
   or scoped harness MCP GitOps and readback is required for delivery.
7. GitOps checks actual merged PR and green CI. Review lives in
   Paperclip, never in a second GitHub account.

## Limits
Legacy PRs without a real issue-scoped pull_request work product and
pinned head SHA are not approved automatically. Do not invent evidence.
A Paperclip DONE transition can end the reviewer heartbeat run, so
the subsequent authorized merger must use a valid board/CHO runtime
context; never fabricate a run id. No Paperclip Core source edits.
GitHub branch protection is a repository-owner setting; the existing
GitHub App deliberately lacks Administration scope.
