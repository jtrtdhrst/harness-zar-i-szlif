import { randomUUID } from "node:crypto";
import { and, eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { agents, companies, createDb, heartbeatRuns, issueRecoveryActions, issues } from "@paperclipai/db";
import { terminalizeLegacyExecution } from "./legacy-execution-recovery.js";
import { getEmbeddedPostgresTestSupport, startEmbeddedPostgresTestDatabase } from "../__tests__/helpers/embedded-postgres.js";

const support = await getEmbeddedPostgresTestSupport();
const runDescribe = support.supported ? describe : describe.skip;

runDescribe("confirmed Hermes create-run auth denial / real PostgreSQL", () => {
  let temporary!: Awaited<ReturnType<typeof startEmbeddedPostgresTestDatabase>>;
  let db!: ReturnType<typeof createDb>;
  beforeAll(async () => {
    temporary = await startEmbeddedPostgresTestDatabase("paperclip-hermes-auth-denial-");
    db = createDb(temporary.connectionString);
  }, 30_000);
  afterAll(async () => { await temporary?.cleanup(); });

  async function seed() {
    const companyId = randomUUID(), agentId = randomUUID(), issueId = randomUUID(), runId = randomUUID();
    await db.insert(companies).values({
      id: companyId, name: "Hermes admission fixture", issuePrefix: "H"+randomUUID().slice(0,5).toUpperCase(),
      requireBoardApprovalForNewAgents: false,
    });
    await db.insert(agents).values({
      id: agentId, companyId, name: "Hermes Executor", role: "engineer", status: "idle",
      adapterType: "hermes_gateway", adapterConfig: {}, runtimeConfig: {}, permissions: {},
    });
    const [run] = await db.insert(heartbeatRuns).values({
      id: runId, companyId, agentId, invocationSource: "assignment",
      triggerDetail: "system", status: "running", runtimeMode: "legacy",
      contextSnapshot: { issueId, wakeReason: "issue_assigned" },
      scheduledRetryAttempt: 3, scheduledRetryReason: "transient_failure",
    }).returning();
    await db.insert(issues).values({
      id: issueId, companyId, identifier: "HAD-"+randomUUID().slice(0,6),
      title: "Hermes create run", priority: "medium", status: "in_progress",
      assigneeAgentId: agentId, executionRunId: runId, checkoutRunId: runId,
      executionLockedAt: new Date(),
    });
    return { companyId, agentId, issueId, runId, run };
  }

  it("denied create clears the issue lease, records the actual auth blocker, never invents recovery", async () => {
    const f = await seed();
    const result = await terminalizeLegacyExecution({
      db, run: f.run, status: "failed", fromStatuses: ["running"], reconcileIfNeeded: true,
      patch: { errorCode: "hermes_gateway_auth_failed", resultJson: {
        connectionFailure: { schemaVersion: 1, provider: "hermes_gateway",
          operation: "create_run", reason: "authentication_failed" },
      } },
    });
    expect(result).toMatchObject({ status: "failed", errorCode: "hermes_gateway_auth_failed" });
    const [task] = await db.select().from(issues).where(eq(issues.id, f.issueId));
    expect(task).toMatchObject({
      status: "blocked", checkoutRunId: null, executionRunId: null,
      executionLockedAt: null, unblockDescriptor: { owner: { agentId: f.agentId } },
    });
    expect(task.unblockDescriptor?.action).toContain("API_SERVER_KEY");
    const actions = await db.select().from(issueRecoveryActions)
      .where(and(eq(issueRecoveryActions.companyId, f.companyId), eq(issueRecoveryActions.sourceIssueId, f.issueId)));
    expect(actions).toHaveLength(0);
  });

  it("keeps no-replay recovery for a possible accepted run with network timeout", async () => {
    const f = await seed();
    const result = await terminalizeLegacyExecution({
      db, run: f.run, status: "failed", fromStatuses: ["running"], reconcileIfNeeded: true,
      patch: { errorCode: "hermes_gateway_connect_failed", resultJson: {
        connectionFailure: { schemaVersion: 1, provider: "hermes_gateway",
          operation: "create_run", reason: "connection_timeout" },
      } },
    });
    expect(result?.status).toBe("failed");
    const actions = await db.select().from(issueRecoveryActions)
      .where(and(eq(issueRecoveryActions.companyId, f.companyId), eq(issueRecoveryActions.sourceIssueId, f.issueId)));
    expect(actions.length).toBeGreaterThan(0);
    const [task] = await db.select().from(issues).where(eq(issues.id, f.issueId));
    expect(task.unblockDescriptor?.action ?? "").not.toContain("API_SERVER_KEY");
  });

  it("never clears a replacement execution lease after the old run is denied", async () => {
    const f = await seed();
    const replacementId = randomUUID();
    await db.insert(heartbeatRuns).values({
      id: replacementId, companyId: f.companyId, agentId: f.agentId,
      invocationSource: "assignment", triggerDetail: "system",
      status: "running", runtimeMode: "legacy",
      contextSnapshot: { issueId: f.issueId },
    });
    await db.update(issues).set({
      checkoutRunId: replacementId, executionRunId: replacementId,
    }).where(eq(issues.id, f.issueId));
    const result = await terminalizeLegacyExecution({
      db, run: f.run, status: "failed", fromStatuses: ["running"],
      reconcileIfNeeded: true, patch: {
        errorCode: "hermes_gateway_auth_failed",
        resultJson: { connectionFailure: {
          schemaVersion: 1, provider: "hermes_gateway",
          operation: "create_run", reason: "authentication_failed",
        } },
      },
    });
    expect(result?.status).toBe("failed");
    const [task] = await db.select().from(issues).where(eq(issues.id, f.issueId));
    expect(task).toMatchObject({
      status: "in_progress", checkoutRunId: replacementId,
      executionRunId: replacementId, unblockDescriptor: null,
    });
  });
});
