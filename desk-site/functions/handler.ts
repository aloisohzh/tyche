// Tyche desk live adapter — server-side reads only, no writes, no secrets in responses.
//
// /state      → latest sanitized desk state committed to the public repo (the desk's
//               push-back refreshes it; the Python builders stay the single source of truth).
// /automation → live Forward schedule/session health via a server-side PAT, overlaid on the
//               committed deterministic calendar; degrades to the committed export when the
//               secret is absent or Forward is unreachable.
//
// The browser never sees the PAT. Only selected (slimmed) fields are returned, never raw
// upstream bodies or exception text.

const REPO_RAW = "https://raw.githubusercontent.com/aloisohzh/tyche/main/desk-site/web/data";
const FORWARD_BASE = "https://api.qoder.com/api/v1/forward";
const TIMEOUT_MS = 8000;

type Json = Record<string, unknown>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function fetchJson(url: string, headers?: Record<string, string>): Promise<Json> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { headers, signal: ctrl.signal, redirect: "follow" });
    if (!res.ok) throw new Error("upstream HTTP " + res.status);
    return (await res.json()) as Json;
  } finally {
    clearTimeout(timer);
  }
}

function slimSchedule(d: Json): Json {
  return {
    id: d.id,
    name: d.name,
    description: d.description,
    status: d.status,
    trigger_policy: d.trigger_policy,
    initial_events_version: d.initial_events_version,
    template_id: d.template_id,
    updated_at: d.updated_at,
  };
}

function slimSession(d: Json): Json {
  const template = (d.template as Json) || {};
  return {
    id: d.id,
    title: d.title,
    status: d.status,
    source_type: d.source_type,
    template: { id: template.id, name: template.name },
    stats: d.stats,
    usage: d.usage,
    metadata: d.metadata,
    created_at: d.created_at,
  };
}

async function handleState(): Promise<Response> {
  try {
    return json(await fetchJson(REPO_RAW + "/state.json"));
  } catch {
    return json({ error: "state_unavailable" }, 502);
  }
}

async function handleAutomation(): Promise<Response> {
  let base: Json;
  try {
    base = await fetchJson(REPO_RAW + "/automation.json");
  } catch {
    base = { ok: false, source: "committed export unreachable", schedules: [], sessions: [], calendar: null };
  }

  const pat = Deno.env.get("TYCHE_FORWARD_PAT");
  if (!pat) {
    return json({ ...base, live: false, secret_configured: false });
  }

  try {
    const headers = { authorization: "Bearer " + pat, accept: "application/json" };
    const [sched, sess] = await Promise.all([
      fetchJson(FORWARD_BASE + "/schedules?limit=20", headers),
      fetchJson(FORWARD_BASE + "/sessions?limit=12", headers),
    ]);
    const schedules = (((sched.data as Json[]) || [])).map(slimSchedule);
    const sessions = (((sess.data as Json[]) || [])).map(slimSession);
    return json({
      ok: true,
      live: true,
      secret_configured: true,
      source: "live - api.qoder.com/api/v1/forward",
      fetched_at: new Date().toISOString(),
      schedules,
      sessions,
      calendar: base.calendar ?? null,
    });
  } catch {
    return json({
      ...base,
      ok: false,
      live: false,
      secret_configured: true,
      source: "Forward API unreachable - committed export",
      fetched_at: new Date().toISOString(),
    });
  }
}

export async function handleRequest(req: Request): Promise<Response> {
  if (req.method !== "GET") return json({ error: "method_not_allowed" }, 405);
  const path = new URL(req.url).pathname.replace(/\/+$/, "");
  if (path.endsWith("/state")) return handleState();
  if (path.endsWith("/automation")) return handleAutomation();
  if (path === "" || path.endsWith("/app") || path.endsWith("/health")) {
    return json({ ok: true, service: "tyche-desk-adapter", endpoints: ["/state", "/automation"] });
  }
  return json({ error: "not_found" }, 404);
}