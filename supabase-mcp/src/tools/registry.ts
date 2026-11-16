/**
 * Single source of truth for the MCP tool registry.
 *
 * Every tool must declare an explicit `privilegeLevel`. The registry is validated at
 * startup (see `validateToolRegistry`) and by the test suite, so a tool can never
 * silently inherit an implicit privilege level: an undeclared level is treated as a
 * configuration error and the tool is refused instead of defaulting to `regular`.
 */

import type { z } from 'zod';
import type { ToolContext, ToolPrivilegeLevel } from './types.js';
import { listTablesTool } from './list_tables.js';
import { listExtensionsTool } from './list_extensions.js';
import { listMigrationsTool } from './list_migrations.js';
import { applyMigrationTool } from './apply_migration.js';
import { executeSqlTool } from './execute_sql.js';
import { getDatabaseConnectionsTool } from './get_database_connections.js';
import { getDatabaseStatsTool } from './get_database_stats.js';
import { getProjectUrlTool } from './get_project_url.js';
import { generateTypesTool } from './generate_typescript_types.js';
import { rebuildHooksTool } from './rebuild_hooks.js';
import { verifyJwtSecretTool } from './verify_jwt_secret.js';
import { listAuthUsersTool } from './list_auth_users.js';
import { getAuthUserTool } from './get_auth_user.js';
import { deleteAuthUserTool } from './delete_auth_user.js';
import { createAuthUserTool } from './create_auth_user.js';
import { updateAuthUserTool } from './update_auth_user.js';
import listStorageBucketsTool from './list_storage_buckets.js';
import listStorageObjectsTool from './list_storage_objects.js';
import listRealtimePublicationsTool from './list_realtime_publications.js';
import { listCronJobsTool } from './list_cron_jobs.js';
import { listVectorIndexesTool } from './list_vector_indexes.js';
import { listEdgeFunctionsTool } from './list_edge_functions.js';
import { getEdgeFunctionDetailsTool } from './get_edge_function_details.js';
import { getLogsTool } from './get_logs.js';
import { getAdvisorsTool } from './get_advisors.js';
import { getStorageConfigTool } from './get_storage_config.js';
import { updateStorageConfigTool } from './update_storage_config.js';
import { listTableColumnsTool } from './list_table_columns.js';
import { listIndexesTool } from './list_indexes.js';
import { listConstraintsTool } from './list_constraints.js';
import { listForeignKeysTool } from './list_foreign_keys.js';
import { listRlsPoliciesTool } from './list_rls_policies.js';
import { listTriggersTool } from './list_triggers.js';
import { listDatabaseFunctionsTool } from './list_database_functions.js';
import { getFunctionDefinitionTool } from './get_function_definition.js';
import { getTriggerDefinitionTool } from './get_trigger_definition.js';
import { getRlsStatusTool } from './get_rls_status.js';
import { listAvailableExtensionsTool } from './list_available_extensions.js';
import { getCronJobHistoryTool } from './get_cron_job_history.js';
import { listEdgeFunctionLogsTool } from './list_edge_function_logs.js';
import { getIndexStatsTool } from './get_index_stats.js';
import { getVectorIndexStatsTool } from './get_vector_index_stats.js';
import { explainQueryTool } from './explain_query.js';
import { addNullableColumnTool } from './add_nullable_column.js';

/**
 * Shape of every registered MCP tool.
 *
 * `privilegeLevel` is required on purpose: an optional field previously let tools fall
 * back to 'regular' by accident, which exposed sensitive tools to ordinary callers.
 */
export interface AppTool {
    name: string;
    description: string;
    inputSchema: z.ZodTypeAny;
    mcpInputSchema: object;
    outputSchema: z.ZodTypeAny;
    privilegeLevel: ToolPrivilegeLevel;
    execute: (input: unknown, context: ToolContext) => Promise<unknown>;
}

/**
 * All tools this server can expose, before any `--tools-config` filtering.
 */
export const ALL_TOOLS: readonly AppTool[] = [
    listTablesTool,
    listExtensionsTool,
    listMigrationsTool,
    applyMigrationTool,
    executeSqlTool,
    getDatabaseConnectionsTool,
    getDatabaseStatsTool,
    getProjectUrlTool,
    generateTypesTool,
    rebuildHooksTool,
    verifyJwtSecretTool,
    listAuthUsersTool,
    getAuthUserTool,
    deleteAuthUserTool,
    createAuthUserTool,
    updateAuthUserTool,
    listStorageBucketsTool,
    listStorageObjectsTool,
    listRealtimePublicationsTool,
    listCronJobsTool,
    listVectorIndexesTool,
    listEdgeFunctionsTool,
    getEdgeFunctionDetailsTool,
    getLogsTool,
    getAdvisorsTool,
    getStorageConfigTool,
    updateStorageConfigTool,
    listTableColumnsTool,
    listIndexesTool,
    listConstraintsTool,
    listForeignKeysTool,
    listRlsPoliciesTool,
    listTriggersTool,
    listDatabaseFunctionsTool,
    getFunctionDefinitionTool,
    getTriggerDefinitionTool,
    getRlsStatusTool,
    listAvailableExtensionsTool,
    getCronJobHistoryTool,
    listEdgeFunctionLogsTool,
    getIndexStatsTool,
    getVectorIndexStatsTool,
    explainQueryTool,
    addNullableColumnTool,
] as unknown as AppTool[];

/**
 * Builds a Map of tools keyed by name.
 *
 * SECURITY: tools without an explicit privilege level are dropped (never defaulted to
 * 'regular'), and duplicate tool names are dropped rather than silently shadowing.
 */
export function buildToolRegistry(
    tools: readonly AppTool[] = ALL_TOOLS,
    log: (message: string, level?: 'info' | 'warn' | 'error') => void = (message) =>
        console.error(message)
): Map<string, AppTool> {
    const registry = new Map<string, AppTool>();

    for (const tool of tools) {
        if (!tool.privilegeLevel) {
            log(
                `[SECURITY] Tool "${tool.name}" declares no privilegeLevel - refusing to register it.`,
                'error'
            );
            continue;
        }
        if (registry.has(tool.name)) {
            log(
                `[SECURITY] Duplicate tool name "${tool.name}" - keeping the first registration only.`,
                'error'
            );
            continue;
        }
        registry.set(tool.name, tool);
    }

    return registry;
}
