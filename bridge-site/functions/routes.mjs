// Tyche bridge: Telegram <-> Forward desk relay. Dependency-injected for local
// tests; index.ts retains Deno.serve. Secrets come only from the runtime env.
// NEVER auto-approves: /approve and /deny are the only confirmation paths and
// only the allowlisted Telegram chat can issue them.
export function application({ db, env, fetch, BackendError }) {
  const ORIGIN = 'https://api.qoder.com';
  const FORWARD = ORIGIN + '/api/v1/forward';
  const IDENTITY_ID = 'idn_1d7b9ab60a1bcc934d4a1d8f';
  const DESK_TEMPLATE_ID = 'tmpl_004fa008901a6c256bd0ed3f';
  const SCHEDULE_IDS = [
    'sched_52f7a8a04e4bf656e25fac47', // tyche-premarket
    'sched_f522c892f2a72e77dd7c590f', // tyche-eod
    'sched_7d7dcb7101f048b8b4df159f', // tyche-eod-halfday
  ];
  const ASK_EVENTS = new Set(['agent.tool_use', 'agent.mcp_tool_use']);
  const RESOLUTION_EVENTS = new Set(['user.tool_confirmation', 'agent.tool_result', 'agent.mcp_tool_result']);
  const MAX_PREVIEW = 1500;
  const MAX_MESSAGE = 3900;
  const MAX_BODY = 262144;
  const DRAIN_PAGES = 20;

  const fail = (code, status) => { throw new BackendError(code, status); };
  const rows = result => { if (result.error) fail('database_unavailable', 503); return result.data; };
  const now = () => new Date().toISOString();
  const esc = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const maskIds = text => String(text).replace(/\d{7,}/g, m => '...' + m.slice(-3));

  function timingSafeEqual(a, b) {
    if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    return diff === 0;
  }

  async function readBody(request) {
    const reader = request.body?.getReader();
    if (!reader) fail('invalid_input', 400);
    let size = 0; const chunks = [];
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > MAX_BODY) { await reader.cancel(); fail('payload_too_large', 413); }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const raw = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { raw.set(chunk, offset); offset += chunk.length; }
    let json;
    try { json = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)); }
    catch { fail('invalid_input', 400); }
    return { raw, json };
  }

  // ---- upstream clients (fixed trusted destinations only) ----

  async function forwardReq(method, path, body) {
    const token = env('QODER_PAT');
    if (!token) fail('service_not_configured', 503);
    try {
      const response = await fetch(FORWARD + path, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(25000),
      });
      const text = await response.text();
      if (!response.ok) return { http_error: response.status, body: text.slice(0, 500) };
      try { return text ? JSON.parse(text) : {}; } catch { return {}; }
    } catch { return { http_error: 0, body: 'network' }; }
  }

  async function telegramApi(method, params) {
    const token = env('TELEGRAM_BOT_TOKEN');
    if (!token) return { ok: false };
    try {
      const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: AbortSignal.timeout(25000),
      });
      const payload = await response.json().catch(() => null);
      return payload && payload.ok ? payload : { ok: false };
    } catch { return { ok: false }; }
  }

  async function say(text) {
    const chatId = env('TELEGRAM_CHAT_ID');
    if (!chatId) return;
    if (text.length > MAX_MESSAGE) text = text.slice(0, MAX_MESSAGE) + '\n... (truncated)';
    const result = await telegramApi('sendMessage', { chat_id: chatId, text, parse_mode: 'HTML' });
    if (!result.ok) console.warn('telegram_send_failed');
  }

  // ---- durable state ----

  async function getState(key, fallback) {
    const found = rows(await db.from('bridge_state').select('data').eq('id', key).limit(1));
    return found?.length ? found[0].data : fallback;
  }

  async function setState(key, data) {
    const inserted = rows(await db.from('bridge_state')
      .insertIfAbsent({ id: key, data, updated_at: now() }, { onConflict: 'id' }).select('id'));
    if (!inserted?.length) {
      rows(await db.from('bridge_state').update({ data, updated_at: now() }).eq('id', key));
    }
  }

  const loadBinding = () => getState('binding', { session_id: null, next_n: 1 });
  const loadCursors = () => getState('cursors', {});
  const loadThreads = () => getState('threads', {});

  async function listPending() {
    return rows(await db.from('pending_asks')
      .select('tool_use_id,n,session_id,name,server,input,thread_id,thread_name')
      .order('n', { ascending: true }).limit(200)) || [];
  }

  // ---- event interpretation (ported from the proven local bridge) ----

  function isAsk(event) {
    if (!ASK_EVENTS.has(event.type)) return false;
    if (event.evaluated_permission === 'ask') return true;
    return event.evaluation?.type === 'always_ask' && !('evaluated_permission' in event);
  }

  function resolutionId(event) {
    if (!RESOLUTION_EVENTS.has(event.type)) return null;
    return event.tool_use_id || event.mcp_tool_use_id || null;
  }

  function formatPreview(ask) {
    let tool = ask.name || 'tool';
    if (ask.server) tool = `${ask.server}/${tool}`;
    let body = JSON.stringify(ask.input ?? {}, null, 1);
    if (body.length > MAX_PREVIEW) body = body.slice(0, MAX_PREVIEW) + '\n... (truncated)';
    const thread = ask.thread_name || ask.thread_id || '?';
    return `<b>Approval required #${ask.n}</b> — a member thread asks to run `
      + `<code>${esc(tool)}</code>\n<pre>${esc(maskIds(body))}</pre>\n`
      + `Reply <code>/approve ${ask.n}</code> or <code>/deny ${ask.n} [reason]</code>. `
      + `Nothing runs without your explicit approve. (thread ${esc(thread)})`;
  }

  async function refreshThreads(sessionId) {
    const result = await forwardReq('GET', `/sessions/${sessionId}/threads`);
    if (result.http_error) return null;
    const threads = {};
    for (const thread of result.data || []) {
      threads[thread.id] = {
        role: thread.role ?? null,
        name: thread.name ?? null,
        archived: Boolean(thread.archived_at),
      };
    }
    await setState('threads', threads);
    return threads;
  }

  async function drainThread(sessionId, threadId, cursors) {
    const events = [];
    let cursor = cursors[threadId] ?? null;
    for (let page = 0; page < DRAIN_PAGES; page++) {
      let path = `/sessions/${sessionId}/threads/${threadId}/events?limit=100`;
      if (cursor) path += `&after_id=${cursor}`;
      const result = await forwardReq('GET', path);
      if (result.http_error) break;
      const batch = result.data || [];
      for (const event of batch) if (!event.session_thread_id) event.session_thread_id = threadId;
      events.push(...batch);
      cursor = result.last_id || cursor;
      if (!result.has_more) break;
    }
    cursors[threadId] = cursor;
    return events;
  }

  // Track asks, resolve confirmations, relay coordinator text. Returns fresh ask rows.
  async function processEvents(events, threads, { relayCoordinator = false } = {}) {
    const binding = await loadBinding();
    const pending = await listPending();
    const byId = new Map(pending.map(ask => [ask.tool_use_id, ask]));
    const fresh = [];
    let nextN = binding.next_n;
    for (const event of events) {
      const resolved = resolutionId(event);
      if (resolved && byId.has(resolved)) {
        rows(await db.from('pending_asks').delete().eq('tool_use_id', resolved));
        byId.delete(resolved);
      }
      if (isAsk(event) && !byId.has(event.id)) {
        const info = threads[event.session_thread_id] || {};
        const ask = {
          tool_use_id: event.id,
          n: nextN++,
          session_id: binding.session_id,
          name: event.name ?? null,
          server: event.mcp_server_name ?? null,
          input: event.input ?? {},
          thread_id: event.session_thread_id ?? null,
          thread_name: info.name ?? null,
          seen_at: now(),
        };
        rows(await db.from('pending_asks').insert(ask).select('tool_use_id'));
        byId.set(event.id, ask);
        fresh.push(ask);
      }
    }
    if (nextN !== binding.next_n) {
      await setState('binding', { ...binding, next_n: nextN });
    }
    for (const ask of fresh) await say(formatPreview(ask));
    if (relayCoordinator) {
      for (const event of events) {
        if (threads[event.session_thread_id]?.role !== 'coordinator') continue;
        if (event.type === 'agent.message') {
          const text = (event.content || [])
            .filter(block => block.type === 'text')
            .map(block => block.text || '')
            .join('\n').trim();
          if (text) await say(esc(maskIds(text)));
        } else if (event.type === 'session.error') {
          await say(`<b>Session error</b>: ${esc(maskIds(JSON.stringify(event.error ?? null)))}`);
        }
      }
    }
    return fresh;
  }

  async function bind(sessionId, label = 'Bound') {
    const binding = await loadBinding();
    rows(await db.from('pending_asks').delete().gte('n', 0));
    await setState('binding', { session_id: sessionId, next_n: binding.next_n });
    await setState('cursors', {});
    const threads = await refreshThreads(sessionId);
    if (!threads) {
      await say(`Cannot bind <code>${esc(sessionId)}</code>: thread list unavailable.`);
      return false;
    }
    const cursors = {};
    let pendingCount = 0;
    for (const threadId of Object.keys(threads)) {
      const events = await drainThread(sessionId, threadId, cursors);
      const fresh = await processEvents(events, threads);
      pendingCount += fresh.length;
    }
    await setState('cursors', cursors);
    await say(
      `${label} to session <code>${esc(sessionId)}</code>. ${pendingCount} pending approval(s). `
      + 'Send any question to relay it to the desk; /help for commands.'
    );
    return true;
  }

  async function isDeskSession(sessionId) {
    const session = await forwardReq('GET', `/sessions/${sessionId}`);
    if (session.http_error) return false;
    return session.identity_id === IDENTITY_ID && session.template?.id === DESK_TEMPLATE_ID;
  }

  // Bind automatically when a schedule run starts so mid-run approvals route here.
  async function ensureBound(sessionId) {
    const binding = await loadBinding();
    if (binding.session_id === sessionId) return true;
    if (!(await isDeskSession(sessionId))) return false;
    return bind(sessionId, 'Auto-bound');
  }

  async function drainBoundSession(sessionId, onlyThreadId) {
    const threads = (await refreshThreads(sessionId)) || (await loadThreads());
    const cursors = await loadCursors();
    for (const [threadId, info] of Object.entries(threads)) {
      if (info.archived) continue;
      if (onlyThreadId && threadId !== onlyThreadId) continue;
      const events = await drainThread(sessionId, threadId, cursors);
      if (events.length) await processEvents(events, threads, { relayCoordinator: true });
    }
    await setState('cursors', cursors);
  }

  async function latestSessionId() {
    let best = null;
    for (const scheduleId of SCHEDULE_IDS) {
      const result = await forwardReq(
        'GET', `/schedule_runs?identity_id=${IDENTITY_ID}&schedule_id=${scheduleId}&limit=1`);
      for (const run of result.data || []) {
        if (run.session_id && (!best || run.created_at > best[0])) best = [run.created_at, run.session_id];
      }
    }
    return best ? best[1] : null;
  }

  // ---- Telegram inbound commands ----

  async function confirm(token, result, reason) {
    if (!/^\d+$/.test(token)) {
      await say('Usage: /approve N or /deny N [reason] (see /pending).');
      return;
    }
    const n = Number(token);
    const found = rows(await db.from('pending_asks')
      .select('tool_use_id,n,session_id,name').eq('n', n).limit(1));
    if (!found?.length) {
      await say(`No pending approval #${esc(token)}. Use /pending to list.`);
      return;
    }
    const ask = found[0];
    const binding = await loadBinding();
    if (ask.session_id !== binding.session_id) {
      await say(`Approval #${n} belongs to an older session; rebind with /session latest.`);
      return;
    }
    const body = { type: 'user.tool_confirmation', tool_use_id: ask.tool_use_id, result };
    if (reason) body.deny_message = reason;
    const response = await forwardReq('POST', `/sessions/${binding.session_id}/events`, { events: [body] });
    if (response.http_error) {
      await say(`Confirmation failed: HTTP ${response.http_error} ${esc(String(response.body).slice(0, 200))}`);
      return;
    }
    rows(await db.from('pending_asks').delete().eq('tool_use_id', ask.tool_use_id));
    rows(await db.from('decisions').insert({ n, tool: ask.name, result, reason: reason ?? null }).select('id'));
    const verb = result === 'allow' ? 'Approved' : 'Denied';
    await say(
      `${verb} #${n} <code>${esc(ask.name)}</code>. `
      + (result === 'allow'
        ? 'A submit is not a fill — watch for the broker order state.'
        : 'The desk will see your denial.')
    );
  }

  // Like Python str.split(maxsplit=2): the remainder keeps its inner spaces.
  function split3(text) {
    const trimmed = text.trim();
    const i1 = trimmed.search(/\s/);
    if (i1 === -1) return [trimmed];
    const head = trimmed.slice(0, i1);
    const rest = trimmed.slice(i1).trimStart();
    const i2 = rest.search(/\s/);
    if (i2 === -1) return [head, rest];
    return [head, rest.slice(0, i2), rest.slice(i2).trimStart()];
  }

  async function handleCommand(text) {
    const parts = split3(text);
    const command = parts[0].toLowerCase().split('@')[0];
    const binding = await loadBinding();
    if (command === '/start' || command === '/help') {
      await say(
        '<b>Tyche bridge (cloud)</b>\n'
        + '/session latest — bind the newest schedule-run session\n'
        + '/session &lt;sess_id&gt; — bind a specific session\n'
        + '/status — session status and credits\n'
        + '/pending — list approvals waiting for you\n'
        + '/approve N — allow pending approval N\n'
        + '/deny N [reason] — deny pending approval N\n'
        + '/interrupt — stop the current desk turn\n'
        + 'Any other text is relayed to the desk as a question.\n'
        + 'Approvals are never automatic; only this chat can issue them.'
      );
    } else if (command === '/session') {
      let target = parts[1] || null;
      if (target === 'latest') {
        target = await latestSessionId();
        if (!target) { await say('No schedule-run session found yet.'); return; }
      }
      if (!target) {
        await say(`Current: <code>${esc(binding.session_id || 'unbound')}</code>`);
        return;
      }
      if (!/^sess_[A-Za-z0-9]+$/.test(target)) { await say('Invalid session id.'); return; }
      await bind(target);
    } else if (command === '/status') {
      if (!binding.session_id) { await say('Not bound. Use /session latest.'); return; }
      const session = await forwardReq('GET', `/sessions/${binding.session_id}`);
      if (session.http_error) { await say(`Status failed: HTTP ${session.http_error}`); return; }
      const pending = await listPending();
      await say(
        `<b>${esc(session.title || session.id)}</b>\n`
        + `Status: ${esc(session.status)} | credits: ${esc(session.usage?.total_credits ?? '?')}\n`
        + `Pending approvals: ${pending.length}`
      );
    } else if (command === '/pending') {
      const pending = await listPending();
      if (!pending.length) { await say('No pending approvals.'); return; }
      for (const ask of pending) await say(formatPreview(ask));
    } else if (command === '/approve') {
      await confirm(parts[1] || '', 'allow', null);
    } else if (command === '/deny') {
      await confirm(parts[1] || '', 'deny', parts[2] || null);
    } else if (command === '/interrupt') {
      if (!binding.session_id) { await say('Not bound.'); return; }
      const response = await forwardReq('POST', `/sessions/${binding.session_id}/events`,
        { events: [{ type: 'user.interrupt' }] });
      await say(response.http_error ? `Interrupt failed: HTTP ${response.http_error}` : 'Interrupt sent.');
    } else {
      if (!binding.session_id) { await say('Not bound. Use /session latest first.'); return; }
      const response = await forwardReq('POST', `/sessions/${binding.session_id}/events`,
        { events: [{ type: 'user.message', content: [{ type: 'text', text }] }] });
      if (response.http_error === 409) {
        await say('Desk is mid-turn; message NOT sent. Retry when idle (/status).');
      } else if (response.http_error) {
        await say(`Relay failed: HTTP ${response.http_error} ${esc(String(response.body).slice(0, 200))}`);
      } else {
        await say('Relayed to the desk; the reply will appear here.');
      }
    }
  }

  async function handleTelegram(request) {
    const secret = env('TELEGRAM_WEBHOOK_SECRET');
    if (!secret) fail('service_not_configured', 503);
    if (!timingSafeEqual(request.headers.get('x-telegram-bot-api-secret-token') || '', secret)) {
      fail('unauthorized', 401);
    }
    const { json: update } = await readBody(request);
    const message = update?.message;
    const chatId = String(message?.chat?.id ?? '');
    if (!chatId || chatId !== String(env('TELEGRAM_CHAT_ID') ?? '')) return Response.json({ ok: true });
    const text = String(message?.text ?? '').trim();
    const updateId = Number(update?.update_id);
    if (!text || !Number.isSafeInteger(updateId)) return Response.json({ ok: true });
    const seen = await getState('telegram', { last_update_id: 0 });
    if (updateId <= seen.last_update_id) return Response.json({ ok: true, duplicate: true });
    await handleCommand(text);
    await setState('telegram', { last_update_id: updateId });
    return Response.json({ ok: true });
  }

  // ---- Forward webhook inbound ----

  async function verifySignature(request, raw) {
    const secret = env('FORWARD_SIGNING_SECRET');
    const id = request.headers.get('webhook-id');
    const timestamp = request.headers.get('webhook-timestamp');
    const header = request.headers.get('webhook-signature');
    if (!secret?.startsWith('whsec_') || !id || !timestamp || !header) return false;
    const ts = Number(timestamp);
    if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > 300) return false;
    let keyBytes;
    try { keyBytes = Uint8Array.from(atob(secret.slice(6)), c => c.charCodeAt(0)); }
    catch { return false; }
    const prefix = new TextEncoder().encode(`${id}.${timestamp}.`);
    const message = new Uint8Array(prefix.length + raw.length);
    message.set(prefix);
    message.set(raw, prefix.length);
    const key = await crypto.subtle.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, message));
    let binary = '';
    for (const byte of mac) binary += String.fromCharCode(byte);
    const expected = btoa(binary);
    return header.split(/\s+/).some(value => value.startsWith('v1,') && timingSafeEqual(value.slice(3), expected));
  }

  async function handleForwardEvent(data) {
    const type = data?.type;
    if (type === 'webhook.test') {
      await say('Forward webhook test received — the cloud bridge is live.');
      return;
    }
    if (type === 'forward.schedule_run.succeeded' || type === 'forward.schedule_run.failed') {
      if (!SCHEDULE_IDS.includes(data.schedule_id)) return;
      const run = await forwardReq('GET', `/schedule_runs/${data.run_id}`);
      if (run.http_error || !run.session_id) return;
      if (type === 'forward.schedule_run.failed') {
        await say(`<b>Schedule run FAILED</b> (${esc(data.schedule_id)}): `
          + `${esc(data.error_type || 'unknown')}. Check the console; the desk may need a restart.`);
      }
      await ensureBound(run.session_id);
      await drainBoundSession(run.session_id, null);
      return;
    }
    if (type === 'session.status_run_started' || type === 'session.thread_created'
      || type === 'session.thread_idled' || type === 'session.status_idled') {
      const sessionId = data.id;
      if (typeof sessionId !== 'string' || !sessionId.startsWith('sess_')) return;
      if (!(await ensureBound(sessionId))) return;
      if (type === 'session.thread_created') { await refreshThreads(sessionId); return; }
      const only = type === 'session.thread_idled' ? data.session_thread_id : null;
      await drainBoundSession(sessionId, only);
    }
  }

  async function handleForward(request) {
    const { raw, json } = await readBody(request);
    if (!(await verifySignature(request, raw))) fail('unauthorized', 401);
    const webhookId = request.headers.get('webhook-id');
    const eventType = String(json?.data?.type ?? request.headers.get('webhook-event-type') ?? 'unknown');
    const inserted = rows(await db.from('webhook_events')
      .insertIfAbsent({ webhook_id: webhookId, event_type: eventType }, { onConflict: 'webhook_id' })
      .select('webhook_id'));
    if (!inserted?.length) return Response.json({ ok: true, duplicate: true });
    try {
      await handleForwardEvent(json?.data);
    } catch (error) {
      // Let Forward retry: remove the dedup marker so the retry reprocesses.
      await db.from('webhook_events').delete().eq('webhook_id', webhookId);
      throw error;
    }
    return Response.json({ ok: true });
  }

  async function handleStatus() {
    const binding = await loadBinding();
    const pending = await listPending();
    const recent = rows(await db.from('webhook_events')
      .select('event_type,received_at').order('received_at', { ascending: false }).limit(1));
    return Response.json({
      ok: true,
      session_id: binding.session_id,
      pending: pending.map(ask => ({ n: ask.n, tool: ask.name, thread: ask.thread_name })),
      last_event: recent?.[0] ?? null,
      approvals: 'manual-only',
    });
  }

  return async ctx => {
    const request = ctx.request;
    const pathname = new URL(request.url).pathname;
    const match = pathname.match(/^\/(?:functions\/v1\/)?(?:app|app-d[0-9a-f]{32})(\/.*)?$/);
    if (!match) fail('not_found', 404);
    const path = match[1] || '/';
    if (path === '/api/health' && request.method === 'GET') return Response.json({ ok: true });
    if (path === '/api/status' && request.method === 'GET') return handleStatus();
    if (path === '/telegram' && request.method === 'POST') return handleTelegram(request);
    if (path === '/forward' && request.method === 'POST') return handleForward(request);
    fail('not_found', 404);
  };
}