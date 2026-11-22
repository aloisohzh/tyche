// Local harness for the Sites Function handler. Deno is not installed here, so we shim
// Deno.env and run the handler under Node 24 (native TS type-stripping). This exercises the
// real handler logic and real upstream fetches; it is NOT the deployed edge runtime.
import { handleRequest } from "../desk-site/functions/handler.ts";
import { readFileSync } from "node:fs";

globalThis.Deno = { env: { get: (k) => process.env[k] } };

const BASE = "http://localhost/functions/v1/app";
let failures = 0;

async function call(path, method = "GET") {
  const res = await handleRequest(new Request(BASE + path, { method }));
  const text = await res.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  return { status: res.status, body, text };
}

function check(name, cond, detail = "") {
  console.log((cond ? "PASS" : "FAIL") + " - " + name + (detail ? " :: " + detail : ""));
  if (!cond) failures++;
}

const masked = (s) => /^\*\*\*\d{3}$/.test(String(s || ""));

// 1. health
{
  const r = await call("");
  check("health 200", r.status === 200 && r.body.ok === true, JSON.stringify(r.body));
}
// 2. state from public repo raw
{
  const r = await call("/state");
  if (r.status === 200) {
    check("state has chain+snapshot", !!r.body.chain && "snapshot" in r.body, "generated_at=" + r.body.generated_at);
    const accts = [r.body.snapshot && r.body.snapshot.account, r.body.feed && r.body.feed.primary_account, ...Object.keys(r.body.snapshots || {})].filter(Boolean);
    check("state account ids masked", accts.length > 0 && accts.every(masked), accts.join(","));
    check("state no bearer token", !/Bearer\s+[A-Za-z0-9._-]{10,}/.test(r.text));
  } else {
    check("state reachable (GitHub raw)", false, "status=" + r.status + " body=" + JSON.stringify(r.body));
  }
}
// 3. automation without secret → committed export, live=false
{
  delete process.env.TYCHE_CLOUD_PAT;
  const r = await call("/automation");
  check("automation no-secret 200", r.status === 200, "live=" + r.body.live + " secret_configured=" + r.body.secret_configured);
  check("automation no-secret live=false", r.body.live === false && r.body.secret_configured === false);
  check("automation carries calendar", !!r.body.calendar, "phase=" + (r.body.calendar && r.body.calendar.phase));
}
// 4. automation with bogus secret → cloud rejected → graceful degrade (no raw error leak)
{
  process.env.TYCHE_CLOUD_PAT = "bogus-token-for-degradation-test";
  const r = await call("/automation");
  check("automation bogus-secret 200", r.status === 200, "ok=" + r.body.ok + " live=" + r.body.live);
  check("automation bogus-secret degrades", r.body.live === false && r.body.secret_configured === true);
  check("automation bogus-secret not live-as-cloud", !/api\/v1\/forward/.test(r.text));
  check("automation no raw exception leak", !/Traceback|Authorization|Bearer bogus/i.test(r.text), r.body.source);
  delete process.env.TYCHE_CLOUD_PAT;
}
// 5. automation with the desk's own token → live Managed cards, and nothing sensitive in the payload
{
  let pat = "";
  try {
    const line = readFileSync(new URL("../.env", import.meta.url), "utf8")
      .split(/\r?\n/).find((l) => l.startsWith("QODER_PAT="));
    pat = line ? line.split("=")[1].trim() : "";
  } catch { /* no .env on this machine */ }
  if (!pat) {
    console.log("SKIP - no QODER_PAT in .env, so the live Managed read is untested");
  } else {
    process.env.TYCHE_CLOUD_PAT = pat;
    const r = await call("/automation");
    const scheds = r.body.schedules || [];
    const sess = r.body.sessions || [];
    check("automation live 200", r.status === 200, "live=" + r.body.live);
    check("automation live is the cloud base", r.body.ok === true && r.body.live === true && /api\/v1\/cloud/.test(String(r.body.source)), r.body.source);
    check("cards come back as cadence, not templates", scheds.length > 0
      && scheds.every((s) => s.cron && s.timezone && s.window && s.agent && s.id),
      scheds.map((s) => `${s.name} · ${s.cron} · ${s.status}`).join(" | "));
    check("no forward-era fields survive", !/trigger_policy|template_id|initial_events_version|source_type/.test(r.text));
    check("sessions state how they arrived", sess.every((s) => !!s.origin), sess.map((s) => s.origin).join(","));
    check("cadence table rides the overlay", Array.isArray((r.body.calendar || {}).schedules)
      && (r.body.calendar || {}).schedules.length > 0, "rows=" + ((r.body.calendar || {}).schedules || []).length);
    // L-050: raw deployment and session rows carry environment_variables and vault_ids in plaintext.
    check("no plaintext env or vault keys", !/environment_variables|vault_ids/.test(r.text));
    check("no token in the payload", !/pt-[A-Za-z0-9_-]{6,}|Bearer\s+\S{10,}/.test(r.text));
    delete process.env.TYCHE_CLOUD_PAT;
  }
}
// 6. method rejection
{
  const r = await call("/state", "POST");
  check("POST rejected 405", r.status === 405);
}
// 7. unknown path 404
{
  const r = await call("/does-not-exist");
  check("unknown path 404", r.status === 404);
}

console.log(failures === 0 ? "\nALL HANDLER CHECKS PASSED" : "\n" + failures + " CHECK(S) FAILED");
process.exit(failures === 0 ? 0 : 1);