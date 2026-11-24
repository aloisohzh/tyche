# Coordinator config/cap measurement — 2026-11-19 observe run (read-only)

Measured at 2026-11-19 ~04:55–05:05 UTC (2026-11-18 ~23:55 ET, market closed).

## Roots and pins
- Ordinary repo: /data/workspace/tyche, HEAD b9ced85d9c123ea30e1041a02bcce943ee3ac66f
  (contains tested release 7288d68758ec2fedcee137622fee472be5d9a41d; verified ancestor).
- Pinned lifecycle engine: LC_ROOT=/tmp/tyche-lifecycle-KXBWpbxx, branch lifecycle-hourly-release,
  HEAD 1e902cf57c26599b69c49496e81b7a493ae5bc49 (exact match verified). Schema command exits 0;
  imports resolve inside LC_ROOT.

## Config hashes (sha256)
| File | Current root | Release LC |
|---|---|---|
| config/risk.yaml | 294552e6c1e582f4be36f60145175d086706086ac6fa623880ffe6f97a85284c | 8dd5e97341192f2e9c719f0f690d09274952d884350561a0233ae2169a3d5ba5 |
| config/strategies/pb-001.yaml | 9e7f80f7b84a4c60c8abdd921d8eeb125492dc68539e163c5c7293ffc1907f8f | 90e7a782b3a831c601d9a943dd4732dbfc97e0e7f915cc1c57b38340eca247c9 |
| config/universe.yaml | a7b97e01de7a7cb985336779d997c22871d1ee9c8e477032d5eb067f8e2365d0 | a7b97e01de7a7cb985336779d997c22871d1ee9c8e477032d5eb067f8e2365d0 (identical) |
| config/tactical.yaml | 2d0c00336f298e7c3b73998f21f2ef564b58779a05f2e43243c853b12fe17275 (execution_enabled=false, line 5) | absent in release |

PB-001 rules_hash (sha256(pb-001.yaml bytes + universe.yaml bytes)[:12], pipeline.py:39):
- Current root: 4105d7a680a3
- Release LC: 7799974f9fd0  ← used in draft plans so the pinned engine validates; divergence flagged.

## Cap semantics (verified in code, not docs)
- `allocation_cap` (current pb-001.yaml = 0.25) is the WHOLE PB-001 sleeve budget:
  rotation.py:269 `max_invested = min(strategy.allocation_cap, 1 - min_cash_weight)`.
- `max_weight` (pb-001.yaml = 0.30) is a PER-NAME cap inside the sleeve:
  rotation.py:184 `caps = min(asset.max_weight, strategy_max)`; universe per-asset:
  SPY 0.30, EFA 0.20, VNQ 0.15. Effective per-name: SPY 30%, EFA 20%, VNQ 15%.
- These are DIFFERENT limits. Prior auditor claim conflating 25% allocation_cap with
  30% per-name max_weight is incorrect and is not repeated here.
- risk.yaml (current): max_order_notional_pct 0.30 per order; max_position_weight 0.40 absolute;
  max_gross_exposure 0.95; min_cash_weight 0.05; risk_per_trade_pct 0.01; soft/hard DD 0.04/0.06;
  daily_loss_limit_pct 0.025; max_orders_per_day 40; competition_order_cap 200;
  max_daily_turnover_pct 1.50; option_risk_per_trade_pct 0.0075; max_option_premium_pct 0.25.
- config.py:242 cross-lane budget check: 0.25 (PB-001) + 0.45 (tactical stock_allocation_cap)
  + 0.25 (option premium) = 0.95 = max_gross_exposure. Tactical max_name_weight 0.20.

## Release vs current differences (activation reconciliation required)
Release risk.yaml: max_daily_turnover_pct 0.50 (vs 1.50), max_orders_per_day 6 (vs 40),
NO competition_order_cap, NO option caps. Release pb-001.yaml: NO allocation_cap — and the
release engine's config.py has NO allocation_cap field at all (auditor-verified; the 0.95
default exists only in current-root config.py:69). I.e. release has no 25% sleeve budget concept.
Per addendum: these pinned conservative rehearsal settings are NOT permission to replace
operator-approved portfolio caps; activation requires a reviewed release reconciling
config/rules hashes with operator-approved caps and cross-lane exposure.

## Existing holdings vs budgets (marks from 03:02Z rollout capture; executor refreshing)
- SPY 28 @ cost 731.54, mark 730.20 → mv 20,445.60 ≈ 20.46% NAV (99,927.13).
- EFA 142 @ cost 100.495, mark 100.26 → mv 14,236.92 ≈ 14.25% NAV.
- Combined ballast ≈ 34.71% NAV > 25% current-root sleeve budget → sleeve budget breach
  under CURRENT semantics (existing holdings; NOT automatic liquidation permission).
  Under release semantics (no allocation_cap) each name is within its per-name cap.
- Exits must remain possible under any cap regime (act/wait: sells always act,
  pipeline.py act_wait; risk breaches gate new entries — auditor to verify in tick path).

## Deterministic regime/conviction (latest actual kernel plan, not defaults)
- Source: /data/drive/tyche-raw/2026-11-18-eod/plans/2026-11-17-plan.json (as_of 2026-11-17,
  prices.csv through 2026-11-17, 370 bars, 11 symbols).
- regime=neutral; regime_checks {equity_trend:true, golden_cross:true, vol_calm:false,
  credit_trend:false} → conviction_tier(2,4)=medium. Label: as-of Nov-17 close, PENDING REFRESH
  (Nov-18 daily bars not yet in prices.csv; no kernel re-run during hold).

## NAV references (authoritative journal, read-only)
- /data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl, eod.reconcile ts 2026-11-18T21:11:13Z:
  prior_close_nav 99,914.93; high_water_nav 100,000.00; cash 57,360.28; frozen 7,884.33;
  fees_modeled=fees_implied=1.98. 12 events; last hash 5df92f3d… (notify.delivery_failed 22:08Z).
- EOD nav-refs.json matches. Fresh NAV comparison pending executor.

## Shared state (read-only inspection)
- /data/drive/tyche-raw/lifecycle: DOES NOT EXIST → no production lifecycle ledger, no grants,
  no reservations, no latches. Coverage blocker; synthetic empty state only in isolated run dir.
- lifecycle-rehearsal-20261119-a/: probe.json (nonce 787f4ae0…, code_hash bd8d6ad3…,
  git_head 1e902cf5…, written 2026-11-19T03:50:32Z); owner.lock/ exists as EMPTY directory
  (mkdir-style lock; rclone FUSE mkdir is NOT proven distributed mutual exclusion).
- rollout-20261119/: state-probe.json (02:58Z), mcp/ broker captures (~03:02Z),
  post-template-verification/ NVDA option template artifacts (verification only).
- No watchlist.json at /data/drive/tyche-raw/ (tactical research working copy absent).
- Single durable writer for both lanes: UNRESOLVED. Drive flock/fsync not distributed locks.

## Calendar (live clock, tyche calendar --json, exit 1 = closed/skip, not failure)
- now 2026-11-19T04:55:32Z / 2026-11-18T23:55:32-05:00; phase closed; run=false;
  new_entries=false; max_orders=0; event_caution=false.
- Next scheduled hourly run 2026-11-19T13:05Z (08:05 ET). Nov 26 Thanksgiving closed;
  Nov 27 early close 13:00 ET → last scheduled hourly RTH check 12:05 ET.
- Draft exit_deadline proposed 2026-11-27T12:05:00-05:00 (researcher verifying feasibility).