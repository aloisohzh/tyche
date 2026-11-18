# Runbook — Telegram sentinel push

Status: wired 2026-11-18. First rehearsal `srun_843b2035dbc452e2b7848c06` FAILED at the
30-min attempt timeout (researcher hand-transcribing kline CSVs); no digest was sent.
Remediated 2026-11-18: researcher v5+ fast data path (`scripts/mcp_prices.py`, one
`num=370` kline call per symbol) + `timeout_ms` raised to 3600000 on all three schedules.
Rehearsal 2 `srun_84820bb31f5900a61a3429d1` COMPLETED (27.5 min): risk alert 12:59 UTC
and digest 13:10 UTC both delivered ok. Inbound bridge (`listen`) wired same day — see
below. Operator: alois.

## Why not a Forward channel

Forward `channel_type` supports only `wechat`, `wecom`, `feishu`, `dingtalk` (+ `teams`
on Global). Telegram is not a channel type, and personal WeChat QR binding failed in
practice (5 sessions expired with no `scanned` event; see bonus-tips lessons). Vaults
hold MCP-server credentials only, so they cannot inject a Bot API token. The sentinel
therefore pushes **outbound** from schedule runs via the Telegram Bot API; inbound
tasking stays in console/API. Schedules keep `sinks: []` (`im_channel` sinks require a
bound IM channel); delivery lives in the run instructions instead.

## Architecture

- Bot: `@tyche_sentinel_bot` (BotFather). Token + chat id live **server-side** in the
  desk template's `environment_variables` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`),
  merged with existing keys. Local copy in gitignored `.env` for local tests only.
- Each schedule's `initial_events` (version 3) ends with a TELEGRAM DELIVERY contract:
  plain-language HTML digest < 3500 chars — bold header (phase, date, UTC clock),
  one-sentence market mood + stance, an **Orders** `<pre>` monospace table
  (ACTION SYMBOL QTY VALUE STATUS REASON, plain words first, rule id in parentheses),
  **Account** lines (NAV, cash, positions, kill-switch), **Problems** (or none);
  immediate alert on kill-switch engagement or risk rejection; one retry after 5 s;
  delivery failure is recorded but never blocks risk work; no tokens/credentials/full
  account ids in messages or logs.
- Schedules: `tyche-premarket` (13:45 UTC), `tyche-eod` (22:15 UTC),
  `tyche-eod-halfday` (27 Nov 18:15 UTC).

## Setup from scratch

1. BotFather `/newbot` → name `Tyche Sentinel`, username ending in `bot`. Copy token.
2. Put token in gitignored `.env` as `TELEGRAM_BOT_TOKEN=` (never in chat/repo).
3. Send the bot any message; then `.venv/Scripts/python scripts/telegram.py chat-id`
   (writes `TELEGRAM_CHAT_ID` to `.env`).
4. Operator explicitly authorizes the secret write, then:
   `MSYS_NO_PATHCONV=1 .venv/Scripts/python scripts/forward.py env-set /templates/<desk-template-id> TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID`
   (merge semantics: existing env keys are carried over; values never printed).
5. Append the delivery contract to each schedule via
   `POST /api/v1/forward/schedules/{id}` with the full replaced `initial_events`.
6. Verify: `POST /schedules/{id}/run`, watch `GET /schedule_runs/{run_id}`, and confirm
   the digest arrives in Telegram. A submit is not a delivery: check the chat.

## Local commands

- `scripts/telegram.py chat-id` — derive chat id from `getUpdates`.
- `scripts/telegram.py send "<text>"` — connection check / manual alert.
- `scripts/forward.py get|post|delete|env-set|qr|poll` — Forward API client (PAT from
  `.env`; `MSYS_NO_PATHCONV=1` in Git Bash).

## Inbound (questions / commands) — wired 2026-11-18

`scripts/telegram.py listen` runs on the operator's PC and bridges Telegram to a
desk session via `POST /api/v1/forward/sessions/{id}/events`:

- **Auth**: only `TELEGRAM_CHAT_ID` from `.env` is accepted; every other chat is
  ignored. PAT stays in local `.env`; nothing secret is committed.
- **State**: `.telegram-bridge.json` (gitignored) holds the getUpdates offset,
  bound session, event cursor, pending approvals and a decision log. First run
  drains stale updates so old messages are never replayed into the desk.
- **Commands**: `/session latest` (bind newest schedule-run session) or
  `/session <sess_id>`; `/status`; `/pending`; `/approve N`; `/deny N [reason]`;
  `/interrupt`; `/help`. Any other text is relayed as `user.message`; the desk
  coordinator's replies are relayed back (account ids masked to last 3 digits).
- **Approvals**: the bridge polls each member thread's event stream for
  `agent.tool_use` / `agent.mcp_tool_use` with `evaluated_permission: ask` (the
  executor's `always_ask` order gate — MCP calls only surface in thread streams,
  not the session stream), sends the full tool input as a preview, and waits.
  `/approve N` posts `user.tool_confirmation {tool_use_id, result: allow}`;
  `/deny N` posts `deny` with an optional reason. **Never auto-approves** — an
  explicit numbered reply from the allowlisted chat is the only path. A submit
  is still not a fill; fills come from broker order state.
- **Busy desk**: a relay while the session is mid-turn returns 409; the bridge
  tells the operator the message was NOT sent (no silent queueing).
- Binding scans session history once to surface any already-pending approval.

Run it: `MSYS_NO_PATHCONV=1 .venv/Scripts/python scripts/telegram.py listen`
(Git Bash). Stop with Ctrl+C; state persists across restarts.

Verification status 2026-11-18: bind + history scan + `/status` + question
relay smoke-tested against rehearsal session `sess_00vvadnsde5fkxq15t9z`;
round trip confirmed (desk reply `RELAY-OK` delivered to Telegram via the
listener). The approval relay (`user.tool_confirmation`) is API-verified but
has NOT yet been exercised against a real pending order ask — do a controlled
drill on the PERSONAL paper account before relying on it for challenge orders.

## Cloud bridge (no PC) — Sites function, 2026-11-18

The local listener above requires the operator's PC to be on. The cloud bridge
replaces it with a Qoder Sites Edge Function (`bridge-site/`) that receives
webhooks directly, so questions and approvals work from Telegram alone.

**Path**: Telegram → Sites Function (`POST /functions/v1/app/telegram`) and
Forward events → Sites Function (`POST /functions/v1/app/forward`) → desk
session via the Forward API. Durable state (bound session, cursors, pending
approvals, decisions, webhook dedup) lives in the site's private
function-backend database (`app.bridge_state`, `app.pending_asks`,
`app.decisions`, `app.webhook_events`); no browser or local process is involved.

**Credentials** (four tiers, none in the repo or browser):
- `QODER_PAT` — platform-provisioned server-side when the site's `qoder`
  backend capability was enabled (operator-confirmed). Read only inside the
  Function via `Deno.env.get`; never an application Secret, never in chat.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
  `FORWARD_SIGNING_SECRET` — application Secrets entered by the operator in
  Site Settings (values copied by hand from gitignored `.env`; never chat/args).

**Inbound auth**:
- Telegram: shared-secret header `X-Telegram-Bot-Api-Secret-Token`
  (timing-safe compare) + chat-id allowlist + `update_id` dedup.
- Forward: HMAC-SHA256 over `Webhook-ID.Webhook-Timestamp.raw_body` with the
  endpoint signing secret (`whsec_` prefix stripped, base64-decoded key),
  300 s timestamp tolerance, multi-signature header support; `Webhook-ID`
  dedup row is rolled back on processing error so Forward retries reprocess.
- Same command set as the local listener (`/session`, `/status`, `/pending`,
  `/approve N`, `/deny N [reason]`, `/interrupt`, free-text relay). Never
  auto-approves; account ids masked to last 3 digits in previews.
- Auto-binding: `session.status_run_started` / thread events from the three
  desk schedules bind the newest matching desk session (identity + template
  check), so mid-run approvals route without manual `/session`.

**Setup / wiring** (`scripts/cloud_bridge.py`, PAT from `.env`,
`MSYS_NO_PATHCONV=1` in Git Bash):
- `gen-secret` — create `TELEGRAM_WEBHOOK_SECRET` in `.env`.
- `create-endpoint <site-url>` — register the Forward webhook endpoint
  (6 session/thread/schedule events); captures `FORWARD_SIGNING_SECRET` +
  endpoint id to `.env` (secret returned once, never printed).
- `set-webhook <site-url>` — point Telegram at the function with the secret
  token; `webhook-info` / `test-endpoint` / `delete-webhook` /
  `delete-endpoint` for inspection and rollback.

**Rollback**: `delete-webhook` restores `getUpdates` mode; run the local
listener (`scripts/telegram.py listen`) as fallback. The Forward endpoint can
stay registered (harmless) or be removed with `delete-endpoint`.

**Status page**: the site root shows bound session, pending approvals and last
webhook only — read-only, no order actions. Site access is public solely so
Telegram/Forward can deliver webhooks anonymously; every route is gated by the
secret checks above.

Verification status: local fixture suite (13 route checks incl. signature
rejection, dedup, approve/deny, 409 handling) passes; live publication and
end-to-end webhook round trip pending at time of writing — update this section
after the first real `webhook.test` delivery and operator `/status` round trip.

## Rotation and revocation

- BotFather `/revoke` issues a new token; update `.env`, re-run `env-set` (operator
  authorization required again), re-verify with a rehearsal run. For the cloud
  bridge, also update `TELEGRAM_BOT_TOKEN` in Site Settings and re-run
  `set-webhook` if the webhook secret changed.
- `FORWARD_SIGNING_SECRET` rotates by deleting and re-creating the Forward
  endpoint (`delete-endpoint` → `create-endpoint`), then updating the Site
  Settings value. `TELEGRAM_WEBHOOK_SECRET` rotates via `gen-secret` +
  `set-webhook` + Site Settings.
- Chat id changes only if the operator chats from a different account; re-run chat-id.

## Failure modes

- `getUpdates` empty → message went to a different bot; check the exact username.
- Run `push_status: skipped` is EXPECTED (no sinks); proof of delivery is the chat
  message plus run `status=succeeded`.
- Telegram API unreachable from sandbox → run records delivery failure and continues;
  operator still gets artifacts via console Files / Drive persistence.
- Token leak → revoke immediately (BotFather), rotate as above; blast radius is
  messaging chats the bot is in, nothing else.