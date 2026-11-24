# TYCHE close fire — 2026-11-20 (15:05 ET / 20:05 UTC), run close-2005

READ-ONLY run. **No orders submitted.** Halt engaged (writer-safety incident
2026-11-19); production approvals empty; single-writer ownership verified for
today (no new broker orders since 2026-11-19T18:15:21Z).

## Calendar / bootstrap
- `tyche calendar --json` rc=0: trading_day, not half day, phase closing_drive,
  event_caution=true, max_orders=1. Regular close 21:00Z.
- Repo HEAD e53d045; fast-forwarded local main to 9b03b77 from the premarket
  Drive bundle (engaged shared halt flag + Nov-20 event pins). **Push failed
  (auth) again this session**; close-fire bundle saved to
  /data/drive/tyche-raw/2026-11-20-sanitized-git/close-2005.bundle. Next session
  must fetch+rebase+push.
- Journal lineage restored from 2026-11-20-midday-1705 (31 events, sha
  4d0e675f…), chain verified; run.start appended. Final chain: 36 events, sha
  5d71c6e0a1f4d166947fdc55e5463e1022e6cba57d5da0fd16004c8a071c89f8.
- Effective halt: ENGAGED (journal flag 2026-11-19T20:28:29Z; repo flag now
  synced engaged locally via bundle ff).

## Reconciliation (executor, read-only; report-executor.md)
- Account ***598: NAV 97,788.36 (20:16Z mark; 97,727.78–97,788.36 across fire),
  cash 45,680.12, frozen 0.
- Positions: SPY 28 (avg 731.54, last 694.05), EFA 142 (avg 100.495, last
  96.43), MSFT 39 (avg 503.33, last 486.60) — MSFT UNOWNED incident lot.
- Order history: full unfiltered pagination, 1 page, 11 orders, has_more=false.
  Latest order ever 3118578 created 2026-11-19T18:15:16Z → NO new writer today.
  Correction to prior notes: 4 historical status4 SELLs exist (NVDA 33, AMD 10,
  MU 7 — Nov-19 incident round-trips, symbols flat). Zero live/pending orders.
- Status-5 UNRESOLVED (not terminal): VNQ 3116597 (83 @94.98, cum 0), SMH
  3118500 (10 @454.48, cum 0); frozen 0 both.
- Env quirk persists: session allowlist provisions ***4748, not ***598;
  read-only ticks used disclosed session-scoped TYCHE_ALLOWED_ACCOUNT_IDS
  injection (tactical config_hash 160b7d96 injected). No file/config writes.

## Risk state
- **SOFT DRAWDOWN BREACHED**: NAV 97,788.36 vs working HWM pin 102,208.99 =
  -4.33% (soft line 98,120.63). Hard -6% floor 96,076.45 NOT breached. Daily
  -2.13% vs prior_close_nav 99,914.93 (2.5% limit intact). HWM pin is a working
  value pending operator confirmation. Journaled risk.drawdown.
- SPY/EFA r2 daily-close stops BREACHED on official Nov-19 bars (715.87<727.50,
  98.78<100.00); Nov-20 marks far below again (694.05 / 96.43). Second breach
  likely but official Nov-20 closes only exist after 21:00Z — no scheduled
  check then; evidence pending.
- **ALL THREE LOTS UNCOVERED**: no live exit orders, no approved exit path,
  MSFT has no plan/grant at all. No protection.gap journaled (approvals=[] →
  no approved exit request_ids exist; gaps reported, not invented).

## Engine (dry, isolated copies, no --record)
- Lifecycle production decisions: SPY/EFA "review: held position has no
  approved lifecycle ownership"; gap "US.MSFT missing a complete lifecycle
  plan". Diagnostic-only tick (synthetic approvals DIAGNOSTIC-NOT-APPROVED,
  run-dir only) demonstrates would-exit SPY 28 @691.97 / EFA 142 @96.15
  stop_loss — NOT authorization.
- Tactical tick: closing_drive, no entries; "unprotected tactical positions:
  US.MSFT; block new entries". Scalp PB-004 dry: all 5 symbols wait, no 5-bar
  breakout; feeds complete.

## Research (focused revalidation, no broad scout)
- Fresh exact-plan-hash Reviews (reviewed_at 20:13:00Z, valid to 21:13:00Z),
  schema-validated: SPY r2 e73ee77d… INVALIDATED, EFA r2 add27d1a… INVALIDATED
  (completed-bar breaches re-affirmed, no contradicting evidence).
- MSFT: no issuer-specific negative catalyst; decline is AI/sector
  deleveraging; lot -652 USD unrealized. Disposition operator-owned.
- Macro: hike regime intact (FedWatch Nov-19 22:01Z: Dec +25bp 96.4% / +50bp
  3.6% — freshest available, post-event pricing UNKNOWN). UMich final 51.5,
  1y inflation expectations 4.7%→3.7% (dovish datapoint, equities fell anyway;
  SPX below 200-DMA, VIX ~30). Waller speech content, Cook full text, EZ
  confidence actual NOT verified → news_feed_ok=false in published book.
- New events: none. Watchlist pin has entries=[] (no open tactical proposal).
- Book published: sha 295ad864… (prior 02f78128… retained in state/); plans,
  events, approvals untouched. Journaled research.published.

## Actions taken
1. Executor read-only reconcile + dry ticks (no broker writes).
2. Researcher focused revalidation; desk validated + published reviews.
3. Advisor consulted on soft-DD breach; guidance followed.
4. URGENT RISK ALERT sent: telegram msg 46, ref 0b59d9f1, rc=0 (journaled).
5. Journal: run.start, research.published, reconcile.completed,
   risk.drawdown, notify.sent → 36 events, chain OK.
6. Sanitized persist + local commit + Drive bundle (push blocked by auth).

## Operator blockers (unchanged + new)
1. Disposition SPY/EFA breached r2 contracts: exact exit plans + fresh audit +
   grant + reserve, or directed hold with new contract; nothing executable
   under halt without approvals.
2. MSFT 39 ownership decision (adopt with complete plan or directed exit).
3. Resolve VNQ/SMH status-5 semantics; re-provision TYCHE_ALLOWED_ACCOUNT_IDS
   to include ***598; attribute the Nov-19 writer; then kill-switch release.
4. Confirm HWM pin 102,208.99; soft-DD breach response is operator-owned.
5. Push the halt flag bundle (auth failed in this session twice-adjacent
   sessions; cloud runs rely on Drive journal flag meanwhile).

## Coverage gaps
- No scheduled desk check between 21:00Z today and Mon 2026-11-23 13:05Z
  (08:05 ET) — weekend gap with all lots uncovered and stops breached.
- Official Nov-20 daily closes unverifiable at this fire; prior_close_nav /
  HWM refresh for Nov-20 pending an operator-directed or next-fire review.
- Waller/Cook/EZ-conf outcomes and post-event FedWatch unverified.
- No durable cross-session writer lock beyond the halt; ownership verified
  only by absence of new broker orders.

Next scheduled card fire: Mon 2026-11-23 08:05 ET / 13:05 UTC.