# Runbook — Telegram sentinel push

Status: wired 2026-11-18. First rehearsal `srun_843b2035dbc452e2b7848c06` FAILED at the
30-min attempt timeout (researcher hand-transcribing kline CSVs); no digest was sent.
Remediated 2026-11-18: researcher v5 fast data path (`scripts/mcp_prices.py`, one
`num=370` kline call per symbol) + `timeout_ms` raised to 3600000 on all three schedules.
Delivery verification = the next successful rehearsal/cron run. Operator: alois.

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

## Inbound (questions / commands) — not wired yet

Today the sentinel is **outbound-only**: nothing polls `getUpdates`, so messages sent
to the bot are not read. Inbound is feasible without a Forward channel:

- A local bridge (`scripts/telegram.py listen`, to build) polls `getUpdates`, accepts
  only the operator chat id, and relays to a desk session via
  `POST /api/v1/forward/sessions/{id}/events`.
- Verified API support: `user.message` (ask questions / task the desk) and
  `user.tool_confirmation` with `tool_use_id` + `result: allow|deny` — this is exactly
  the executor's `always_ask` per-order gate, so **order approvals can be relayed from
  Telegram** while keeping per-order preview + explicit confirmation.
- Constraints: the operator's machine must run the bridge; PAT stays in local `.env`;
  chat-id allowlist is the only inbound auth, so order commands must still surface a
  preview and wait for an explicit approve reply. Never auto-approve.

## Rotation and revocation

- BotFather `/revoke` issues a new token; update `.env`, re-run `env-set` (operator
  authorization required again), re-verify with a rehearsal run.
- Chat id changes only if the operator chats from a different account; re-run chat-id.

## Failure modes

- `getUpdates` empty → message went to a different bot; check the exact username.
- Run `push_status: skipped` is EXPECTED (no sinks); proof of delivery is the chat
  message plus run `status=succeeded`.
- Telegram API unreachable from sandbox → run records delivery failure and continues;
  operator still gets artifacts via console Files / Drive persistence.
- Token leak → revoke immediately (BotFather), rotate as above; blast radius is
  messaging chats the bot is in, nothing else.