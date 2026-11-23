import { z } from "zod";
import { createHash } from "node:crypto";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { uploadImageAuto } from "../services/image-management.js";
import { resolveToolSurfacePolicy, toolAllowed } from "./tool-surface-filter.js";

const MAX_IMAGE_BYTES = 60 * 1024 * 1024;
const supported = /\.(png|jpg|jpeg|webp|gif|bmp)$/i;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function fail(reason) { throw new Error(reason); }
function nameOK(name) {
  return typeof name === "string" && name.length > 0 && name.length <= 160 &&
    /^[A-Za-z0-9._-]+$/.test(name) && !name.includes("..") && supported.test(name);
}
function folderOK(name) {
  return typeof name === "string" && (name === "" ||
    (name.length < 256 && name.split("/").every(s => s.length > 0 && s !== "." && s !== ".." && /^[A-Za-z0-9._-]+$/.test(s))));
}
function encodeID(x) {
  return "comfy:v1:" + Buffer.from(JSON.stringify([x.prompt_id, x.node_id, x.image_index, x.filename, x.subfolder]), "utf8").toString("base64url");
}
function decodeID(id) {
  if (typeof id !== "string" || !id.startsWith("comfy:v1:") || id.length > 1100) fail("Invalid ComfyUI image_id");
  let parts;
  try { parts = JSON.parse(Buffer.from(id.slice(9), "base64url").toString("utf8")); } catch { fail("Malformed ComfyUI image_id"); }
  if (!Array.isArray(parts) || parts.length !== 5) fail("Invalid ComfyUI image_id fields");
  const [prompt_id, node_id, image_index, filename, subfolder] = parts;
  if (!uuid.test(prompt_id) || !/^\d+$/.test(node_id) ||
      !Number.isInteger(image_index) || image_index < 0 ||
      !nameOK(filename) || !folderOK(subfolder)) fail("Untrusted ComfyUI image_id fields");
  return { prompt_id, node_id, image_index, filename, subfolder, type: "output" };
}
function comfyBase() {
  const base = new URL(process.env.COMFYUI_URL || "http://comfyui:8188");
  if (base.protocol !== "http:" && base.protocol !== "https:") fail("Invalid COMFYUI_URL");
  return base;
}
function publicBase() {
  const base = new URL(process.env.COMFYUI_PUBLIC_URL || "https://comfy.kompaszbiorek.pl/");
  if (base.protocol !== "https:") fail("COMFYUI_PUBLIC_URL must use HTTPS");
  return base;
}
function viewURL(base, img) {
  const url = new URL("/view", base);
  url.searchParams.set("filename", img.filename);
  url.searchParams.set("type", img.type);
  if (img.subfolder) url.searchParams.set("subfolder", img.subfolder);
  return url;
}
async function bytesFor(img) {
  if (!nameOK(img.filename) || !folderOK(img.subfolder) || !["output","input"].includes(img.type)) fail("Invalid image path");
  const response = await fetch(viewURL(comfyBase(), img), { signal: AbortSignal.timeout(40000) });
  if (!response.ok) fail("ComfyUI image readback HTTP " + response.status);
  if (Number(response.headers.get("content-length") || 0) > MAX_IMAGE_BYTES) fail("Image exceeds 60 MiB");
  const raw = Buffer.from(await response.arrayBuffer());
  if (raw.length < 16 || raw.length > MAX_IMAGE_BYTES) fail("Empty/oversize image response");
  return raw;
}
async function metadataFor(img) {
  const raw = await bytesFor(img);
  return {
    ...img, image_id: encodeID(img),
    view_url: viewURL(publicBase(), img).toString(),
    bytes: raw.length,
    sha256: createHash("sha256").update(raw).digest("hex")
  };
}
async function refsFromHistory(promptId, nodeId, index) {
  if (!uuid.test(promptId)) fail("Invalid prompt_id (UUID required)");
  const res = await fetch(new URL("/history/" + promptId, comfyBase()), { signal: AbortSignal.timeout(15000) });
  if (!res.ok) fail("ComfyUI history HTTP " + res.status);
  const history = (await res.json())[promptId];
  if (!history) fail("No completed workflow for prompt_id");
  const outputs = history.outputs || {};
  const records = [];
  for (const [node, value] of Object.entries(outputs)) {
    if (!/^\d+$/.test(node) || (nodeId !== undefined && nodeId !== node)) continue;
    for (const [i, file] of (value.images || []).entries()) {
      if (index !== undefined && i !== index) continue;
      if (!file || file.type !== "output" || !nameOK(file.filename) || !folderOK(file.subfolder || "")) continue;
      records.push({
        prompt_id: promptId, node_id: node, image_index: i,
        filename: file.filename, subfolder: file.subfolder || "", type: "output",
        width: file.metadata?.width ?? null, height: file.metadata?.height ?? null
      });
    }
  }
  if (!records.length) fail("No matching saved output images in this prompt (select a SaveImage node)");
  return Promise.all(records.map(metadataFor));
}
function result(data, message) {
  return { content: [{ type:"text", text: message + "\n" + JSON.stringify(data) }], structuredContent:data };
}
function error(e) { return { isError:true, content:[{type:"text",text:"ComfyUI image reference error: " + String(e?.message || e)}] }; }
export function registerComfyImageReferences(server) {
  if (typeof server.registerTool !== "function") return;
  if (toolAllowed("get_output_image_ref", resolveToolSurfacePolicy())) {
    server.registerTool("get_output_image_ref", {
      title:"Get exact ComfyUI output image URL and persistent image ID",
      description:"Resolve a completed render's prompt_id (and optional node_id/image_index) to exact image_id, publicly openable view_url, filename, SHA-256 and dimensions. Or resolve one image_id in another conversation. No preview or resized thumbnail.",
      inputSchema: {
        prompt_id: z.string().optional(),
        image_id: z.string().optional(),
        node_id: z.string().optional(),
        image_index: z.number().int().min(0).optional()
      },
      annotations: { readOnlyHint:true, openWorldHint:false }
    }, async ({prompt_id,image_id,node_id,image_index}) => {
      try {
        if (Boolean(prompt_id) === Boolean(image_id)) fail("Provide exactly one of prompt_id or image_id");
        let images;
        if (image_id) {
          const ref = decodeID(image_id);
          images = [await metadataFor(ref)];
        } else images = await refsFromHistory(prompt_id,node_id,image_index);
        return result({count:images.length, images, primary:images[0]},
          "Exact ComfyUI image links (each image_id resolves the same stored output file):");
      } catch(e) { return error(e); }
    });
  }
  if (toolAllowed("stage_output_image_reference", resolveToolSurfacePolicy())) {
    server.registerTool("stage_output_image_reference", {
      title:"Reuse a previous ComfyUI output as a lossless LoadImage reference",
      description:"Take exact image_id returned by get_output_image_ref, copy its original bytes from ComfyUI output into input without re-encoding, verify SHA-256, return input_filename for LoadImage in any new workflow.",
      inputSchema: {
        image_id:z.string(),
        filename:z.string().optional()
      },
      annotations: { readOnlyHint:false, destructiveHint:false, openWorldHint:false }
    }, async ({image_id,filename}) => {
      let temp;
      try {
        const ref=decodeID(image_id);
        const raw=await bytesFor(ref);
        if (raw.length > 30*1024*1024) fail("Reference upload exceeds 30 MiB");
        const hash=createHash("sha256").update(raw).digest("hex");
        const target=filename || ("reference_"+hash.slice(0,16)+"_"+ref.filename);
        if (!nameOK(target) || target.length>120) fail("Invalid destination filename");
        temp=await mkdtemp(join(tmpdir(),"comfy-output-ref-"));
        const path=join(temp,target);
        await writeFile(path,raw,{mode:0o600});
        const uploaded=await uploadImageAuto(path,target);
        if (!uploaded.loaderSelectable) fail("Uploaded reference not selectable in LoadImage");
        const copied=await bytesFor({filename:uploaded.filename,subfolder:"",type:"input"});
        const readback=createHash("sha256").update(copied).digest("hex");
        if (copied.length!==raw.length || readback!==hash) fail("Reference data changed during stage");
        return result({
          image_id, input_filename:uploaded.filename,
          load_image:{class_type:"LoadImage",inputs:{image:uploaded.filename}},
          bytes:raw.length, sha256:hash, readback_sha256:readback,
          byte_identical:true, loader_selectable:true, type:"input"
        },"Lossless reference staged in ComfyUI input. Use input_filename in a LoadImage node:");
      } catch(e) { return error(e); }
      finally { if(temp) await rm(temp,{recursive:true,force:true}); }
    });
  }
}
