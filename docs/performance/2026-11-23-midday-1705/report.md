# TYCHE midday run report - 2026-11-23 12:05 ET fire (private)

Run: 2026-11-23-midday-1705. Desk head: tyche-desk. Fire: midday protection fire, ALERT-ONLY (submits nothing).
Repo: /data/workspace/tyche, HEAD 90d98189eee343ad0c3bb823ca428f8bc856c367 (contains tested release 3312287). tyche installed editable --no-deps this session.

## Gate, lineage, authority
- `tyche calendar --json` exit 0 at 17:05:31Z: trading_day true, half_day false, phase midday, activity monitor, new_entries false, event_caution false. Calendar drift check skipped (midday; done at premarket, IN SYNC).
- Restored newest verified descendant: /data/drive/tyche-raw/2026-11-23-cap-cut-freeze/journal/events.jsonl (51 events, sha 91fea255a066685e864d8b1b18f9b90e5179510e533299026860d1a00af96e4e = premarket 49-event lineage 21695d84... + operator rules.frozen/rules.refrozen for the 0.45->0.25 tactical cap cut, new PB-002/003 hash a1d9df1c687c). Prefix sha verified byte-identical. Chain intact.
- HALT RELEASED: repo data/halt.json ts 2026-11-23T15:11:25Z, operator PR #39 ("19 Nov writer incident reviewed, 23 Nov premarket reconcile found no second writer"). New effective_halt semantics: newest-stamped flag governs. halt-status on run journal (released halt.json copied beside it): halted=false, source journal.
- Authority: WITHIN MY BOUNDS - same-day data/approvals.json approved 15:31:37Z, max_orders 5: SELL SPY 28 floor 690.00, SELL EFA 142 floor 94.50, SELL MSFT 39 floor 474.00, BUY AAPL <=28 limit_max 343.08 + protective SELL AAPL 28 floor 315.39 (PR #41 operator yes to the premarket PB-007 proposal; JNJ/PEP explicitly not carried over). Envelope NEVER edited. Midday submits nothing regardless of envelope.
- Switches: PB-004 scalp OFF (skipped), PB-007 ON, PB-003 options OFF. config/tactical.yaml re-read: enabled true, execution_enabled true, stock_allocation_cap 0.25, symbols MSFT/KO/PG/JNJ/PEP/MCD.
- NAV refs per card: baseline/HWM 100,000.00 (102,208.99 pin RETIRED, used nowhere); prior_close_nav 97,788.36 (Nov-20 verified close).

## Executor reconcile (read-only; artifacts mcp/, state-tick/, batch-4/, batch-5/)
- Reads 17:07:52Z-17:19:07Z, full account batches re-read at 17:08/17:12/17:14/17:16/17:18/17:19 for the 120s/60s gates. Env TYCHE_ALLOWED_ACCOUNT_IDS now resolves to the CHALLENGE account ***598 (correct) - NO id injection used this fire (prior sessions' ***4748 quirk resolved).
- History: ONE unfiltered page has_more=false, 11 orders ever; newest = boundary 3118578 (2026-11-19T18:15:16Z); re-read 17:14:04Z byte-identical. NO second writer, zero live/pending orders. Desk head independently re-verified orders-1.json (11 orders, has_more false, newest 3118578).
- Positions: SPY 28 (avg 731.54, receipt 3116580), EFA 142 (avg 100.495, receipt 3116594) - fills match receipts. MSFT 39 (avg 503.33, broker 3118578) still UNOWNED (no journal receipt; Nov-19 incident). status5 UNRESOLVED: VNQ 3116597 83@94.98, SMH 3118500 10@454.48 (cum 0, frozen 0).
- Quotes 17:18:13Z (RTH live, all six AFTERNOON market state): SPY 723.035, EFA 98.715, MSFT 499.20, AAPL 348.60; JNJ/PEP books captured; spreads all inside 0.3% gate. KO/PG/MCD feeds not captured (coverage gap, nothing inferred).
- Production dry lifecycle tick (isolated copies, approvals=[], no --record, --config-root repo, batch 17:14:04Z): exit 0; SPY e73ee77d.../EFA add27d1a... action=review "held position has no approved lifecycle ownership"; AAPL 3dd88f86... review "research review expired or future-dated"; gap "US.MSFT: held position missing a complete lifecycle plan". State bytes unchanged (diff clean).
- Diagnostic tick (run-dir copies, synthetic refs DIAGNOSTIC-NOT-APPROVED, --at 17:17:30Z replay): engine WOULD latch daily-close stop_loss SELL SPY 28 @721.90 / SELL EFA 142 @98.48 - inspection only, NOT approval/reservation/order. Both limits above envelope floors.
- Tactical dry tick (fresh 17:18:13Z quotes+books, tick 17:19:35Z): JNJ/PEP wait "watchlist stale/inactive/invalidated or protection coverage incomplete"; alerts "monitor starting or heartbeat gap; rebuild entry confirmations" and "unprotected tactical positions: US.MSFT; block new entries". config_hash 3e1fe7494bb6... (no injection). Scalp SKIPPED (PB-004 off).
- Production state verified unchanged at 17:20:24Z and again by desk head: book bc9e6d50643f722fac9f04e2947fde14bd31b12b1326aef42323f152650f3eaa, state a7a9e99496ffc4f9b6c1c2819e2ace95a3b8de421fe5f34b4238d7bd293f0d58.

## Protection verdict (alert-only)
- SPY 28: daily-close stop 727.50 breached on TWO completed bars (Nov-19 715.87, Nov-20 689.81); last 723.035 still 4.465 below stop. NO live exit order, no reservation, no submit_before. Envelope floor 690.00 (last +4.79% above).
- EFA 142: stop 100.00 breached two bars (98.78, 96.14); last 98.715, 1.285 below. NO live exit. Floor 94.50 (+4.46%).
- MSFT 39: no plan, no stop, no deadline, no exit order - unowned incident lot. Floor 474.00 (+5.32%).
- AAPL PB-007 proposal (operator-approved in envelope, NOT yet a holding): last 348.60 is +5.52 (+1.61%) ABOVE zone 338.89-343.08 - pullback-only, no chase; entry_expires 15:50 ET today; stop 331.99, protective floor 315.39.
- NO protection.gap journaled: production approvals=[] - no approved exit request_id exists to gap; journal has never contained an exit order.requested. Broker shows no live exit orders either. Gap rule satisfied without invention.
- URGENT RISK ALERT sent (breached levels + uncovered lots): message_id 49, content_ref 559e09cb, rc 0, renderer path. Per card, this fire then STOPS - the 15:05 ET close fire and operator decide/execute exits inside the envelope.

## NAV / risk (17:19:07Z read)
- total_asset 99,415.801 (frozen 0.00 included), cash 45,680.121 (45.949%), MV 53,735.68, gross 54.051% (<=95%).
- DD vs baseline 100,000.00 = -0.5842%; soft -4% (96,000) and hard -6% (94,000) clear. Day +1,627.441 (+1.6642%) vs prior close 97,788.36; daily-loss floor 95,343.65 clear.
- Gross 54.05% is lifecycle/incident inventory (SPY+EFA ballast ~34.4% + MSFT ~19.7%), not new tactical exposure; existing holdings above target are not liquidation permission - the operator's envelope IS the explicit exit authorization for the close fire.

## Decisions and actions
- NOTHING submitted, reserved, canceled, modified, approved or re-armed. No envelope/config edit. No production state mutation. No researcher/auditor delegation (midday rule).
- Journal: run.start (52), reconcile.completed (53), notify.sent (54). Lineage 54 events, chain intact, sha256 6b8af2c0f8f204f3f9a7237e1560f69fd506ce0813deaf72160dcadf7d1ff05f.

## Operator queue for the 15:05 ET close fire
1. Execute envelope exits: SPY 28 (floor 690.00), EFA 142 (94.50), MSFT 39 (474.00) - fresh quotes, exact-order audit, reserve, then ONE order each; envelope max_orders 5.
2. AAPL entry only on a pullback into 338.89-343.08 before 15:50 ET; last 348.60 above zone at midday - likely no fill; protective sell line must accompany any entry per envelope.
3. status5 semantics VNQ 3116597 / SMH 3118500 still unresolved.
4. Writer attribution for MSFT 39 / Nov-19 scalp round-trips still open (envelope exit is the disposition).
5. Reviews expired 14:15/14:25Z - close fire needs fresh targeted revalidation for anything executable beyond the envelope exits.

## Quirks confirmed this fire (for next runs)
- Env allowlist now correct (***598) - no injection needed; prior config_hash-under-injection quirk moot this session.
- lifecycle capture/tick need --config-root /data/workspace/tyche when run from a Drive run dir (else "missing config file: .../config/risk.yaml").
- Tactical tick creates journal/events.jsonl.lock (chain untouched). Book staleness (>120s) masquerades as "missing/stale/non-tradable quote or order book" - read quotes+books as one fresh pair.
- effective_halt: newest-stamped flag governs (PR #39); a repo release now clears an older journal halt.

## Next check
15:05 ET close fire (20:05Z) today - verified from the active three-fire card (calendar next_run 20:05Z).

## Publication
- scripts/publish_desk_data.py run once at 17:23Z: secret guard PASS, feed rebuilt (primary source still cloud run 2026-11-18-midday3 - today's raw snapshots live on Drive, not the repo cloud-run discovery path), performance pack SKIPPED (no repo-local journal - expected). PUSH FAILED: "remote: Invalid username or token. Password authentication is not supported for Git operations." Local commit e1bb92a; fallback bundle /data/drive/tyche-raw/2026-11-23-sanitized-git/midday-1705.bundle (origin/main..main). persist.push_failed journaled (event 55). Operator action: run the publish script with a valid push token. Not retried.
- Final lineage: 55 events, chain intact, sha256 db2776f8d85e47d9bfc033df3129a1ef1a6ab4422fd3b24c9ce2447a3ba99428 (run.start 52, reconcile.completed 53, notify.sent 54, persist.push_failed 55).