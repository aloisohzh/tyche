// Local harness for the Sites Function operator console (/control). Deno is not installed
// here, so we shim Deno.env and run the real handler under Node 24 (native TS type-stripping).
// A stub GitHub contents API stands in for the real one (TYCHE_GITHUB_API override), so every
// arm/disarm/halt commit is exercised against an in-memory repo - no real writes, no secrets.
// Synthetic passphrase/PAT only; no account ids appear here. NOT the deployed edge runtime.
import http from "node:http";
import { handleRequest } from "../desk-site/functions/handler.ts";

const PASS = "test-operator-passphrase";
const PAT = "test-github-pat";
const REPO = "aloisohzh/tyche";
const store = new Map(); // path -> { sha, text }
const commits = []; // { method, path, message }
let shaSeq = 0;
const nextSha = () => "stubsha" + (++shaSeq);

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://stub");
  const m = url.pathname.match(/^\/repos\/([^/]+\/[^/]+)\/contents\/(.+)$/);
  const send = (code, obj) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(obj)); };
  if (!m || m[1] !== REPO) return send(404, { message: "not found" });
  if (req.headers.authorization !== "Bearer " + PAT) return send(401, { message: "bad credentials" });
  const path = decodeURIComponent(m[2]);
  let body = "";
  req.on("data", (c) => { body += c; });
  req.on("end", () => {
    const parsed = body ? JSON.parse(body) : {};
    if (req.method === "GET") {
      const cur = store.get(path);
      if (!cur) return send(404, { message: "not found" });
      return send(200, { sha: cur.sha, content: Buffer.from(cur.text, "utf-8").toString("base64") });
    }
    if (req.method === "PUT") {
      const cur = store.get(path);
      if (parsed.sha && (!cur || cur.sha !== parsed.sha)) return send(409, { message: "sha conflict" });
      const text = Buffer.from(parsed.content, "base64").toString("utf-8");
      const sha = nextSha();
      store.set(path, { sha, text });
      commits.push({ method: "PUT", path, message: parsed.message });
      return send(200, { content: { sha } });
    }
    if (req.method === "DELETE") {
      const cur = store.get(path);
      if (parsed.sha && (!cur || cur.sha !== parsed.sha)) return send(409, { message: "sha conflict" });
      store.delete(path);
      commits.push({ method: "DELETE", path, message: parsed.message });
      return send(200, { content: null });
    }
    return send(405, { message: "method not allowed" });
  });
});

await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
process.env.TYCHE_GITHUB_API = "http://127.0.0.1:" + port;
process.env.TYCHE_OPERATOR_PASSPHRASE = PASS;
process.env.TYCHE_GITHUB_PAT = PAT;
globalThis.Deno = { env: { get: (k) => process.env[k] } };

const BASE = "http://localhost/functions/v1/app";
let failures = 0;
function check(name, cond, detail = "") {
  console.log((cond ? "PASS" : "FAIL") + " - " + name + (detail ? " :: " + detail : ""));
  if (!cond) failures++;
}
async function call(path, method = "GET", body) {
  const init = { method };
  if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "content-type": "application/json" }; }
  const res = await handleRequest(new Request(BASE + path, init));
  const text = await res.text();
  let parsed; try { parsed = JSON.parse(text); } catch { parsed = text; }
  return { status: res.status, body: parsed, text };
}
const noSecret = (t) => !t.includes(PASS) && !t.includes(PAT);

const VALID = { max_orders: 2, note: "drill batch", orders: [
  { symbol: "DBC", side: "buy", max_qty: 100, limit_max: 29.5 },
  { symbol: "GLD", side: "sell", max_qty: 50, limit_min: 300.0 },
] };

// status reflects configuration
{
  const r = await call("/control/status");
  check("status configured", r.status === 200 && r.body.operator_configured === true, JSON.stringify(r.body));
}
// unconfigured -> 503
{
  delete process.env.TYCHE_OPERATOR_PASSPHRASE;
  const r = await call("/control", "POST", { passphrase: PASS, action: "ping" });
  check("unconfigured 503", r.status === 503 && r.body.configured === false);
  const s = await call("/control/status");
  check("status unconfigured", s.body.operator_configured === false);
  process.env.TYCHE_OPERATOR_PASSPHRASE = PASS;
}
// auth gate
{
  const missing = await call("/control", "POST", { action: "ping" });
  check("missing passphrase 401", missing.status === 401);
  const wrong = await call("/control", "POST", { passphrase: "nope", action: "ping" });
  check("wrong passphrase 401", wrong.status === 401 && noSecret(wrong.text));
  const ok = await call("/control", "POST", { passphrase: PASS, action: "ping" });
  check("ping ok", ok.status === 200 && ok.body.ok === true && ok.body.operator === true);
}
// method + unknown action
{
  const g = await call("/control", "GET");
  check("GET /control 405", g.status === 405);
  const u = await call("/control", "POST", { passphrase: PASS, action: "bogus" });
  check("unknown action 400", u.status === 400);
}
// halt engage + release commit the shared flag
{
  const on = await call("/control", "POST", { passphrase: PASS, action: "halt", halted: true, reason: "drill halt" });
  check("halt engage ok", on.status === 200 && on.body.pushed === true && on.body.halt.halted === true);
  check("halt engage committed", store.has("data/halt.json") && JSON.parse(store.get("data/halt.json").text).halted === true);
  check("halt engage set_by", JSON.parse(store.get("data/halt.json").text).set_by === "operator (hosted desk)");
  check("halt no secret leak", noSecret(on.text));
  const off = await call("/control", "POST", { passphrase: PASS, action: "halt", halted: false });
  check("halt release ok", off.status === 200 && off.body.halt.halted === false);
  check("halt release committed", JSON.parse(store.get("data/halt.json").text).halted === false);
  const bad = await call("/control", "POST", { passphrase: PASS, action: "halt", halted: "yes" });
  check("halt non-bool 400", bad.status === 400);
}
// arm fresh envelope
{
  const r = await call("/control", "POST", { passphrase: PASS, action: "arm", ...VALID });
  check("arm fresh ok", r.status === 200 && r.body.armed === true && r.body.pushed === true);
  const saved = JSON.parse(store.get("data/approvals.json").text);
  check("arm as_of today ET", /^\d{4}-\d{2}-\d{2}$/.test(saved.as_of));
  check("arm approved_by", saved.approved_by === "operator (hosted desk)");
  check("arm bounds preserved", saved.orders[0].limit_max === 29.5 && saved.orders[1].limit_min === 300.0);
  check("arm no secret leak", noSecret(r.text));
}
// arm invalid envelope rejected, no commit
{
  const before = commits.length;
  const r = await call("/control", "POST", { passphrase: PASS, action: "arm", max_orders: 1, orders: [{ symbol: "DBC", side: "buy", max_qty: 100 }] });
  check("arm invalid 400", r.status === 400 && /Envelope invalid/.test(r.body.error));
  check("arm invalid no commit", commits.length === before);
}
// reuse_last re-dates the stored envelope
{
  const r = await call("/control", "POST", { passphrase: PASS, action: "arm", reuse_last: true });
  check("reuse_last ok", r.status === 200 && r.body.armed === true);
  const saved = JSON.parse(store.get("data/approvals.json").text);
  check("reuse_last re-arm tag", /auto re-arm/.test(saved.approved_by) && /re-armed for today/.test(saved.note));
}
// disarm deletes the envelope
{
  const r = await call("/control", "POST", { passphrase: PASS, action: "disarm" });
  check("disarm ok", r.status === 200 && r.body.disarmed === true);
  check("disarm removed file", !store.has("data/approvals.json"));
  const again = await call("/control", "POST", { passphrase: PASS, action: "arm", reuse_last: true });
  check("reuse_last after disarm 400", again.status === 400 && /No previous envelope/.test(again.body.error));
}
// every commit carried an operator message
{
  check("commits journaled", commits.length >= 5 && commits.every((c) => /operator via hosted desk/.test(c.message)), commits.length + " commits");
}

server.closeAllConnections();
await new Promise((r) => server.close(r));
try { await process.getBuiltinModule("undici").getGlobalDispatcher().close(); } catch {}
console.log(failures === 0 ? "\nALL CONTROL CHECKS PASSED" : "\n" + failures + " CHECK(S) FAILED");
process.exitCode = failures === 0 ? 0 : 1;