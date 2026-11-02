#!/usr/bin/env node
// Durable, idempotent ChatGPT original-file tool registration for comfyui-mcp@0.52.206.
// Must run AFTER the pinned upstream patch chain in this directory.
import { readFileSync, writeFileSync } from "node:fs";

const root="/usr/local/lib/node_modules/comfyui-mcp/dist/tools/";
const tool=root+"image-management.js";
const filter=root+"tool-surface-filter.js";
const text=readFileSync(tool,"utf8");
const anchor="export function registerImageManagementTools(server) {";
const call="registerChatGptFileTool(server)";
if (!text.includes(anchor)) throw new Error("MCP version drift: image management registration missing");
if (!text.includes(call)) {
  const patched='import { registerChatGptFileTool } from "./chatgpt-file-tool.js";\n'+text.replace(anchor,anchor+"\n    "+call+";");
  writeFileSync(tool,patched);
}
let policy=readFileSync(filter,"utf8");
const before='    "upload_image",';
const after='    "upload_chatgpt_image",';
if (!policy.includes(before)) throw new Error("MCP version drift: tool-surface policy anchor missing");
if (!policy.includes(after)) {
  policy=policy.replace(before,after+"\n"+before);
  writeFileSync(filter,policy);
}
// Register exact output links and stage-as-reference tools within the same canonical registrar.
let image=readFileSync(tool,"utf8");
const importLine='import { registerComfyImageReferences } from "./output-image-refs.js";';
if (!image.includes(importLine)) {
  image=importLine+"\n"+image;
  if(!image.includes(call+";"))throw Error("ChatGPT tool registrar missing");
  image=image.replace(call+";",call+";\n    registerComfyImageReferences(server);");
  writeFileSync(tool,image);
}
let updatedPolicy=readFileSync(filter,"utf8");
const safeMarker='    "upload_chatgpt_image",';
const readMarker='    "get_history",';
if (!updatedPolicy.includes(safeMarker) || !updatedPolicy.includes(readMarker)) throw Error("Tool classification anchors missing");
if(!updatedPolicy.includes('    "stage_output_image_reference",'))updatedPolicy=updatedPolicy.replace(safeMarker,safeMarker+'\n    "stage_output_image_reference",');
if(!updatedPolicy.includes('    "get_output_image_ref",'))updatedPolicy=updatedPolicy.replace(readMarker,readMarker+'\n    "get_output_image_ref",');
writeFileSync(filter,updatedPolicy);
console.log("ChatGPT upload, exact image URL, and reference tools registered with surface policy");
