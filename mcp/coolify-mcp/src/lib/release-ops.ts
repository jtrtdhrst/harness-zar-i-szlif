/**
 * Żar i Szlif release evidence for the owned Coolify MCP runtime.
 *
 * This is a read-only view of the existing signed Harness delivery lane.
 * Never infer a production revision from Coolify's running:healthy status.
 * The trusted release catalog is mounted by the operator, not writable via MCP.
 */
import { lstatSync, readFileSync } from 'node:fs';
import type { CoolifyClient } from './coolify-client.js';

const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const UUID = /^[a-z0-9-]{8,64}$/;
const PINNED = /^([a-z0-9][a-z0-9._:/-]*)@(sha256:[a-f0-9]{64})$/;
export type Promotion = 'auto_main' | 'manual' | 'hold';
export interface ReleaseTarget {
  uuid: string;
  kind: 'application' | 'service';
  source_sha: string;
  image: string;
  promotion: Promotion;
  component_uuid?: string;
  git_repository?: string;
  git_branch?: string;
  base_directory?: string;
  dockerfile_location?: string;
}
export interface ReleaseCatalog {
  schema_version: 1;
  targets: ReleaseTarget[];
}
export class ReleaseRefusal extends Error {
  constructor(public readonly code: string) { super(code); }
}
export function validatePath(value: string): boolean {
  return value.length > 0 && value.length < 256 && !value.includes('\\') &&
    !value.includes('..') && !value.includes('//') && !/[\r\n\0]/.test(value) &&
    (value.startsWith('/') || !value.startsWith('.'));
}
export function validateCatalog(input: unknown): ReleaseCatalog {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new ReleaseRefusal('invalid_catalog');
  const catalog = input as Record<string, unknown>;
  if (catalog.schema_version !== 1 || !Array.isArray(catalog.targets) || catalog.targets.length > 100) {
    throw new ReleaseRefusal('invalid_catalog_schema');
  }
  const targets: ReleaseTarget[] = [];
  const seen = new Set<string>();
  for (const value of catalog.targets) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ReleaseRefusal('invalid_target');
    const t = value as Record<string, unknown>;
    if (typeof t.uuid !== 'string' || !UUID.test(t.uuid) ||
        (t.kind !== 'application' && t.kind !== 'service') ||
        typeof t.source_sha !== 'string' || !SHA.test(t.source_sha) ||
        typeof t.image !== 'string' || !PINNED.test(t.image) ||
        !['auto_main', 'manual', 'hold'].includes(String(t.promotion))) {
      throw new ReleaseRefusal('invalid_target');
    }
    const key = t.kind + ':' + t.uuid;
    if (seen.has(key)) throw new ReleaseRefusal('duplicate_target');
    seen.add(key);
    if (t.component_uuid !== undefined && (t.kind !== 'service' ||
        typeof t.component_uuid !== 'string' || !UUID.test(t.component_uuid))) {
      throw new ReleaseRefusal('invalid_component_uuid');
    }
    for (const pathKey of ['base_directory', 'dockerfile_location']) {
      if (t[pathKey] !== undefined &&
          (typeof t[pathKey] !== 'string' || !validatePath(t[pathKey]))) {
        throw new ReleaseRefusal('invalid_build_path');
      }
    }
    if (t.git_branch !== undefined && t.git_branch !== 'main') throw new ReleaseRefusal('untrusted_branch');
    if (t.git_repository !== undefined &&
       (typeof t.git_repository !== 'string' || !/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(t.git_repository))) {
      throw new ReleaseRefusal('invalid_repository');
    }
    targets.push(t as unknown as ReleaseTarget);
  }
  return { schema_version: 1, targets };
}
export function readReleaseCatalog(filename = process.env.COOLIFY_RELEASE_CATALOG_FILE): ReleaseCatalog {
  if (!filename || !filename.startsWith('/')) throw new ReleaseRefusal('release_catalog_not_mounted');
  let stat;
  try { stat = lstatSync(filename); }
  catch { throw new ReleaseRefusal('release_catalog_missing'); }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 262144 || (stat.mode & 0o022)) {
    throw new ReleaseRefusal('release_catalog_untrusted_permissions');
  }
  let raw;
  try { raw = JSON.parse(readFileSync(filename, 'utf8')) as unknown; }
  catch { throw new ReleaseRefusal('release_catalog_invalid_json'); }
  return validateCatalog(raw);
}
function targetByUuid(catalog: ReleaseCatalog, uuid: string): ReleaseTarget {
  const matches = catalog.targets.filter((t) => t.uuid === uuid);
  if (matches.length !== 1) throw new ReleaseRefusal('resource_not_in_release_catalog');
  return matches[0];
}
export interface ConfigEvidence {
  uuid: string;
  kind: string;
  status: string | null;
  configured_image: string | null;
  component_uuid: string | null;
  git_repository?: string | null;
  git_branch?: string | null;
  base_directory?: string | null;
  dockerfile_location?: string | null;
}
export async function getConfigEvidence(client: CoolifyClient, target: ReleaseTarget): Promise<ConfigEvidence> {
  if (target.kind === 'service') {
    const s = await client.getService(target.uuid) as {
      uuid?: string; status?: string; applications?: Array<{uuid?: string; image?: string; status?: string}>;
    };
    const comps = s.applications ?? [];
    const matched = target.component_uuid
      ? comps.filter((c) => c.uuid === target.component_uuid)
      : comps.length === 1 ? comps : [];
    if (matched.length !== 1) throw new ReleaseRefusal('compose_component_ambiguous_or_missing');
    return {
      uuid: target.uuid, kind: 'service', status: s.status ?? null,
      configured_image: matched[0].image ?? null,
      component_uuid: matched[0].uuid ?? null,
    };
  }
  const a = await client.getApplication(target.uuid) as {
    uuid?: string; status?: string; docker_registry_image_name?: string;
    docker_registry_image_tag?: string; git_repository?: string; git_branch?: string;
    base_directory?: string; dockerfile_location?: string;
  };
  // Coolify exposes registry name/tag here, but not necessarily the container's live digest.
  const image = a.docker_registry_image_name
    ? a.docker_registry_image_name + (a.docker_registry_image_tag ? ':' + a.docker_registry_image_tag : '')
    : null;
  return {
    uuid: target.uuid, kind: 'application', status: a.status ?? null,
    configured_image: image, component_uuid: null,
    git_repository: a.git_repository ?? null, git_branch: a.git_branch ?? null,
    base_directory: a.base_directory ?? null, dockerfile_location: a.dockerfile_location ?? null,
  };
}
export function evaluateConfig(target: ReleaseTarget, evidence: ConfigEvidence) {
  const blockers: string[] = [];
  if (target.promotion === 'hold') blockers.push('hold');
  if (evidence.kind !== target.kind || evidence.uuid !== target.uuid) blockers.push('resource_mismatch');
  if (evidence.configured_image !== target.image) blockers.push('configured_image_not_pinned_to_approved_digest');
  for (const key of ['git_repository', 'git_branch', 'base_directory', 'dockerfile_location'] as const) {
    if (target[key] !== undefined && target[key] !== evidence[key]) blockers.push(key + '_mismatch');
  }
  return {
    uuid: target.uuid, kind: target.kind, promotion: target.promotion,
    catalog_source_sha: target.source_sha,
    catalog_image_digest: target.image.split('@')[1],
    configured_image: evidence.configured_image,
    config_matches_catalog: blockers.length === 0,
    blockers,
    live_image_digest_verified: false,
    runtime_source_sha_verified: false,
    production_e2e_verified: false,
    release_verified: false,
    status: blockers.length ? 'BLOCKED' : 'CONFIG_MATCH_ONLY_NOT_DONE',
  };
}
export async function releaseStatus(client: CoolifyClient, uuid: string, filename?: string) {
  if (!UUID.test(uuid)) throw new ReleaseRefusal('invalid_uuid');
  const target = targetByUuid(readReleaseCatalog(filename), uuid);
  const evidence = await getConfigEvidence(client, target);
  return evaluateConfig(target, evidence);
}
export async function releaseDrift(client: CoolifyClient, filename?: string) {
  const catalog = readReleaseCatalog(filename);
  const results = [];
  for (const target of catalog.targets) {
    try {
      results.push(evaluateConfig(target, await getConfigEvidence(client, target)));
    } catch (e) {
      results.push({ uuid: target.uuid, status: 'BLOCKED', blockers: [
        e instanceof ReleaseRefusal ? e.code : 'coolify_readback_failed',
      ], release_verified: false });
    }
  }
  return { checked: results.length, all_configured: results.every((v) => v.status === 'CONFIG_MATCH_ONLY_NOT_DONE'),
    all_production_verified: false, results };
}
export async function releasePreflight(client: CoolifyClient, input: {
  uuid: string; source_sha: string; image_digest: string;
}, filename?: string) {
  if (!UUID.test(input.uuid) || !SHA.test(input.source_sha) || !DIGEST.test(input.image_digest))
    throw new ReleaseRefusal('invalid_candidate');
  const target = targetByUuid(readReleaseCatalog(filename), input.uuid);
  const result = await releaseStatus(client, input.uuid, filename);
  const blockers = [...result.blockers];
  if (target.source_sha !== input.source_sha) blockers.push('source_sha_not_in_catalog');
  if (!target.image.endsWith('@' + input.image_digest)) blockers.push('digest_not_in_catalog');
  // The existing root-owned Harness admission and external production E2E are authoritative.
  blockers.push('independent_release_admission_required', 'live_sha_digest_e2e_required');
  return { ...result, blockers, authorized_to_deploy: false, status: 'NOT_AUTHORIZED' };
}
