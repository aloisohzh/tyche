// Local route checks with credential-free fakes (no Deno, no cloud, no secrets).
// Run: node dev/local-test.mjs   (from bridge-site/)
import assert from 'node:assert/strict';
import { createHmac, randomBytes } from 'node:crypto';
import { application } from '../functions/routes.mjs';

import { BackendError, fakeDb, fakeFetch, sent, posted, threadEvents, setRelayStatus, SESSION } from './fakes.mjs';

const signingSecret = 'whsec_' + randomBytes(24).toString('base64');
const envValues = {
  QODER_PAT: 'test-pat',
  TELEGRAM_BOT_TOKEN: 'test-bot-token',
  TELEGRAM_CHAT_ID: '42',
  TELEGRAM_WEBHOOK_SECRET: 'tg-webhook-secret',
  FORWARD_SIGNING_SECRET: signingSecret,
};
const db = fakeDb();
const handle = application({ db, env: name => envValues[name], fetch: fakeFetch, BackendError });

function telegramRequest(text, { chat = '42', secret = 'tg-webhook-secret', updateId = 1 } = {}) {
  return new Request('https://site.test/functions/v1/app/telegram', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': secret },
    body: JSON.stringify({ update_id: updateId, message: { chat: { id: Number(chat) }, text } }),
  });
}
function forwardRequest(data, { id = 'whe_test1', secret = signingSecret, tamper = false } = {}) {
  const body = JSON.stringify({ type: 'event', id, created_at: new Date().toISOString(), data });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const key = Buffer.from(secret.slice(6), 'base64');
  const mac = createHmac('sha256', key).update(`${id}.${timestamp}.${tamper ? body + 'x' : body}`).digest('base64');
  return new Request('https://site.test/functions/v1/app/forward', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Webhook-ID': id, 'Webhook-Event-Type': data.type,
      'Webhook-Timestamp': timestamp, 'Webhook-Signature': `v1,${mac}`,
    },
    body,
  });
}
// Mirrors index.ts: the deployed errorResponse maps BackendError to HTTP status.
const run = async request => {
  try { return await handle({ request, requestId: 'test' }); }
  catch (error) {
    if (error instanceof BackendError) {
      return new Response(JSON.stringify({ error: error.code }), { status: error.status });
    }
    throw error;
  }
};
const lastSent = () => sent.at(-1)?.text ?? '';

let checks = 0;
async function check(name, fn) { await fn(); checks++; console.log('ok -', name); }

await check('health and empty status', async () => {
  const health = await run(new Request('https://site.test/functions/v1/app/api/health'));
  assert.deepEqual(await health.json(), { ok: true });
  const status = await run(new Request('https://site.test/functions/v1/app/api/status'));
  const body = await status.json();
  assert.equal(body.ok, true);
  assert.equal(body.session_id, null);
  assert.deepEqual(body.pending, []);
});

await check('telegram rejects wrong secret', async () => {
  const response = await run(telegramRequest('/help', { secret: 'wrong' }));
  assert.equal(response.status, 401);
});

await check('telegram ignores other chats', async () => {
  const before = sent.length;
  const response = await run(telegramRequest('/help', { chat: '999', updateId: 2 }));
  assert.equal(response.status, 200);
  assert.equal(sent.length, before);
});

await check('telegram /help answers allowlisted chat', async () => {
  const response = await run(telegramRequest('/help', { updateId: 3 }));
  assert.equal(response.status, 200);
  assert.match(lastSent(), /Tyche bridge/);
  assert.match(lastSent(), /never automatic/);
});

await check('forward rejects bad signature', async () => {
  const response = await run(forwardRequest({ type: 'session.status_idled', id: SESSION }, { id: 'whe_bad', tamper: true }));
  assert.equal(response.status, 401);
});

await check('forward run_started auto-binds desk session and surfaces ask', async () => {
  const response = await run(forwardRequest({ type: 'session.status_run_started', id: SESSION }, { id: 'whe_run1' }));
  assert.equal(response.status, 200);
  assert.match(sent.map(s => s.text).join('\n'), /Auto-bound/);
  const preview = sent.find(s => /Approval required #1/.test(s.text));
  assert.ok(preview, 'preview sent');
  assert.match(preview.text, /sim_submit_order/);
  assert.ok(preview.text.includes('...001'), 'account id masked');
  assert.ok(!preview.text.includes('9000001'), 'full account id never leaked');
  assert.equal(db.tables.pending_asks.length, 1);
  const status = await (await run(new Request('https://site.test/functions/v1/app/api/status'))).json();
  assert.equal(status.session_id, SESSION);
  assert.equal(status.pending.length, 1);
});

await check('forward dedups by Webhook-ID', async () => {
  const before = sent.length;
  const response = await run(forwardRequest({ type: 'session.status_run_started', id: SESSION }, { id: 'whe_run1' }));
  assert.deepEqual(await response.json(), { ok: true, duplicate: true });
  assert.equal(sent.length, before);
});

await check('telegram /approve 1 sends confirmation and clears pending', async () => {
  const response = await run(telegramRequest('/approve 1', { updateId: 4 }));
  assert.equal(response.status, 200);
  const confirmation = posted.at(-1).events[0];
  assert.equal(confirmation.type, 'user.tool_confirmation');
  assert.equal(confirmation.result, 'allow');
  assert.equal(confirmation.tool_use_id, 'evt_a1');
  assert.equal(db.tables.pending_asks.length, 0);
  assert.equal(db.tables.decisions.length, 1);
  assert.match(lastSent(), /Approved #1/);
  assert.match(lastSent(), /submit is not a fill/);
});

await check('forward thread_idled relays coordinator text and resolves asks', async () => {
  threadEvents.sthr_exec.push({ id: 'evt_r1', type: 'agent.mcp_tool_result', mcp_tool_use_id: 'evt_a1' });
  threadEvents.sthr_coord.push({ id: 'evt_c2', type: 'agent.message', content: [{ type: 'text', text: 'Order submitted; watching fills.' }] });
  const response = await run(forwardRequest(
    { type: 'session.thread_idled', id: SESSION, session_thread_id: 'sthr_coord' }, { id: 'whe_idle1' }));
  assert.equal(response.status, 200);
  assert.match(lastSent(), /Order submitted/);
});

await check('telegram free text relays user.message; 409 reported', async () => {
  await run(telegramRequest('What is the plan today?', { updateId: 5 }));
  assert.equal(posted.at(-1).events[0].type, 'user.message');
  assert.match(lastSent(), /Relayed to the desk/);
  setRelayStatus(409);
  await run(telegramRequest('again?', { updateId: 6 }));
  assert.match(lastSent(), /mid-turn; message NOT sent/);
  setRelayStatus(200);
});

await check('telegram /deny carries reason', async () => {
  threadEvents.sthr_exec.push({ id: 'evt_a2', type: 'agent.tool_use', name: 'sim_submit_order',
    evaluated_permission: 'ask', input: { symbol: 'US.QQQ', qty: 3 } });
  await run(forwardRequest({ type: 'session.thread_idled', id: SESSION, session_thread_id: 'sthr_exec' }, { id: 'whe_idle2' }));
  assert.equal(db.tables.pending_asks.length, 1);
  await run(telegramRequest('/deny 2 too risky', { updateId: 7 }));
  const confirmation = posted.at(-1).events[0];
  assert.equal(confirmation.result, 'deny');
  assert.equal(confirmation.deny_message, 'too risky');
  assert.match(lastSent(), /Denied #2/);
});

await check('duplicate telegram update_id is skipped', async () => {
  const before = sent.length;
  const response = await run(telegramRequest('/pending', { updateId: 7 }));
  assert.deepEqual(await response.json(), { ok: true, duplicate: true });
  assert.equal(sent.length, before);
});

await check('unknown route and wrong method are 404', async () => {
  assert.equal((await run(new Request('https://site.test/functions/v1/app/nope'))).status, 404);
  assert.equal((await run(new Request('https://site.test/functions/v1/app/telegram'))).status, 404);
});

console.log(`\n${checks} route checks passed (local fakes; not a cloud integration test).`);