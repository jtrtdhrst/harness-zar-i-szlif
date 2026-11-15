// Regresja procedury migracji wolumenu /state z README.
//
// Historia defektu: instrukcja używała `docker stop "$SERVICE"`, gdzie SERVICE
// był opisany jako "Coolify service id or Compose service name", oraz nie
// zatrzymywała się po błędzie. Przy nieudanym `stop` procedura nadal robiła
// backup, `chown -R` i weryfikację i kończyła się kodem 0 — czyli mutowała
// wolumen mimo działającego writera.
//
// Test wykonuje DOKŁADNIE blok z README (nie jego kopię) ze stubem `docker` na
// PATH. Prawdziwy docker ani prawdziwy wolumen nie są dotykane: stub obsługuje
// wszystkie wywołania i zapisuje je do logu.
import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, existsSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const README = join(here, "..", "README.md");

/** Blok ```bash z sekcji migracji wolumenu. */
function migrationBlock(): string {
  const readme = readFileSync(README, "utf8");
  const at = readme.indexOf("### Migrating a populated volume");
  assert.ok(at >= 0, "README must document the populated-volume migration");
  const fence = readme.slice(at).match(/```bash\n([\s\S]*?)```/);
  assert.ok(fence, "the migration section must contain a runnable bash block");
  return fence[1];
}

type Mode = "ok" | "fail-stop" | "still-running" | "backup-fails";

/** Uruchamia udokumentowaną procedurę ze stubem docker; zwraca log wywołań. */
function runMigration(mode: Mode): { status: number | null; calls: string[]; stderr: string } {
  const dir = mkdtempSync(join(tmpdir(), "state-migration-"));
  const bin = join(dir, "bin");
  const backup = join(dir, "backup");
  mkdirSync(bin);
  mkdirSync(backup);
  const log = join(dir, "docker.log");

  // Wartości, które operator wpisałby w miejsce placeholderów.
  const script = migrationBlock()
    .replaceAll("<container id or name>", "plasmic-mcp-1")
    .replaceAll("<state volume name>", "plasmic_mcp_state")
    .replaceAll("<absolute host path with free space>", backup);

  writeFileSync(
    join(bin, "docker"),
    `#!/usr/bin/env bash
printf '%s\\n' "$*" >> ${JSON.stringify(log)}
mode=${JSON.stringify(mode)}
case "$1" in
  stop)
    [ "$mode" = "fail-stop" ] && { echo "cannot stop container: simulated failure" >&2; exit 1; }
    exit 0 ;;
  inspect)
    case "$*" in
      *State.Running*) [ "$mode" = "still-running" ] && echo true || echo false; exit 0 ;;
      *".Mounts"*) echo plasmic_mcp_state; exit 0 ;;
      *) echo "[]"; exit 0 ;;
    esac ;;
  run)
    case "$*" in
      *"tar czf"*)
        [ "$mode" = "backup-fails" ] && exit 0
        host=""; prev=""
        for a in "$@"; do
          case "$prev" in -v) case "$a" in *:/backup) host="\${a%:/backup}" ;; esac ;; esac
          prev="$a"
        done
        name=$(printf '%s' "$*" | sed -n 's#.*tar czf /backup/\\([^ ]*\\) .*#\\1#p')
        [ -n "$host" ] && [ -n "$name" ] && printf 'archive' > "$host/$name"
        exit 0 ;;
      *) exit 0 ;;
    esac ;;
  *) exit 0 ;;
esac
`,
  );
  chmodSync(join(bin, "docker"), 0o755);

  const scriptPath = join(dir, "migrate.sh");
  writeFileSync(scriptPath, script);
  const r = spawnSync("bash", [scriptPath], {
    cwd: dir,
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}` },
    encoding: "utf8",
    timeout: 30000,
  });
  const calls = existsSync(log) ? readFileSync(log, "utf8").trim().split("\n").filter(Boolean) : [];
  return { status: r.status, calls, stderr: r.stderr || "" };
}

const chownRan = (calls: string[]) => calls.some((c) => c.includes("chown"));
const backupRan = (calls: string[]) => calls.some((c) => c.includes("tar czf"));

test("migration procedure is fail-fast", () => {
  const block = migrationBlock();
  assert.match(block, /set -euo pipefail/, "the procedure must abort on the first failure");
  assert.doesNotMatch(block, /\bSERVICE=/, "stop must target a real container, not an undefined service id");
});

test("a failed docker stop aborts before any volume mutation", () => {
  const { status, calls, stderr } = runMigration("fail-stop");
  assert.notEqual(status, 0, "a failed stop must not exit successfully");
  assert.equal(chownRan(calls), false, "chown must not run when the writer was not stopped");
  assert.equal(backupRan(calls), false, "backup must not run when the writer was not stopped");
  assert.match(stderr, /simulated failure/);
});

test("a container still reported running aborts before any volume mutation", () => {
  const { status, calls, stderr } = runMigration("still-running");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false, "chown must not run while the container is running");
  assert.match(stderr, /still running/);
});

test("a missing backup archive aborts before chown", () => {
  const { status, calls, stderr } = runMigration("backup-fails");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false, "chown must not run without a verified backup");
  assert.match(stderr, /missing or empty/);
});

test("the happy path stops, backs up, chowns, verifies and starts", () => {
  const { status, calls } = runMigration("ok");
  assert.equal(status, 0, "the documented procedure must succeed when every step succeeds");
  const order = (needle: string) => calls.findIndex((c) => c.includes(needle));
  assert.ok(order("stop") < order("tar czf"), "stop must precede the backup");
  assert.ok(order("tar czf") < order("chown"), "the backup must precede chown");
  assert.ok(order("chown") < order("start"), "the service must be started again after chown");
  assert.equal(chownRan(calls), true);
});
