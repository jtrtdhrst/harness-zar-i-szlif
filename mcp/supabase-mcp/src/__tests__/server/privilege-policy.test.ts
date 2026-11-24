/**
 * Tests for the least-privilege tool authorization policy.
 *
 * These are local (mocked) security tests, NOT production E2E evidence.
 *
 * Covered:
 * - unknown / missing roles fail closed (previously they inherited 'authenticated')
 * - 'authenticated' is limited to schema metadata ('regular') and never user PII, logs or mutations
 * - 'anon' has no tool access
 * - 'service_role' keeps full access
 * - every registered tool declares an explicit privilege level (registry can't regress silently)
 */

import { describe, test, expect } from 'bun:test';
import {
    canAccessTool,
    getAllowedPrivilegeLevels,
    isKnownRole,
    TOOL_PRIVILEGE_LEVELS,
    type ToolPrivilegeLevel,
} from '../../tools/types.js';
import { ALL_TOOLS, buildToolRegistry, type AppTool } from '../../tools/registry.js';

describe('role to privilege mapping', () => {
    describe('unknown roles fail closed', () => {
        const unknownRoles = [
            'admin',
            'editor',
            'service_role_typo',
            'Service_Role',
            'supabase_admin',
            'authenticated ',
            '',
        ];

        test.each(unknownRoles)('role %p gets no privileges', (role) => {
            for (const level of TOOL_PRIVILEGE_LEVELS) {
                expect(canAccessTool(role, level)).toBe(false);
            }
            expect(getAllowedPrivilegeLevels(role).size).toBe(0);
        });

        test('undefined and null roles get no privileges', () => {
            expect(getAllowedPrivilegeLevels(undefined).size).toBe(0);
            expect(getAllowedPrivilegeLevels(null).size).toBe(0);
            expect(canAccessTool(undefined as unknown as string, 'regular')).toBe(false);
        });

        test('isKnownRole only accepts mapped roles', () => {
            expect(isKnownRole('authenticated')).toBe(true);
            expect(isKnownRole('anon')).toBe(true);
            expect(isKnownRole('service_role')).toBe(true);
            expect(isKnownRole('admin')).toBe(false);
            expect(isKnownRole(undefined)).toBe(false);
        });
    });

    describe('authenticated role', () => {
        test('may read schema metadata', () => {
            expect(canAccessTool('authenticated', 'regular')).toBe(true);
        });

        test('may not read sensitive data (PII, logs, function source)', () => {
            expect(canAccessTool('authenticated', 'sensitive')).toBe(false);
        });

        test('may not run privileged mutations or arbitrary SQL', () => {
            expect(canAccessTool('authenticated', 'privileged')).toBe(false);
        });
    });

    describe('anon role', () => {
        test('has no access at any level', () => {
            for (const level of TOOL_PRIVILEGE_LEVELS) {
                expect(canAccessTool('anon', level)).toBe(false);
            }
        });
    });

    describe('service_role', () => {
        test('keeps full access', () => {
            for (const level of TOOL_PRIVILEGE_LEVELS) {
                expect(canAccessTool('service_role', level)).toBe(true);
            }
        });
    });
});

describe('tool registry privilege policy', () => {
    /**
     * Pinned classification. Any change to a tool's privilege level fails this test on
     * purpose: widening access is a security decision that must be reviewed.
     */
    const EXPECTED: Record<string, ToolPrivilegeLevel> = {
        // Schema metadata: safe for authenticated callers
        list_tables: 'regular',
        list_table_columns: 'regular',
        list_indexes: 'regular',
        list_constraints: 'regular',
        list_foreign_keys: 'regular',
        list_rls_policies: 'regular',
        list_triggers: 'regular',
        list_database_functions: 'regular',
        get_function_definition: 'regular',
        get_trigger_definition: 'regular',
        get_rls_status: 'regular',
        list_extensions: 'regular',
        list_available_extensions: 'regular',
        list_migrations: 'regular',
        list_cron_jobs: 'regular',
        list_realtime_publications: 'regular',
        list_vector_indexes: 'regular',
        get_index_stats: 'regular',
        get_vector_index_stats: 'regular',
        get_database_stats: 'regular',
        get_project_url: 'regular',
        verify_jwt_secret: 'regular',
        generate_typescript_types: 'regular',
        get_advisors: 'regular',
        list_storage_buckets: 'regular',
        get_storage_config: 'regular',
        list_edge_functions: 'regular',

        // User data, PII, log contents and function source
        list_auth_users: 'sensitive',
        get_auth_user: 'sensitive',
        get_logs: 'sensitive',
        list_edge_function_logs: 'sensitive',
        list_storage_objects: 'sensitive',
        get_edge_function_details: 'sensitive',
        get_database_connections: 'sensitive',
        get_cron_job_history: 'sensitive',

        // Mutations, arbitrary SQL and admin operations
        apply_migration: 'privileged',
        execute_sql: 'privileged',
        explain_query: 'privileged',
        create_auth_user: 'privileged',
        update_auth_user: 'privileged',
        delete_auth_user: 'privileged',
        rebuild_hooks: 'privileged',
        update_storage_config: 'privileged',
        add_nullable_column: 'privileged',
    };

    test('every registered tool declares an explicit privilege level', () => {
        for (const tool of ALL_TOOLS) {
            expect(tool.privilegeLevel).toBeDefined();
            expect(TOOL_PRIVILEGE_LEVELS).toContain(tool.privilegeLevel);
        }
    });

    test('registry contains no duplicate tool names', () => {
        const names = ALL_TOOLS.map((tool) => tool.name);
        expect(new Set(names).size).toBe(names.length);
    });

    test('registry matches the pinned classification exactly', () => {
        const actual: Record<string, string> = {};
        for (const tool of ALL_TOOLS) {
            actual[tool.name] = tool.privilegeLevel;
        }
        expect(actual).toEqual(EXPECTED);
    });

    test('PII and log-reading tools are never callable by an authenticated user', () => {
        const sensitiveTools = ALL_TOOLS.filter((tool) => tool.privilegeLevel === 'sensitive');
        expect(sensitiveTools.length).toBeGreaterThan(0);
        for (const tool of sensitiveTools) {
            expect(canAccessTool('authenticated', tool.privilegeLevel)).toBe(false);
            expect(canAccessTool('admin', tool.privilegeLevel)).toBe(false);
        }
    });

    test('buildToolRegistry refuses tools without a privilege level', () => {
        const undeclared = {
            name: 'legacy_tool_without_level',
            description: 'tool that forgot to declare a privilege level',
            inputSchema: {},
            mcpInputSchema: {},
            outputSchema: {},
            execute: async () => ({}),
        } as unknown as AppTool;

        const messages: string[] = [];
        const registry = buildToolRegistry([undeclared], (message) => messages.push(message));

        expect(registry.has('legacy_tool_without_level')).toBe(false);
        expect(registry.size).toBe(0);
        expect(messages.join(' ')).toContain('no privilegeLevel');
    });

    test('buildToolRegistry drops duplicate names instead of shadowing', () => {
        const tool = ALL_TOOLS.find((candidate) => candidate.name === 'list_tables');
        expect(tool).toBeDefined();
        const registry = buildToolRegistry([tool as AppTool, tool as AppTool], () => {});

        expect(registry.size).toBe(1);
    });

    test('full registry builds with every declared tool', () => {
        const registry = buildToolRegistry(ALL_TOOLS, () => {});
        expect(registry.size).toBe(ALL_TOOLS.length);
    });
});
