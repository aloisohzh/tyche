// Credential-free fakes shared by local-test.mjs and preview-server.mjs.
import { randomBytes } from 'node:crypto';

class BackendError extends Error {
  constructor(code, status) { super(code); this.code = code; this.status = status; }
}

// ---- in-memory fake database (only the operations routes.mjs uses) ----
function fakeDb() {
  const tables = { bridge_state: [], pending_asks: [], decisions: [], webhook_events: [] };
  const pk = { bridge_state: 'id', pending_asks: 'tool_use_id', decisions: 'id', webhook_events: 'webhook_id' };
  function from(table) {
    const state = { filters: [], order: null, limit: null, mode: 'select', payload: null, conflict: null };
    const chain = {
      select() { return chain; },
      eq(col, val) { state.filters.push(r => r[col] === val); return chain; },
      gte(col, val) { state.filters.push(r => r[col] >= val); return chain; },
      order(col, opts) { state.order = [col, opts?.ascending !== false]; return chain; },
      limit(n) { state.limit = n; return chain; },
      insert(row) { state.mode = 'insert'; state.payload = row; return chain; },
      insertIfAbsent(row, opts) { state.mode = 'insertIfAbsent'; state.payload = row; state.conflict = opts.onConflict; return chain; },
      update(row) { state.mode = 'update'; state.payload = row; return chain; },
      delete() { state.mode = 'delete'; return chain; },
      then(resolve) {
        const rows = tables[table];
        const match = r => state.filters.every(f => f(r));
        let data = null;
        if (state.mode === 'select') {
          data = rows.filter(match);
          if (state.order) {
            const [col, asc] = state.order;
            data = [...data].sort((a, b) => (a[col] > b[col] ? 1 : a[col] < b[col] ? -1 : 0) * (asc ? 1 : -1));
          }
          if (state.limit != null) data = data.slice(0, state.limit);
        } else if (state.mode === 'insert') {
          const row = { ...state.payload };
          if (table === 'decisions' && !row.id) row.id = randomBytes(16).toString('hex');
          rows.push(row);
          data = [row];
        } else if (state.mode === 'insertIfAbsent') {
          const key = state.conflict;
          if (rows.some(r => r[key] === state.payload[key])) data = [];
          else { rows.push({ ...state.payload }); data = [{ ...state.payload }]; }
        } else if (state.mode === 'update') {
          data = [];
          for (const row of rows) if (match(row)) Object.assign(row, state.payload);
        } else if (state.mode === 'delete') {
          tables[table] = rows.filter(r => !match(r));
          data = [];
        }
        resolve({ data, error: null });
      },
    };
    return chain;
  }
  return { from, tables };
}

// ---- fake upstreams ----
const SESSION = 'sess_test0000000000000001';
const DESK_TEMPLATE = 'tmpl_004fa008901a6c256bd0ed3f';
const IDENTITY = 'idn_1d7b9ab60a1bcc934d4a1d8f';
const sent = [];          // Telegram sendMessage payloads
const posted = [];        // Forward POST /sessions/.../events bodies
let relayStatus = 200;    // simulate 409 mid-turn
const threadEvents = {
  sthr_coord: [
    { id: 'evt_c1', type: 'agent.message', content: [{ type: 'text', text: 'Desk online. Account 9000001 ready.' }] },
  ],
  sthr_exec: [
    { id: 'evt_a1', type: 'agent.mcp_tool_use', name: 'sim_submit_order', mcp_server_name: 'moomoo',
      evaluated_permission: 'ask', input: { account_id: '9000001', symbol: 'US.SPY', qty: 5 } },
  ],
};
const threads = [
  { id: 'sthr_coord', role: 'coordinator', name: 'desk', archived_at: null },
  { id: 'sthr_exec', role: 'member', name: 'executor', archived_at: null },
];
function fakeFetch(url, options = {}) {
  const u = String(url);
  if (u.startsWith('https://api.telegram.org/')) {
    const body = JSON.parse(options.body);
    if (u.endsWith('/sendMessage')) { sent.push(body); return jsonResponse({ ok: true, result: { message_id: sent.length } }); }
    return jsonResponse({ ok: true, result: [] });
  }
  if (u.startsWith('https://api.qoder.com/api/v1/forward')) {
    const path = u.replace('https://api.qoder.com/api/v1/forward', '');
    const method = options.method || 'GET';
    if (method === 'POST' && /\/sessions\/[^/]+\/events$/.test(path)) {
      posted.push(JSON.parse(options.body));
      if (relayStatus !== 200) return new Response('busy', { status: relayStatus });
      return jsonResponse({});
    }
    if (path === `/sessions/${SESSION}`) {
      return jsonResponse({ id: SESSION, identity_id: IDENTITY, template: { id: DESK_TEMPLATE }, status: 'running', title: 'tyche-test', usage: { total_credits: 12 } });
    }
    if (path === `/sessions/${SESSION}/threads`) return jsonResponse({ data: threads });
    const eventsMatch = path.match(/^\/sessions\/([^/]+)\/threads\/([^/]+)\/events/);
    if (eventsMatch) {
      const all = threadEvents[eventsMatch[2]] || [];
      const after = new URL(u).searchParams.get('after_id');
      const index = after ? all.findIndex(e => e.id === after) + 1 : 0;
      const batch = all.slice(index);
      return jsonResponse({ data: batch, last_id: batch.at(-1)?.id ?? after, has_more: false });
    }
    if (path.startsWith('/schedule_runs')) return jsonResponse({ data: [] });
    return new Response('not found', { status: 404 });
  }
  throw new Error('unexpected fetch ' + u);
}
const jsonResponse = obj => new Response(JSON.stringify(obj), { status: 200, headers: { 'Content-Type': 'application/json' } });


export { BackendError, fakeDb, fakeFetch, jsonResponse, SESSION, DESK_TEMPLATE, IDENTITY, sent, posted, threadEvents, threads };
export function setRelayStatus(v) { relayStatus = v; }
