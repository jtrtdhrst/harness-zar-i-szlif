import { EventEmitter } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PaperclipApiClient } from "./client.js";
import { createWorkspaceNativeTools, ghEnv, runJailedExec, isAllowedReadOnlyGithubApiArgv, nativeGitPushBranchAllowed, assertAllowedPublicationRepo } from "./workspace-native.js";

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn: spawnMock }));

const COMPANY = "11111111-1111-1111-1111-111111111111";
// Explicitly authorized implementation agent; the global Git publisher role filter is enforced.
const AGENT = "3fe90c23-8386-40d5-b0a8-52d8c40f812e";
const ISSUE = "44444444-4444-4444-8444-444444444444";
const OTHER_ISSUE = "66666666-6666-4666-8666-666666666666";
const RUN = "77777777-7777-4777-8777-777777777777";
const WORKSPACE = "55555555-5555-4555-8555-555555555555";

function client() {
  return new PaperclipApiClient({
    apiUrl: "http://localhost:3100/api",
    apiKey: "test",
    companyId: COMPANY,
    agentId: AGENT,
    runId: null,
    agentApiKey: null,
    boardApiKey: null,
  });
}

function tool(name: string) {
  const found = createWorkspaceNativeTools(client()).find((candidate) => candidate.name === name);
  if (!found) throw new Error(`missing ${name}`);
  return found;
}

describe("GitHub checks fail closed without prompting", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    spawnMock.mockReset();
  });

  it.each(["paperclipGitGetChecks", "paperclipGitGetMergeReadiness"])("returns GITHUB_AUTH_MISSING for %s before workspace or gh access", async (name) => {
    vi.stubEnv("GH_TOKEN", "");
    vi.stubEnv("GITHUB_TOKEN", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await tool(name).execute({ issueId: ISSUE, workspaceId: WORKSPACE });

    expect(result.content[0]?.text).toContain("GITHUB_AUTH_MISSING");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sets non-interactive GitHub and git environment flags", () => {
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("GITHUB_TOKEN", "");
    expect(ghEnv()).toMatchObject({
      GH_TOKEN: "test-token",
      GH_PROMPT_DISABLED: "1",
      GIT_TERMINAL_PROMPT: "0",
    });
  });
});

describe("agent Git ancestry preflight under jailed workspace exec", () => {
  afterEach(() => spawnMock.mockReset());

  it("permits read-only rev-list, merge-base and cat-file without opening destructive git commands", async () => {
    const temp = await mkdtemp(join(tmpdir(), "paperclip-git-preflight-"));
    const old = process.env.PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR;
    process.env.PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR = temp;
    const ws = { cwd: process.cwd(), workspaceId: WORKSPACE } as never;
    spawnMock.mockImplementation((_command: string, args: string[]) => {
      const child = new EventEmitter() as EventEmitter & { stdout: EventEmitter; stderr: EventEmitter; kill: ReturnType<typeof vi.fn> };
      child.stdout = new EventEmitter();
      child.stderr = new EventEmitter();
      child.kill = vi.fn();
      queueMicrotask(() => {
        const stdout = args.includes("--count") ? "1\n" : args.includes("-t") ? "commit\n" : `${"a".repeat(40)}\n`;
        child.stdout.emit("data", Buffer.from(stdout));
        child.emit("close", 0);
      });
      return child;
    });
    try {
      const rev = await runJailedExec({ ws, argv: ["git", "rev-list", "--count", "HEAD"] });
      expect(rev.exitCode).toBe(0);
      expect(Number(rev.stdout.trim())).toBeGreaterThan(0);
      const base = await runJailedExec({ ws, argv: ["git", "merge-base", "HEAD", "HEAD"] });
      expect(base.exitCode).toBe(0);
      expect(base.stdout.trim()).toMatch(/^[a-f0-9]{40}$/);
      const type = await runJailedExec({ ws, argv: ["git", "cat-file", "-t", "HEAD"] });
      expect(type.exitCode).toBe(0);
      expect(type.stdout.trim()).toBe("commit");
      await expect(runJailedExec({ ws, argv: ["git", "reset", "--hard"] })).rejects.toThrow(/not allowlisted/);
      expect(spawnMock).toHaveBeenCalledTimes(3);
    } finally {
      if (old === undefined) delete process.env.PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR;
      else process.env.PAPERCLIP_WORKSPACE_OPS_LEDGER_DIR = old;
      await rm(temp, { recursive: true, force: true });
    }
  });
});

describe("run-bound Git delivery tool handlers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    spawnMock.mockReset();
  });

  function gitTool(name: "paperclipGitCommit" | "paperclipGitPush") {
    const found = createWorkspaceNativeTools(client()).find((candidate) => candidate.name === name);
    if (!found) throw new Error(`missing ${name}`);
    return found;
  }

  function mockRun(status: string, issueId: string) {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.endsWith("/agents/me")) return new Response(JSON.stringify({ id: AGENT }), { status: 200 });
      if (url.endsWith(`/heartbeat-runs/${RUN}`)) return new Response(JSON.stringify({
        id: RUN, companyId: COMPANY, agentId: AGENT, status, contextSnapshot: { issueId },
      }), { status: 200 });
      if (url.endsWith(`/execution-workspaces/${WORKSPACE}`)) return new Response(JSON.stringify({
        id: WORKSPACE, companyId: COMPANY, sourceIssueId: ISSUE, cwd: process.cwd(), branchName: "KOMAA-1465",
      }), { status: 200 });
      if (url.endsWith(`/issues/${ISSUE}`)) return new Response(JSON.stringify({
        id: ISSUE, companyId: COMPANY, identifier: "KOMAA-1465", status: "in_progress",
      }), { status: 200 });
      if (url.includes(`/issues/${ISSUE}/documents`)) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({ error: "unexpected request" }), { status: 404 });
    }));
    return requests;
  }

  function mockGit() {
    let head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const nextHead = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    spawnMock.mockImplementation((_command: string, args: string[]) => {
      const child = new EventEmitter() as EventEmitter & {
        stdout: EventEmitter;
        stderr: EventEmitter;
        kill: ReturnType<typeof vi.fn>;
      };
      child.stdout = new EventEmitter();
      child.stderr = new EventEmitter();
      child.kill = vi.fn();
      queueMicrotask(() => {
        const joined = args.join(" ");
        let stdout = "";
        if (joined.includes("rev-parse --abbrev-ref HEAD")) stdout = "KOMAA-1465\n";
        else if (joined.includes("rev-parse HEAD")) stdout = `${head}\n`;
        else if (joined.includes("diff --cached --name-only")) stdout = "src/workspace-native.test.ts\n";
        else if (joined.includes("diff --cached")) stdout = "diff --git a/src/workspace-native.test.ts b/src/workspace-native.test.ts\n+test\n";
        else if (joined.includes("ls-remote origin KOMAA-1465")) stdout = `${head}\trefs/heads/KOMAA-1465\n`;
        else if (joined.includes("commit -m")) { head = nextHead; stdout = "[KOMAA-1465 bbbbbbb] test\n"; }
        child.stdout.emit("data", Buffer.from(stdout));
        child.emit("close", 0);
      });
      return child;
    });
  }

  it.each(["paperclipGitCommit", "paperclipGitPush"] as const)("refuses %s for a live run bound to another issue before any Git subprocess", async (name) => {
    const requests = mockRun("running", OTHER_ISSUE);
    const input = name === "paperclipGitCommit"
      ? { issueId: ISSUE, workspaceId: WORKSPACE, files: ["src/workspace-native.test.ts"], message: "test: KOMAA-1465 deny cross issue", runId: RUN }
      : { issueId: ISSUE, workspaceId: WORKSPACE, runId: RUN };

    const result = await gitTool(name).execute(input);

    expect(result.content[0]?.text).toContain("scope_denied");
    expect(requests).toHaveLength(3);
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it.each(["paperclipGitCommit", "paperclipGitPush"] as const)("refuses %s when the supplied run has ended before any Git subprocess", async (name) => {
    const requests = mockRun("succeeded", ISSUE);
    const input = name === "paperclipGitCommit"
      ? { issueId: ISSUE, workspaceId: WORKSPACE, files: ["src/workspace-native.test.ts"], message: "test: KOMAA-1465 deny ended run", runId: RUN }
      : { issueId: ISSUE, workspaceId: WORKSPACE, runId: RUN };

    const result = await gitTool(name).execute(input);

    expect(result.content[0]?.text).toContain("auth_failed");
    expect(result.content[0]?.text).toContain("not live");
    expect(requests).toHaveLength(2);
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it.each(["paperclipGitCommit", "paperclipGitPush"] as const)("allows %s for the caller's own running issue-bound run", async (name) => {
    mockRun("running", ISSUE);
    mockGit();
    vi.stubEnv("GH_TOKEN", "test-token");
    vi.stubEnv("PAPERCLIP_GITHUB_OPS_LEDGER_DIR", process.env.TMPDIR || "/tmp");
    const input = name === "paperclipGitCommit"
      ? { issueId: ISSUE, workspaceId: WORKSPACE, files: ["src/workspace-native.test.ts"], message: "test: KOMAA-1465 authorized commit", runId: RUN }
      : { issueId: ISSUE, workspaceId: WORKSPACE, runId: RUN };

    const result = await gitTool(name).execute(input);
    const body = JSON.parse(result.content[0]?.text ?? "{}");

    expect(body.error).toBeUndefined();
    expect(body.attribution).toMatchObject({ authority: "agent-run", runId: RUN, agentId: AGENT, runIssueId: ISSUE });
    expect(spawnMock.mock.calls.some(([, args]) => args.includes(name === "paperclipGitCommit" ? "commit" : "push"))).toBe(true);
    if (name === "paperclipGitCommit") expect(body.after.head).toBe("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    else expect(body.shaMatch).toBe(true);
  });
});

describe("read-only GitHub REST command boundary", () => {
  const base = "repos/miloszspyrka-code/harness-zar-i-szlif/";
  const product = "repos/miloszspyrka-code/zar-i-szlif/";
  it("permits exact native checks/review reads", () => {
    for (const args of [
      ["gh","api",base+"commits/KOMAA-1465","--jq",".sha"],
      ["gh","api",product+"commits/feature%2Fsafe","--jq",".sha"],
      ["gh","api",base+"commits/"+"a".repeat(40)+"/check-runs?per_page=100"],
      ["gh","api",base+"pulls?head=miloszspyrka-code:KOMAA-1465&state=all&per_page=5"],
      ["gh","api",product+"pulls/141"],
      ["gh","api",base+"pulls/17/reviews?per_page=100"],
    ]) expect(isAllowedReadOnlyGithubApiArgv(args)).toBe(true);
  });
  it("rejects gh api mutations, foreign repos, custom flags and excess data", () => {
    for (const args of [
      ["gh","api",base+"pulls","--method","POST"],
      ["gh","api",base+"pulls","-F","title=bad"],
      ["gh","api",base+"pulls/17","--method","PATCH"],
      ["gh","api","repos/other/foreign/pulls/1"],
      ["gh","api",base+"actions/secrets"],
      ["gh","api",base+"contents/private"],
      ["gh","api",base+"pulls/17/comments"],
      ["gh","api",base+"pulls/17","--jq",".token"],
      ["gh","api",base+"pulls/17/reviews?per_page=200"],
      ["gh","api",base+"commits/..%2F..%2Funsafe","--jq",".sha"],
      ["gh","api",base+"pulls?state=all"],
      ["gh","api",base+"commits/"+"a".repeat(40)+"/check-runs?per_page=100","--method","POST"],
    ]) expect(isAllowedReadOnlyGithubApiArgv(args)).toBe(false);
  });
});

describe("native Git push branch protection", () => {
  it("rejects direct pushes to main and release even with allowProtected", () => {
    for (const branch of ["main","master","release/panel-stable-20261027"]) {
      expect(nativeGitPushBranchAllowed(branch,false)).toBe(false);
      expect(nativeGitPushBranchAllowed(branch,true)).toBe(false);
    }
  });
  it("permits dedicated implementation branches", () => {
    for (const branch of ["fix/KOMAA-1512","feature/new-panel","test/canary"]) {
      expect(nativeGitPushBranchAllowed(branch)).toBe(true);
    }
  });
});

describe("Git publication is restricted to owned origins, never official Paperclip upstream", () => {
  it.each([
    "https://github.com/miloszspyrka-code/paperclip.git",
    "git@github.com:miloszspyrka-code/paperclip.git",
    "ssh://git@github.com/miloszspyrka-code/paperclip.git",
    "https://github.com/miloszspyrka-code/zar-i-szlif",
    "https://github.com/miloszspyrka-code/harness-zar-i-szlif.git",
  ])("permits the authorized origin %s", (url) => {
    expect(assertAllowedPublicationRepo(url)).toMatch(/^miloszspyrka-code\//);
  });

  it.each([
    "https://github.com/paperclipai/paperclip.git",
    "git@github.com:paperclipai/paperclip.git",
    "https://github.com/miloszspyrka-code/random-repository.git",
    "https://github.com/other/paperclip.git",
    "https://github.com/miloszspyrka-code/paperclip.git/../other",
    "https://evil.example/github.com/miloszspyrka-code/paperclip.git",
    "https://github.com/miloszspyrka-code/paperclip.git?redirect=upstream",
    "",
  ])("refuses foreign/upstream or ambiguous destination %s", (url) => {
    expect(() => assertAllowedPublicationRepo(url)).toThrow(/restricted to owned repositories/);
  });
});
