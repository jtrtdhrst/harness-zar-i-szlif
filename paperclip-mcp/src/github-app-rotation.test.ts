import { describe, expect, it } from "vitest";
import { validateGithubAppTokenRecord, readBoundGitToken } from "./workspace-native.js";
import { deriveScopedInstallationPermissions } from "./p1-git.js";

const MOCK_TOKEN = "ghs_" + "x".repeat(75);
const NOW = Date.UTC(2026, 10, 3, 14, 20, 0);
function scoped() {
  return {
    token: MOCK_TOKEN,
    expires_at: new Date(NOW + 3600_000).toISOString(),
    app_id: 5398752,
    installation_id: 173456397,
    repositories: ["miloszspyrka-code/harness-zar-i-szlif", "miloszspyrka-code/zar-i-szlif"],
    permissions: { contents: "write", pull_requests: "write", metadata: "read" },
  };
}
describe("short-lived GitHub App credential verification", () => {
  it("accepts exactly the two approved repositories and write scopes", () => {
    expect(validateGithubAppTokenRecord(scoped(), NOW)).toBe(MOCK_TOKEN);
  });
  it("fails closed on expired token and near-expiry token", () => {
    expect(validateGithubAppTokenRecord({ ...scoped(), expires_at: new Date(NOW - 1).toISOString() }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), expires_at: new Date(NOW + 60_000).toISOString() }, NOW)).toBeNull();
  });
  it("accepts Checks read during scoped token rollout and rejects write or over-grant", () => {
    const minimal = scoped();
    expect(validateGithubAppTokenRecord({
      ...minimal,
      permissions: { ...minimal.permissions, checks: "read" },
    }, NOW)).toBe(MOCK_TOKEN);
    expect(validateGithubAppTokenRecord({
      ...minimal,
      permissions: { ...minimal.permissions, checks: "write" },
    }, NOW)).toBeNull();
  });
  it("rejects token with expanded repository scope", () => {
    expect(validateGithubAppTokenRecord({ ...scoped(), repositories: [...scoped().repositories, "some/other-repo"] }, NOW)).toBeNull();
  });
  it("rejects permissions above / below requested grants", () => {
    expect(validateGithubAppTokenRecord({ ...scoped(), permissions: { contents: "admin", pull_requests: "write", metadata: "read" } }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), permissions: { contents: "read", pull_requests: "write", metadata: "read" } }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), permissions: { ...scoped().permissions, administration: "write" } }, NOW)).toBeNull();
  });
  it("rejects identity drift, missing token and malformed timestamps", () => {
    expect(validateGithubAppTokenRecord({ ...scoped(), app_id: 0 }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), installation_id: 0 }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), token: null }, NOW)).toBeNull();
    expect(validateGithubAppTokenRecord({ ...scoped(), expires_at: "yesterday" }, NOW)).toBeNull();
  });
  it("correctly interprets installation grants despite user-centric permission flags", () => {
    expect(deriveScopedInstallationPermissions("miloszspyrka-code/zar-i-szlif").allowedOperations).toContain("push");
    expect(deriveScopedInstallationPermissions("miloszspyrka-code/harness-zar-i-szlif").allowedOperations).toContain("create_pr");
    expect(deriveScopedInstallationPermissions("someone/else").allowedOperations).toEqual([]);
  });
  it("refuses legacy PAT fallback when the installation token file is configured", () => {
    expect(readBoundGitToken({ PAPERCLIP_GITHUB_APP_TOKEN_FILE: "/tmp/missing-token.json", GH_TOKEN: "legacy-PAT" })).toBeNull();
  });
});
