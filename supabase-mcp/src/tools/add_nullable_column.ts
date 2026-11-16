/**
 * add_nullable_column - narrowly scoped, typed schema mutation for MCP callers.
 *
 * SECURITY MODEL
 * - Only additive nullable columns on an operator-pinned allowlist of schemas.
 * - Never arbitrary SQL: identifiers are validated and quoted, and the column type is an
 *   enum of non-destructive types. No DROP, no ALTER TYPE, no NOT NULL, no DEFAULT.
 * - Fails closed when the allowlist is unset/empty or the target schema is reserved.
 * - Runs inside a single transaction, reads the column back from information_schema, and
 *   rolls back by default so a caller can prove the change without persisting it.
 * - Requires the direct database connection (DATABASE_URL); it never uses a service_role
 *   JWT, so no standing elevated credential is needed by the calling agent.
 */

import { z } from 'zod';
import type { ToolContext, ToolPrivilegeLevel } from './types.js';

/** Schema allowlist env var, e.g. "zari_test,engineer_test". Unset means the tool is disabled. */
export const DDL_SCHEMA_ALLOWLIST_ENV = 'SUPABASE_MCP_DDL_SCHEMA_ALLOWLIST';

/**
 * Schemas that are never valid DDL targets, even if an operator lists them.
 */
const RESERVED_SCHEMAS = new Set<string>([
    'pg_catalog',
    'information_schema',
    'auth',
    'storage',
    'extensions',
    'graphql',
    'graphql_public',
    'realtime',
    'vault',
    'supabase_migrations',
    'supabase_functions',
    'net',
    '_analytics',
    '_realtime',
    'pgsodium',
    'pgsodium_masks',
]);

/** Safe, additive column types only. */
const ALLOWED_DATA_TYPES = [
    'text',
    'integer',
    'bigint',
    'boolean',
    'numeric',
    'timestamptz',
    'date',
    'uuid',
    'jsonb',
] as const;

/** PostgreSQL identifier rule used by this tool (lower case, bounded length). */
const IDENTIFIER_PATTERN = /^[a-z_][a-z0-9_]{0,62}$/;

const AddNullableColumnInputSchema = z.object({
    schema: z
        .string()
        .describe('Target schema. Must be present in SUPABASE_MCP_DDL_SCHEMA_ALLOWLIST.'),
    table: z.string().describe('Target table (existing table in the target schema).'),
    column: z.string().describe('New column name to add. Must not already exist with a different type.'),
    data_type: z
        .enum(ALLOWED_DATA_TYPES)
        .describe('Column type. Only additive, nullable-safe types are permitted.'),
    mode: z
        .enum(['rollback', 'commit'])
        .optional()
        .default('rollback')
        .describe("'rollback' (default) verifies then rolls back; 'commit' persists the column."),
});
type AddNullableColumnInput = z.infer<typeof AddNullableColumnInputSchema>;

const ReadbackSchema = z.object({
    column_name: z.string(),
    data_type: z.string(),
    is_nullable: z.string(),
    column_default: z.string().nullable(),
});
const AddNullableColumnOutputSchema = z.object({
    schema: z.string(),
    table: z.string(),
    column: z.string(),
    data_type: z.string(),
    mode: z.enum(['rollback', 'commit']),
    applied: z.boolean(),
    rolled_back: z.boolean(),
    statement: z.string(),
    readback: ReadbackSchema.nullable(),
    message: z.string(),
});
type AddNullableColumnOutput = z.infer<typeof AddNullableColumnOutputSchema>;

const mcpInputSchema = {
    type: 'object',
    properties: {
        schema: {
            type: 'string',
            description: 'Target schema. Must be present in SUPABASE_MCP_DDL_SCHEMA_ALLOWLIST.',
        },
        table: { type: 'string', description: 'Target table.' },
        column: { type: 'string', description: 'New nullable column name.' },
        data_type: {
            type: 'string',
            enum: ALLOWED_DATA_TYPES,
            description: 'Additive column type.',
        },
        mode: {
            type: 'string',
            enum: ['rollback', 'commit'],
            description: "'rollback' (default) verifies then rolls back; 'commit' persists.",
        },
    },
    required: ['schema', 'table', 'column', 'data_type'],
};

/** Internal signal used to roll back a verified transaction while keeping the readback. */
class RollbackAfterVerification<T> extends Error {
    constructor(public readonly value: T) {
        super('Rollback after verification (expected)');
        this.name = 'RollbackAfterVerification';
    }
}

/** Parses the operator allowlist; unset/empty means the feature is disabled. */
export function parseSchemaAllowlist(raw: string | undefined | null): string[] {
    if (!raw) {
        return [];
    }
    return raw
        .split(',')
        .map((entry) => entry.trim().toLowerCase())
        .filter((entry) => entry.length > 0);
}

/** Validates a schema name against the allowlist and the reserved-schema deny list. */
export function resolveDdlTargetSchema(
    schema: string,
    allowlist: readonly string[]
): { ok: true; schema: string } | { ok: false; reason: string } {
    // Strict: identifiers must already be lower case. Case folding here would silently
    // retarget "Engineer_Test" onto a different schema than the caller asked for.
    const normalized = schema.trim();

    if (!IDENTIFIER_PATTERN.test(normalized)) {
        return { ok: false, reason: `Invalid schema identifier: "${schema}".` };
    }
    if (RESERVED_SCHEMAS.has(normalized)) {
        return { ok: false, reason: `Schema "${normalized}" is reserved and cannot be altered.` };
    }
    if (allowlist.length === 0) {
        return {
            ok: false,
            reason:
                `DDL is disabled: ${DDL_SCHEMA_ALLOWLIST_ENV} is not set. ` +
                'An operator must pin the schema allowlist before typed DDL is available.',
        };
    }
    if (!allowlist.includes(normalized)) {
        return {
            ok: false,
            reason: `Schema "${normalized}" is not in the operator-pinned allowlist.`,
        };
    }
    return { ok: true, schema: normalized };
}

/** Quote a validated identifier for safe interpolation. */
function quoteIdentifier(name: string): string {
    if (!IDENTIFIER_PATTERN.test(name)) {
        throw new Error(`Invalid SQL identifier: "${name}".`);
    }
    return `"${name}"`;
}

export const addNullableColumnTool = {
    name: 'add_nullable_column',
    description:
        'Adds one nullable column to a table inside an operator-pinned allowlist of schemas, ' +
        'reads it back from information_schema and rolls the transaction back by default. ' +
        'Typed alternative to execute_sql for controlled schema changes.',
    privilegeLevel: 'privileged' as ToolPrivilegeLevel,
    inputSchema: AddNullableColumnInputSchema,
    mcpInputSchema: mcpInputSchema,
    outputSchema: AddNullableColumnOutputSchema,
    execute: async (
        input: AddNullableColumnInput,
        context: ToolContext
    ): Promise<AddNullableColumnOutput> => {
        const client = context.selfhostedClient;
        const { table, column, data_type, mode } = input;

        const allowlist = parseSchemaAllowlist(process.env[DDL_SCHEMA_ALLOWLIST_ENV]);
        const target = resolveDdlTargetSchema(input.schema, allowlist);
        if (!target.ok) {
            context.log(`[SECURITY] add_nullable_column refused: ${target.reason}`, 'warn');
            throw new Error(target.reason);
        }

        if (!IDENTIFIER_PATTERN.test(table.trim())) {
            throw new Error(`Invalid table identifier: "${table}".`);
        }
        if (!IDENTIFIER_PATTERN.test(column.trim())) {
            throw new Error(`Invalid column identifier: "${column}".`);
        }
        if (!ALLOWED_DATA_TYPES.includes(data_type)) {
            throw new Error(`Unsupported column type: "${data_type}".`);
        }
        if (!client.isPgAvailable()) {
            throw new Error(
                'Typed DDL requires the direct database connection (DATABASE_URL); no service_role JWT is used.'
            );
        }

        const schemaName = target.schema;
        const tableName = table.trim();
        const columnName = column.trim();
        const statement =
            `ALTER TABLE ${quoteIdentifier(schemaName)}.${quoteIdentifier(tableName)} ` +
            `ADD COLUMN IF NOT EXISTS ${quoteIdentifier(columnName)} ${data_type} NULL`;

        const readbackSql =
            'SELECT column_name, data_type, is_nullable, column_default ' +
            'FROM information_schema.columns ' +
            'WHERE table_schema = $1 AND table_name = $2 AND column_name = $3';

        try {
            const outcome = await client.executeTransactionWithPg(async (pg) => {
                await pg.query(statement);

                const readback = await pg.query(readbackSql, [schemaName, tableName, columnName]);
                const row = readback.rows[0];
                if (!row) {
                    // The ALTER reported success but the column is not visible: abort.
                    throw new Error(
                        `Readback failed: column ${schemaName}.${tableName}.${columnName} was not found after ALTER.`
                    );
                }

                const value: AddNullableColumnOutput = {
                    schema: schemaName,
                    table: tableName,
                    column: columnName,
                    data_type,
                    mode,
                    applied: mode === 'commit',
                    rolled_back: mode !== 'commit',
                    statement,
                    readback: {
                        column_name: String(row.column_name),
                        data_type: String(row.data_type),
                        is_nullable: String(row.is_nullable),
                        column_default: row.column_default === null ? null : String(row.column_default),
                    },
                    message:
                        mode === 'commit'
                            ? `Column ${schemaName}.${tableName}.${columnName} added and committed.`
                            : `Column ${schemaName}.${tableName}.${columnName} verified, transaction rolled back.`,
                };

                if (mode !== 'commit') {
                    // Verified: roll back so nothing persists (proof without a lasting change).
                    throw new RollbackAfterVerification(value);
                }
                return value;
            });

            return outcome;
        } catch (error) {
            if (error instanceof RollbackAfterVerification) {
                return error.value as AddNullableColumnOutput;
            }
            context.log(
                `add_nullable_column failed on ${schemaName}.${tableName}.${columnName}: ${String(error)}`,
                'error'
            );
            throw error;
        }
    },
};
