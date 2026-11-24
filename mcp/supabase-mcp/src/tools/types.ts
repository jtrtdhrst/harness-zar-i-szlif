import type { SelfhostedSupabaseClient } from '../client/index.js';

// Define log function type
type LogFunction = (message: string, level?: 'info' | 'warn' | 'error') => void;

/**
 * Privilege levels for tools.
 * - 'regular': Schema/structure metadata only (table, column, index, policy, extension
 *              definitions). No user rows, no log contents, no personal data.
 * - 'sensitive': Reads that expose user data, personal data (PII), log contents or
 *              function source through the server's privileged DB path. Denied for
 *              ordinary authenticated callers by default.
 * - 'privileged': Admin and mutation operations (arbitrary SQL, migrations, auth-user
 *              administration, config changes, DDL).
 */
export type ToolPrivilegeLevel = 'regular' | 'sensitive' | 'privileged';

/** Every privilege level a tool can declare, ordered least to most sensitive. */
export const TOOL_PRIVILEGE_LEVELS: readonly ToolPrivilegeLevel[] = [
    'regular',
    'sensitive',
    'privileged',
];

/**
 * User context from JWT authentication (HTTP mode only).
 */
export interface UserContext {
    userId: string;
    email: string | null;
    role: string;
}

/**
 * Maps JWT roles to allowed tool privilege levels using a Map to avoid object injection patterns.
 * - 'service_role': Can access all tools (regular + sensitive + privileged)
 * - 'authenticated': Schema metadata only (regular). Never user data, logs or mutations.
 * - 'anon': No tool access (anonymous users should not access MCP tools directly)
 *
 * SECURITY NOTE: Anonymous users are blocked from MCP tool access because:
 * 1. MCP tools provide admin-level database introspection
 * 2. Anon JWTs are meant for public API access, not admin tooling
 * 3. If anon access is needed, use authenticated role with appropriate RLS
 */
const ROLE_PRIVILEGE_MAP = new Map<string, Set<ToolPrivilegeLevel>>([
    ['service_role', new Set<ToolPrivilegeLevel>(TOOL_PRIVILEGE_LEVELS)],
    ['authenticated', new Set<ToolPrivilegeLevel>(['regular'])],
    ['anon', new Set<ToolPrivilegeLevel>([])], // No access for anonymous users
]);

/**
 * SECURITY: Unknown roles fail closed.
 *
 * Previously an unknown role (typo, custom role, future Supabase role) fell back to the
 * 'authenticated' level, which silently granted regular tool access. Authorization must
 * never widen because a role string is unrecognised, so unknown roles now receive no
 * privileges at all. New roles must be added explicitly to ROLE_PRIVILEGE_MAP.
 */
const UNKNOWN_ROLE_PRIVILEGES: ReadonlySet<ToolPrivilegeLevel> = new Set<ToolPrivilegeLevel>();

/**
 * Returns the privilege levels granted to a role. Unknown roles get an empty set.
 */
export function getAllowedPrivilegeLevels(userRole: string | undefined | null): ReadonlySet<ToolPrivilegeLevel> {
    if (!userRole) {
        return UNKNOWN_ROLE_PRIVILEGES;
    }
    return ROLE_PRIVILEGE_MAP.get(userRole) ?? UNKNOWN_ROLE_PRIVILEGES;
}

/**
 * True when the role is explicitly modelled in the privilege map.
 */
export function isKnownRole(userRole: string | undefined | null): boolean {
    return !!userRole && ROLE_PRIVILEGE_MAP.has(userRole);
}

/**
 * Checks if a JWT role can access a tool with the given privilege level.
 *
 * @param userRole - The role from the JWT token
 * @param toolPrivilegeLevel - The privilege level required by the tool
 * @returns true if access is allowed, false otherwise
 */
export function canAccessTool(
    userRole: string,
    toolPrivilegeLevel: ToolPrivilegeLevel
): boolean {
    // Use Map.get() which is safe from prototype pollution
    return getAllowedPrivilegeLevels(userRole).has(toolPrivilegeLevel);
}

/**
 * Defines the expected shape of the context object passed to tool execute functions.
 */
export interface ToolContext {
    selfhostedClient: SelfhostedSupabaseClient;
    log: LogFunction; // Explicitly define the log function
    workspacePath?: string; // Path to the workspace root
    user?: UserContext; // User context from JWT (HTTP mode only)
    [key: string]: unknown; // Allow other context properties
}
