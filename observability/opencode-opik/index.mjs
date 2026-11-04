// opik-observability: rozszerzone logi egzekucji Paperclip -> Opik (bez zmian Core).
// Wzorzec: paperclip-run-sync (te same hooki, te same env, no-op bez PAPERCLIP_RUN_ID).
// Jeden trace na RUN_ID w projekcie `paperclip-<agent8>` (fallback `paperclip-runs`),
// jeden span na wywołanie narzędzia. Logowanie nigdy nie wywala runa (best-effort + timeout).
const RUN_ID = (process.env.PAPERCLIP_RUN_ID || "").trim();
const AGENT_ID = (process.env.PAPERCLIP_AGENT_ID || "").trim();
const COMPANY_ID = (process.env.PAPERCLIP_COMPANY_ID || "").trim();
const TASK_ID = (process.env.PAPERCLIP_TASK_ID || "").trim();
const BASE = (process.env.OPIK_BASE_URL || "https://opik.kompaszbiorek.pl/api").replace(/\/$/, "");
const PROJECT = AGENT_ID ? `paperclip-${AGENT_ID.slice(0, 8)}` : "paperclip-runs";

const SECRET_KEY = /api[_-]?key|token|secret|passwd|password|authorization|bearer|cookie|private[_-]?key/i;
const trunc = (s, n) => (typeof s === "string" && s.length > n ? s.slice(0, n) + `…[+${s.length - n}]` : s);
function redact(v, depth = 0) {
  if (typeof v === "string") return trunc(v, 2000);
  if (Array.isArray(v)) return depth > 4 ? [`[array ${v.length}]`] : v.slice(0, 50).map((x) => redact(x, depth + 1));
  if (v && typeof v === "object") {
    const o = {};
    for (const [k, val] of Object.entries(v).slice(0, 100)) o[k] = SECRET_KEY.test(k) ? "[REDACTED]" : redact(val, depth + 1);
    return o;
  }
  return v;
}
const cap = (v, n = 8000) => { const s = JSON.stringify(v ?? null); return s.length > n ? s.slice(0, n) : s; };
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// Do not log URLs, payloads, headers or credentials. A failed request must not
// be silently counted as ingested. Only a bounded transport/status code is logged.
async function send(method, path, body) {
  let category = "TRANSPORT_OR_TIMEOUT";
  for (let attempt = 0; attempt < 3; attempt++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 3000);
    try {
      const response = await fetch(BASE + path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctl.signal,
      });
      if (response.ok || (method === "POST" && response.status === 409)) return true;
      category = "HTTP_" + String(response.status);
      if (response.status >= 400 && response.status < 500 && response.status !== 429) break;
    } catch { category = "TRANSPORT_OR_TIMEOUT"; }
    finally { clearTimeout(timer); }
    if (attempt < 2) await pause(40 * (attempt + 1));
  }
  console.error("[opik-observability] delivery_failed " + method + " " + category);
  return false;
}
const post = (path, body) => send("POST", path, body);
const patchTrace = (id, body) =>
  send("PATCH", "/v1/private/traces/" + id, { project_name: PROJECT, ...body });

function uuidv7() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  const ms = BigInt(Date.now());
  b[0] = Number((ms >> 40n) & 0xffn); b[1] = Number((ms >> 32n) & 0xffn);
  b[2] = Number((ms >> 24n) & 0xffn); b[3] = Number((ms >> 16n) & 0xffn);
  b[4] = Number((ms >> 8n) & 0xffn); b[5] = Number(ms & 0xffn);
  b[6] = (b[6] & 0x0f) | 0x70; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
}
// Opik wymaga UUIDv7 (time-ordered) dla trace/span id.
const runs = new Map(); // Paperclip run -> { traceId, rootBody, readyPromise, finalized }
const calls = new Map();
const recordedGenerations = new Set();
const pendingGenerations = new Set();
let seq = 0;
function run() {
  let r = runs.get(RUN_ID);
  if (!r) {
    const traceId = uuidv7();
    r = {
      traceId, finalized: false, readyPromise: null,
      rootBody: {
        id: traceId, project_name: PROJECT,
        name: "run " + RUN_ID.slice(0, 8),
        start_time: new Date().toISOString(),
        tags: ["paperclip", "opencode-runtime"],
        metadata: {
          paperclip_run_id: RUN_ID, agent_id: AGENT_ID || null,
          task_id: TASK_ID || null, company_id: COMPANY_ID || null,
          service: "paperclip-opencode",
          billing_status: "unknown_until_verified",
        },
        input: { run_id: RUN_ID },
      },
    };
    runs.set(RUN_ID, r);
  }
  return r;
}
async function ensureRoot(r) {
  if (!r.readyPromise) {
    r.readyPromise = post("/v1/private/traces", r.rootBody);
  }
  const ok = await r.readyPromise;
  if (!ok) r.readyPromise = null; // next real event may retry
  return ok;
}

// OPIK_MODEL_USAGE_V1: OpenCode emits the final per-generation token counters on
// message.updated (same native event consumed by Langfuse). No prompt contents,
// credentials, or user text are sent. Do not infer billed USD from tokens.
async function recordGeneration(message) {
  if (message?.role !== "assistant" || !message?.id || message?.time?.completed == null) return;
  const key = String(message.id);
  if (recordedGenerations.has(key) || pendingGenerations.has(key)) return;
  const finished = new Date(message.time.completed);
  if (!Number.isFinite(finished.getTime())) return;
  const candidateStart = new Date(message.time.created ?? message.time.completed);
  const started = Number.isFinite(candidateStart.getTime()) ? candidateStart : finished;
  const n = (value) => Number.isFinite(Number(value)) && Number(value) >= 0 ? Math.floor(Number(value)) : 0;
  const token = message.tokens ?? {};
  const fresh = n(token.input);
  const read = n(token.cache?.read);
  const write = n(token.cache?.write);
  const out = n(token.output);
  const reasoning = n(token.reasoning);
  const usage = {
    prompt_tokens: fresh + read + write,
    completion_tokens: out + reasoning,
    total_tokens: fresh + read + write + out + reasoning,
    input_tokens: fresh, output_tokens: out,
    cache_read_tokens: read, cache_write_tokens: write,
    reasoning_tokens: reasoning,
  };
  pendingGenerations.add(key);
  try {
    const r = run();
    if (!await ensureRoot(r)) return;
    const delivered = await post("/v1/private/spans", {
      id: uuidv7(), trace_id: r.traceId, project_name: PROJECT,
      name: "opencode.generation", type: "llm",
      start_time: started.toISOString(), end_time: finished.toISOString(),
      model: message.modelID ? String(message.modelID) : null,
      provider: message.providerID ? String(message.providerID) : null,
      usage, output: { finish: message.finish ?? null },
      metadata: {
        paperclip_run_id: RUN_ID, agent_id: AGENT_ID || null,
        company_id: COMPANY_ID || null, task_id: TASK_ID || null,
        session_id: message.sessionID || null,
        open_code_message_id: key,
        provider_reported_cost_usd:
          typeof message.cost === "number" && Number.isFinite(message.cost) ? message.cost : null,
        billing_type: "unknown",
        cost_provenance: "provider_reported_unverified",
        usage_semantics: "fresh_input_separate_from_cache_read_and_write",
      },
    });
    if (delivered) recordedGenerations.add(key);
  } finally {
    pendingGenerations.delete(key);
  }
}

const OpikObservability = async () => {
  if (!RUN_ID) return {};
  return {
    event: async (input) => {
      try {
        const t = input?.event?.type || input?.type || "";
        if (t === "message.updated") {
          await recordGeneration(input?.event?.properties?.info ?? input?.properties?.info);
          return;
        }
        const r = run();
        if (!await ensureRoot(r)) return;
        if (t === "session.idle" || t === "session.deleted" || t === "session.error") {
          if (r.finalized) return;
          const err = input?.event?.properties?.error ?? input?.properties?.error;
          const safeErrorType = t === "session.error"
            ? String(err?.name || err?.code || "session_error").replace(/[^a-zA-Z0-9_.-]/g, "").slice(0, 64)
            : null;
          const ok = await patchTrace(r.traceId, {
            end_time: new Date().toISOString(),
            metadata: {
              paperclip_run_id: RUN_ID, agent_id: AGENT_ID || null,
              task_id: TASK_ID || null, company_id: COMPANY_ID || null,
              service: "paperclip-opencode", end_event: t,
              run_signal: t === "session.error" ? "error" : "ended",
              error_type: safeErrorType,
            },
          });
          if (ok) r.finalized = true;
        }
      } catch { console.error("[opik-observability] event_handler_failed"); }
    },
    "tool.execute.before": async (input, output) => {
      try {
        const r = run();
        if (!await ensureRoot(r)) return;
        const tool = String(input?.tool ?? output?.tool ?? "unknown");
        const key = [RUN_ID, tool, ++seq].join(":");
        calls.set(key, { tool, start: Date.now(), args: cap(redact({ ...(input?.args ?? {}), ...(output?.args ?? {}) })) });
        if (input && typeof input === "object") input.__opikCallKey = key;
      } catch { console.error("[opik-observability] tool_before_failed"); }
    },
    "tool.execute.after": async (input, output) => {
      try {
        const r = run();
        if (!await ensureRoot(r)) return;
        const tool = String(input?.tool ?? "unknown");
        const key = input?.__opikCallKey;
        const prev = (key && calls.get(key)) || null;
        if (key) calls.delete(key);
        const end = new Date(); const start = new Date(prev?.start || Date.now());
        await post("/v1/private/spans", {
          id: uuidv7(), trace_id: r.traceId, project_name: PROJECT,
          name: tool, type: "tool",
          start_time: start.toISOString(), end_time: end.toISOString(),
          input: parseArgs(prev?.args),
          output: { result: cap(redact(output?.output ?? output ?? null)), duration_ms: end - start },
          metadata: {
            paperclip_run_id: RUN_ID, agent_id: AGENT_ID || null,
            task_id: TASK_ID || null, compa

... [373 characters truncated]