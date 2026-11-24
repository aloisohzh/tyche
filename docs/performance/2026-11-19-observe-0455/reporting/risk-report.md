# Lifecycle adoption drafts — coordinator risk report (PROPOSALS ONLY, NOT ARMED)

Run: 2026-11-19-observe-0455. Compiled 2026-11-19 ~05:15 UTC (2026-11-19 00:15 ET; market CLOSED).
Hourly lifecycle monitoring deployed; orders unarmed. execution_enabled=false. No approvals recorded.

## Draft plans (unapproved, immutable fingerprints)
| Plan | Symbol | Qty | plan_hash |
|---|---|---|---|
| LC-20261119-SPY-ADOPT-r1 | US.SPY | 28 | 8ca9176daf7d09b4030cc15cf5460896fd871ef2c66b48db60fc6f886fbdd954 |
| LC-20261119-EFA-ADOPT-r1 | US.EFA | 142 | 237408a874860bebfe8731bbfec7742d18f42e2dc717646b24afa46600903395 |

Book: plan/book.json sha256 c710ffe137b968479694c4f34da7420a6ea1ad7beae3061700f5da8de342d166
(schema-validated via pinned LC engine 1e902cf5; rules_hash 7799974f9fd0 = release PB-001+universe).
Both mode=adopt_position, exact reconciled quantities (executor 04:59Z reads), strategy PB-001 ETF ballast.
Entry bands are adoption anchors only (Nov 18 RTH ranges) — NO new buys. exit_on_invalidation=true,
review_max_age 60min, quote_max_age 300s, max_slippage 20bps (<=30 required).
entry_expires_at 2026-11-19T16:00 ET; exit_deadline 2026-11-27T12:05 ET = last scheduled hourly
RTH check on the early-close final day (13:00 ET close; verified vs calendar). Nov 26 closed.

## Per-position plain-language risk (NAV 99,927.13; marks = Nov 18 regular close)
### US.SPY — SPDR S&P 500 ETF (stock ETF, PB-001 ballast, full-position exit only)
- Invested at cost: $20,483.12 = 20.50% NAV. Worst case total investment loss = the entire
  $20,483.12 (an ETF gap to zero is implausible but nothing caps loss at the stop).
- Stop 725.00 (basis last; below observed Nov 17/18 lows 727.00/726.795; buffer = design choice).
  P&L vs cost at stop: −$183.12 (−0.183% NAV). Forward downside from current mark 730.20: −$145.60
  (−0.146% NAV). Engine planned loss from adoption anchor high 735.06: $281.68 (0.282% NAV).
- Target 749.50 (basis last; anchor Nov 16 high 749.82; placement = design choice).
  P&L vs cost at target: +$502.88; from mark: +$540.40. Reward/risk from anchor high: 1.435.
- Exit fees (model): $0.99 (platform 0.99 + TAF 0.0046). Slippage bound 20bps at stop ≈ $40.60.
  Worst planned loss incl slippage+fees: $323.27 = 0.324% NAV. Gaps/nonfills can exceed this.
- Unrealized now: −$37.52. Time exit: 2026-11-27 12:05 ET deadline; adoption window expires Nov 19 16:00 ET.
### US.EFA — iShares MSCI EAFE ETF (stock ETF, PB-001 ballast, full-position exit only)
- Invested at cost: $14,270.29 = 14.28% NAV. Worst case total investment loss = entire $14,270.29.
- Stop 99.40 (basis last; below Nov 18 low 99.96; 0.56% buffer = design choice).
  P&L vs cost at stop: −$155.49 (−0.156% NAV). Forward downside from mark 100.26: −$122.12
  (−0.122% NAV). Engine planned loss from anchor high 100.87: $208.74 (0.209% NAV).
- Target 101.90 (basis last; anchor Nov 17 high 102.00; placement = design choice).
  P&L vs cost at target: +$199.51; from mark: +$232.88. Reward/risk from anchor high: 0.701 (<1 —
  trader decision point: tight stop under a broken range floor; adoption, not a new entry).
- Exit fees (model): $1.01. Slippage 20bps at stop ≈ $28.23. Worst planned incl both: $237.98 = 0.238% NAV.
- Unrealized now: −$33.37. Same deadline/adoption window as SPY.
### Combined
- Planned stop risk: $490.42 (0.491% NAV) engine anchors; $338.61 (0.339%) vs cost;
  $267.72 (0.268%) forward from marks; $561.25 (0.562%) worst incl slippage+fees.
  All below the 1% NAV stock stop-risk budget (risk_per_trade_pct 0.01; applies per buy at plan
  time — adoption places no buys). Fee model matched EOD actuals exactly (1.98 = 1.98 on Nov 18).

## Shared risk mechanics (both)
- Synthetic hourly stops/targets/time exits — NOT broker-native orders; no resting protection.
  Hourly cadence 08:05–17:05 ET checks; quote_max_age 300s means quotes must be re-fetched at each
  check; between checks (up to 60min, overnight ~15.5h, Thanksgiving gap Nov 25 close→Nov 27 open)
  there is NO monitoring. Gaps, halts, stale feeds and nonfills can exceed planned loss; daily-close
  basis triggers (none proposed here; both basis=last) execute no earlier than next session.
- All-at-once full-position exit; no ladder, no scaling, no shorting, no automatic re-entry.
- Reviews: SPY valid / EFA uncertain (thesis-level, PENDING-REFRESH). Both expire 06:10 UTC —
  BEFORE the next hourly run 13:05 UTC. Fresh quotes + fresh review mandatory before any action.
  EFA uncertainty blocks NEW entries, not retained-ballast exit evaluation.

## Operational gates before these could ever be armed (ALL unresolved)
1. ROLLOUT HOLD: execution_enabled=false; operator deployment release required after validation.
2. No production lifecycle ledger (/data/drive/tyche-raw/lifecycle absent); single durable
   cross-lane writer unproven (rclone FUSE mkdir/flock/fsync ≠ distributed lock; rehearsal
   owner.lock/ is an empty dir with no owner metadata).
3. Config reconciliation: release rules_hash 7799974f9fd0 ≠ current-root 4105d7a680a3;
   release lacks the 25% PB-001 allocation_cap and uses turnover 0.50/orders 6 vs current
   1.50/40 + option caps. Existing ballast 34.7% NAV exceeds the current 25% sleeve budget
   (existing holdings — not liquidation permission; exits must remain possible).
4. Fresh independent audit of these exact hashes + explicit operator approval of the complete
   preview (approve requires exact broker quantity match, fresh review, fresh market snapshot).
5. Paper-option round-trip validation and 120s tactical monitoring remain incomplete (tactical
   lane; does not block stock-only adoption mechanics but blocks overall release).
6. Broker drill / operational validation per hold; reserve→submit path never exercised.

## Read-only engine evidence this run
- preview exit 0 both plans (plan/preview-*.json): approved=false, submitted=false.
- capture exit 0 → plan/market.json (observed_at 04:59:07Z = oldest actual broker read;
  regime neutral / conviction medium from latest actual kernel plan 2026-11-17, PENDING REFRESH;
  NAV refs from verified journal; orders_complete=true; 3 orders incl. VNQ status 5 unfilled).
- tick LIVE clock: exit 1 "broker snapshot stale or future-dated; fetch again" — honest closed-market
  result; a live tick needs a fresh broker read at check time.
- tick REPLAY --at 04:59:30Z, synthetic EMPTY state /tmp/lifecycle-synthetic-0455/ (isolated, NOT a
  production ledger), NO --record: both held symbols → action=review, "held position has no approved
  lifecycle ownership", authorized=false; warning "research review expired or future-dated" (reviews
  drafted 05:10Z > replay time — correct deterministic behavior). Nothing latched, nothing written.

## Artifact hashes (sha256)
- plan/book.json c710ffe137b968479694c4f34da7420a6ea1ad7beae3061700f5da8de342d166
- plan/market.json 13673d965b8de683b22603c8710f149517b47149b5a35d54f7c507fa41b89581 (contains full account id — PRIVATE)
- plan/preview-LC-20261119-SPY-ADOPT-r1.json aebb0fd058f0d13ae228023e261d2cc63ff509113108615fbfaa94161604bd80
- plan/preview-LC-20261119-EFA-ADOPT-r1.json d783502ee1006eb52e74c9e991cd53db5c25e1296c271686ba2631c720bf9ce8
- plan/tick-synthetic-replay.json 2614d8cc14ce1c9a09ea9dbeb7e076720910e94e54f619446551832142f20aa7
- plan/risk-numbers.json 1676697ea35198170c0752f1ecb52c1bc19d2855ec48f6b124774a9621c79fff
- Executor captures + SHA256SUMS in mcp/ (all verified); research drafts + raw payloads in research/.

## Audit response (independent draft audit, reviewed_at 2026-11-19T05:14Z per findings.json; audit/draft-audit.md + findings.json)
Both plans APPROVE-WITH-CHANGES (draft quality; NOT approval, no execution authority). All six
check groups PASS (C3 with sourced gaps); blockers confirmed. Coordinator accepts and records:
1. SPY entry_low 726.80 rounds the observed Nov-18 low 726.795 UP by 0.005. Documented here;
   book.json NOT edited (immutable hash preserved). Operator may accept as-is or request r2.
2. %NAV figures in the per-position section are COST basis (20.50%/14.28%); market-value basis
   is 20.46%/14.25% = 34.71% combined. Both exceed the current-root 25% sleeve budget.
3. Fees are MODELS (fees.py) reconciled to cash-residual-implied actuals, not confirmed charged
   fees; exit fee estimates carry the same caveat.
4. Correction accepted: release engine config.py has NO allocation_cap field at all (the 0.95
   default is current-root only). coordinator-config-caps.md amended.
5. Exit reachability verified with line evidence: lifecycle.py:420-451 held path, :472-473 halt
   entry-only, pipeline.py:65-70 sells always act, risk.py:85-123 entry gates buy-only (sells
   still subject to no_short/pending/limit-deviation/competition-cap-200).
6. At the 13:05Z hourly check: recapture fresh broker snapshot + quotes, re-review both exact
   hashes (current reviews expire 06:10Z), surface the retained-exit coverage gap. EFA R/R 0.701,
   stop-design vs 8% initial_stop_pct, and sleeve-breach handling are OPERATOR decisions.