import { constants } from "node:fs";
import { access, mkdir } from "node:fs/promises";

/**
 * Stan MCP trzymany jest na wolumenie (/state). Obraz działa jako
 * nieuprzywilejowany użytkownik `mcp` (uid 10001) z read-only rootfs, więc
 * katalog stanu musi należeć do tego użytkownika. Gdy wolumen został
 * zainicjalizowany przez wcześniejszy obraz działający jako root, zapis kończy
 * się gołym EACCES, które nie mówi, co naprawić.
 */

export interface StateDirProbe {
  ok: boolean;
  detail?: string;
}

const uid = () => (typeof process.getuid === "function" ? process.getuid() : "?");

export function stateDirHint(dir: string): string {
  return `${dir} must be owned by the container user (uid 10001 / mcp); ` +
    `initialise the volume once with: docker run --rm -v <state-volume>:/state alpine chown 10001:10001 /state`;
}

/** Sprawdza (bez zapisu danych) czy katalog stanu da się utworzyć i zapisać. */
export async function probeStateDir(dir: string): Promise<StateDirProbe> {
  try {
    await mkdir(dir, { recursive: true });
    await access(dir, constants.W_OK);
    return { ok: true };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code ?? "UNKNOWN";
    return { ok: false, detail: `${code}: ${stateDirHint(dir)} (process uid ${uid()})` };
  }
}

/**
 * Twarda bramka dla ścieżek zapisu: zamiast surowego EACCES zwraca błąd z
 * konkretną ścieżką, uid procesu i instrukcją naprawy.
 */
export async function requireWritableStateDir(dir: string, purpose: string): Promise<void> {
  const probe = await probeStateDir(dir);
  if (!probe.ok) {
    throw new Error(`STATE_DIR_UNWRITABLE (${purpose}): ${probe.detail}`);
  }
}
