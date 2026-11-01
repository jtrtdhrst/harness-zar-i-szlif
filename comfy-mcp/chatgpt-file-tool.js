import { z } from "zod";
import { createHash } from "node:crypto";
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { request as httpsRequest } from "node:https";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { join, basename } from "node:path";
import { tmpdir } from "node:os";
import { uploadImageAuto } from "../services/image-management.js";
import { resolveToolSurfacePolicy, toolAllowed } from "./tool-surface-filter.js";

const MAX_BYTES = 30 * 1024 * 1024;
const FILE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]);
const octets = (ip) => ip.split(".").map(Number);
function publicIPv4(ip) {
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) return false;
  const [a,b,c] = octets(ip);
  if (octets(ip).some(x => x > 255)) return false;
  return !(a === 0 || a === 10 || a === 127 || a >= 224 ||
    a === 169 && b === 254 || a === 172 && b >= 16 && b <= 31 ||
    a === 192 && (b === 168 || b === 0 && c === 0) ||
    a === 100 && b >= 64 && b <= 127 ||
    a === 198 && (b === 18 || b === 19) ||
    a === 192 && b === 0 && c === 0 ||
    a === 198 && b === 51 && c === 100 ||
    a === 203 && b === 0 && c === 113);
}
function publicIp(ip) {
  if (isIP(ip) === 4) return publicIPv4(ip);
  if (isIP(ip) !== 6) return false;
  const s=ip.toLowerCase();
  if (s.startsWith("::ffff:")) return publicIPv4(s.slice(7));
  return ! (s === "::" || s === "::1" || s.startsWith("fc") || s.startsWith("fd") ||
    s.startsWith("fe8") || s.startsWith("fe9") || s.startsWith("fea") ||
    s.startsWith("feb") || s.startsWith("ff") || s.startsWith("2001:db8:"));
}
function normalizeName(filename) {
  const name = basename(String(filename || "chatgpt-reference.png")).replace(/[^a-zA-Z0-9._-]/g, "_");
  if (!name || name.length > 120 || name === "." || name === ".." || name.includes("..")) throw new Error("Invalid filename");
  const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
  if (!FILE_EXTENSIONS.has(ext)) throw new Error("Only png, jpg, jpeg, webp, gif, bmp are accepted");
  return name;
}
function sniffImage(buf, name) {
  const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
  const png = buf.length >= 8 && buf.subarray(0,8).equals(Buffer.from("89504e470d0a1a0a", "hex"));
  const jpeg = buf.length >= 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff;
  const webp = buf.length >= 12 && buf.toString("ascii",0,4) === "RIFF" && buf.toString("ascii",8,12) === "WEBP";
  const gif = buf.length >= 6 && ["GIF87a","GIF89a"].includes(buf.toString("ascii",0,6));
  const bmp = buf.length >= 2 && buf.toString("ascii",0,2) === "BM";
  if (!(ext === ".png" && png || [".jpg",".jpeg"].includes(ext) && jpeg ||
    ext === ".webp" && webp || ext === ".gif" && gif || ext === ".bmp" && bmp)) throw new Error("Image signature does not match extension");
}
async function fetchChatFile(rawUrl) {
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" || url.username || url.password || url.port && url.port !== "443" ||
      isIP(url.hostname) !== 0 || url.hostname === "localhost" ||
      !url.hostname.includes(".")) throw new Error("Only secure HTTPS download URLs with public DNS names are accepted");
  const ipRecords = await lookup(url.hostname, { all: true });
  const allowed = ipRecords.filter(r => publicIp(r.address));
  if (!allowed.length || allowed.length !== ipRecords.length) throw new Error("Download URL DNS is not public");
  return new Promise((resolve, reject) => {
    const req = httpsRequest(url, {
      method: "GET", timeout: 30000, maxRedirects: 0,
      headers: { "Accept": "image/*,application/octet-stream", "User-Agent": "ComfyUI-MCP-ChatGPT-File/1" },
      lookup: (_name, opts, cb) => {
        if (opts.all) return cb(null, allowed.map(r => ({ address: r.address, family: r.family })));
        const address = allowed.find(x => x.family === (opts.family || allowed[0].family)) || allowed[0];
        cb(null, address.address, address.family);
      }
    }, async res => {
      if (res.statusCode !== 200) { res.resume(); reject(new Error("File download returned HTTP " + res.statusCode + " (redirects disabled)")); return; }
      if (Number(res.headers["content-length"] || 0) > MAX_BYTES) { res.destroy(); reject(new Error("File exceeds 30MiB")); return; }
      const chunks = [];
      let n = 0;
      try {
        for await (const part of res) {
          n += part.length;
          if (n > MAX_BYTES) throw new Error("File exceeds 30MiB");
          chunks.push(part);
        }
        if (!n) throw new Error("Empty downloaded image");
        resolve(Buffer.concat(chunks, n));
      } catch(e) { reject(e); res.destroy(); }
    });
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("Download timed out")));
    req.end();
  });
}
export function registerChatGptFileTool(server) {
  if (typeof server.registerTool !== "function" || !toolAllowed("upload_chatgpt_image", resolveToolSurfacePolicy())) return; // respect tool surface policy and compact ToolCatalog
  if (typeof server.registerTool !== "function" || !toolAllowed("upload_chatgpt_image", resolveToolSurfacePolicy())) return; // respect tool surface policy and compact ToolCatalog
  server.registerTool("upload_chatgpt_image", {
    title: "Upload ChatGPT attachment to ComfyUI",
    description: "Save an image the user attached in ChatGPT into the connected ComfyUI input folder, retaining exact bytes and making it selectable in LoadImage. Prefer this tool for user attachments; upload_image remains available for filesystem paths and base64.",
    inputSchema: {
      file: z.object({
        download_url: z.string(),
        file_id: z.string(),
        mime_type: z.string().optional(),
        file_name: z.string().optional(),
      }).strict(),
      filename: z.string().optional().describe("Optional destination filename; defaults to the attached file's name")
    },
    _meta: { "openai/fileParams": ["file"] },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true, idempotentHint: false }
  }, async ({ file, filename }) => {
    let folder;
    try {
      const name = normalizeName(filename || file.file_name || "chatgpt-reference.png");
      if (file.mime_type && !/^image\/(png|jpeg|webp|gif|bmp|x-ms-bmp)$/.test(file.mime_type)) throw new Error("Unsupported image MIME");
      const data = await fetchChatFile(file.download_url);
      sniffImage(data, name);
      const sha256 = createHash("sha256").update(data).digest("hex");
      folder = await mkdtemp(join(tmpdir(), "comfy-chat-file-"));
      const path = join(folder, name);
      await writeFile(path, data, { mode: 0o600 });
      const uploaded = await uploadImageAuto(path, name);
      if (!uploaded.loaderSelectable) throw new Error("ComfyUI LoadImage did not enumerate uploaded image");
      return {
        content: [{type: "text", text: "ComfyUI reference uploaded and verified. Filename: " + uploaded.filename +
            "; file_id: " + file.file_id + "; size: " + data.length + " bytes; SHA-256: " + sha256 +
            ". Use the filename as the image input in LoadImage."}],
        structuredContent: { filename: uploaded.filename, file_id: file.file_id, bytes: data.length,
          sha256, loader_selectable: true, type: "input" }
      };
    } catch(e) {
      return { isError: true, content: [{type:"text",text:"ComfyUI attachment upload failed: "+String(e.message||e)}] };
    } finally { if (folder) await rm(folder, { recursive: true, force: true }); }
  });
}

