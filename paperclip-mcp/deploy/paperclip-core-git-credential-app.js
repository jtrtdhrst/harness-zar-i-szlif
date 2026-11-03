#!/usr/local/bin/node
"use strict";
// Git credential-helper protocol. No static PAT. App token is updated by the
// root-owned rotation timer and accepted for exactly two HTTPS repository paths.
const fs = require("node:fs");
const action = process.argv[2] || "";
if (action !== "get") process.exit(0);
const fields = Object.fromEntries(
  fs.readFileSync(0, "utf8").split("\n").filter(Boolean).map((line) => {
    const equals = line.indexOf("=");
    return equals >= 0 ? [line.slice(0, equals), line.slice(equals + 1)] : ["", ""];
  })
);
const path = String(fields.path || "").replace(/\.git$/, "").replace(/^\/+|\/+$/g, "");
const repos = [
  "miloszspyrka-code/harness-zar-i-szlif",
  "miloszspyrka-code/zar-i-szlif",
];
if (fields.protocol !== "https" || fields.host !== "github.com" || !repos.includes(path)) process.exit(0);
try {
  const filename = "/paperclip/.github-app-installation-token.json";
  const stat = fs.lstatSync(filename);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 100 || stat.size > 8192 || (stat.mode & 0o077) !== 0) process.exit(0);
  const p = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (p.app_id !== 5398752 || p.installation_id !== 173456397) process.exit(0);
  if (JSON.stringify(p.repositories) !== JSON.stringify(repos)) process.exit(0);
  if (!p.permissions || p.permissions.contents !== "write" || p.permissions.pull_requests !== "write"
      || p.permissions.metadata !== "read" || ![undefined, "read"].includes(p.permissions.checks)
      || ![3, 4].includes(Object.keys(p.permissions).length)
      || Object.keys(p.permissions).some((k) => !["contents","pull_requests","metadata","checks"].includes(k))) process.exit(0);
  if (typeof p.token !== "string" || p.token.length < 40 || p.token.length > 512 || /\s/.test(p.token)) process.exit(0);
  if (typeof p.expires_at !== "string" || Date.parse(p.expires_at) < Date.now() + 120000) process.exit(0);
  process.stdout.write("username=x-access-token\npassword=" + p.token + "\n");
} catch {
  process.exit(0);
}
