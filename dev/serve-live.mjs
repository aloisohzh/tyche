// Local live-preview server: serves the live-exported static site and proxies
// /functions/v1/app/* to the real Sites Function handler (Deno shimmed under Node).
// Dev-only; production routing belongs to the Sites platform.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, resolve, sep } from "node:path";
import { handleRequest } from "../desk-site/functions/handler.ts";

globalThis.Deno = { env: { get: (k) => process.env[k] } };

const ROOT = resolve(process.argv[2] || "C:/Users/alois/AppData/Local/Temp/desk-live-test/web");
const PORT = Number(process.argv[3] || 8770);
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname.startsWith("/functions/v1/app")) {
    const r = await handleRequest(new Request("http://localhost" + req.url, { method: req.method }));
    res.writeHead(r.status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
    res.end(await r.text());
    return;
  }
  const rel = url.pathname === "/" ? "/index.html" : url.pathname;
  const file = resolve(join(ROOT, rel));
  if (file !== ROOT && !file.startsWith(ROOT + sep)) { res.writeHead(403); res.end("forbidden"); return; }
  try {
    const data = await readFile(file);
    res.writeHead(200, { "content-type": MIME[extname(file)] || "application/octet-stream", "cache-control": "no-store" });
    res.end(data);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
  }
});

server.listen(PORT, "127.0.0.1", () => console.log("tyche live preview -> http://127.0.0.1:" + PORT + " (root " + ROOT + ")"));