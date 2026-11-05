import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createWorkspaceNativeTools } from "./workspace-native.js";
import { createP1PlatformTools } from "./p1-platform.js";

const approvedTransport = vi.hoisted(() => ({ enabled: false, head: "", calls: [] as string[] }));
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  const { EventEmitter } = await import("node:events");
  const { PassThrough } = await import("node:stream");
  return {
    ...actual,
    spawn: ((command: string, args: string[], options: unknown) => {
      if (approvedTransport.enabled && command === "git" && (args.includes("push") || args.includes("ls-remote"))) {
        const child = new EventEmitter() as EventEmitter & {
          stdout: InstanceType<typeof PassThrough>;
          stderr: InstanceType<typeof PassThrough>;
          kill: (signal?: string) => boolean;
        };
        child.stdout = new PassThrough();
        child.stderr = new PassThrough();
        child.kill = () => true;
        const mode = args.includes("push") ? "push" : "ls-remote";
        approvedTransport.calls.push(mode);
        queueMicrotask(() => {
          if (mode === "ls-remote") child.stdout.write(approvedTransport.head + "\trefs/heads/KOMAA-TEST\n");
          child.stdout.end();
          child.stderr.end();
          child.emit("close", 0);
        });
        return child as never;
      }
      return actual.spawn(command, args, options as never);
    }) as typeof actual.spawn,
  };
});


const COMPANY = "11111111-1111-4111-8111-111111111111";
const AGENT = "ada5390b-b87e-43f3-a250-3657811e7a0c";
const OTHER = "ff703eba-3c3d-46f0-b265-df0db1101a19";
const ISSUE = "44444444-4444-4444-8444-444444444444";
const WORKSPACE = "55555555-5555-4555-8555-555555555555";
const RUN = "66666666-6666-4666-8666-666666666666";

const cleanupPaths: string[] = [];
afterEach(async () => {
  vi.unstubAllEnvs();
  approvedTransport.enabled = false;
  approvedTransport.head = "";
  approvedTransport.calls.length = 0;
  await Promise.all(cleanupPaths.splice(0).map(p => rm(p, { recursive: true, force: true })));
});
function git(cwd: string, ...args: string[]) {
  const p = spawnSync("git", args, { cwd, encoding: "utf8", timeout: 10000 });
  if (p.status !== 0) throw Error("git " + args[0] + " failed: " + p.stderr);
  return p.stdout.trim();
}
function fakeClient(cwd: string, runStatus = "running", runIssue = ISSUE, preflightOverride?: Record<string, unknown>) {
  const repoUrl = "https://github.com/miloszspyrka-code/harness-zar-i-szlif.git";
  const hash = (text: string) => createHash("sha256").update(text).digest("hex");
  const preflight = {
    issueId: ISSUE, agentId: AGENT, runId: RUN, workspaceId: WORKSPACE,
    repo: "miloszspyrka-code/harness-zar-i-szlif", repoUrl,
    baseSha: git(cwd, "rev-parse", "refs/remotes/origin/main"),
    readDocs: [
      { path: "README.md", sha256: hash("test repository\n") },
      { path: "AGENTS.md", sha256: hash("test instructions\n") },
    ],
    targetPaths: ["mcp/paperclip/**"], releaseLane: "test-only", decision: "PASS",
    ...(preflightOverride ?? {}),
  };
  return {
    callerApiKey: "agent-test-key",
    defaults: { runId: RUN },
    resolveCompanyId: () => COMPANY,
    getJsonOrNull: async (path: string) => {
      if (path === "/heartbeat-runs/" + RUN) return {
        agentId: AGENT, companyId: COMPANY, status: runStatus,
        contextSnapshot: { issueId: runIssue },
      };
      if (path === "/execution-workspaces/" + OTHER) return null;
      if (path === "/execution-workspaces/" + WORKSPACE) return {
        id: WORKSPACE, companyId: COMPANY, projectId: "77777777-7777-4777-8777-777777777777", sourceIssueId: ISSUE,
        branchName: "KOMAA-TEST", cwd,
      };
      if (path === `/issues/${ISSUE}/comments?limit=500`) return [{
        authorAgentId: AGENT, createdByRunId: RUN, body: `DOC_PREFLIGHT v1\n${JSON.stringify(preflight)}`,
      }];
      if (path.startsWith("/issues/" + ISSUE + "/documents")) return [];
      throw Error("unexpected getJsonOrNull " + path);
    },
    requestJson: async (_method: string, path: string) => {
      if (path === "/agents/me") return { id: AGENT };
      if (path === "/projects/77777777-7777-4777-8777-777777777777") return {
        codebase: { repoUrl, defaultRef: "main" },
      };
      if (path === "/issues/" + ISSUE) return {
        id: ISSUE, companyId: COMPANY, identifier: "KOMAA-TEST", status: "in_progress", reviewPolicy: "not_creator",
        executionPolicy: { stages: [{ type: "review", participants: [{ type: "agent", agentId: OTHER }] }] },
      };
      throw Error("unexpected requestJson " + path);
    },
  } as never;
}
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "agent-push-contract-"));
  cleanupPaths.push(root);
  const cwd = join(root, "work"), bare = join(root, "remote.git");
  await mkdir(cwd);
  await writeFile(join(cwd, "README.md"), "test repository\n");
  await writeFile(join(cwd, "AGENTS.md"), "test instructions\n");
  git(root, "init", "--bare", bare);
  git(cwd, "init", "-b", "KOMAA-TEST");
  git(cwd, "config", "user.name", "Test Git Agent");
  git(cwd, "config", "user.email", "ci@users.noreply.github.com");
  await mkdir(join(cwd, "mcp", "paperclip"), { recursive: true });
  await writeFile(join(cwd, "mcp", "paperclip", "delivery.txt"), "initial\n");
  git(cwd, "add", "--", "README.md", "AGENTS.md", "mcp/paperclip/delivery.txt");
  git(cwd, "commit", "-m", "initial test state");
  git(cwd, "update-ref", "refs/remotes/origin/main", git(cwd, "rev-parse", "HEAD"));
  git(cwd, "remote", "add", "origin", "https://github.com/miloszspyrka-code/harness-zar-i-szlif.git");
  git(cwd, "remote", "set-url", "--push", "origin", bare);
  await writeFile(join(cwd, "mcp", "paperclip", "delivery.txt"), "changed by agent run\n");
  return { cwd, bare, root };
}
describe("native agent-run git commit and push contract (local bare remote)", () => {
  it("commits using a valid run and verified document hashes", async () => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    vi.stubEnv("PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR", join(f.root, "ledger"));
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd)).find(x => x.name === "paperclipGitCommit")!;
    const result = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: verify scoped Git commit",
    });
    const committed = JSON.parse(result.content[0]!.text);
    expect(committed.after.head).toMatch(/^[0-9a-f]{40}$/);
    expect(committed.after.head).not.toBe(committed.before.head);
  });
  it("pushes approved canonical GitHub branch and confirms remote SHA with deterministic transport", async () => {
    const f = await fixture();
    git(f.cwd, "remote", "set-url", "--push", "origin", "https://github.com/miloszspyrka-code/harness-zar-i-szlif.git");
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    vi.stubEnv("GH_TOKEN", "ghp_" + "x".repeat(40));
    vi.stubEnv("GITHUB_TOKEN", "");
    vi.stubEnv("PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR", join(f.root, "ledger"));
    const tools = createWorkspaceNativeTools(fakeClient(f.cwd));
    const commit = tools.find(x => x.name === "paperclipGitCommit")!;
    const push = tools.find(x => x.name === "paperclipGitPush")!;
    const c = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: canonical push approved by preflight",
    });
    const committed = JSON.parse(c.content[0]!.text);
    expect(committed.after.head).toMatch(/^[0-9a-f]{40}$/);
    approvedTransport.enabled = true;
    approvedTransport.head = committed.after.head;
    const p = await push.execute({ workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN });
    const pushed = JSON.parse(p.content[0]!.text);
    expect(pushed.shaMatch).toBe(true);
    expect(pushed.remoteSha).toBe(committed.after.head);
    expect(approvedTransport.calls).toEqual(["push", "ls-remote"]);
  });
  it("rejects a local or redirected Git push destination", async () => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    vi.stubEnv("GH_TOKEN", "ghp_" + "x".repeat(40));
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd)).find(x => x.name === "paperclipGitCommit")!;
    const c = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: commit before redirected push rejection",
    });
    const committed = JSON.parse(c.content[0]!.text);
    expect(committed.after.head).toMatch(/^[0-9a-f]{40}$/);
    const push = createWorkspaceNativeTools(fakeClient(f.cwd)).find(x => x.name === "paperclipGitPush")!;
    const response = await push.execute({ workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN });
    expect(response.content[0]!.text).toMatch(/push_denied/i);
  });
  it.each([
    ["ended run", "succeeded", ISSUE],
    ["run bound to another issue", "running", OTHER],
  ])("refuses %s before creating any commit", async (_reason, status, boundIssue) => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR", join(f.root, "ledger"));
    const before = git(f.cwd, "rev-parse", "HEAD");
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd, status, boundIssue))
      .find(x => x.name === "paperclipGitCommit")!;
    const r = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: must not write",
    });
    expect(r.content[0]!.text).toMatch(/auth_failed|scope_denied/i);
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });

  it.each([
    ["missing document hashes", { readDocs: [] }],
    ["forged document hash", { readDocs: [{ path: "README.md", sha256: "0".repeat(64) }, { path: "AGENTS.md", sha256: "1".repeat(64) }] }],
    ["wrong repository", { repo: "someone-else/repo" }],
    ["unapproved path", { targetPaths: ["docs/**"] }],
    ["wrong run", { runId: OTHER }],
    ["stale base SHA", { baseSha: "f".repeat(40) }],
    ["secret-like material", { addedCredential: "ghp_" + "x".repeat(40) }],
  ])("refuses commit with %s before any Git mutation", async (_reason, override) => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR", join(f.root, "ledger"));
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    const before = git(f.cwd, "rev-parse", "HEAD");
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd, "running", ISSUE, override))
      .find(x => x.name === "paperclipGitCommit")!;
    const r = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: reject invalid documentation admission",
    });
    expect(r.content[0]!.text).toMatch(/doc_preflight_(denied|stale)/i);
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });

  it("refuses a workspace that is not bound to the issue before Git mutation", async () => {
    const f = await fixture();
    const before = git(f.cwd, "rev-parse", "HEAD");
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd)).find(x => x.name === "paperclipGitCommit")!;
    const r = await commit.execute({ workspaceId: OTHER, issueId: ISSUE, runId: RUN, files: ["mcp/paperclip/delivery.txt"], message: "test: reject wrong workspace" });
    expect(r.content[0]!.text).toMatch(/scope_denied|not_found/i);
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });

  it("refuses a DOC_PREFLIGHT pinned to an old default-branch ref", async () => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    const tree = git(f.cwd, "rev-parse", "HEAD^{tree}");
    const movedBase = git(f.cwd, "commit-tree", tree, "-m", "advanced origin main");
    git(f.cwd, "update-ref", "refs/remotes/origin/main", movedBase);
    const before = git(f.cwd, "rev-parse", "HEAD");
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd)).find(x => x.name === "paperclipGitCommit")!;
    const r = await commit.execute({ workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN, files: ["mcp/paperclip/delivery.txt"], message: "test: refuse stale base" });
    expect(r.content[0]!.text).toContain("doc_preflight_stale");
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });

  it("rejects a reviewer who is the writing agent", async () => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
    const client = fakeClient(f.cwd) as unknown as { requestJson: (method: string, path: string) => Promise<unknown> };
    const original = client.requestJson.bind(client);
    client.requestJson = async (method, path) => {
      const value = await original(method, path) as Record<string, unknown>;
      return path === "/issues/" + ISSUE
        ? { ...value, executionPolicy: { stages: [{ type: "review", participants: [{ type: "agent", agentId: AGENT }] }] } }
        : value;
    };
    const before = git(f.cwd, "rev-parse", "HEAD");
    const commit = createWorkspaceNativeTools(client as never).find(x => x.name === "paperclipGitCommit")!;
    const r = await commit.execute({ workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN, files: ["mcp/paperclip/delivery.txt"], message: "test: reject self review" });
    expect(r.content[0]!.text).toContain("doc_preflight_denied");
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });
  it.each(["paperclipWorkspaceBatchChange", "paperclipWorkspaceApplyUnifiedDiff"])(
    "rejects %s bypass without valid DOC_PREFLIGHT before writing a byte", async (name) => {
      const f = await fixture();
      vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "enforce");
      const file = join(f.cwd, "mcp", "paperclip", "delivery.txt");
      const before = await readFile(file, "utf8");
      const tool = createP1PlatformTools(fakeClient(f.cwd, "running", ISSUE, { targetPaths: ["docs/**"] }))
        .find(x => x.name === name)!;
      const input = name === "paperclipWorkspaceBatchChange"
        ? { workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN, changes: [{ path: "mcp/paperclip/delivery.txt", content: "WRONG\n" }] }
        : { workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN, path: "mcp/paperclip/delivery.txt",
            expectedSha: createHash("sha256").update(before).digest("hex"),
            unifiedDiff: "@@ -1 +1 @@\n-changed by agent run\n+WRONG\n" };
      const result = await tool.execute(input);
      expect(result.content[0]!.text).toContain("doc_preflight_denied");
      expect(await readFile(file, "utf8")).toBe(before);
    },
  );

  it("enforces canary issue selection, and refuses forged hashes for the selected run", async () => {
    const f = await fixture();
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_MODE", "canary");
    vi.stubEnv("PAPERCLIP_DOC_PREFLIGHT_CANARY_ISSUES", ISSUE);
    const commit = createWorkspaceNativeTools(fakeClient(f.cwd, "running", ISSUE, {
      readDocs: [{ path: "README.md", sha256: "f".repeat(64) }, { path: "AGENTS.md", sha256: "f".repeat(64) }],
    })).find(x => x.name === "paperclipGitCommit")!;
    const before = git(f.cwd, "rev-parse", "HEAD");
    const result = await commit.execute({
      workspaceId: WORKSPACE, issueId: ISSUE, runId: RUN,
      files: ["mcp/paperclip/delivery.txt"], message: "test: deny forged canary admission",
    });
    expect(result.content[0]!.text).toMatch(/doc_preflight_stale/i);
    expect(git(f.cwd, "rev-parse", "HEAD")).toBe(before);
  });

});
