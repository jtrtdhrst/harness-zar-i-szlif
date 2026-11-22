/**
 * Error translation for the Mautic API v2 (API Platform) surface.
 *
 * The six `*_project` tools are the only v2 consumers. Without this mapping a
 * provider 401 (the credential is a v1 OAuth client, which is not automatically
 * valid on /api/v2) surfaced as a bare "Mautic API Error: Unauthorized" that
 * named neither the API surface nor what the caller could do instead.
 *
 * Every translator here throws: callers either get a real result or an error
 * that names v2 explicitly. There is deliberately no path that reports success.
 */
import axios from 'axios';
import { ErrorCode, McpError } from '../errors.js';
import { MauticApiClient } from './client.js';

export const V2_SURFACE = 'Mautic API v2 (API Platform, /api/v2/**)';

/** Translate a v2 request failure into a typed, self-describing McpError. */
export function mapV2Error(toolName: string, error: unknown): never {
  if (error instanceof McpError) throw error;

  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === 401 || status === 403) {
      throw new McpError(
        ErrorCode.InternalError,
        `${toolName}: ${V2_SURFACE} is not available to this credential - the provider answered HTTP ${status}. ` +
          'A Mautic v1 (FOSRestBundle) OAuth client is not automatically valid on v2. ' +
          'Use the v1 tools, or ask the owner to confirm the v2 surface and the credential scopes.',
      );
    }
    if (status === 404) {
      throw new McpError(
        ErrorCode.InternalError,
        `${toolName}: ${V2_SURFACE} endpoint not found - the provider answered HTTP 404. ` +
          'This Mautic instance may not expose API Platform v2.',
      );
    }
    throw new McpError(
      ErrorCode.InternalError,
      `${toolName}: ${V2_SURFACE} request failed: ${MauticApiClient.extractErrorMessage(error)}`,
    );
  }

  const message = error instanceof Error ? error.message : String(error);
  throw new McpError(
    ErrorCode.InternalError,
    `${toolName}: unexpected failure calling ${V2_SURFACE}: ${message}`,
  );
}
