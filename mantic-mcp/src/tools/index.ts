import type { MauticApiClient } from '../api/client.js';
import type { ToolDefinition, ToolResult } from '../types/index.js';
import { WriteGuard } from '../security/write-guard.js';

import * as contacts from './contacts.js';
import * as campaigns from './campaigns.js';
import * as emails from './emails.js';
import * as forms from './forms.js';
import * as segments from './segments.js';
import * as content from './content.js';
import * as business from './business.js';
import * as advanced from './advanced.js';
import * as integration from './integration.js';
import * as projects from './projects.js';
import * as instance from './instance.js';

const modules = [
  contacts,
  campaigns,
  emails,
  forms,
  segments,
  content,
  business,
  advanced,
  integration,
  projects,
  instance,
];

export const allToolDefinitions: ToolDefinition[] = modules.flatMap(m => m.toolDefinitions);

const allHandlers: Record<string, (client: MauticApiClient, args: any) => Promise<ToolResult>> = {};
for (const mod of modules) {
  Object.assign(allHandlers, mod.toolHandlers);
}

let environmentGuard: WriteGuard | null = null;

/**
 * The guard is the transport boundary: every tool call — including a model
 * calling a write tool directly — is authorized here before a handler runs.
 * Deployments that pass no explicit guard still get the fail-closed default
 * built from the process environment.
 */
function resolveGuard(guard?: WriteGuard): WriteGuard {
  if (guard) return guard;
  if (!environmentGuard) {
    const env = typeof process !== 'undefined' && process.env ? process.env : {};
    environmentGuard = new WriteGuard(env);
  }
  return environmentGuard;
}

export async function dispatchTool(
  toolName: string,
  client: MauticApiClient,
  args: any,
  guard?: WriteGuard,
): Promise<ToolResult> {
  await resolveGuard(guard).authorize(toolName, client, args);

  const handler = allHandlers[toolName];
  if (!handler) {
    return {
      content: [{ type: 'text', text: `Unknown tool: ${toolName}` }],
      isError: true,
    };
  }
  return handler(client, args);
}
