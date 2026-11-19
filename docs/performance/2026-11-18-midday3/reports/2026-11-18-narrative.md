# Desk narrative — 2026-11-18 (PRE-MARKET RE-PLAN)

- Desk: tyche (Moomoo x Qoder AI Agent Paper Trading Challenge, window 17–28 Nov 2026).
- Phase: scheduled pre-market run, 13:45 UTC start; plan rebuilt 13:49 UTC; audit returned ~13:58 UTC; narrative written ~14:02 UTC. Session 14:30–21:00 UTC.
- This run SUPERSEDES the earlier pre-market run today (~12:58–13:05 UTC), persisted at /data/drive/tyche-raw/2026-11-18-premarket/. Reason: operator raised the per-order notional cap 20%→30% (commit 18b97cf, authored 13:18 UTC, "Operator-approved" per commit message; risk-card and tests updated in the same commit). The earlier plan blocked the SPY leg under the old cap; a deterministic re-plan under the new config is the correct response, not a manual edit.
- Account: competition paper account ****2598 (env=paper, account_type=2, market_id=100, source=sim_list; allowlist matched via TYCHE_ALLOWED_ACCOUNT_IDS). Full id never written in reports.
- Kill-switch: NOT engaged (no journal/halt.json). Journal: chain intact, 2 events (both plan.created; zero order events).

## State restore (ephemeral sandbox)

Fresh session found an empty journal. Restored verbatim from the Drive locker: journal/events.jsonl (1 event), data/prices.csv, reports/2026-11-18-research.md, plans/2026-11-17-plan.{json,md} (prior version). Restored hashes matched the earlier narrative's pins exactly (prices 7e6500d5…, prior plan dbd2e15d…). No hand edits to config/, plans/, journal/ at any point; the new plan was written by the kernel CLI.

## Inputs and provenance (desk-head recomputed 14:01 UTC, post-audit — C5 attestation)

| Artifact | sha256 | Notes |
|---|---|---|
| plans/2026-11-17-plan.json | f11456dfafe83dfa6fd55de15fca7b8742cca4a20d809e407289c806b7016931 | kernel re-plan 13:49 UTC, as-of 2026-11-17 close |
| runs/2026-11-18/snapshot.json | 48c1d73d49b80656fff518968edb0e1665f70a943caebb7937e975676989f99e | fresh executor fetch 13:48 UTC; NAV 100,000.00, cash 100,000.00, 0 positions; prior_close_nav=high_water_nav=100,000.0 (C3 reference; flat account reconciles) |
| data/prices.csv | 7e6500d583c204fafa70ed76e3190f4bf8ae4c39a0c458ae0b39e373db9b4b52 | unchanged; 11 symbols x 370 daily bars through 2026-11-17; no kline re-fetch needed pre-open |
| config/risk.yaml | 96b6b0c11b652eef979f2425decebf98df0dcf7a8ea8bcd7ccf8f00afbfab83a | max_order_notional_pct 0.30; unchanged pre/post audit |
| config/strategy.yaml | bdcff4418a2ad856d3da7e2c286de5d8808a0b50f5181e6ecd5cb14e2874d1e5 | unchanged |
| config/universe.yaml | a7b97e01de7a7cb985336779d997c22871d1ee9c8e477032d5eb067f8e2365d0 | unchanged |
| reports/2026-11-18-research.md | 92bc7061022778be14a88a4e06b9c0020eee048f5eb4513a3bb2a0f5b0284b77 | earlier body + appended U1–U7 refresh (~13:50 UTC) |
| reports/2026-11-18-audit.md | 65a6e58da9ff617da48b3c9aba594a6469c6256b9b65f4adadef1610d4777409 | re-plan audit, supersedes ~13:04 UTC audit |
| commit 18b97cf | git show verified by desk head | cap change + turnover default alignment (25%→50% code vs docs) + root-anchored gitignore; auditor could not verify commit without shell — this row is the C5 attestation |

Pipeline: executor fetched accounts/cash/positions via MCP (raw payloads in runs/2026-11-18/mcp/), ran `tyche snapshot`, added the NAV reference fields. Researcher refreshed news/thesis (no shell in its session; report-only). Desk head ran `tyche plan --prices data/prices.csv --account runs/2026-11-18/snapshot.json`. No quantities invented or altered.

## Regime and thesis

Kernel regime: **neutral** (2/4: equity_trend PASS, golden_cross PASS, vol_calm FAIL, credit_trend FAIL), portfolio vol 8.71%, vol scale 1.00. Targets: SPY 30%, CASH 30%, EFA 20%, VNQ 10.96%, DBC 9.04%. Research refresh concurs: neutral with risk_off skew. Key news (untrusted data, UTC timestamps in research report): Waller floats 50bp Dec risk (13:27); Oct retail sales in line/ex-autos beat, CME Dec 25bp 95.7%; FOMC October minutes CONFIRMED 19:00 UTC today (news schedule; calendar API still empty — data gap); US strike on Iranian Qeshm Island site supports the DBC leg; NVDA H200 China halt confirmed but bounce firmed (SPY pre 735.21, +0.38%).

Invalidation levels (research): SPY close < ~727.5 (200d SMA flip zone 725–730); EFA close < 100.00; VNQ close < 93.50 (REVISED from 94.78, which was 0.12% below close — inside daily noise; 93.50 ≈ 1.5 daily σ below close); DBC close < 30.00 (kept tight deliberately, noise-adjacent, flagged). Tape overlay: QQQ red close on high volume = sell-the-news.

## Plan and risk verdict

| # | Order | Kernel | Auditor | % NAV | Notes |
|---|---|---|---|---|---|
| 1 | BUY US.SPY 28 @ 733.17 = $20,528.76 | APPROVED | APPROVE | 20.53% | passes new 30% cap; prior order.max_notional block superseded (correct under old policy) |
| 2 | BUY US.EFA 142 @ 101.45 = $14,405.90 | APPROVED | APPROVE | 14.41% | limit +0.099% vs close 101.35 |
| 3 | BUY US.VNQ 83 @ 94.98 = $7,883.34 | APPROVED | APPROVE | 7.88% | +0.095% vs 94.89; RTH limit only |
| 4 | BUY US.DBC 215 @ 30.22 = $6,497.30 | APPROVED | APPROVE | 6.50% | +0.099% vs 30.19; thin book — accept non-fill, never chase |

**OVERALL AUDIT VERDICT: APPROVE** (all four as written; conditions C1–C3 + C5). Auditor independently reproduced kernel sizing from prices.csv closes (pre-fit 40/197/115/299 = $69,270.93; turnover factor 50,000/69,270.93 = 0.721804 → 28/142/83/215) and all cap math. Post-fill: turnover $49,315.30 = 49.315% ≤ 50% (headroom $684.70); modeled fees $3.96; cash $50,680.74 = 50.68% ≥ 5%; gross 49.27% ≤ 95%; equity sleeve 34.90% ≤ 50%, real_asset 14.37% ≤ 20%; max name 20.5% ≤ 38% target; 4 positions, 4/6 orders. DD/daily-loss guards now ARMED at 0% (NAV reference present — earlier C3 satisfied).

Audit conditions:
- **C1**: execute-time allowlist + sim-list re-check before any submit (code-enforced).
- **C2**: RTH-only fixed limit orders; never chase SPY > 733.17 or thin DBC/VNQ books; accept non-fills; all initiations done or abandoned by 18:30 UTC; no re-submits 18:30–19:30 UTC (FOMC minutes 19:00).
- **C3**: EOD reconcile_cash ($3.96 fees provisional) and persist day-2 NAV references (prior close + high-water). Day-2 open without them = REJECT.
- **C5**: desk-head sha256/chain/commit attestations kept in the record (table above; auditor has no shell).
- **C4 CLOSED**: the day-1 sizing quirk is resolved by alignment, not masked — order cap 30% now equals strategy max target weight 30%, so pre-fit notionals cannot exceed the order cap; floor-after-scale fitting only shrinks (conservative). fit_turnover_budget code unchanged.

Key auditor findings adopted by the desk:
1. Researcher's U5 "turnover may shave the 4th order" warning is mechanically wrong: the turnover guard uses LIMIT notional (risk.py), execute submits fixed qty/limit with no re-sizing, and buy fills ≤ limit, so realized turnover ≤ 49.32% by construction. Upward price drift → non-fill, not a shaved order.
2. Real drift risk: execute pre-flight is BATCH-ATOMIC — any symbol's last price >3% from its fixed limit rejects ALL FOUR orders. Trip bands: SPY <711.82/>755.85; EFA <98.50/>104.59; VNQ <92.21/>97.92; DBC <29.34/>31.15. If it fires: re-plan via kernel, never override.
3. No time-of-day guard exists in code for the FOMC window — C2 is operator/executor discipline, not a kernel guarantee.

## Decisions and rejections (first-class record)

- DECISION: restore persisted state verbatim and re-plan under the operator's new 30% cap; accept kernel output as-is (~49% invested, ~51% cash — the cash is the minutes hedge, consistent with neutral/risk_off skew and research's 50–70% invested expectation).
- DECISION: adopt auditor's correction of the researcher turnover-shave claim; no kernel change.
- REJECTION (historical, superseded): SPY buy blocked under old 20% cap (order.max_notional) in the ~12:58 UTC plan; no manual split was made then or now.
- REJECTION: no options today (research: ETFs only); no leverage, no shorts.
- ADVISORY (backlog, unchanged): cap-aware turnover fitting is now moot for the order cap but the fit still floor-rounds; no action.
- Kill-switch not engaged; no feed/auth/journal failures this run.

## Execution gate

NOT ARMED. No orders submitted in this phase. Execution requires explicit operator arming in-session plus per-order operator confirmation (executor sim writes always_ask). Approved orders 1–4 are queued for the execution phase only if the operator arms it, subject to C1/C2 and the batch-atomic drift bands above.

## Operator arm and amendment — 17:29 UTC (execution phase)

- OPERATOR ARM received 17:29 UTC, scoped: submit ONLY SPY 28 @ 733.17, EFA 142 @ 101.45, VNQ 83 @ 94.98, verbatim, each with its own always_ask confirmation.
- OPERATOR WITHDRAWAL: DBC 215 @ 30.22 dropped — midday invalidation per reports/2026-11-18-research-midday.md (17:07 UTC quotes: DBC 29.4502, below the 30.00 invalidation all afternoon, day high 29.92 never reclaimed; IEA Q4 surplus 1.7M bpd + API +5.28M bbl build + Iran de-escalation diplomacy broke the war-premium thesis). DBC also sat 0.37% from the 29.34 batch-atomic reject edge — withdrawing it removes the single biggest execution risk to the other three. Journaled as order.rejected (reason: operator withdrawal — midday invalidation 17:07 UTC); decision recorded here as a first-class artifact.
- Audit disposition: per-order APPROVE verdicts for SPY/EFA/VNQ stand unchanged (quantities/limits verbatim); DBC removal strictly reduces portfolio risk (turnover 49.32%→42.82%, cash 50.68%→57.18% if the three fill). Operator authorization supersedes the four-order scope; no re-audit required for a strict risk reduction. C1/C2 and the 18:30–19:30 UTC FOMC no-initiation window remain in force.
- Desk-head pre-submit checks 17:30–17:32 UTC: sandbox intact (no restore needed), journal OK (2 events), no halt.json, plan pin f11456df… unchanged, no config drift on origin/main (new commits are schedule/watchlist/docs only). Git rebased onto origin/main (local sanitized commit now 4a60760); push retried via three credential paths (embedded URL token, env GITHUB_TOKEN header, vault helper) — ALL 403 in THIS session despite the 16:50 UTC fix verified in the midday session. Push deferred to EOD retry; Drive fallback remains authoritative.
- Execution delegated to tyche-executor 17:32 UTC: halt check → DBC withdrawal journal → fresh snapshot (runs/2026-11-18-exec/) → C1 allowlist/sim-list re-check → live-quote freshness pre-flight (3% bands, ≥$1; any breach withholds the WHOLE batch) → three sequential always_ask submissions with order.requested/submitted/rejected journaling and plans/execution-*.json receipts → broker-state fill confirmation. Outcomes appended below when the executor reports.

## Execution outcomes — 17:50 UTC (desk-head verified 17:54 UTC)

Preconditions (executor-verified, desk-head spot-checked): no halt; plan pin f11456df… and risk.yaml 96b6b0c1… matched; fresh snapshot flat NAV 100,000, C1 pass (env=paper, type=2, market=100, sim_list, allowlisted); freshness pre-flight on 17:33 UTC live quotes: SPY −0.079%, EFA +0.820%, VNQ −0.315% deviation — all inside 3% bands, all ≥$1. DBC withdrawal journaled FIRST (order.rejected, operator midday invalidation); DBC never submitted. All three initiations completed by 17:50 UTC, before the 18:30 FOMC cutoff. Each order had its own operator always_ask confirmation; all three approved by operator.

| Order | Broker id | Broker state (desk-head verified from sim_trade_history_order_list_post.json) | Outcome |
|---|---|---|---|
| BUY US.SPY 28 @ 733.17 | 3116580 | status 4, cum_qty 28, avg 731.54 | FILLED 28 @ 731.54 = $20,483.12 |
| BUY US.EFA 142 @ 101.45 | 3116594 | status 4, cum_qty 142, avg 100.495 | FILLED 142 @ 100.495 = $14,270.29 |
| BUY US.VNQ 83 @ 94.98 | 3116597 | status 2, cum_qty 0 | SUBMITTED, RESTING UNFILLED (limit below market; no chase per C2) |
| BUY US.DBC 215 @ 30.22 | — | order.rejected journaled | WITHDRAWN by operator (midday invalidation) |

Post-trade broker state (17:50 UTC fetch): cash 57,360.28; frozen 7,884.33 (VNQ resting order); positions mv 34,748.98; NAV 99,993.59. Implied fill fees ≈ $1.98 (100,000 − 34,753.41 fills − 65,244.61 cash+frozen); EOD reconcile via tyche.fees.reconcile_cash pending (model estimated $2.97 for three fills — reconcile governs). Journal: 9 events (2 plan.created, 1 order.rejected DBC, 3 order.requested, 3 order.submitted), chain intact — desk head verified 17:54 UTC. Receipts: plans/execution-2026-11-18-US.{SPY,EFA,VNQ}.json (request + broker receipt, acc_id masked). Raw payloads: runs/2026-11-18-exec/mcp/ incl. quotes and post-trade order/cash/positions.

Open items:
- VNQ resting RTH-only limit 94.98 (id 3116597): monitor broker state into the 21:00 UTC close; non-fill is acceptable — never chase. If unfilled at close, it expires/cancels per broker RTH semantics; confirm state at EOD.
- FOMC minutes 19:00 UTC: no initiations/re-submits 18:30–19:30 UTC (C2). De-risk triggers from research remain live (SPY close < ~727.5; EFA close < 100.00; VNQ close < 93.50; QQQ sell-the-news overlay).
- EOD (after 21:00 UTC): reconcile_cash, VNQ final state, reports/2026-11-18-eod.md, persist day-2 NAV references (C3), push retry (this session 403 on all credential paths at 17:33 UTC).
- No halts, no feed/auth failures, no blind retries this phase.

## Next steps

1. If operator arms execution after 14:30 UTC open: executor re-checks allowlist/sim-list (C1), previews each order, waits for per-order confirmation, journals via `tyche record-order`. Fills reported only from broker order state.
2. Intraday: monitor invalidation levels and the 18:30–19:30 UTC FOMC window (no initiations/re-submits); de-risk per plan on triggers.
3. After 21:00 UTC: EOD reconcile (tyche.fees.reconcile_cash), reports/2026-11-18-eod.md, persist raw + sanitized, persist day-2 NAV references (C3), deliver bundle + EOD report.
## Midday monitor #2 — 18:05–18:12 UTC (hourly gate)

Gate: `tyche calendar --json` exit 0, phase=midday, activity=monitor, new_entries=false, max_orders=1, event_caution=false (FOMC minutes 19:00 UTC listed). Fresh sandbox: restored journal (9 events), prices, plans, reports verbatim from /data/drive/tyche-raw/2026-11-18-execution/; `tyche journal-verify` OK. Repo HEAD 4776c5a = origin/main (executor v7 fail-closed no-envelope path). Pins unchanged: plan f11456df…, risk.yaml 96b6b0c1…, strategy.yaml bdcff441…. No halt.json.

Contracts: watchlist MISSING on Drive (`tyche watchlist` exit 1) — intraday, no re-scout allowed => no new entries, monitor held positions only, gap flagged. Approvals envelope MISSING (`tyche approvals` exit 1) => no pre-authorized submissions; per-order confirmation only, and none needed (no breach).

Executor read-only fetch 18:07 UTC (runs/2026-11-18-midday2/): account ...598 re-verified (paper, type 2, market 100, allowlisted). Broker: cash 57,360.28, frozen 7,884.33, mv 34,729.51, NAV(total_asset) 99,974.12 (−0.026% vs prior close 100,000). VNQ order 3116597 STILL RESTING (status 2, cum_qty 0, limit 94.98×83 RTH). SPY/EFA fills reconfirmed (status 4). Quotes 18:07Z: SPY 730.971, EFA 100.435, VNQ 95.255 — all NORMAL.

Desk-head checks (NAV = broker total_asset; CLI snapshot.nav 92,089.79 excludes frozen — do not use for drift while VNQ rests):
- Drift vs plan-fit weights: SPY 20.47% vs 20.53% (−0.06pp), EFA 14.27% vs 14.41% (−0.14pp) — no breach. VNQ 0% vs 7.88% is the known resting non-fill; no chase per audit C2.
- Caps: gross 34.74% ≤ 95%; free cash 57.38% ≥ 5%; max name 20.47% ≤ 38% desk target; 2 positions ≤ 100.
- Loss guards: daily −0.026% ≤ 2.5%; drawdown vs high-water 100,000 = 0.026% ≤ 4% soft. Armed, far from trip.
- De-risk triggers (close-based, from midday research): SPY 730.97 > ~727.5; EFA 100.435 > 100.00; VNQ 95.255 > 93.50 — none hit. SPY sits 0.48% above its trigger with FOMC minutes at 19:00 UTC; next hourly run 19:05 UTC lands inside the 18:30–19:30 no-initiation window (C2) — de-risking sells would still be allowed on a confirmed breach with per-order operator confirmation.

DECISION: no orders this run (monitor-only; no breach, no halt). max_orders=1 unused. No researcher/auditor delegation needed — deterministic checks, nothing to approve.

OBSERVATIONS / open items:
- VNQ day low 94.125 printed below the 94.98 resting limit yet broker shows no fill — possible quote/sim sequencing artifact; treat broker order state as authoritative, no blind action; re-confirm at next run and EOD.
- C3 gap: `tyche snapshot` CLI cannot write prior_close_nav/high_water_nav (executor flag; loader reads them at plan stage, cli.py:67). Desk head must inject 100000.0/100000.0 into the account payload at next plan stage and persist refs at EOD.
- Watchlist + approvals still absent operator-side; evening digest should propose the batch for SGT approval.

Persist #2: `tyche persist` 9 raw + 9 sanitized; narrative sanitized via tyche.persist.sanitize, leak gate PASS; commit 325da01 pushed to origin/main OK at ~18:12 UTC (this session auth works). Telegram digest sent (message_id 35). Raw bundle: /data/drive/tyche-raw/2026-11-18-midday2/.

## Midday monitor #3 — 19:05–19:15 UTC (hourly gate, post-FOMC-minutes)

Gate: `tyche calendar --json` exit 0, phase=midday, activity=monitor, new_entries=false, max_orders=1, event_caution=false; FOMC minutes 19:00 UTC listed (released 5 min before this run). Fresh sandbox: restored journal (9 events), prices, plans, reports verbatim from Drive (midday2 journal == execution journal, byte-identical); `tyche journal-verify` OK. No halt.

CONFIG DRIFT REVIEW (operator-side, legitimate): repo HEAD advanced 4776c5a → 97f3b9c. Commits 010cd9b (ADR 0014: config/strategy.yaml replaced by config/strategies/pb-001.yaml + registry) and 43b85ca (ADR 0016: new rule trade.risk_budget — initial risk ≤1% NAV per buy, qty×(limit−stop), 8% initial stop; risk_per_trade_pct 0.01 added to risk.yaml), both authored operator-side 18:26/18:50 UTC. All competition caps UNCHANGED (order cap 30%, gross 95%, min cash 5%, turnover 50%, DD 4%/6%, daily loss 2.5%). New pins: risk.yaml 8dd5e97341192f2e9c719f0f690d09274952d884350561a0233ae2169a3d5ba5; strategies/pb-001.yaml 90e7a782b3a831c601d9a943dd4732dbfc97e0e7f915cc1c57b38340eca247c9; universe a7b97e01… and plan f11456df… and prices 7e6500d5… unchanged. trade.risk_budget applies at PLAN time to new buys — not retroactive to today's fills; next pre-market kernel run will size under it (existing SPY/EFA entries would exceed a 1%-risk re-fit; flag for re-plan, no intraday action).

Contracts: watchlist MISSING on Drive (exit 1) — intraday, no re-scout => no new entries, monitor held positions only, gap flagged. Envelope MISSING (data/approvals.json absent, exit 1) => per-order confirmation only; none needed (no breach). Calendar-check skipped (intraday; alert-only pre-market duty).

Delegations (19:07 UTC, both self-contained): executor read-only fetch → runs/2026-11-18-midday3/ (accounts/cash/positions/snapshot + mcp/history_orders, quotes, vnq_1min_kline); researcher post-minutes check → reports/2026-11-18-research-midday3.md. No auditor delegation — nothing to approve (monitor-only, no orders proposed; same precedent as midday #2).

Executor findings (19:08–19:12 UTC, account ...598 re-verified paper/type2/market100/sim_list/allowlisted): total_asset NAV 99,931.44 (−42.68 vs 18:07); cash 57,360.28; frozen 7,884.33 (VNQ); mv 34,686.83. Orders: SPY 3116580 FILLED 28 @ 731.54; EFA 3116594 FILLED 142 @ 100.495; VNQ 3116597 STILL RESTING (status 2, cum_qty 0). Zero order/journal writes; journal 9 events chain intact after.

VNQ NO-FILL ANOMALY RESOLVED: 278 RTH 1-min bars show day low 94.125 printed 14:31 UTC — 3h22m BEFORE order placement (17:53:07 UTC). Min low after placement 95.05; zero bars ≤94.98 since. Broker state fully consistent; midday #2's concern was a timing artifact. Closed.

Researcher findings (report 2026-11-18-research-midday3.md): minutes HAWKISH — "almost all" expect further HIKES after the Oct pause; pause vote "very close"; SEVERAL officials (not just Waller) floated a larger 50bp Dec hike (Benzinga 1004936834/1004936833/1004936879, 19:01–19:03 UTC). Direction correction: desk delegation said "Dec cut odds" — all sourced data describes a HIKE cycle (Dec 25bp hike 95.7%/50bp 4.3% pre-minutes); researcher correctly used sourced framing. Reaction orderly: SPY −0.09%, EFA −0.17%, VNQ −0.18% vs 18:07; QQQ GREEN +0.21% (sell-the-news overlay NOT hit). No post-minutes FedWatch print yet — re-check after 19:30 UTC; watch the 50bp tail (3–4%, spike toward ~12.7% = hawkish surprise, VNQ headwind). Stance: HOLD with de-risk PREPARATION.

Desk-head deterministic checks (19:13 UTC, NAV = broker total_asset 99,931.44; snapshot.nav 92,047.11 excludes frozen — not used):
- Drift vs plan-fit weights: SPY 20.47% vs 20.53% (−0.06pp); EFA 14.24% vs 14.41% (−0.17pp) — no breach. VNQ 0% vs 7.88% = known resting non-fill; never chase (C2).
- Caps: gross 34.71% ≤ 95%; free cash 57.40% ≥ 5%; max name 20.47% ≤ 38% desk target; 2 positions ≤ 100.
- Loss guards: daily −0.069% ≤ 2.5%; drawdown vs high-water 100,000 = 0.069% ≤ 4% soft. Armed, far from trip.
- Close-based de-risk triggers at 19:08 quotes: SPY 730.44 > 727.5 (+0.40%, NEAR — day low 726.795 already in flip zone); EFA 100.245 > 100.00 (+0.245%, NEAR — low 99.965 breached intraday); VNQ 95.08 > 93.50 (+1.66%); QQQ overlay not hit. Triggers are CLOSE-based (21:00 UTC): no confirmed breach.

DECISION: no orders this run (monitor-only; no confirmed breach, no halt). max_orders=1 unused. Inside 18:30–19:30 UTC FOMC no-initiation window (C2) regardless. No halt engaged.

Operator flags for the 19:30+ / closing-drive window:
1. SPY/EFA cushions thinned (0.40%/0.245% above close triggers). Stage contingent de-risk: on a CONFIRMED close breach, de-risking sells allowed with per-order operator confirmation (no envelope). Next hourly run 20:05 UTC = closing_drive.
2. VNQ resting buy 83 @ 94.98 (3116597) is a hawkish-minutes headwind (rate-sensitive sleeve); last 95.08, 0.10% above limit — unlikely to fill without a dip. Operator may prefer to cancel (cancel/modify stays always_ask); desk takes no action without instruction. If unfilled at close it expires per RTH/DAY semantics; EOD must reconcile frozen release.
3. Watchlist + approvals envelope still absent operator-side; evening digest should propose the batch for SGT approval.
4. New trade.risk_budget rule: next pre-market plan must run under HEAD 97f3b9c config (per-strategy registry); desk head still injects prior_close_nav/high_water_nav at plan stage (C3 CLI gap).
