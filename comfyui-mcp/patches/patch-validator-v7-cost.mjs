#!/usr/bin/env node
// COMFY_PATCH_MEDIA_HINT_V1: avoid dumping unrelated input-image names when an
// agent uses a stale/not-staged LoadImage filename. Preserve all validator
// errors, severity, and non-image enum diagnostics. Strict upstream anchors.
import { readFileSync, writeFileSync } from 'node:fs';

const TARGET = process.env.COMFY_MCP_VALIDATOR_FILE ||
  '/usr/local/lib/node_modules/comfyui-mcp/dist/services/workflow-validator.js';
let source = readFileSync(TARGET, 'utf8');
const marker = 'COMFY_PATCH_MEDIA_HINT_V1';
if (source.includes(marker)) {
  console.log('Media validator hint already patched');
  process.exit(0);
}
const anchor = '        const isModel = /\\.(safetensors|gguf|ckpt|pt|pth|bin|sft)$/i.test(value);';
if (source.split(anchor).length !== 2) {
  throw new Error('workflow-validator upstream anchor mismatch; refusing silent patch');
}
source = source.replace(
  anchor,
  '        // COMFY_PATCH_MEDIA_HINT_V1: compact recovery for exact input media refs.\n' +
  '        const isMediaInput = /^(LoadImage|LoadImageMask|LoadImageOutput)$/.test(classType) && inputName === "image";\n' +
  anchor,
);
const hintStart = source.indexOf('        const hint = isModel');
const optionAnchor = '            : validValues.length';
const at = source.indexOf(optionAnchor, hintStart);
if (hintStart < 0 || at < 0 || at - hintStart > 500) {
  throw new Error('workflow-validator hint anchor mismatch; refusing silent patch');
}
source = source.slice(0, at) +
  '            : isMediaInput\n' +
  '                ? " Input image is not staged under this exact filename. Use get_output_image_ref then stage_output_image_reference, and use the returned filename in LoadImage; do not guess a filename or dump the full image dropdown."\n' +
  source.slice(at);
writeFileSync(TARGET, source);
console.log('Compact LoadImage validation hint installed; other enum diagnostics unchanged');
