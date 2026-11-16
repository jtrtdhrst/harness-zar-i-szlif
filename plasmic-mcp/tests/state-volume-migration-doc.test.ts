// Regresja procedury migracji wolumenu /state z README.
//
// Historia defektów:
//  1. instrukcja używała `docker stop "$SERVICE"` (Coolify service id ≠ nazwa
//     kontenera) i nie zatrzymywała się po błędzie: przy nieudanym `stop`
//     procedura nadal robiła backup, `chown -R` i weryfikację, kończąc kodem 0.
//  2. wariant Compose sprawdzał stop przez `... ps --status running | grep -qx`
//     jako lewą stronę `&&`, więc BŁĄD `docker compose ps` (demon nieosiągalny)
//     był traktowany jak "zatrzymane" i procedura szła dalej do `chown`.
//
// Test wykonuje DOKŁADNIE bloki z README (nie ich kopie) ze stubem `docker` na
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

/** Bloki ```bash z sekcji migracji wolumenu, w kolejności dokumentu. */
function migrationBlocks(): string[] {
  const readme = readFileSync(README, "utf8");
  const at = readme.indexOf("### Migrating a populated volume");
  assert.ok(at >= 0, "README must document the populated-volume migration");
  const blocks = [...readme.slice(at).matchAll(/```bash\n([\s\S]*?)```/g)].map((m) => m[1]);
  assert.ok(blocks.length >= 2, "README must document both the docker and the Compose procedure");
  return blocks;
}

const primaryBlock = () => migrationBlocks()[0];
const composeBlock = () => migrationBlocks()[1];

type Mode =
  | "ok"
  | "fail-stop"
  | "still-running"
  | "backup-fails"
  | "running"
  | "ps-error"
  | "mount-mismatch"
  | "enum-error";

/** Wartości, które operator wpisałby w miejsce placeholderów. */
function fill(block: string, backup: string): string {
  return block
    .replaceAll("<container id or name>", "plasmic-mcp-1")
    .replaceAll("<state volume name>", "plasmic_mcp_state")
    .replaceAll("<absolute host path with free space>", backup)
    .replaceAll("<compose project>", "plasmic-mcp")
    .replaceAll("<service name>", "mcp");
}

/** Stub `docker`: loguje każde wywołanie i realizuje tryb awarii. */
const stub = (log: string, mode: Mode) => `#!/usr/bin/env bash
printf '%s\\n' "$*" >> ${JSON.stringify(log)}
mode=${JSON.stringify(mode)}
if [ "$1" = "compose" ]; then
  case "$*" in
    *"--all --quiet"*)
      [ "$mode" = "enum-error" ] && { echo "cannot connect to the docker daemon" >&2; exit 1; }
      echo "cid-1"; exit 0 ;;
    *"ps --status running"*)
      [ "$mode" = "ps-error" ] && { echo "cannot connect to the docker daemon" >&2; exit 1; }
      [ "$mode" = "running" ] && echo "mcp"
      exit 0 ;;
    *) exit 0 ;;
  esac
fi
case "$1" in
  stop)
    [ "$mode" = "fail-stop" ] && { echo "cannot stop container: simulated failure" >&2; exit 1; }
    exit 0 ;;
  inspect)
    case "$*" in
      *".Mounts"*)
        [ "$mode" = "mount-mismatch" ] && echo "some_other_volume" || echo "plasmic_mcp_state"
        exit 0 ;;
      *State.Running*)
        [ "$mode" = "still-running" ] && echo true || echo false
        exit 0 ;;
      *) echo "[]"; exit 0 ;;
    esac ;;
  volume) exit 0 ;;
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
`;

/** Uruchamia udokumentowany blok ze stubem docker; zwraca log wywołań. */
function run(block: string, mode: Mode): { status: number | null; calls: string[]; stderr: string } {
  const dir = mkdtempSync(join(tmpdir(), "state-migration-"));
  const bin = join(dir, "bin");
  const backup = join(dir, "backup");
  mkdirSync(bin);
  mkdirSync(backup);
  const log = join(dir, "docker.log");

  const scriptPath = join(dir, "migrate.sh");
  writeFileSync(scriptPath, fill(block, backup));
  writeFileSync(join(bin, "docker"), stub(log, mode));
  chmodSync(join(bin, "docker"), 0o755);

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
const order = (calls: string[], needle: string) => calls.findIndex((c) => c.includes(needle));

// ── primary (single container) procedure ────────────────────────────────────

test("migration procedure is fail-fast", () => {
  const block = primaryBlock();
  assert.match(block, /set -euo pipefail/, "the procedure must abort on the first failure");
  assert.doesNotMatch(block, /\bSERVICE=/, "stop must target a real container, not an undefined service id");
});

test("a failed docker stop aborts before any volume mutation", () => {
  const { status, calls, stderr } = run(primaryBlock(), "fail-stop");
  assert.notEqual(status, 0, "a failed stop must not exit successfully");
  assert.equal(chownRan(calls), false, "chown must not run when the writer was not stopped");
  assert.equal(backupRan(calls), false, "backup must not run when the writer was not stopped");
  assert.match(stderr, /simulated failure/);
});

test("a container still reported running aborts before any volume mutation", () => {
  const { status, calls, stderr } = run(primaryBlock(), "still-running");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false, "chown must not run while the container is running");
  assert.match(stderr, /still running/);
});

test("a missing backup archive aborts before chown", () => {
  const { status, calls, stderr } = run(primaryBlock(), "backup-fails");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false, "chown must not run without a verified backup");
  assert.match(stderr, /missing or empty/);
});

test("the happy path stops, backs up, chowns, verifies and starts", () => {
  const { status, calls } = run(primaryBlock(), "ok");
  assert.equal(status, 0, "the documented procedure must succeed when every step succeeds");
  assert.ok(order(calls, "stop") < order(calls, "tar czf"), "stop must precede the backup");
  assert.ok(order(calls, "tar czf") < order(calls, "chown"), "the backup must precede chown");
  assert.ok(order(calls, "chown") < order(calls, "start"), "the service must be started again after chown");
  assert.equal(chownRan(calls), true);
});

// ── Compose-managed procedure ───────────────────────────────────────────────

test("the Compose procedure is self-contained and fail-fast", () => {
  const block = composeBlock();
  assert.match(block, /set -euo pipefail/, "the Compose procedure must abort on the first failure");
  assert.match(block, /chown -R 10001:10001 \/state/, "the Compose block must carry the full procedure");
  assert.doesNotMatch(
    block,
    /\|\s*grep\s+-qx[^\n]*\\?\n?\s*&&/,
    "a discarded pipeline status must not guard the stop step — under set -e that reads as 'verified safe'",
  );
  assert.match(block, /if ! RUNNING=/, "the stop verification must capture the query and abort when it fails");
});

test("Compose: a ps error aborts before chown instead of reading as 'stopped'", () => {
  const { status, calls, stderr } = run(composeBlock(), "ps-error");
  assert.notEqual(status, 0, "an unverifiable stop must not exit successfully");
  assert.equal(chownRan(calls), false, "a failed `docker compose ps` must not fall through to chown");
  assert.match(stderr, /cannot verify/);
});

test("Compose: a still-running service aborts before chown", () => {
  const { status, calls, stderr } = run(composeBlock(), "running");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false);
  assert.match(stderr, /still running/);
});

test("Compose: the service container must mount this volume at /state", () => {
  const mismatch = run(composeBlock(), "mount-mismatch");
  assert.notEqual(mismatch.status, 0, "a volume mismatch must abort");
  assert.equal(chownRan(mismatch.calls), false, "an unrelated volume must never be chowned");
  assert.match(mismatch.stderr, /not plasmic_mcp_state/);

  const unverifiable = run(composeBlock(), "enum-error");
  assert.notEqual(unverifiable.status, 0, "a failed container lookup must abort");
  assert.equal(chownRan(unverifiable.calls), false);
  assert.match(unverifiable.stderr, /cannot enumerate/);
});

test("Compose: a missing backup archive aborts before chown", () => {
  const { status, calls, stderr } = run(composeBlock(), "backup-fails");
  assert.notEqual(status, 0);
  assert.equal(chownRan(calls), false);
  assert.match(stderr, /missing or empty/);
});

test("Compose happy path binds, stops, backs up, chowns, verifies and starts", () => {
  const { status, calls } = run(composeBlock(), "ok");
  assert.equal(status, 0, "the documented Compose procedure must succeed when every step succeeds");
  assert.ok(order(calls, ".Mounts") >= 0, "the binding must be checked before anything is touched");
  assert.ok(order(calls, "stop") < order(calls, "tar czf"), "stop must precede the backup");
  assert.ok(order(calls, "tar czf") < order(calls, "chown"), "the backup must precede chown");
  assert.ok(order(calls, "chown") < order(calls, "start"), "the service must be started again after chown");
  assert.equal(chownRan(calls), true);
});
