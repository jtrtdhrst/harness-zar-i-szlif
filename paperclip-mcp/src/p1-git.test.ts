import { EventEmitter } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildMergeArgv, createP1GitTools, deriveGitPermissions, evaluateMergeGate, evaluateNativePaperclipReview, evaluatePrChecks, evaluateRestCheckRuns, scopedGhEnv } from "./p1-git.js";
import type { PaperclipApiClient } from "./client.js";

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn: spawnMock }));

function authTool() {
  const tool = createP1GitTools({} as PaperclipApiClient).find((item) => item.name === "paperclipGitAuthStatus");
  if (!tool) throw new Error("missing paperclipGitAuthStatus");
  return tool;
}

describe("paperclipGitAuthStatus", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    spawnMock.mockReset();
  });

  it("fails closed when no token is injected", async () => {
    vi.stubEnv("GH_TOKEN", "");
    vi.stubEnv("GITHUB_TOKEN", "");

    const result = await authTool().execute({ repository: "miloszspyrka-code/zar-i-szlif", operation: "read" });
    const body = JSON.parse(result.content[0]?.text ?? "{}");

    expect(body.error.code).toBe("GITHUB_AUTH_MISSING");
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it("checks repo access through token-aware gh api instead of unauthenticated git ls-remote", async () => {
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("GITHUB_TOKEN", "");
    const child = new EventEmitter() as EventEmitter & { kill: ReturnType<typeof vi.fn> };
    child.kill = vi.fn();
    spawnMock.mockImplementation((_command: string, _args: string[], _options: unknown) => {
      queueMicrotask(() => child.emit("close", 0));
      return child;
    });

    const result = await authTool().execute({ repository: "miloszspyrka-code/zar-i-szlif", operation: "read" });
    const body = JSON.parse(result.content[0]?.text ?? "{}");
    const [command, args, options] = spawnMock.mock.calls[0] as [string, string[], { env: Record<string, string> }];

    expect(command).toBe("gh");
    expect(args).toEqual(["api", "repos/miloszspyrka-code/zar-i-szlif", "--jq", ".full_name"]);
    expect(options.env.GH_TOKEN).toBe("test-token");
    expect(options.env.GH_PROMPT_DISABLED).toBe("1");
    expect(options.env.GIT_TERMINAL_PROMPT).toBe("0");
    expect(body.authenticated).toBe(true);
    expect(body.repositoryAccessible).toBe(true);
    // The transport is read through git with the SAME projected credential.
    const [transportCommand, transportArgs, transportOptions] = spawnMock.mock.calls[1] as [string, string[], { env: Record<string, string> }];
    expect(transportCommand).toBe("git");
    expect(transportArgs).toEqual(["ls-remote", "--heads", "https://github.com/miloszspyrka-code/zar-i-szlif.git"]);
    expect(transportOptions.env.GIT_CONFIG_COUNT).toBe("3");
    expect(transportOptions.env.GIT_TERMINAL_PROMPT).toBe("0");
    expect(body.transportAuthenticated).toBe(true);
  });
});

describe("deriveGitPermissions (Phase 4)", () => {
  it("reports push/create_pr when the token carries push", () => {
    expect(deriveGitPermissions({ push: true, admin: false, pull: true })).toEqual({
      allowedOperations: ["read", "push", "create_pr"],
      missingPermissions: [],
    });
  });
  it("reports push/create_pr for admins", () => {
    expect(deriveGitPermissions({ push: false, admin: true, pull: true }).allowedOperations).toContain("push");
  });
  it("stays read-only when scopes are absent or unfetchable", () => {
    expect(deriveGitPermissions({ push: false, admin: false, pull: true })).toEqual({
      allowedOperations: ["read"],
      missingPermissions: ["contents:write", "pull-requests:write"],
    });
    expect(deriveGitPermissions(null).missingPermissions).toContain("contents:write");
  });
});

describe("paperclipGitAuthStatus scope reporting", () => {
  function ghChild(stdout: string, code = 0) {
    const child = new EventEmitter() as EventEmitter & {
      kill: ReturnType<typeof vi.fn>;
      stdout: { on: (ev: string, cb: (d: unknown) => void) => void };
    };
    child.kill = vi.fn();
    const handlers: Record<string, (d?: unknown) => void> = {};
    child.stdout = { on(ev: string, cb: (d: unknown) => void): void { handlers[ev] = cb; } };
    queueMicrotask(() => {
      if (stdout) handlers["data"]?.(stdout);
      child.emit("close", code);
    });
    return child;
  }
  it("push op with push-scoped token reports push allowed (no false denial)", async () => {
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("GITHUB_TOKEN", "");
    spawnMock.mockImplementation((_command: string, args: string[], _options: unknown) => {
      if (args.join(" ").includes(".permissions")) return ghChild('{"push":true,"admin":false,"pull":true}');
      return ghChild("");
    });
    const result = await authTool().execute({ repository: "miloszspyrka-code/zar-i-szlif", operation: "push" });
    const body = JSON.parse(result.content[0]?.text ?? "{}");
    expect(body.authenticated).toBe(true);
    expect(body.allowedOperations).toContain("push");
    expect(body.missingPermissions).toEqual([]);
    expect(body.transportAuthenticated).toBe(true);
    // gh api (access) + gh api (permissions) + git ls-remote (transport)
    expect(spawnMock).toHaveBeenCalledTimes(3);
  });
  it("push op drops push when the transport cannot authenticate even though the API allows it", async () => {
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("GITHUB_TOKEN", "");
    spawnMock.mockImplementation((command: string, args: string[], _options: unknown) => {
      if (args.join(" ").includes(".permissions")) return ghChild('{"push":true,"admin":false,"pull":true}');
      if (command === "git") return ghChild("", 128);
      return ghChild("");
    });
    const result = await authTool().execute({ repository: "miloszspyrka-code/zar-i-szlif", operation: "push" });
    const body = JSON.parse(result.content[0]?.text ?? "{}");
    expect(body.allowedOperations).toEqual(["read"]);
    expect(body.missingPermissions).toContain("transport:not-authenticated");
    expect(body.transportAuthenticated).toBe(false);
    expect(body.transportReason).toContain("refused");
  });
  it("push op with read-only token stays fail-closed", async () => {
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("GITHUB_TOKEN", "");
    spawnMock.mockImplementation((_command: string, args: string[], _options: unknown) => {
      if (args.join(" ").includes(".permissions")) return ghChild('{"push":false,"admin":false,"pull":true}');
      return ghChild("");
    });
    const result = await authTool().execute({ repository: "miloszspyrka-code/zar-i-szlif", operation: "push" });
    const body = JSON.parse(result.content[0]?.text ?? "{}");
    expect(body.allowedOperations).toEqual(["read"]);
    expect(body.missingPermissions).toContain("contents:write");
  });
});

describe("paperclipGitWaitChecks evaluation (fail-closed)", () => {
  it("never reports success when the checks context is unreadable (denied Checks:Read)", () => {
    // Observed live defect: exit 4 with empty stdout returned success/terminal.
    expect(evaluatePrChecks(4, "")).toMatchObject({ state: "unverified" });
    expect(evaluatePrChecks(1, "")).toMatchObject({ state: "unverified" });
    expect(evaluatePrChecks(0, "no checks reported on the 'KOMAA-1415' branch")).toMatchObject({ state: "unverified" });
  });

  it("reports success only for explicit pass lines with a zero exit", () => {
    expect(evaluatePrChecks(0, "verify-infrastructure\tpass\t1m\thttps://example/1")).toMatchObject({ state: "success" });
    expect(evaluatePrChecks(0, "verify-infrastructure\tpass\t1m")).toMatchObject({ state: "success" });
    expect(evaluatePrChecks(3, "verify-infrastructure\tpass\t1m")).toMatchObject({ state: "unverified" });
  });

  it("separates failure and pending states", () => {
    expect(evaluatePrChecks(1, "mcp-tests\tfail\t2m")).toMatchObject({ state: "failure" });
    expect(evaluatePrChecks(1, "mcp-tests\tpending\t0")).toMatchObject({ state: "pending" });
    expect(evaluatePrChecks(1, "mcp-tests\tqueued\t0")).toMatchObject({ state: "pending" });
  });
});

describe("paperclipGitWaitChecks REST checks regression", () => {
  const run = (status: string, conclusion: string | null) => ({ name: "validate-paperclip-mcp", status, conclusion });
  it("accepts successful REST check runs even when gh pr checks lacks GraphQL access", () => {
    expect(evaluateRestCheckRuns(0, JSON.stringify({ total_count: 1, check_runs: [run("completed", "success")] }))).toMatchObject({ state: "success", total: 1 });
  });
  it("treats pending REST checks as pending rather than an authorization failure", () => {
    expect(evaluateRestCheckRuns(0, JSON.stringify({ total_count: 1, check_runs: [run("in_progress", null)] }))).toMatchObject({ state: "pending" });
  });
  it("fails closed on denied, invalid, empty or paginated check data", () => {
    expect(evaluateRestCheckRuns(1, "")).toMatchObject({ state: "unverified" });
    expect(evaluateRestCheckRuns(0, "not-json")).toMatchObject({ state: "unverified" });
    expect(evaluateRestCheckRuns(0, JSON.stringify({ total_count: 0, check_runs: [] }))).toMatchObject({ state: "unverified" });
    expect(evaluateRestCheckRuns(0, JSON.stringify({ total_count: 101, check_runs: [run("completed", "success")] }))).toMatchObject({ state: "unverified" });
  });
  it("preserves failure status from REST check-runs", () => {
    expect(evaluateRestCheckRuns(0, JSON.stringify({ total_count: 1, check_runs: [run("completed", "failure")] }))).toMatchObject({ state: "failure" });
  });
});

describe("paperclipGitMergePR gate (fail-closed)", () => {
  const base = { headRefOid: "df09a54950358a6acb179f59738919e71962f8ec", reviewDecision: "APPROVED", mergeable: "MERGEABLE", mergeStateStatus: "CLEAN" };

  it("allows a clean, exact-head, approved PR", () => {
    expect(evaluateMergeGate(base, "df09a54950358a6acb179f59738919e71962f8ec").ok).toBe(true);
  });

  it("refuses when the head or gate state is unreadable", () => {
    expect(evaluateMergeGate({ ...base, headRefOid: "" }, "df09a549").ok).toBe(false);
    expect(evaluateMergeGate({ ...base, mergeStateStatus: "UNKNOWN" }, "df09a549").ok).toBe(false);
    expect(evaluateMergeGate({ ...base, mergeable: "UNKNOWN" }, "df09a549").ok).toBe(false);
  });

  it("refuses a mismatched SHA, requested changes, or blocked merge state", () => {
    expect(evaluateMergeGate(base, "0000000000000000000000000000000000000000").ok).toBe(false);
    expect(evaluateMergeGate({ ...base, reviewDecision: "CHANGES_REQUESTED" }, "df09a549").ok).toBe(false);
    expect(evaluateMergeGate({ ...base, reviewDecision: "" }, "df09a549").ok).toBe(true);
    expect(evaluateMergeGate({ ...base, reviewDecision: "REVIEW_REQUIRED" }, "df09a549").ok).toBe(true);
    expect(evaluateMergeGate({ ...base, mergeStateStatus: "UNSTABLE" }, "df09a549").ok).toBe(false);
    expect(evaluateMergeGate({ ...base, mergeStateStatus: "BLOCKED" }, "df09a549").ok).toBe(false);
  });
});

describe("paperclipGitMergePR head-race guard", () => {
  const headSha = "fd281ca51f67207dabbeaaa7a832555071d81b6f";

  it("pins the merge to the verified full head SHA", () => {
    // A head push between the gate read and the merge must make gh refuse.
    expect(buildMergeArgv(98, ["--repo", "owner/repo"], "--merge", headSha)).toEqual([
      "gh", "pr", "merge", "98", "--repo", "owner/repo", "--merge", "--match-head-commit", headSha,
    ]);
  });

  it("pins every merge method, not just the default", () => {
    for (const methodFlag of ["--merge", "--squash", "--rebase"]) {
      const argv = buildMergeArgv(7, [], methodFlag, headSha);
      expect(argv).toContain("--match-head-commit");
      expect(argv[argv.indexOf("--match-head-commit") + 1]).toBe(headSha);
    }
  });
});

describe("native Paperclip first-class approval, not synthetic GitHub review", () => {
  const sha = "a".repeat(40);
  const url = "https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/26";
  const issue = {
    status: "done", reviewPolicy: "not_creator",
    executionState: {
      status: "completed", lastDecisionOutcome: "approved",
      lastDecisionId: "123e4567-e89b-42d3-a456-426614174000",
      completedStageIds: ["review-stage"], returnAssignee: { type:"agent", agentId:"engineer" },
    },
    executionPolicy: {
      stages: [{ id:"review-stage", type:"review", participants:[{ type:"agent", agentId:"CHO" }], approvalsNeeded:1 }],
    },
    workProducts: [{id:"pr-record",type:"pull_request",provider:"github",url,
      metadata:{headSha:sha,branch:"task-branch",repository:"miloszspyrka-code/harness-zar-i-szlif"}}],
  };
  it("permits a real approved issue and its exact PR artifact head SHA", () => {
    expect(evaluateNativePaperclipReview(issue,url,sha).ok).toBe(true);
  });
  it("trusts first-class not_creator enforcement even when returnAssignee points to reviewer", () => {
    const delegated = { ...issue,executionState:{...issue.executionState,
      returnAssignee:{type:"agent",agentId:"CHO"}} };
    expect(evaluateNativePaperclipReview(delegated,url,sha).ok).toBe(true);
    expect(evaluateNativePaperclipReview({...delegated,reviewPolicy:"none"},url,sha).ok).toBe(false);
  });
  it("refuses unapproved, self-reviewed, absent or stale artifact", () => {
    const cases = [
      { ...issue,status:"in_review" },
      { ...issue,executionState:{...issue.executionState,lastDecisionOutcome:"changes_requested"} },
      { ...issue,executionState:{...issue.executionState,lastDecisionId:null} },
      { ...issue,executionState:{...issue.executionState,completedStageIds:[]} },
      { ...issue,reviewPolicy:null,executionState:{...issue.executionState,returnAssignee:{type:"agent",agentId:"CHO"}} },
      { ...issue,workProducts:[] },
      { ...issue,workProducts:[{...issue.workProducts[0],metadata:{headSha:"b".repeat(40)}}] },
      { ...issue,workProducts:[{...issue.workProducts[0],url:"https://github.com/miloszspyrka-code/zar-i-szlif/pull/26"}] },
    ];
    for(const x of cases)expect(evaluateNativePaperclipReview(x,url,sha).ok).toBe(false);
    expect(evaluateNativePaperclipReview(issue,url,"b".repeat(40)).ok).toBe(false);
    expect(evaluateNativePaperclipReview(issue,"https://github.com/foreign/repo/pull/26",sha).ok).toBe(false);
  });
});

describe("GitHub App credential projection into noninteractive gh", () => {
  it("refuses to synthesize an auth environment from a missing credential", () => {
    // The test runtime does not mount a root-owned production token.
    // Do not mistake a placeholder for a real installation credential.
    const projected = scopedGhEnv();
    expect(projected === null || (typeof projected.GH_TOKEN === "string"
      && projected.GH_TOKEN === projected.GITHUB_TOKEN
      && projected.GH_PROMPT_DISABLED === "1")).toBe(true);
  });
});
