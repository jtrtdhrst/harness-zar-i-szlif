import { describe, expect, it } from "vitest";
import { gitPublicationAllowed, assertGitPublicationRole } from "./workspace-native.js";
const ENGINEER = "3fe90c23-8386-40d5-b0a8-52d8c40f812e";
const HARNESS = "ada5390b-b87e-43f3-a250-3657811e7a0c";
const MCP_ENGINEER = "1a9eba12-8a05-4a58-ac99-17d1bc80ed62";
const CHO = "5595f2c4-95e2-4c3e-97b4-c00d4e4d6601";
const CTO = "ff703eba-3c3d-46f0-b265-df0db1101a19";
const MASCOT = "43957949-8d00-4020-85d7-b69caf71d8c2";

describe("Git role scope / fail-closed publication", () => {
  it("grants implementation operations only to three coding agents", () => {
    for (const id of [ENGINEER, HARNESS, MCP_ENGINEER]) {
      expect(gitPublicationAllowed(id, "paperclipGitPush")).toBe(true);
      expect(gitPublicationAllowed(id, "paperclipGitCreatePR")).toBe(true);
      expect(gitPublicationAllowed(id, "paperclipWorkspaceExec")).toBe(true);
      expect(gitPublicationAllowed(id, "paperclipGitMergePR")).toBe(false);
    }
  });
  it("allows CHO and CTO to merge, not implement or run generic commands", () => {
    for (const id of [CHO, CTO]) {
      expect(gitPublicationAllowed(id, "paperclipGitMergePR")).toBe(true);
      expect(gitPublicationAllowed(id, "paperclipGitPush")).toBe(false);
      expect(gitPublicationAllowed(id, "paperclipWorkspaceExec")).toBe(false);
    }
  });
  it("denies non-coding agents all publication actions", () => {
    for (const name of ["paperclipGitPush", "paperclipGitMergePR", "paperclipGitCreatePR", "paperclipWorkspaceExec"]) {
      expect(gitPublicationAllowed(MASCOT, name)).toBe(false);
    }
  });
  it("verifies the caller identity instead of trusting caller-supplied agent IDs", async () => {
    const fakeClient = (id: string) => ({
      callerApiKey: "non-board-canary",
      requestJson: async (_method: string, path: string) => {
        if (path === "/agents/me") return { id };
        throw Error("Unexpected probe");
      },
    });
    await expect(assertGitPublicationRole(fakeClient(CHO) as never, "paperclipGitPush")).rejects.toThrow(/role denied/);
    await expect(assertGitPublicationRole(fakeClient(ENGINEER) as never, "paperclipGitPush")).resolves.toBeUndefined();
  });
  it("denies push to the reviewer role and merge to the implementation role", async () => {
    const fakeClient = (id: string) => ({
      callerApiKey: "non-board-canary",
      requestJson: async (_method: string, path: string) => {
        if (path === "/agents/me") return { id };
        throw Error("Unexpected probe");
      },
    });
    await expect(assertGitPublicationRole(fakeClient(CHO) as never, "paperclipGitPush")).rejects.toThrow(/role denied/);
    await expect(assertGitPublicationRole(fakeClient(HARNESS) as never, "paperclipGitMergePR")).rejects.toThrow(/role denied/);
  });
});
