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
- Each schedule's `initial_events` (version 5) ends with a TELEGRAM DELIVERY contract:
  send via the repo helper `python scripts/telegram.py send "<digest>"` (reads
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from session env). The helper normalizes
  Markdown **or** HTML to Telegram HTML — `**bold**`→bold, pipe tables→aligned `<pre>`
  monospace — so a digest composed in either syntax renders correctly (fix 2026-11-18:
  the desk had drifted to Markdown while sending `parse_mode=HTML`, showing literal
  `**` and pipes). Compliant HTML passes through unchanged. Plain-language digest
  < 3500 chars - use the shared digest format below: bold headings, a compact
  **Orders** table with explanations outside it, separate **Account** lines,
  **Protection**, and **Problems**. Immediate alerts use the same style. Delivery
  failure is recorded but never blocks risk work; no tokens/credentials/full account
  ids in messages or logs. Use the existing helper with explicit Telegram HTML when
  the new structured renderer is unavailable; do not bypass it with raw curl.
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
- `scripts/telegram.py send "<text>"` — connection check / manual alert / digest.
  Normalizes Markdown or HTML to Telegram HTML (`parse_mode=HTML`), masks account
  ids, caps length, appends a stable content ref (`ref: <8 hex>`, sha256 of the
  input digest). Works locally (`.env`) and in the cloud desk (session env vars).

## Shared digest format (2026-11-20)

The active Managed premarket/close deployments replaced the older Forward schedule.
Their shortened `TELEGRAM` instruction omitted the original formatting requirements;
plain text therefore passed through the helper unchanged. The November and December
cards need the same presentation contract for normal digests **and urgent alerts**.
The paused Forward schedules and the separate local MSFT exit task are not notification
owners and must not be resumed or otherwise changed for this formatting fix.

Preferred path: fill `templates/sentinel-digest.example.json` with verified run facts,
then use the deterministic renderer in `scripts/telegram.py`:

```sh
# Offline example preview only - reads no credentials and sends nothing:
python scripts/telegram.py render-digest templates/sentinel-digest.example.json
# Actual runs validate their own private payload before sending it:
python scripts/telegram.py render-digest <run-dir>/sentinel.json
python scripts/telegram.py send-digest <run-dir>/sentinel.json
```

Both commands also accept `-` for JSON on stdin. Never send the example as a live
account report. The required JSON keys are `phase`, `timestamp` (date + UTC/ET/SGT),
`mode`, `stance`, `orders_summary`, `orders`, `account`, `protection`, and `problems`.
Optional keys: boolean `urgent`, list `proposals`, and string `next_check`.
All text values are single-line plain strings, not Markdown or HTML.

- Bold title and mode, then a one-sentence plain-English market/desk stance.
- Bold **Orders**, with the explicit verified submission count. A compact monospace
  `ACTION SYMBOL QTY` table contains only supplied rows; each row requires `action`,
  `symbol`, `qty`, `value`, `status`, and `reason` strings. Value, status and short
  reason appear **below** the table, grouped by symbol, so prose cannot widen it.
  A held position is not a newly submitted order; never infer submission count from
  the table. Empty orders omit the table but retain the caller's factual summary.
- Bold **Account**, with `nav`, `cash`, `positions`, and `kill_switch` on separate lines.
- Bold **Protection** and **Problems**, with short list items. Empty lists mean
  "Not reported", not "safe" or "none". Include every uncovered lot and uncertain
  order, including re-armed exits. Optional **Proposals** contains each one-line
  thesis and invalidation; **Next check** must be verified, not promised.
- Explain technical codes in ordinary language first: "another process placed orders"
  instead of "single-writer invariant failed"; "no shares filled" instead of "cum0";
  "approval missing" instead of "adoption r2 blocked". Retain material qualifiers,
  brief rule/audit/reserve references, and the distinction between a receipt and a
  fill. Put long evidence trails in the private run report, not the table.
- Use hyphens, not em dashes. The renderer escapes markup, masks account IDs, enforces
  short fields and a conservative 3500-character HTML budget. Invalid or oversized
  input fails **before sending**; shorten prose without deleting risk facts and
  re-render. Do not silently truncate protection warnings or invent missing values.

Cloud rollout is compatible with older repo mounts: if the structured renderer is
not present, compose this exact layout as explicit escaped `<b>`/`<pre>` HTML and
pass it to the existing `send` helper using an argument array, not shell interpolation.
No raw curl, no plain-text alternative, and no bypass of the helper's delivery status.
Local code changes alone do not update the cloud repository mount; explicit HTML
is the compatibility path once the formatting instruction is installed, until the
renderer is published. The reusable instruction is saved at
`templates/prompts/sentinel-telegram.txt`.

Rollout status (applied 2026-11-20): the contract is installed on both active Managed cards -
`dep_00vzb9h4ezawwl4thnva` (Nov, window 2026-11-19..2026-11-30) and `dep_00vzd8d5rdfr4w0denqh`
(Dec, window 2026-12-01..2026-12-31) - with
`scripts/deploy_two_fire_automation.py --apply-update <deployment_id> --month <YYYY-MM>`, which stays
the card's source of truth; `prompt_markers` now also asserts `has_sentinel_format_v1` and
`has_renderer_path`. Only the `TELEGRAM` section changed (6913 -> 9403 characters, one hunk); cron,
agent pin v28, environment, resources and metadata were untouched, and both cards re-read as `active`
with every marker true. GitHub `main` carries the renderer commit, so `render-digest`, `send-digest`
and `templates/sentinel-digest.example.json` exist in the cloud repo mount: the structured renderer is
the live path and the explicit-HTML route above is a fallback only. The example renders correctly
offline. No schedule ran, no trade was placed and no Telegram message was sent for this rollout - the
first real proof is the next card fire's digest arriving formatted.

## Delivery semantics (hardened 2026-11-19)

Delivery is **at-least-once**: the schedule protocol retries once after 5 s on a
non-ok response, and a read timeout cannot distinguish "delivered, response
lost" from "never delivered". Incident: the 18 Nov 22:05 UTC skip notice
(`srun_19b685d96db900f5cb3ee663`) timed out on both attempts yet both copies
reached Telegram — the operator saw a duplicate. Hardening in the helper:

- Socket timeout raised 40 s → **60 s** (`SEND_TIMEOUT`) to cut false timeouts.
- Every digest carries a **content ref footer**; a retry of the same digest
  produces the same ref, so duplicates are recognizable at a glance.
- Exit codes: `0` sent (message_id + ref printed); `2` **UNCONFIRMED**
  (timeout/socket error — may have been delivered; a retry duplicates it, ref
  unchanged); `1` definitive failure (missing token, Telegram API error).
- The Bot API has no sent-message history, so true dedupe is impossible; the
  ref makes duplicates harmless instead of mysterious. Delivery never blocks
  risk work.
- `scripts/forward.py get|post|delete|env-set|qr|poll` — Forward API client (PAT from
  `.env`; `MSYS_NO_PATHCONV=1` in Git Bash).

## Inbound (questions / commands) — local listener, STOPPED 2026-11-18

> Per the operator's decision, Telegram is an **outbound-only sentinel**; the inbound
> listener below is stopped (restart on demand with `listen`). Order approvals are
> handled in the Qoder console session thread, not via Telegram. Kept as a fallback.

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

## Cloud bridge (no PC) — Sites function experiment, ARCHIVED 2026-11-18

> **Outcome: not feasible on Qoder Sites; inbound bridge dropped.** The operator
> decided to keep Telegram as an **outbound-only sentinel** (schedule-run digests).
> The Sites Function gateway enforces a **same-origin check on every write (POST)**:
> a POST with no `Origin` header, or a foreign one, is rejected at the gateway with
> `sites_gateway_origin_forbidden` before it reaches the function; only a POST
> carrying `Origin: https://<site-host>` passes. Telegram `setWebhook` and Forward
> webhook deliveries are server-to-server and send no `Origin`, and neither source
> supports custom headers (Forward endpoint body is only `url`/`events`/`metadata`).
> Verified empirically: anonymous GET (status/health) works; the Forward `webhook.test`
> delivery was rejected at the gateway and never reached the function. The skill
> contract confirms it: "writes also require same-origin checks." Sites Functions are
> built for `browser → function → Qoder`, not for receiving external webhooks.
>
> Cleanup done: site reverted to **private**; Forward webhook endpoint deleted;
> local listener and dev preview server stopped; no Telegram webhook set (outbound
> `sendMessage` digests unaffected). `bridge-site/` and `scripts/cloud_bridge.py`
> are retained as a documented experiment, not a live path. A no-PC inbound bridge
> would need either a scheduled Qoder cloud poller (drains `getUpdates` on a cron)
> or an external serverless receiver that accepts anonymous POSTs — neither built.

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

Verification status (closed 2026-11-20): the local fixture suite (13 route checks incl. signature
rejection, dedup, approve/deny, 409 handling) passes, and that is as far as this path ever got. Live
publication and the webhook round trip will **not** be verified, because the gateway same-origin rule
above makes them unreachable: this section is a record of an abandoned experiment, not pending work.
Do not reopen it as a to-do. Inbound tasking and order approvals stay in the Qoder console;
`scripts/telegram.py listen` remains the documented local fallback if the operator ever reverses the
outbound-only decision.

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