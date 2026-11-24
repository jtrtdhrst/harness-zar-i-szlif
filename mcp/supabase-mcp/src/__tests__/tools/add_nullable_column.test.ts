/**
 * Tests for add_nullable_column, the typed DDL surface.
 *
 * These are local (mocked) tests against a simulated transaction, NOT production E2E.
 *
 * Covered:
 * - fails closed when the operator allowlist is unset or the schema is not allowlisted
 * - never targets reserved schemas
 * - rejects identifier injection attempts and unsupported column types
 * - rollback mode: ALTER runs, readback happens, transaction rolls back (nothing persists)
 * - commit mode: applied and committed
 * - aborts when readback cannot see the column
 * - requires the direct DB connection (no service_role JWT path)
 */

import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import type { SelfhostedSupabaseClient } from '../../client/index.js';
import {
    addNullableColumnTool,
    DDL_SCHEMA_ALLOWLIST_ENV,
    describeReadbackMismatch,
    parseSchemaAllowlist,
    resolveDdlTargetSchema,
} from '../../tools/add_nullable_column.js';

interface RecordedQuery {
    text: string;
    params?: unknown[];
}

interface FakePgOptions {
    pgAvailable?: boolean;
    readbackRow?: Record<string, unknown> | null;
}

function createDdlClient(options: FakePgOptions = {}) {
    const { pgAvailable = true, readbackRow = {
        column_name: 'colour',
        data_type: 'text',
        is_nullable: 'YES',
        column_default: null,
    } } = options;

    const state = {
        queries: [] as RecordedQuery[],
        committed: false,
        rolledBack: false,
        transactions: 0,
    };

    const fakePg = {
        query: async (text: string, params?: unknown[]) => {
            state.queries.push({ text, params });
            if (text.includes('information_schema.columns')) {
                return { rows: readbackRow === null ? [] : [readbackRow] };
            }
            return { rows: [] };
        },
    };

    const client = {
        isPgAvailable: () => pgAvailable,
        executeTransactionWithPg: async <T>(callback: (pg: unknown) => Promise<T>): Promise<T> => {
            state.transactions += 1;
            try {
                const value = await callback(fakePg);
                state.committed = true;
                return value;
            } catch (error) {
                state.rolledBack = true;
                throw error;
            }
        },
    } as unknown as SelfhostedSupabaseClient;

    return { client, state };
}

function context(client: SelfhostedSupabaseClient) {
    const logs: string[] = [];
    return {
        ctx: {
            selfhostedClient: client,
            log: (message: string) => logs.push(message),
            workspacePath: '/test/workspace',
        },
        logs,
    };
}

const VALID_INPUT = {
    schema: 'engineer_test',
    table: 'canary_table',
    column: 'colour',
    data_type: 'text' as const,
    mode: 'rollback' as const,
};

describe('add_nullable_column', () => {
    let previousAllowlist: string | undefined;

    beforeEach(() => {
        previousAllowlist = process.env[DDL_SCHEMA_ALLOWLIST_ENV];
    });

    afterEach(() => {
        if (previousAllowlist === undefined) {
            delete process.env[DDL_SCHEMA_ALLOWLIST_ENV];
        } else {
            process.env[DDL_SCHEMA_ALLOWLIST_ENV] = previousAllowlist;
        }
    });

    describe('metadata', () => {
        test('is privileged-only', () => {
            expect(addNullableColumnTool.privilegeLevel).toBe('privileged');
        });

        test('exposes a static MCP input schema', () => {
            expect(addNullableColumnTool.mcpInputSchema).toBeDefined();
            expect(addNullableColumnTool.inputSchema).toBeDefined();
        });
    });

    describe('allowlist gating', () => {
        test('parseSchemaAllowlist handles unset, empty and mixed values', () => {
            expect(parseSchemaAllowlist(undefined)).toEqual([]);
            expect(parseSchemaAllowlist('')).toEqual([]);
            expect(parseSchemaAllowlist(' Engineer_Test , ,canary ')).toEqual([
                'engineer_test',
                'canary',
            ]);
        });

        test('refuses to run when the allowlist is unset (fail closed)', async () => {
            delete process.env[DDL_SCHEMA_ALLOWLIST_ENV];
            const { client, state } = createDdlClient();

            await expect(
                addNullableColumnTool.execute(VALID_INPUT, context(client).ctx)
            ).rejects.toThrow(DDL_SCHEMA_ALLOWLIST_ENV);

            expect(state.transactions).toBe(0);
        });

        test('refuses a schema that is not allowlisted', async () => {
            process.env[DDL_SCHEMA_ALLOWLIST_ENV] = 'engineer_test';
            const { client, state } = createDdlClient();

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, schema: 'public' },
                    context(client).ctx
                )
            ).rejects.toThrow(/not in the operator-pinned allowlist/);

            expect(state.transactions).toBe(0);
        });

        test.each(['auth', 'storage', 'pg_catalog', 'information_schema', 'vault'])(
            'refuses reserved schema %p even when allowlisted',
            async (schema) => {
                process.env[DDL_SCHEMA_ALLOWLIST_ENV] = `engineer_test,${schema}`;
                const { client, state } = createDdlClient();

                await expect(
                    addNullableColumnTool.execute(
                        { ...VALID_INPUT, schema },
                        context(client).ctx
                    )
                ).rejects.toThrow(/reserved/);

                expect(state.transactions).toBe(0);
            }
        );

        test('resolveDdlTargetSchema rejects case folding and bad identifiers', () => {
            expect(resolveDdlTargetSchema('engineer_test', ['engineer_test'])).toEqual({
                ok: true,
                schema: 'engineer_test',
            });
            // Case folding would silently retarget a different schema than requested.
            expect(resolveDdlTargetSchema('Engineer_Test', ['engineer_test'])).toEqual({
                ok: false,
                reason: 'Invalid schema identifier: "Engineer_Test".',
            });
            expect(resolveDdlTargetSchema('engineer-test', ['engineer-test'])).toEqual({
                ok: false,
                reason: 'Invalid schema identifier: "engineer-test".',
            });
        });
    });

    describe('identifier and type validation', () => {
        beforeEach(() => {
            process.env[DDL_SCHEMA_ALLOWLIST_ENV] = 'engineer_test';
        });

        test.each([
            ['table', 'canary_table; DROP TABLE users'],
            ['table', 'Canary'],
            ['table', '"canary"'],
            ['column', 'colour); DROP TABLE users; --'],
            ['column', 'colour name'],
        ])('rejects unsafe %s identifier %p', async (field, value) => {
            const { client, state } = createDdlClient();
            const input = { ...VALID_INPUT, [field]: value };

            await expect(
                addNullableColumnTool.execute(input, context(client).ctx)
            ).rejects.toThrow(/Invalid (table|column) identifier/);

            expect(state.transactions).toBe(0);
        });

        test('rejects a column type outside the additive allowlist', async () => {
            const { client, state } = createDdlClient();
            const input = { ...VALID_INPUT, data_type: 'text; DROP TABLE users' };

            await expect(
                addNullableColumnTool.execute(input as unknown as typeof VALID_INPUT, context(client).ctx)
            ).rejects.toThrow(/Unsupported column type/);

            expect(state.transactions).toBe(0);
        });

        test('requires the direct database connection', async () => {
            const { client, state } = createDdlClient({ pgAvailable: false });

            await expect(
                addNullableColumnTool.execute(VALID_INPUT, context(client).ctx)
            ).rejects.toThrow(/DATABASE_URL/);

            expect(state.transactions).toBe(0);
        });
    });

    describe('execution modes', () => {
        beforeEach(() => {
            process.env[DDL_SCHEMA_ALLOWLIST_ENV] = 'engineer_test';
        });

        test('rollback mode verifies the column then rolls the transaction back', async () => {
            const { client, state } = createDdlClient();

            const result = await addNullableColumnTool.execute(VALID_INPUT, context(client).ctx);

            expect(state.queries[0]?.text).toBe(
                'ALTER TABLE "engineer_test"."canary_table" ADD COLUMN IF NOT EXISTS "colour" text NULL'
            );
            expect(state.queries[1]?.text).toContain('information_schema.columns');
            expect(state.queries[1]?.params).toEqual(['engineer_test', 'canary_table', 'colour']);

            expect(result.mode).toBe('rollback');
            expect(result.applied).toBe(false);
            expect(result.rolled_back).toBe(true);
            expect(state.rolledBack).toBe(true);
            expect(state.committed).toBe(false);
            expect(result.readback).toEqual({
                column_name: 'colour',
                data_type: 'text',
                is_nullable: 'YES',
                column_default: null,
            });
        });

        test('commit mode persists the column', async () => {
            const { client, state } = createDdlClient();

            const result = await addNullableColumnTool.execute(
                { ...VALID_INPUT, mode: 'commit' },
                context(client).ctx
            );

            expect(result.applied).toBe(true);
            expect(result.rolled_back).toBe(false);
            expect(state.committed).toBe(true);
            expect(state.rolledBack).toBe(false);
        });

        test('aborts when the added column is not visible on readback', async () => {
            const { client, state } = createDdlClient({ readbackRow: null });

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, mode: 'commit' },
                    context(client).ctx
                )
            ).rejects.toThrow(/Readback failed/);

            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });
    });

    describe('readback definition verification', () => {
        beforeEach(() => {
            process.env[DDL_SCHEMA_ALLOWLIST_ENV] = 'engineer_test';
        });

        // ADD COLUMN IF NOT EXISTS is a no-op when the name already exists, so the readback
        // row describes the PRE-EXISTING column. Reporting success from row existence alone
        // would present another column's definition as the requested change.
        test('describeReadbackMismatch accepts the requested nullable, default-free column', () => {
            expect(
                describeReadbackMismatch(
                    { column: 'colour', data_type: 'text' },
                    { column_name: 'colour', data_type: 'text', is_nullable: 'YES', column_default: null }
                )
            ).toBeNull();
        });

        test('describeReadbackMismatch maps requested types to their information_schema name', () => {
            expect(
                describeReadbackMismatch(
                    { column: 'at', data_type: 'timestamptz' },
                    {
                        column_name: 'at',
                        data_type: 'timestamp with time zone',
                        is_nullable: 'YES',
                        column_default: null,
                    }
                )
            ).toBeNull();
        });

        test('describeReadbackMismatch reports type, nullability, default and name differences', () => {
            const wrongType = describeReadbackMismatch(
                { column: 'colour', data_type: 'text' },
                { column_name: 'colour', data_type: 'integer', is_nullable: 'YES', column_default: null }
            );
            expect(wrongType).toContain('data_type');

            const notNull = describeReadbackMismatch(
                { column: 'colour', data_type: 'text' },
                { column_name: 'colour', data_type: 'text', is_nullable: 'NO', column_default: null }
            );
            expect(notNull).toContain('is_nullable');

            const withDefault = describeReadbackMismatch(
                { column: 'colour', data_type: 'text' },
                { column_name: 'colour', data_type: 'text', is_nullable: 'YES', column_default: "'x'::text" }
            );
            expect(withDefault).toContain('column_default');

            const otherName = describeReadbackMismatch(
                { column: 'colour', data_type: 'text' },
                { column_name: 'colour_old', data_type: 'text', is_nullable: 'YES', column_default: null }
            );
            expect(otherName).toContain('column_name');
        });

        test('commit mode rejects an existing column of a different type instead of reporting success', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'colour',
                    data_type: 'integer',
                    is_nullable: 'YES',
                    column_default: null,
                },
            });

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, mode: 'commit' },
                    context(client).ctx
                )
            ).rejects.toThrow(/Readback mismatch/);

            // No false success: the transaction must not commit.
            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });

        test('commit mode rejects a pre-existing NOT NULL column', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'colour',
                    data_type: 'text',
                    is_nullable: 'NO',
                    column_default: null,
                },
            });

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, mode: 'commit' },
                    context(client).ctx
                )
            ).rejects.toThrow(/Readback mismatch: .*is_nullable/);

            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });

        test('commit mode rejects a pre-existing column that carries a default', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'colour',
                    data_type: 'text',
                    is_nullable: 'YES',
                    column_default: "'red'::text",
                },
            });

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, mode: 'commit' },
                    context(client).ctx
                )
            ).rejects.toThrow(/Readback mismatch: .*column_default/);

            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });

        test('rollback mode also refuses to report a mismatched column as verified', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'colour',
                    data_type: 'integer',
                    is_nullable: 'YES',
                    column_default: null,
                },
            });

            await expect(
                addNullableColumnTool.execute(VALID_INPUT, context(client).ctx)
            ).rejects.toThrow(/Readback mismatch/);

            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });

        test('rejects a readback row for a different column name', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'colour_old',
                    data_type: 'text',
                    is_nullable: 'YES',
                    column_default: null,
                },
            });

            await expect(
                addNullableColumnTool.execute(
                    { ...VALID_INPUT, mode: 'commit' },
                    context(client).ctx
                )
            ).rejects.toThrow(/Readback mismatch: .*column_name/);

            expect(state.committed).toBe(false);
            expect(state.rolledBack).toBe(true);
        });

        test('commit mode still succeeds for a definition that matches the request', async () => {
            const { client, state } = createDdlClient({
                readbackRow: {
                    column_name: 'at',
                    data_type: 'timestamp with time zone',
                    is_nullable: 'YES',
                    column_default: null,
                },
            });

            const result = await addNullableColumnTool.execute(
                { ...VALID_INPUT, column: 'at', data_type: 'timestamptz', mode: 'commit' },
                context(client).ctx
            );

            expect(result.applied).toBe(true);
            expect(result.readback?.data_type).toBe('timestamp with time zone');
            expect(state.committed).toBe(true);
            expect(state.rolledBack).toBe(false);
        });
    });
});
