// Tyche desk live adapter - server-side reads, plus an operator-gated control path.
//
// /state      -> latest sanitized desk state committed to the public repo (the desk's
//               push-back refreshes it; the Python builders stay the single source of truth).
// /automation -> live Forward schedule/session health via a server-side PAT, overlaid on the
//               committed deterministic calendar; degrades to the committed export when the
//               secret is absent or Forward is unreachable.
// /schedule   -> the cloud automation card the local desk last published (cadence, next runs, run
//               history). Read-only here: pausing or firing a card needs the cloud token, which stays
//               on the operator's machine, and two write paths to one switch is how cadence drifts.
// /control    -> POST operator console (passphrase-gated): arm/disarm the approval envelope
//               and engage/release the kill-switch by committing data/approvals.json and
//               data/halt.json through the GitHub contents API. GET /control/status reports
//               only whether the console is configured. Visitors without the passphrase see
//               a read-only desk; secrets never appear in responses or client code.
//
// The browser never sees the PATs. Only selected (slimmed) fields are returned, never raw
// upstream bodies or exception text.

const REPO_RAW = "https://raw.githubusercontent.com/aloisohzh/tyche/main/desk-site/web/data";
const REPO_ROOT_RAW = REPO_RAW.replace("/desk-site/web/data", "");
const FORWARD_BASE = "https://api.qoder.com/api/v1/forward";
const GH_REPO = "aloisohzh/tyche";
const TIMEOUT_MS = 8000;

function env(name: string): string | undefined {
  return Deno.env.get(name);
}

function ghApi(): string {
  return env("TYCHE_GITHUB_API") || "https://api.github.com";
}

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
  let base: Json;
  try {
    base = await fetchJson(REPO_RAW + "/state.json");
  } catch {
    return json({ error: "state_unavailable" }, 502);
  }
  // state.json is a published snapshot, but a strategy switch is something the operator just moved:
  // overlay the live switch file so the console cannot show a stale answer for a fresh decision.
  try {
    const sw = await fetchJson(REPO_ROOT_RAW + "/data/strategies.json");
    const view = base.strategies as Json | undefined;
    if (!view || !Array.isArray(view.strategies)) return json(base);
    const rows = view.strategies as Json[];
    const enabled = (sw.enabled && typeof sw.enabled === "object") ? sw.enabled as Json : {};
    for (const row of rows) {
      const value = enabled[String(row.strategy_id)];
      if (typeof value === "boolean") {
        row.enabled = value;
        row.operator_override = value;
        row.source = "data/strategies.json";
      }
    }
    view.live = rows.filter((r) => r.enabled === true).map((r) => r.strategy_id);
    view.switch_file = {
      path: "data/strategies.json", present: true,
      updated_at: sw.updated_at ?? null, updated_by: sw.updated_by ?? null,
    };
  } catch {
    // no switch file yet, or it is unreachable: the snapshot's own answer stands
  }
  return json(base);
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

// The cadence card is cloud state that only the local desk holds a token for, so the hosted page serves
// the snapshot that desk published and marks it read-only in the UI. `fetched_at` inside the payload says
// how old the view is; inventing a second write path here would put two hands on one switch.
async function handleSchedule(): Promise<Response> {
  try {
    return json(await fetchJson(REPO_RAW + "/schedule.json"));
  } catch {
    return json({ ok: false, card: null, cards: [], runs: [], problem: "committed cadence export unreachable" }, 502);
  }
}

// ---------------------------------------------------------------- operator console
function b64encode(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64decode(s: string): string {
  const bin = atob(s.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

function todayET(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

function operatorConfigured(): boolean {
  return Boolean(env("TYCHE_OPERATOR_PASSPHRASE") && env("TYCHE_GITHUB_PAT"));
}

function ghHeaders(pat: string): Record<string, string> {
  return {
    authorization: "Bearer " + pat,
    accept: "application/vnd.github+json",
    "user-agent": "tyche-desk",
    "content-type": "application/json",
  };
}

async function ghFetch(url: string, pat: string, init?: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, headers: ghHeaders(pat), signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function ghRead(path: string, pat: string): Promise<{ sha?: string; text?: string }> {
  const res = await ghFetch(`${ghApi()}/repos/${GH_REPO}/contents/${path}?ref=main`, pat);
  if (res.status === 404) return {};
  if (!res.ok) throw new Error("gh read " + res.status);
  const d = (await res.json()) as Json;
  return { sha: d.sha as string, text: b64decode((d.content as string) || "") };
}

async function ghCommit(path: string, pat: string, message: string, text: string | null, sha?: string): Promise<void> {
  const url = `${ghApi()}/repos/${GH_REPO}/contents/${path}`;
  if (text === null) {
    if (!sha) return; // nothing to delete
    const res = await ghFetch(url, pat, { method: "DELETE", body: JSON.stringify({ message, sha, branch: "main" }) });
    if (!res.ok) throw new Error("gh delete " + res.status);
    return;
  }
  const body: Json = { message, content: b64encode(text), branch: "main" };
  if (sha) body.sha = sha;
  const res = await ghFetch(url, pat, { method: "PUT", body: JSON.stringify(body) });
  if (!res.ok) throw new Error("gh write " + res.status);
}

function finitePos(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x > 0;
}

function validateEnvelope(e: Json): string | null {
  const orders = e.orders;
  if (!Array.isArray(orders) || orders.length < 1) return "envelope needs at least one order line";
  const maxOrders = e.max_orders;
  if (typeof maxOrders !== "number" || !Number.isInteger(maxOrders) || maxOrders < 1) return "max_orders must be a whole number >= 1";
  if (e.max_notional != null && !finitePos(e.max_notional)) return "max_notional must be a positive number";
  const seen = new Set<string>();
  for (const raw of orders) {
    const o = raw as Json;
    if (typeof o.symbol !== "string" || !o.symbol) return "each line needs a symbol";
    if (o.side !== "buy" && o.side !== "sell") return "side must be buy or sell";
    if (typeof o.max_qty !== "number" || !Number.isInteger(o.max_qty) || o.max_qty < 1) return "max_qty must be a whole number >= 1";
    if (o.multiplier != null && o.multiplier !== 1 && o.multiplier !== 100) return "multiplier must be 1 or 100";
    if (o.max_total_qty != null && (typeof o.max_total_qty !== "number" || !Number.isInteger(o.max_total_qty) || o.max_total_qty < 1)) {
      return "max_total_qty must be a whole number >= 1";
    }
    if (o.side === "buy") {
      if (!finitePos(o.limit_max) || o.limit_min != null) return "buy line needs a positive limit_max and no limit_min";
    } else if (!finitePos(o.limit_min) || o.limit_max != null) {
      return "sell line needs a positive limit_min and no limit_max";
    }
    const key = o.symbol + "|" + o.side;
    if (seen.has(key)) return "duplicate symbol+side lines in envelope";
    seen.add(key);
  }
  return null;
}

async function handleControl(req: Request): Promise<Response> {
  const passphrase = env("TYCHE_OPERATOR_PASSPHRASE");
  const pat = env("TYCHE_GITHUB_PAT");
  if (!passphrase || !pat) {
    return json({ ok: false, configured: false, error: "Operator console not configured - add TYCHE_OPERATOR_PASSPHRASE and TYCHE_GITHUB_PAT in Sites Settings." }, 503);
  }
  let body: Json;
  try {
    body = (await req.json()) as Json;
  } catch {
    return json({ ok: false, error: "invalid JSON body" }, 400);
  }
  if (!body || typeof body !== "object" || body.passphrase !== passphrase) {
    return json({ ok: false, error: "passphrase rejected" }, 401);
  }
  const action = body.action;
  try {
    if (action === "ping") return json({ ok: true, operator: true });

    if (action === "halt") {
      if (typeof body.halted !== "boolean") return json({ ok: false, error: "halted must be a boolean" }, 400);
      const reason = String(body.reason || "").slice(0, 200) || (body.halted ? "operator kill-switch via hosted desk" : "operator resume via hosted desk");
      const state = { halted: body.halted, reason, ts: new Date().toISOString(), set_by: "operator (hosted desk)" };
      const cur = await ghRead("data/halt.json", pat);
      await ghCommit("data/halt.json", pat, body.halted ? "Engage kill-switch (operator via hosted desk)" : "Release kill-switch (operator via hosted desk)", JSON.stringify(state, null, 2), cur.sha);
      return json({ ok: true, pushed: true, halt: state });
    }

    if (action === "strategy") {
      const id = String(body.strategy_id || "").trim().toUpperCase();
      if (!/^PB-\d{3}$/.test(id)) return json({ ok: false, error: "strategy_id must look like PB-000" }, 400);
      if (typeof body.enabled !== "boolean") return json({ ok: false, error: "enabled must be a boolean" }, 400);
      const cur = await ghRead("data/strategies.json", pat);
      let state: Json = { enabled: {} };
      if (cur.text) {
        try {
          state = JSON.parse(cur.text) as Json;
        } catch {
          return json({ ok: false, error: "data/strategies.json is unreadable - refusing to overwrite it" }, 409);
        }
      }
      const switches = (state.enabled && typeof state.enabled === "object") ? state.enabled as Json : {};
      switches[id] = body.enabled;
      state.enabled = switches;
      state.updated_at = new Date().toISOString();
      state.updated_by = "operator (hosted desk)";
      await ghCommit("data/strategies.json", pat,
        `${body.enabled ? "Enable" : "Disable"} ${id} (operator via hosted desk)`,
        JSON.stringify(state, null, 2), cur.sha);
      return json({ ok: true, pushed: true, strategy_id: id, enabled: body.enabled });
    }

    if (action === "disarm") {
      const cur = await ghRead("data/approvals.json", pat);
      await ghCommit("data/approvals.json", pat, "Disarm auto approval envelope (operator via hosted desk)", null, cur.sha);
      return json({ ok: true, pushed: true, disarmed: true });
    }

    if (action === "arm") {
      let candidate: Json;
      if (body.reuse_last) {
        const cur = await ghRead("data/approvals.json", pat);
        if (!cur.text) return json({ ok: false, error: "No previous envelope in the cloud feed - use Pre-approve to define bounds." }, 400);
        try {
          candidate = JSON.parse(cur.text) as Json;
        } catch {
          return json({ ok: false, error: "Previous envelope is unreadable." }, 400);
        }
        candidate.approved_by = "operator (hosted auto re-arm)";
        candidate.note = String(candidate.note || "") + " | re-armed for today via hosted desk";
      } else {
        candidate = {
          max_orders: body.max_orders,
          max_notional: body.max_notional ?? null,
          note: String(body.note || "").slice(0, 200),
          orders: body.orders,
          approved_by: "operator (hosted desk)",
        };
      }
      candidate.as_of = todayET();
      candidate.approved_at = new Date().toISOString();
      const invalid = validateEnvelope(candidate);
      if (invalid) return json({ ok: false, error: "Envelope invalid: " + invalid }, 400);
      const cur = await ghRead("data/approvals.json", pat);
      await ghCommit("data/approvals.json", pat, "Arm auto approval envelope (operator via hosted desk)", JSON.stringify(candidate, null, 2), cur.sha);
      return json({ ok: true, pushed: true, armed: true, envelope: candidate });
    }

    return json({ ok: false, error: "unknown action" }, 400);
  } catch {
    return json({ ok: false, error: "Cloud write failed - check that TYCHE_GITHUB_PAT has contents:write on the repo." }, 502);
  }
}

export async function handleRequest(req: Request): Promise<Response> {
  const path = new URL(req.url).pathname.replace(/\/+$/, "");
  if (path.endsWith("/control/status")) {
    if (req.method !== "GET") return json({ error: "method_not_allowed" }, 405);
    return json({ operator_configured: operatorConfigured() });
  }
  if (path.endsWith("/control")) {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    return handleControl(req);
  }
  if (req.method !== "GET") return json({ error: "method_not_allowed" }, 405);
  if (path.endsWith("/state")) return handleState();
  if (path.endsWith("/automation")) return handleAutomation();
  if (path.endsWith("/schedule")) return handleSchedule();
  if (path === "" || path.endsWith("/app") || path.endsWith("/health")) {
    return json({
      ok: true,
      service: "tyche-desk-adapter",
      endpoints: ["/state", "/automation", "/schedule", "/control"],
    });
  }
  return json({ error: "not_found" }, 404);
}