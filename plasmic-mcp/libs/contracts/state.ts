import { mkdir, open, unlink } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

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
    `initialise the volume once with: docker run --rm -v <state-volume>:/state alpine chown -R 10001:10001 /state`;
}

/** Zamienia błąd zapisu na diagnostykę z konkretną ścieżką i uid procesu. */
function probeFailure(dir: string, e: unknown): StateDirProbe {
  const code = (e as NodeJS.ErrnoException).code ?? "UNKNOWN";
  return { ok: false, detail: `${code}: ${stateDirHint(dir)} (process uid ${uid()})` };
}

/**
 * Sprawdza, czy katalog stanu naprawdę da się zapisać.
 *
 * `access(dir, W_OK)` tylko pyta jądro o bity trybu i potrafi zwrócić OK na
 * wolumenie, na którym pierwszy rzeczywisty zapis i tak kończy się EACCES
 * (odziedziczone ACL, read-only mount, brak prawa przejścia w katalogu
 * nadrzędnym). Dlatego próbujemy dokładnie tej operacji, którą wykonują
 * narzędzia: wyłącznego utworzenia pliku, zapisu i usunięcia. Po próbie nic nie
 * zostaje na wolumenie.
 */
export async function probeStateDir(dir: string): Promise<StateDirProbe> {
  try {
    await mkdir(dir, { recursive: true });
  } catch (e) {
    return probeFailure(dir, e);
  }
  const probePath = join(dir, `.write-probe-${process.pid}-${randomUUID()}`);
  try {
    // "wx" = utwórz wyłącznie (O_CREAT|O_EXCL): dowód prawa tworzenia plików.
    const handle = await open(probePath, "wx", 0o600);
    try {
      await handle.writeFile("state-dir-probe");
    } finally {
      await handle.close();
    }
    await unlink(probePath);
    return { ok: true };
  } catch (e) {
    // Sprzątanie jest best-effort: jeśli plik powstał, a padł zapis/usunięcie,
    // nie chcemy zostawiać śmieci ani maskować pierwotnego błędu.
    await unlink(probePath).catch(() => {});
    return probeFailure(dir, e);
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
