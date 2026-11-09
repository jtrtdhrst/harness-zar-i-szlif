import { writeFileSync } from 'node:fs';
import { buildCatalog, loadPaperclipBaseline } from '../catalog.mjs';

const catalog = buildCatalog();
const paperclip = loadPaperclipBaseline();
writeFileSync(new URL('../docs/multica-v0.8.1-capability-catalog.json', import.meta.url), `${JSON.stringify(catalog, null, 2)}\n`);
writeFileSync(new URL('../docs/paperclip-parity-matrix.json', import.meta.url), `${JSON.stringify(paperclip, null, 2)}\n`);
console.log(JSON.stringify({ multicaOperations: catalog.counts, paperclipBaseline: paperclip.tools.length }));
