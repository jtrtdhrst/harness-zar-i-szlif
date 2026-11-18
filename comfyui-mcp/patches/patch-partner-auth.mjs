#!/usr/bin/env node
// COMFY_PATCH_PARTNER_AUTH_V1: OpenAIGPTImageNodeV2 needs a Comfy.org API key
// in prompt extra_data. comfyui-mcp's enqueue_workflow path never sends it, so
// COMFY_API_KEY alone still produces 401 "Please login first". Inject the
// server-side key, and refuse to enqueue the paid node when no key is set.
// Idempotent; fails closed on an unknown upstream shape.
import { readFileSync, writeFileSync } from 'node:fs';

const TARGET = '/usr/local/lib/node_modules/comfyui-mcp/dist/services/workflow-executor.js';
let s = readFileSync(TARGET, 'utf8');
if (s.includes('COMFY_PATCH_PARTNER_AUTH_V1')) {
  console.log('partner-auth already patched');
  process.exit(0);
}

const imp = 'import { JobWatcher } from "./job-watcher.js";';
if (!s.includes(imp)) throw new Error('import anchor not found');
s = s.replace(imp, imp + '\nimport { config } from "../config.js";');

const anchor = `    const extraData = await withWorkflowMetadata(workflow, options?.extra_data);
    logger.info("Enqueueing workflow (fire-and-forget)");
    const result = await clientEnqueuePrompt(workflow, extraData);`;
if (!s.includes(anchor)) throw new Error('enqueue anchor not found');

const patched = `    const extraData = await withWorkflowMetadata(workflow, options?.extra_data);
    // COMFY_PATCH_PARTNER_AUTH_V1
    let partnerExtraData = extraData;
    if (Object.values(workflow).some((n) => n && typeof n === "object" && n.class_type === "OpenAIGPTImageNodeV2")) {
        if (!config.comfyApiKey) {
            throw new Error("COMFY_PARTNER_AUTH_MISSING: workflow uses OpenAIGPTImageNodeV2, which needs a Comfy.org API key. Set COMFY_API_KEY on the comfy-mcp service; refusing to enqueue before spending credits.");
        }
        partnerExtraData = { ...(extraData ?? {}), api_key_comfy_org: config.comfyApiKey };
    }
    logger.info("Enqueueing workflow (fire-and-forget)");
    const result = await clientEnqueuePrompt(workflow, partnerExtraData);`;
s = s.replace(anchor, patched);
writeFileSync(TARGET, s);
console.log('patched workflow-executor.js with COMFY_PATCH_PARTNER_AUTH_V1');
