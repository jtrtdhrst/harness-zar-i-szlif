#!/usr/bin/env node
/**
 * Plasmic MCP production release admission.
 *
 * Run from the checked-out repository before publishing or deploying a
 * production image. Fails closed if the production workflow builds a
 * different source tree than the reviewed canonical MCP code.
 *
 * --source-only validates the canonical Docker build safety without checking
 * GitHub Actions integration (useful for development/PR unit tests).
 *
 * No credentials, network calls, writes or Docker daemon access.
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../.."); // <repo>/plasmic-mcp/scripts -> <repo>
const problems = [];
// A missing canonical source file is a release blocker, not a crash: the CI
// assertion treats a non-zero exit as admissible only when it enumerates
// RELEASE_BLOCKED reasons.
const read = async (p) => {
  try {
    return await readFile(resolve(repo, p), "utf8");
  } catch (e) {
    problems.push(`cannot read ${p} (${e.code ?? e.message})`);
    return "";
  }
};

const dockerfile = await read("mcp/plasmic-mcp/Dockerfile");
if (dockerfile) {
  if (!dockerfile.includes("RUN npm ci --omit=dev --ignore-scripts")) {
    problems.push("Dockerfile must use lockfile-only npm ci --omit=dev --ignore-scripts");
  }
  if (/\|\|\s*npm\s+install|npm\s+install\s+--omit=dev/.test(dockerfile)) {
    problems.push("Dockerfile must not silently fall back to npm install");
  }
  if (!/^USER mcp\s*$/m.test(dockerfile)) {
    problems.push("Docker image must run as unprivileged mcp user");
  }
}

if (!process.argv.includes("--source-only")) {
  const workflow = await read(".github/workflows/opendesign-brand-mcp.yml");
  if (!workflow) {
    problems.push(
      "no canonical GHCR build workflow for plasmic-mcp in this repository; " +
        "release lane for plasmic-mcp is manual_only (scripts/service-coverage.json)",
    );
  } else {
    // Both the build context and dispatch paths must name the same canonical tree.
    if (!/^\s*context:\s*plasmic-mcp\s*$/m.test(workflow)) {
      problems.push("GHCR image workflow builds a noncanonical context; expected context: plasmic-mcp");
    }
    if (!/^\s*file:\s*plasmic-mcp\/Dockerfile\s*$/m.test(workflow)) {
      problems.push("GHCR image workflow does not use mcp/plasmic-mcp/Dockerfile");
    }
    if (!/^\s*-\s*["']?plasmic-mcp\/\*\*/m.test(workflow)) {
      problems.push("GHCR image workflow does not watch mcp/plasmic-mcp/** changes");
    }
    if (!/github\.ref\s*==\s*'refs\/heads\/main'/.test(workflow)) {
      problems.push("GHCR image workflow must gate image push on refs/heads/main");
    }
  }
}
if (problems.length) {
  for (const problem of problems) console.error(`RELEASE_BLOCKED: ${problem}`);
  process.exitCode = 1;
} else {
  console.log(process.argv.includes("--source-only")
    ? "SOURCE_PREFLIGHT_OK: deterministic non-root Dockerfile"
    : "RELEASE_PREFLIGHT_OK: reviewed canonical MCP source matches the GHCR build pipeline");
}
