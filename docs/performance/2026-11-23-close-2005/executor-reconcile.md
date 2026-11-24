# Executor reconcile + reservation-path probe — CLOSE FIRE 2026-11-23

Run dir: `/data/drive/tyche-raw/2026-11-23-close-2005`
Mode: **strictly read-only**. Zero broker writes: no submit, no cancel, no modify, no reserve issued, no approval granted, no envelope/config/state edit. All writes in this run are private run-dir artifacts.
Report clock: 2026-11-23T20:34:50Z (session spanned 20:05Z–20:35Z; every clock below is UTC).
Repo: `/data/workspace/tyche`, HEAD `a1ecc2c7`, contains tested release `3312287c` → RELEASE_OK.
Account: business id `[REDACTED]` ([REDACTED]), MCP tool acc_id `***...54844`, market_id 100, account_type 2, env paper, source sim_list.

## 1. Feed health — TWO BLOCKING FAULTS

**(A) Moomoo account/business service fault mid-run (live).**
Last good account batch read 20:21:35Z–20:23:00Z. From ~20:26:25Z onward, every account read either errors or returns an *empty-but-success* payload, while the quote/book service stayed healthy (advancing `data_time`, two-sided books):

| read | 20:26:25Z | 20:26:40Z | 20:27:00Z | 20:29:11Z | 20:32:00Z | 20:34:20Z |
|---|---|---|---|---|---|---|
| `sim_trade_cash_info` | ret_code -5 | ret_code -5 | ret_code -5 | ret_code -5 | ret_code -5 | ret_code -5 |
| `sim_trade_position_list` | `positions: []` | `[]` | `[]` | `[]` | `[]` | `[]` |
| `sim_trade_history_order_list` | — | — | `orders: []`, has_more=false | `[]` (page_size 50) | `[]` (explicit Nov-18→23 window) | — |

The empty positions/history **contradict** the 20:21–20:23 batch (3 positions, 11 orders) and cannot be a real liquidation: this session placed no order, and a paper account cannot empty positions without one. Treated as a **feed fault, not fact**; the contradictory payloads were quarantined to `mcp-anomaly/account-feed-failures-20261123T2029Z.json` and never used as capture input. Consequence: no fresh-clock normalize could be built after 20:31Z, so **live-clock ticks and captures are currently impossible** — not because of the executor, but because the authoritative account service is down. Entries suppressed by rule; reconciliation evidence preserved.

**(B) Journal lineage defect (pre-existing, discovered by the probe).**
`check_execution_journal` rejects the restored journal: its three `order.requested` events (2026-11-18 17:34:40Z SPY buy 28, 17:45:15Z EFA buy 142, 17:49:52Z VNQ buy 83) carry **no `request_id` and no `authorization.mode`** — legacy rows written before the request-id contract. Every lifecycle reservation path therefore fails at the integrity gate, independent of plans, grants or quotes. Chain hash itself is intact (`db2776f8…`, 55 events, `halt.json` halted=false). This is a hard blocker for *any* future lifecycle submit until an operator remaps/annotates those legacy rows under the single-writer rule; the executor must not rewrite history to make it pass.

## 2. Account reconciliation (from the last good batch, 20:21:35Z–20:23:00Z)

- Cash: balance 45,680.121, hold 0, frozen 0, long_mv 53,700.83, total_asset **99,380.951**.
- Positions (all `pstn_type 0`, all sellable qty = qty): SPY 28 @ avg 731.54 (mv 20,272 @ 724.00), EFA 142 @ 100.495 (mv 14,026.05 @ 98.775), MSFT 39 @ 503.33 (mv 19,402.50 @ 497.50). Σmv 53,700.83 → cash + mv reconciles to NAV (snapshot nav 99,380.671 vs broker 99,380.951, delta 0.28 < 1.0 tolerance → **reconciles**).
- Order history: one page, `has_more=false`, 11 rows. **Newest order ever = 3118578 at 2026-11-19T18:15:16Z → ownership boundary holds, no second-writer incident.**
- Live/pending orders: **zero**. Statuses observed: 4 (terminal) and 5 (unresolved). Unresolved status-5 rows still open as unknown, not canceled: VNQ 3116597 (83 @ 94.98), SMH 3118500 (10 @ 454.48). No other symbol has status ∈ {1,2,3}.
- Calendar: Nov-21 and Nov-22 were market holidays; latest completed daily close is **Nov-20** (SPY 689.81, EFA 96.14, MSFT 484.52, AAPL 342.56). Nov-23 bar is in progress → the "missing Nov-21/23 close" in `closes.json` is correct, not a data gap.

## 3. Market pair (quotes + books), fresh

| symbol | last | quote data_time | bid/ask (NASD | ARCA) | spread |
|---|---|---|---|---|---|
| US.SPY | 724.12 | 20:32:27Z | 724.30/724.31 → 724.12/724.34 band | two-sided | ~0.00–0.03% |
| US.EFA | 98.76 | 20:32:24Z | 98.78/98.79 | two-sided | ~0.01% |
| US.MSFT | 497.36 | 20:32:27Z | 497.44/497.51 | two-sided | ~0.014% |
| US.AAPL | 351.08 | 20:32:27Z | 351.20/351.25 | two-sided | ~0.014% |

Earlier pairs in the same session: 20:22:41Z batch (SPY 723.99 / EFA 98.775 / MSFT 497.54 / AAPL 350.86) and 20:29:16Z batch (SPY 724.39 / EFA 98.775 / MSFT 497.5401 / AAPL 351.38). Books in the capture dir are the 20:30:20Z pair; quotes the 20:29:16Z pair (`mcp/quotes.json` sha `6ca11a35…`, `mcp/book-US.*.json` sha `cc39c74b… / a3ac26bf… / 87e32c17… / bf7c4b6b…`).

## 4. Normalize + dry ticks

`tyche lifecycle capture` succeeded on the corrected **business** account id. Note the earlier rejections were a *plumbing* fault, not a policy block: passing the 64-bit tool acc_id (`***...54844`) instead of `[REDACTED]` produces `market_id=null, account_type=null` → `"unverified or non-allowlisted US paper account"`. Desk config uses `account_allowlist: ["[REDACTED]","[REDACTED]","[REDACTED]"]` matched on the business id; worth pinning in the ops note.

**Lifecycle dry tick.** Live clock at 20:31:35Z rejected with the exact string `"broker snapshot stale or future-dated; fetch again"` (observed_at 20:29:11Z vs tick 20:31:35Z > 120s — the gate is correct, the outage is what makes it unsatisfiable). Replay clock `--at 2026-11-23T20:30:20+00:00` (inspection only, NO `--record`) returned rc=0 on ISOLATED copies with `approvals=[]`:

- `LC-20261119-SPY-ADOPT-r2` (hash `e73ee77d…`): action `review`, **not authorized** — "held position has no approved lifecycle ownership"; warning "research review expired or future-dated".
- `LC-20261119-EFA-ADOPT-r2` (hash `add27d1a…`): same — no approved ownership, review expired.
- `PB-007-20261120-AAPL` (hash `3dd88f86…`): action `review` — "research review expired or future-dated" (entry_expires 2026-11-23T15:50-05:00 already passed at the fire).
- Gap reported: **"US.MSFT: held position missing a complete lifecycle plan"** — an unprotected 19.5% NAV holding.
- Pre/post state identical: `state.iso.json` = `state.iso.pre-tick.json` = `state.iso.post-tick.json`, sha `a7a9e994…`, `approvals/reservations/latched_exits` untouched. Tick mutated nothing.
- Caveat, stated plainly: because the account service died, the replayed market file combines 20:21–20:23 account fields with 20:29–20:30 quotes. The *decision semantics* (ownership/review/plan gaps) are unaffected; NAV-sensitive arithmetic inherits the last good batch.

**Tactical dry tick** (watchlist book `entries=[]`, i.e. no new setups supplied by the brief): rc=0 both replay (20:30:20Z) and live clock (20:33:45Z), `"orders": [], "decisions": []`, alerts: **"stale/missing account snapshot; no orders"** — the tactical kernel refuses to size anything because `captured_at` is 20:10:55Z and the account feed is down. config_hash `3e1fe749…`, phase `closing_drive`. PB-004 scalp: **SKIPPED — not executed** (`tyche tactical scalp` is a separate command and no scalp cycle was run this fire).

## 5. AAPL zone verdict (Task 7)

Zone 338.89–343.08. Fresh last 351.08 (20:32:27Z; 351.38 at 20:29:16Z; 350.86 at 20:22:41Z) → **outside, ~2.3% ABOVE the top of the zone**. Independently, `entry_expires 2026-11-23T15:50:00-05:00` (20:50Z) had already passed when this fire ran, so the plan is expired regardless of price. No entry consideration.

## 6. Reservation-path probe — exact rejection strings

**(a) Envelope gate** — `tyche authorize --symbol US.SPY|US.EFA|US.MSFT --side sell --qty 28|142|39 --limit 724.12|98.76|497.36 --path data/approvals.json --journal journal/events.jsonl` → rc=1 each:
```
{"authorized": false, "reason": "ask me: no Telegram approval journaled today (no envelope); nothing may be submitted", "today": "2026-11-23"}
```

**(b) Lifecycle reserve** — `tyche lifecycle reserve --book state/book.iso.json --market state/market-US.json --state state/state.iso.json --plan-id <id> --hash <full hash> --journal journal/events.jsonl` → rc=1 for both SPY-r2 and EFA-r2:
```
{"ok": false, "reason": "unclassified or duplicate journal request; operator review required", "submitted": false}
```
It fails at the journal integrity gate **before** plan/grant evaluation, so the "no grant" branch was never reached. Nothing reserved; isolated ledger unchanged (sha `a7a9e994…`).

**(c) Tactical reserve** — `tyche tactical reserve --symbol US.SPY|US.EFA|US.MSFT --envelope data/approvals.json --lifecycle-state state/state.iso.json` → rc=1 each:
```
{"ok": false, "reason": "no unique actionable order: []", "submitted": false}
```

**(d) execute-exit** — `tyche lifecycle execute-exit --plan-id <id> --hash <full hash>` (isolated, dry) → rc=1 for both:
```
{"ok": false, "reason": "unclassified or duplicate journal request; operator review required", "submitted": false}
```
The expected `"exact lifecycle requires prior operator approval"` string exists in code (`lifecycle_cli.py:384`) but is unreachable this session because the journal defect at §1(B) gates ahead of it.

Every probe emitted `"submitted": false`; no MCP write call was made; `data/approvals.json` and `audit/` on Drive were not touched; journal hash unchanged (`db2776f8…`, still 55 events).

## 7. Coverage / protection gaps to carry into the next fire

1. **MSFT 39 (~19.5% NAV) has no lifecycle plan** — unprotected holding.
2. **SPY and EFA have plans but no approved lifecycle ownership** (`approvals=[]` in the restored execution state); reviews expired 14:15Z. Protective floors 690.00 (SPY) / 94.50 (EFA) / 474.00 (MSFT) are desk-side envelopes, not resting broker orders — nothing is working at the broker right now.
3. **Two unresolved status-5 orders** (VNQ 3116597, SMH 3118500) still block same-symbol re-entry logic and are not proven canceled.
4. **Journal legacy rows without request_id** (§1B) block every lifecycle reservation.
5. **Account service outage** (§1A) blocks every fresh-clock capture/tick and therefore any submission this session.

## 8. Artifact index (sha256, first 16)

```
4450619f512cc8f7 mcp/accounts.json            e091d78cd710736d mcp/accounts.masked.json
3dfe1b9dbedb28dc mcp/cash.json                0f96527716851e62 mcp/positions.json
3a647f7097b6ecc4 mcp/orders.json              6ca11a3562aa5b09 mcp/quotes.json
8b0d588bcb073101 mcp/quotes.raw.json          05ee568f7511e485 mcp/closes.json
5e0427dbfd9c6d83 mcp/bars.json                90c6f5e8f062d819 mcp/market-state.json
f268c3efe79e61f0 mcp/books.json               3a054a70a894e442 mcp/tactical-account.json
c59c3b7fa968d80e mcp/tactical-quotes.json     cc39c74bfde09412 mcp/book-US.SPY.json
a3ac26bfa95c6e97 mcp/book-US.EFA.json         87e32c173d4197fb mcp/book-US.MSFT.json
bf7c4b6b0214eb11 mcp/book-US.AAPL.json        dc8808f582e18938 state/market-US.json
bc9e6d50643f722f state/book.iso.json          4acda07b7cd4924b state/book-watchlist.empty.json
a7a9e99496ffc4f9 state/state.iso.json (= pre-tick = post-tick)
c338465b4f592e55 state/lifecycle-tick-output.json (live-clock rejection)
e7c3f0fe3b706269 state/lifecycle-tick-replay.json (decisions)
607c26488d4e5ec8 state/tactical-tick-replay.json 6d97002604048db1 state/tactical-tick-live.json
e25e48a45411526d state/lifecycle-capture.json  447efe617d814324 state/tactical-capture.json
fb964c54c6d545a5 audit/probes/6a-authorize-*.json (all three, identical)
83bba5ec258e6f00 audit/probes/6b-lifecycle-reserve-*.json / 6d-execute-exit-*.json
3b78674f6d31c3b6 audit/probes/6c-tactical-reserve-*.json
db2776f8d85e47d9 journal/events.jsonl (unchanged, 55 events)
mcp-anomaly/account-feed-failures-20261123T2029Z.json (6 cash/positions/history reads + 3 order-page variants)
```
