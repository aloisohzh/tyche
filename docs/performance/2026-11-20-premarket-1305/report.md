# TYCHE premarket plan fire - 2026-11-20 (run 2026-11-20-premarket-1305)

Fire 08:05 ET (13:05Z), three-fire card. Window 13:05-13:45Z. Repo HEAD e53d045 (pinned release
3312287 is an ancestor). Calendar gate rc=0: trading day, pre_market, activity=plan,
new_entries=false, max_orders=0. **No orders submitted by this run.**

## Effective state

- **Halt ENGAGED** (journal flag 2026-11-19T20:28:29Z, writer-safety incident). The repo
  data/halt.json "operator resume" was dated Nov-18, BEFORE the incident - stale, not a release.
  Desk synced the engaged flag to the shared repo file via `tyche halt` (commit 4bcc383) so cloud
  mounts fail safe; push got 403 (known session-scoped auth), bundle + copies at
  /data/drive/tyche-raw/2026-11-20-sanitized-git/. Retry at close fire.
- Journal lineage restored from 2026-11-19-close-2005 (21 events, sha 9e9b0d3d... verified),
  run.start + reconcile + nav.references + halt sync + research.published + notify.sent appended;
  chain intact.
- Ownership: operator guard plan (docs/reviews/2026-11-20-protection-guard-plan.md) verifies only
  the Nov/Dec desk cards active, all 8 Forward schedules paused. Calendar next_run still names the
  paused tyche-hourly 14:05Z - stale; real next check 17:05Z (12:05 ET midday, alert-only).

## Reconciliation (executor, read-only, 13:11-13:24Z)

- Account ***598: NAV total_asset 98,379.68 = cash 45,680.12 + frozen 0 + MV 52,699.56 (exact).
  Positions SPY 28/28 @731.54, EFA 142/142 @100.495, MSFT 39/39 @503.33. No options, no shorts.
- Order history: 11 orders, single page has_more=false. **Zero new orders after the incident**
  (latest create 18:15:16Z Nov-19) - no evidence of an active second writer overnight. Attribution
  of the 8 incident orders still UNVERIFIED (prefixes match operator's PB-004 scalp + MSFT tactical
  lanes committed Nov-20 01:45Z; facts only).
- Status-5 unresolved: VNQ 3116597 (83@94.98 cum0), SMH 3118500 (10@454.48 cum0). Not proven
  terminal; no retry/cancel/modify without per-action operator confirmation.
- **Official Nov-19 daily bars: SPY close 715.87 < stop 727.50 BREACHED; EFA 98.78 < 100.00
  BREACHED.** Independently confirmed three ways: executor kline, researcher closing-quote +
  kline payloads, desk prices.csv rebuild. MSFT close 498.30 (no stop exists).
- Env blocker reproduced: TYCHE_ALLOWED_ACCOUNT_IDS=***[REDACTED] excludes challenge ***598; natural-env
  lifecycle tick fails closed. Executor used session-scoped env prefixes for read-only gate
  diagnostics only (disclosed, report §7). Operator re-provision required.
- Dry ticks (isolated copies, no --record): SPY/EFA "held position has no approved lifecycle
  ownership"; MSFT "missing a complete lifecycle plan"; latched_exits empty; tactical/scalp lanes
  report outside-regular-session. Synthetic-approval diagnostic showed the kernel WOULD latch
  stop_loss for both r2 plans from closes.json evidence - nothing persisted, not an approval.
- Pre-market quotes (pre_market fields; main last = prior close, stale): SPY 709.21, EFA 97.76
  (book 850 shares, 0.708% spread - fails 0.3% gate), MSFT 487.15, NVDA 141.08, AMD 456.99,
  AVGO 336.00, MU 653.87, SMH 432.33. quote_market_snapshot absent; order books stored.
- NAV refs: prior_close 99,914.93; HWM candidates 102,208.99 (reproducible) vs 100,193.13 (used
  Nov-18). Working pin 102,208.99 (conservative, advisor-affirmed), operator confirmation requested.
  DD -1.54% vs prior close, -3.75% vs working HWM; soft 4% approaching, not breached.

## Research (researcher, anchor 13:15:49Z)

- Regime: Fed HIKE cycle intact; Waller publicly floated 50bp Dec hike; day-2 AI/growth risk-off
  (Hunterbrook AMD day-2, NVDA House probe + Megaspeed DOJ, gold -9.2% week). FedWatch tail not
  re-verified (no fresher MCP print than Nov-18) - flagged missing.
- Reviews published (book sha 02f78128..., prior 111fcbe2... preserved in run state/):
  SPY e73ee77d INVALIDATED, EFA add27d1a INVALIDATED - rule (i) completed daily-close breach,
  source-backed, valid_until 14:15:49Z. Plans/approvals untouched; nothing executable (approvals=[]).
- MSFT tactical: NO proposal - no same-session long edge (technical/macro/flow/sentiment/catalyst
  fail; fundamental/liquidity pass; seasonality unknown). Watchlist as_of 2026-11-20 entries []
  published (sha 95bdb0b2...), validated by tyche watchlist.
- 5 events validated against persisted AASTOCKS/MT payloads and pinned to config/events.yaml:
  Waller 08:25 ET, UMich final 10:00 ET (cons conflict 51.6/53.3), Cook 12:15 ET, Eurozone
  confidence 10:00 ET, NVDA/Commerce Dec-2 briefing deadline. Book MarketEvents added for the
  four touching held symbols. PBoC LPR unchanged 3.00/3.50 (post-event reviewed).
- Ballast history: 11 symbols x 370 bars (2025-06-03..2026-11-19) via scripts/mcp_prices.py from
  researcher MCP payloads (staged in mcp/klines/); data/prices.csv 4070 rows. No transcription.
- YouTube inbox: no new items; nothing routed to LEAN.

## Decisions and advice

Advisor consulted (full transcript): keep halt; exit is the contractually-specified outcome of
rule (i) - lead with operator-approved exit executable at today's 15:05 ET close fire (midday
cannot submit); hold+r3 re-adoption is the explicit alternative, not pre-built; skip auditor
(nothing executable); push halt flag with disclosure; urgent digest; next check 17:05Z.

## Protection gaps (every lot without a live exit path)

1. SPY 28 - breached daily-close stop, contract expired unapproved, no live exit order.
2. EFA 142 - same; pre-market book illiquid.
3. MSFT 39 - unowned fill, no plan/grant/review/stop/target/deadline; ~19% NAV near 20% name cap;
   $0.98/share ex-div receivable Dec-10.
4. No resting broker stops anywhere; synthetic checks only at the three fires; gaps/halts/nonfills
   can exceed planned loss. Exposure window until the close fire is operator-accepted.
5. VNQ/SMH status-5 orders unresolved.

## Operator actions (in order)

1. Attribute the Nov-19 17:23-18:15Z writer (your PB-004/MSFT tests?).
2. Re-provision TYCHE_ALLOWED_ACCOUNT_IDS to include ***598.
3. Choose SPY/EFA disposition: approved exit at 15:05 ET close fire, or explicit hold with r3
   re-adoption (full preview + independent audit + exact approval either way).
4. Disposition MSFT 39.
5. Resolve-or-accept VNQ/SMH status-5; confirm HWM pin 102,208.99.
6. Then `tyche resume` (or console) - buys stay blocked until then.

## Delivery / persistence

- Telegram urgent digest: sentinel render-digest + send-digest, message_id 44 ref d3dd4ff3, rc=0.
- Git: commit 4bcc383 (halt sync + event pins) LOCAL ONLY (push 403); bundle + flag copies in
  /data/drive/tyche-raw/2026-11-20-sanitized-git/. Close fire must fetch+rebase+push.
- Raw bundle: /data/drive/tyche-raw/2026-11-20-premarket-1305/ (mcp/, research/, state/,
  coordination/, journal/). Sanitized mirror: docs/performance/2026-11-20-premarket/.