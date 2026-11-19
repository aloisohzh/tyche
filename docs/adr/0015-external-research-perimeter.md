# ADR 0015: External research perimeter — local LEAN validation lane, journaled charting

Status: Accepted, 19 November 2026 (operator decision). Amended same day: the
hosted QuantConnect MCP requires a **paid organization agent node**, so the
validation lane moves to the open-source LEAN engine run locally (operator
decision). Charting implemented same day.

## Context

The competition explicitly allows multiple MCPs (TradingView charting,
QuantConnect quant trading, others). The operator intends tyche to run
**post-competition**, so the window clock (ADR-0007) no longer caps platform
work — but the kernel/perimeter boundary (ADR-0006) and paper-only rule
(ADR-0002) still hold. Two gaps motivated this:

- **No validated setup.** Every playbook is honestly labeled unvalidated;
  there is no repeatable hypothesis → test → pre-register lane.
- **No visual evidence.** Judges and the operator read tables and JSON; the
  equity path, entries/exits and regime context are not charted anywhere.

Researched options: the official TradingView MCP (hosted, OAuth, **paid plan
required**, beta with delayed data) — operator has no account, so unavailable.
The official QuantConnect MCP (hosted bridge to the QC API: projects, compile,
backtest, optimize, live deploy) — **requires a paid agent node (A1-1, A4-8,
A16-32) in the organization; the free A-MICRO node cannot use it**. The
operator declines a subscription for research convenience. LEAN, the engine
that powers QuantConnect, is open source (Apache-2.0) and runs locally with no
account or credentials. Community TradingView bridges drive the desktop app's
debug interface and break on updates — rejected as fragile.

## Decision

1. **Local LEAN as a research-only validation lane.** `lean-cli` backtest /
   research / optimize run on the operator's machine against locally stored
   data; results are read from the local output directory. Allowlisted
   command categories: backtest, research, optimize, read results.
   **Excluded: `lean live` and any live-deployment or cloud-push path**
   (ADR-0002; the competition and paper venue is moomoo sim). No credentials
   are required or stored. Workflow: playbook hypothesis → LEAN backtest →
   validation label with evidence link (venue, data source, date range) →
   pre-register (freeze hash) → trade small on moomoo sim. LEAN results are
   research evidence, never kernel inputs. First lane run:
   [2026-11-19 validation note](../validation/2026-11-19-lean-pb001-smoke.md)
   (lane smoke PASS; PB-001 hypothesis NO-GO as alpha, sanity-checked).
2. **Charting from journaled data, not a third-party feed.**
   `scripts/export_charts.py` renders `desk-site/web/charts.html` using a
   vendored copy of TradingView Lightweight Charts (Apache-2.0, attribution
   kept). Inputs: the price CSV (close-only → line series; no fabricated OHLC),
   journal `order.submitted` markers and `plan.created` regime bands / NAV
   marks, filtered by an explicit `--account` whose value is used for filtering
   only and **never embedded** in the output. Markers outside the price range
   are omitted with a visible count, not silently clamped.
3. **Perimeter rule extended (ADR-0008 allowlist).** External research tools —
   local LEAN included — feed research, validation and presentation only. The
   execution kernel consumes pinned config + moomoo prices; no external tool
   output enters signals, sizing, risk verdicts or the order path. Delayed or
   third-party data must not reach the kernel.
4. **TradingView MCP deferred** until a paid account exists; re-evaluate
   post-competition for its screener/news/calendar layer in the scout perimeter.
5. **YouTube research inbox, playlist-scoped (operator decision).** The scout
   perimeter may read text derived from `@moomoomalaysia`'s *US Options Trading*
   and *Macro Insights* playlists only: playlist RSS + transcript extraction on
   the desk machine (`scripts/fetch_youtube_insights.py`). Raw transcripts stay
   in the private locker (copyright); git gets a metadata index and scout
   summaries. Insights are hypotheses routed through the LEAN lane, never
   kernel inputs. The cloud template clause was operator-approved and applied
   2026-11-19 (researcher compile v8, desk roster re-pinned 8/2/7 + advisor);
   see docs/runbooks/youtube-research-inbox.md.

## Consequences

- Playbooks gain a cheap, repeatable gauntlet: the parked validation machinery
  (ADR-0007) returns as a local open-source engine instead of a subscription.
- The desk-site gains judge-visible visual evidence (price path, trade markers,
  regime bands, NAV curve) that is reproducible from journaled inputs.
- New trust boundary: LEAN backtest results are claims about historical data
  on a local engine, not about moomoo sim fills; validation labels must state
  the venue, the engine version and which price source fed the backtest.
- Local setup cost: `lean-cli` plus its engine runtime (Docker for some modes);
  backtests consume operator compute, not shared cloud nodes. Data must be
  supplied locally (converted CSV or operator-provided datasets); no QC data
  subscription is implied.
- Vendored chart library adds a ~200KB static asset; version pinned in the
  vendor filename, upgrade is a deliberate re-download.
- Validation is pre-trade work, never on the intraday critical path.

## Alternatives considered

- **Hosted QuantConnect MCP:** rejected — requires a paid organization agent
  node (free A-MICRO ineligible); operator declines the subscription. The
  allowlist design above carries over unchanged if a paid node ever exists.
- **tyche self-built backtest harness first:** deferred, not rejected — it
  remains DESIGN.md §12 open work for kernel-integrated cost/slippage and
  walk-forward checks; LEAN supplies an external engine reference now.
- **TradingView MCP now:** unavailable (no paid account); delayed beta data
  would also be a kernel contamination risk.
- **Community TradingView desktop bridge:** rejected — undocumented debug
  interface, breaks on app updates, unsuitable for an audited agent.
- **Hosted chart screenshots from a third-party MCP:** rejected — not
  reproducible from journaled inputs; the export script is.
- **QC live trading:** rejected — paper-only ADR and split execution venues.