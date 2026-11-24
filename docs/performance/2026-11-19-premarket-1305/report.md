# TYCHE PRE_MARKET report — 2026-11-19 (hourly validation mode, PRODUCTION HOLD)

Run: 2026-11-19-premarket-1305 · desk head tyche-desk · started 13:05:22 UTC (08:05 ET / 21:05 SGT)
Repo/LC_ROOT: /data/workspace/tyche HEAD 2181c12 (contains tactical release 7288d68 + pinned engine 119d4e5). execution_enabled=false.
Stance: PREVIEW ONLY — NOT ARMED. Zero orders submitted; no broker writes, no reservations, no state mutation.

## Calendar
- Live gate: trading_day=true, phase=pre_market, activity=plan, new_entries=false, max_orders=0, event_caution=false (RTH-active-only per code). Next hourly check 14:05Z.
- NYSE alert-only check (first pre_market of ET day): 2026 rows match pins (Nov 26 closed, Nov 27 13:00 ET early close, Dec 24 early close). ONE discrepancy: Juneteenth 2028 — source Jun 16 vs pinned Jun 19 (Jun 19 2028 is a Monday; re-verify parsing before any re-pin). 2028 only, outside challenge window. Pins govern; operator-reviewed re-pin proposed; no config edit. Evidence: calendar-check.json, nyse-calendar*.txt.
- Events pinned after source validation (config/events.yaml sha256 77abf44779c84510b9a6fec44cbadf30b8fe9f05440ad1bea0581d61cb5e2ed0): Nov 19 Initial Jobless Claims 08:30 ET (MCP econ calendar id294; prev 198K cons 200K); Nov 19 Philadelphia Fed Mfg 08:30 ET (philadelphiafed.org release calendar + FRED confirm Nov 19); Nov 20 PBoC LPR 01:15Z (jin10 item 235457; monthly 20th 09:15 Beijing). Rejected: Oct LEI (flat consensus, low impact), LA/Long Beach port labor (unconfirmed tentative). Both 13:30Z prints landed during this run — post-event revalidation REQUIRED before any entry.

## Account (masked ***598, US paper, allowlisted)
- NAV 100,193.13 = cash 65,244.61 + frozen 0.00 + MV 34,948.52 (exact, Decimal-checked). Drift vs 11:09Z preflight +7.84 = pre-market MTM only.
- Positions: SPY 28 (avbl 28), EFA 142 (avbl 142). No options. Kill-switch: not engaged.
- Order history: 1 unfiltered page, has_more=false. SPY 3116580 / EFA 3116594 status 4 full fills (verified terminal, cross-matched to journal). VNQ 3116597 (83 @ 94.98, cum 0) STILL status 5 — UNRESOLVED MANUAL-REVIEW flag retained; no retry/cancel; VNQ writes blocked pending resolution.
- No pending/working orders. No resting stops. PROTECTION COVERAGE: NONE.

## Protection (top desk risk)
- SPY 28 + EFA 142 = 34.88% NAV UNOWNED: no production lifecycle ledger, no adoption grants, no approved stops/targets/deadlines. Read-only lifecycle tick (isolated state, replay 13:10:45Z, no --record) confirms: "US.SPY / US.EFA: held position missing a complete lifecycle plan".
- PB-001 ballast overage: 34.88% vs 25% cap = 9,900.24 over. Existing holdings — no adds, NOT liquidation permission.
- Gap math (auditor F17): ~−7.2% adverse gap on the sleeve breaches the 2.5% daily-loss limit; ~−11.4% hits 4% soft DD. Hourly synthetic exits are not broker-native stops; gaps/halts/nonfills can exceed planned stops.
- Adoption requires operator-controlled bootstrap after full reconciliation; never initialized from holdings alone.

## Kernel plan (deterministic, real NAV refs prior_close 99,914.93 / high_water 100,000.00)
- Regime risk_off (1/4 checks: equity_trend F, golden_cross T, vol_calm F, credit_trend F), conviction low, outlook bearish, rules_hash 4105d7a680a3, prices 11×370 daily bars last 2026-11-18 (sha256 9ace62129556f14c5700a5b344d745ae07ef62eea8ce087a0e19681e2f7b92a1).
- Targets: CASH 75%, SPY 5.0%, EFA 5.0%, DBC 7.5%, VNQ 7.5%. All 4 intents (sell SPY 21, sell EFA, buy DBC, buy VNQ) BLOCKED by account.reconcile: plan NAV 99,927.13 (prior-close marks) vs broker 100,193.13 (pre-market marks), drift 266.00 > 0.1% tolerance. Legitimate pre-market block; no override. Act/wait: low conviction waits new non-defensive entries; de-risking never gated by conviction (but reconcile + hold + max_orders=0 block all).

## Research (unapproved; watchlist working copy /data/drive/tyche-raw/watchlist.json sha256 3b2401571d6e8783e9686e7220dae25a942a84f79171ec37ee6ab025af242d04)
- Schema-validated (Watchlist.model_validate OK). 3 long-stock catalyst proposals, all exit_at 20:05Z, confirmation_ticks 2, option null:
  1. TAC-20261119-AMD-L1: 538.0–543.5 / stop 535.0 / target 556.5, R:R 1.53, max_qty 36. ANT IPO halo + $26B placement participation; CY2027 server guide >100% (Jefferies Nov 4); Bernstein PT650 Nov 16; Nov 18 main inflow +130.6M.
  2. TAC-20261119-MU-L1: 728.5–740.0 / 728.0 / 758.5, R:R 1.54, max_qty 27. Strongest pre +4.84% but 5-day outflow ~−749M + upside call selling — ranked below AMD.
  3. TAC-20261119-SMH-L1: 469.5–474.0 / 466.0 / 486.5, R:R 1.56, max_qty 42. Sleeve resolved from code: SMH counts toward 45% tactical cap (tactical.py:330-332), NOT the 25% PB-001 sleeve.
- Aggregate max notional 59,454 > 45,086.91 tactical cap — sleeve gate REJECTS (does not scale); any two fit; all three push gross 94.22% / cash 5.78% (near limits). Correlated semi complex; no SMH look-through in kernel — envelope must haircut.
- SPY/EFA thesis reviews: verdict valid, reviewed_at 13:17Z (labeled estimate), valid_until 14:17Z, news_feed_ok true. Entry-review freshness is 30 min (tactical.py:243): stale at 14:05Z; earliest executable entry 15:05Z with refreshed review + 2-tick hourly confirmation. Effective time exit is 19:05Z (next-check anticipation, tactical.py:207-210), not 20:05Z — thesis wording to correct in next revision (new hash).
- Options: none proposed on IV evidence (AMD IV 76.83% @85th pct, MU 80.59%, call selling, crush risk). quote_option_chain NOW AVAILABLE (executor verified 714-contract standard SPY chain, lot 100) — metadata path unblocked; option entry/exit operational validation still required.
- NVDA rejected (beat-and-fade −2.89%, 5-day flow −5.46B). ANT watch-only (LISTING status, no trades; $83 reference not executable). YouTube: 3 unvalidated hypotheses routed to LEAN lane.
- Macro: Fed HIKE cycle, Dec 25bp ~96%, 50bp tail 3–4% (12.7% spike = hawkish-surprise signal), 10y 5.07%, DXY 19-mo high; narrow AI bounce, weak breadth.

## Audit (independent, NOT AN APPROVAL — PRODUCTION HOLD)
- Verdict RESEARCH-READY (research quality scope). 33 findings: 14 pass / 11 concern / 8 block. No execution-approved Audit JSON issued. All desk-head determinations confirmed at code level; GLD −3.2% "anomaly" resolved as real Nov 18 move; NAV/journal/proposal math re-derived and exact.
- Notable concerns: exit-timing wording (F09), 30-min review freshness (F10), event-caution halving exists only in lifecycle lane — envelope/operator must impose on tactical (F15), semi concentration (F20), pre-existing full account IDs in early journal events + missing config-change event for 20→30% cap (F26, lineage gap), research MCP payloads inline-only (F23).

## Preview status
- Tactical capture/tick: BLOCKED — "no verified two-sided quotes" (pre-market payloads lack bid/ask; no order-book captures; last=prior close, stale >60s). At RTH order time executor must capture quote_market_snapshot (pre-market bid/ask) and/or order books fresh.
- Lifecycle tick: read-only coverage demonstration only (see Protection). No production tick possible: no ledger/grants.

## Production-release blockers (unchanged, all still open)
1. Durable single-writer ownership for BOTH lanes unproven (Drive flock/fsync not distributed locks).
2. Operator-controlled lifecycle bootstrap/adoption for SPY/EFA (complete contracts: stop/target/basis/deadline/invalidation; deadlines by last scheduled RTH check incl. Nov 27 early close).
3. VNQ 3116597 status-5 semantics unresolved (manual review; per-action confirmation for any cancel/modify).
4. Exact same-day setup+config+account-bound entry AND exit envelopes; fresh independent exact-order audit (<=120s) at execution; live-clock reserve.
5. Post-13:30Z macro revalidation + 30-min review freshness + 2-tick confirmation (earliest 15:05Z).
6. Executable two-sided quotes <=60s / account capture <=120s at RTH.
7. NAV-ref/high-water persistence + reconciliation at release (candidate 100,193.13 not persisted under hold).
8. Operator-reviewed activation after controlled paper drill; options need own entry/exit validation. Live trading forbidden.

## Persistence
- Private raw bundle: /data/drive/tyche-raw/2026-11-19-premarket-1305/ (mcp captures, research, audit, plan, isolated state, journal).
- Journal lineage: restored 2026-11-18-eod (12 events, sha256 83bf020c…), appended plan.created + run.pre_market → 14 events, chain verified, new descendant sha256 2a77e30fc20797c354ce48e13f0e47ec381bff3d7690d5093fcb25bf3248a9d8. Authoritative history never overwritten.
- data/prices.csv rebuilt from executor kline handoff (no transcription). config/events.yaml pins included in sanitized git persist.