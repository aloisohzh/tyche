# TYCHE close run report - 2026-11-23 15:05 ET fire (private)

Run: 2026-11-23-close-2005. Desk head: tyche-desk. Fire: close (closing_drive). Outcome: OBSERVE-ONLY, ZERO orders submitted. URGENT RISK ALERT sent (msg 50, ref 1ad65450, rc 0).
Repo: /data/workspace/tyche, HEAD a1ecc2c7f0bf00411e1391e3f2392c36bcbd2089 (contains tested release 3312287c). tyche installed editable --no-deps.

## Gate, lineage, authority
- `tyche calendar --json` exit 0 at 20:05:33Z: trading_day true, half_day false, phase closing_drive, activity active, new_entries true, max_orders 3, event_caution false. Calendar drift check skipped (close fire; done at premarket).
- Restored newest verified descendant: 2026-11-23-midday-1705/journal/events.jsonl (55 events, sha db2776f8...). Prefix 51 lines byte-identical to cap-cut-freeze (91fea255...). Chain intact. halt.json copied beside it.
- HALT RELEASED (repo data/halt.json ts 15:11:25Z, operator PR #39). halt-status on run journal: halted=false, source journal.
- Authority: WITHIN MY BOUNDS. data/approvals.json approved 15:31:37Z, max_orders 5: SELL SPY 28 floor 690 / EFA 142 floor 94.50 / MSFT 39 floor 474; BUY AAPL <=28 limit_max 343.08 + protective SELL AAPL 28 floor 315.39 (PR #41). No setup_hash on any line. Envelope NEVER edited.
- Switches: PB-004 scalp OFF (skipped), PB-007 ON, PB-003 options OFF. tactical.yaml: enabled true, execution_enabled true, stock_allocation_cap 0.25, symbols MSFT/KO/PG/JNJ/PEP/MCD, etf_symbols [].
- NAV refs per card: baseline/HWM 100,000.00 (102,208.99 pin retired); prior_close_nav 97,788.36 (Nov-20 verified close). Drive nav-refs.json is stale (Nov-18) - flagged.

## Executor reconcile (read-only; executor-reconcile.md, mcp/, state/, audit/probes/, mcp-anomaly/)
- Last good account batch 20:21:35-20:23:00Z: total_asset 99,380.951 = cash 45,680.121 (frozen 0) + mv 53,700.83; reconciles (snapshot 99,380.671 vs broker 99,380.951, delta 0.28). Positions SPY 28 @731.54, EFA 142 @100.495, MSFT 39 @503.33, all sellable.
- History one page has_more=false, 11 orders. Newest ever 3118578 @2026-11-19T18:15:16Z -> ownership boundary HOLDS, no second writer. Zero live/pending. status5 UNRESOLVED: VNQ 3116597 (83@94.98), SMH 3118500 (10@454.48).
- Plumbing fix pinned: capture --account-id must be BUSINESS id [REDACTED] (not the 64-bit MCP tool acc_id); wrong id -> market_id/account_type null -> "unverified or non-allowlisted". Env TYCHE_ALLOWED_ACCOUNT_IDS correct ([REDACTED]); no injection needed.
- Fresh quotes/books 20:32Z: SPY 724.12, EFA 98.76, MSFT 497.36, AAPL 351.08; all two-sided, spreads <=0.03%.

## TWO BLOCKING FAULTS (operator action)
1. MOOMOO ACCOUNT-SERVICE OUTAGE live since ~20:26Z: cash_info ret_code -5 x6; position_list/history_order_list return success-with-EMPTY while quotes/books stayed healthy. Empty contradicts the 20:21-20:23 batch and cannot be a real liquidation (no order placed this session). Quarantined to mcp-anomaly/, never used as capture input. Fresh-clock capture->tick impossible (120s gate unsatisfiable) -> any submit blocked by feed health.
2. JOURNAL LINEAGE DEFECT (pre-existing): the 3 Nov-18 order.requested rows (SPY 28, EFA 142, VNQ 83) carry no request_id and no authorization.mode. check_execution_journal fails EVERY lifecycle reserve/execute-exit with "unclassified or duplicate journal request; operator review required" BEFORE plan/grant evaluation. Chain hash intact. Needs operator-sanctioned remap; executor did not rewrite history. Blocks all future lifecycle submits.

## Reservation-path probe (exact rejections; audit/probes/)
- (a) `tyche authorize` with CORRECT absolute envelope path -> authorized=true, mode=bounds, "within operator envelope 2026-11-23: US.SPY sell <= 28 @ 690.0 (1/5)". (Executor's probe used a relative --path that missed the envelope -> false "no envelope"; corrected here.) authorize is a GATE, not a reserve.
- (b) `tyche lifecycle reserve` SPY-r2/EFA-r2 -> "unclassified or duplicate journal request; operator review required" (journal defect gates ahead of the no-grant branch).
- (c) `tyche tactical reserve` SPY/EFA/MSFT -> "no unique actionable order: []" (no watchlist entry/protected_setup; SPY/EFA outside tactical universe).
- (d) `tyche lifecycle execute-exit` SPY/EFA -> same journal-integrity string; the "exact lifecycle requires prior operator approval" branch (lifecycle_cli.py:384) unreachable.

## Structural gap (desk-head code review, confirmed by advisor)
The operator's envelope authorizes the exits (commit msgs: "so the 23 Nov 15:05 ET close fire exits them"), but the pinned engine has NO deterministic reservation path that consumes unbound envelope sell lines for these legacy/incident lots:
- lifecycle reserve needs a grant (state.approvals=[]).
- lifecycle approve needs verdict=="valid" review; honest SPY/EFA verdict is INVALIDATED (2 completed bars below daily-close stop), MSFT has no plan. Cannot fabricate valid.
- tactical reserve needs setup_hash binding (envelope lacks it) + universe membership (SPY/EFA ETFs, etf_symbols=[]; MSFT no watchlist entry).
- Nov-23 PRs #39-#44 added only performance pack + effective_halt semantics + config/data; NO new envelope-exit submit command (verified git diff).
Hard constraints honored: no fabricated valid review, no record-order+direct-MCP bypass, no adoption grant from holdings alone, no legacy execute, no envelope/config/state edit.

## Researcher narrow revalidation (research/revalidation.md + 3 Review JSONs; reviews 20:12Z valid 21:12Z)
- SPY r2 (e73ee77d...): INVALIDATED. Closes Nov-19 715.87 / Nov-20 689.81 < stop 727.50 re-verified via kline; live 721.785 still below; today's 727.98 high intraday-only, does not cure latch.
- EFA r2 (add27d1a...): INVALIDATED. Closes 98.78/96.14 < 100.00; live 98.67; DXY >104 19-month high headwind (fx678 1005374523 16:25Z).
- AAPL PB-007 (3dd88f86...): UNCERTAIN. Last 350.00, session low 345.4422 > zone top 343.08 - never in zone all day; entry_expires 15:50 ET passed; DO NOT CHASE; expires unfilled.
- MSFT 39: COVERAGE GAP, no plan/review fabricated; live 496.125; no material news since 13:25Z.
- New events PROPOSED (events-proposed.json): EV-20261123-NVDA-CEO (Huang reinstated, NVDA +30.87%, rebound catalyst; DJ 1005368220/MT 1005374024; exact announcement time not captured), EV-20261123-US-PMI-FLASH (14:45Z composite 54.6 vs 55.9, services miss), EV-20261123-WILLIAMS (21:00Z speech, SINGLE-SOURCE). Dec 25bp hike ~99% priced (update to pinned FED-REPRICING).

## Event pinning decision: DEFERRED
Desk head did NOT pin events this fire. Rationale: account/news feed unstable; desk head lacks the MCP news tool to independently re-verify; researcher's raw news payloads not preserved (only kline/quotes); NVDA-CEO claim extraordinary (+30.87%); WILLIAMS explicitly single-source. Carried as unvalidated proposals for the operator and the next fire (feed recovery + primary-source verification). Reviews already acknowledge the proposed ids. No config/events.yaml edit.

## NAV / risk (last good 20:21Z read)
- total_asset 99,380.951, cash 45,680.121 (45.97%), frozen 0, mv 53,700.83, gross 54.03% (<=95%).
- DD vs baseline 100,000 = -0.619%; soft -4% (96,000) / hard -6% (94,000) clear. Day +1,592.59 (+1.63%) vs prior close 97,788.36; daily-loss floor clear.
- Gross 54% is lifecycle/incident inventory (SPY+EFA ballast ~34.4% + MSFT ~19.5%), not new tactical exposure. Existing holdings above target are not liquidation permission; the envelope IS the explicit exit authorization - but it is mechanically unexecutable this fire.

## Decisions / actions
- NOTHING submitted, reserved, canceled, modified, approved or re-armed. No envelope/config/state edit. No production book/state mutation (isolated tick copies byte-identical a7a9e994...).
- AAPL: no entry (outside zone + expired). PB-007 switch ON but no setup executable.
- Journal: run.start (56), reconcile.completed (57), notify.sent (58). Lineage 58 events, chain intact, sha256 b99ece2c85951e699ef98a4868745d0468594ce2e315835fb2b7c4572c49beef.
- URGENT RISK ALERT sent: msg 50, ref 1ad65450, rc 0 (renderer path). All 3 lots UNCOVERED; operator-authorized exits mechanically blocked.

## Operator queue (next fire 08:05 ET Tue 24 Nov)
1. Restore Moomoo account service; re-run capture/tick when healthy.
2. Sanctioned remap/annotation of the 3 legacy Nov-18 order.requested rows (add request_id + authorization.mode) so lifecycle reservations can pass integrity. Single-writer rule; desk must not rewrite history.
3. Make the envelope exits executable: either `tyche lifecycle approve` per hash from console with a VALID review (SPY/EFA theses are invalidated - an exit-only adoption path may be needed), or re-arm the envelope with setup_hash-bound lines, or direct a manual exit. Desk cannot self-approve or fabricate bindings.
4. Decide MSFT 39 ownership/disposition (unowned incident lot, ~19.5% NAV).
5. status5 semantics VNQ 3116597 / SMH 3118500 still unresolved.
6. Validate + pin material events (NVDA-CEO, PMI; verify WILLIAMS against primary Fed calendar) once feed recovers.
7. Refresh stale Drive nav-refs.json (still Nov-18) at a verified close.

## Publication
- scripts/publish_desk_data.py run once (see below). Midday push already 403'd; expect possible failure - journal and move on, no loop.

## Next check
08:05 ET Tue 24 Nov (13:05Z) per the active three-fire card. (Calendar next_run tyche-hourly 21:05Z is a PAUSED schedule - not used.)