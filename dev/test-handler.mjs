// Local harness for the Sites Function handler. Deno is not installed here, so we shim
// Deno.env and run the handler under Node 24 (native TS type-stripping). This exercises the
// real handler logic and real upstream fetches; it is NOT the deployed edge runtime.
import { handleRequest } from "../desk-site/functions/handler.ts";

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
  delete process.env.TYCHE_FORWARD_PAT;
  const r = await call("/automation");
  check("automation no-secret 200", r.status === 200, "live=" + r.body.live + " secret_configured=" + r.body.secret_configured);
  check("automation no-secret live=false", r.body.live === false && r.body.secret_configured === false);
  check("automation carries calendar", !!r.body.calendar, "phase=" + (r.body.calendar && r.body.calendar.phase));
}
// 4. automation with bogus secret → Forward rejected → graceful degrade (no raw error leak)
{
  process.env.TYCHE_FORWARD_PAT = "bogus-token-for-degradation-test";
  const r = await call("/automation");
  check("automation bogus-secret 200", r.status === 200, "ok=" + r.body.ok + " live=" + r.body.live);
  check("automation bogus-secret degrades", r.body.live === false && r.body.secret_configured === true);
  check("automation no raw exception leak", !/Traceback|Authorization|Bearer bogus/i.test(r.text), r.body.source);
  delete process.env.TYCHE_FORWARD_PAT;
}
// 5. method rejection
{
  const r = await call("/state", "POST");
  check("POST rejected 405", r.status === 405);
}
// 6. unknown path 404
{
  const r = await call("/does-not-exist");
  check("unknown path 404", r.status === 404);
}

console.log(failures === 0 ? "\nALL HANDLER CHECKS PASSED" : "\n" + failures + " CHECK(S) FAILED");
process.exit(failures === 0 ? 0 : 1);