# Dashboard framework — the research-to-execution pipeline as the spine

The dashboard's information architecture is the professional pipeline (kickoff briefing diagram):
**Thesis → Multi-factor inputs → Outlook → Vehicle & Edge → Edge/Expectancy**, with an
**Execution & Trade Management** band underneath. Every idea/trade is a card that moves through the
stages; the dashboard shows where each one is and the evidence at each stage. This makes the process
visible to judges and to the operator, and it is exactly the "strategy & risk design" story.

## Stage mapping — current plan vs the pipeline

| Stage | Diagram | tyche today | Status / gap |
|---|---|---|---|
| 1 Thesis | market hypothesis & theme | playbook thesis + edge + invalidation | **built**: `plan.pipeline.thesis_ref` = PB-001 + frozen rules hash, journaled in plan.created |
| 2 Multi-factor | macro, fundamental filter, technical, sentiment & flow, seasonality & earnings | v0.1 core = **technicals only** (momentum/regime/vol). Researcher child + MCP news/capital-flow/event-calendar add macro/sentiment/seasonality; "fundamental" = eligibility filter (cap ≥$500M, price ≥$1, liquidity) | designed, not built; brief path pinnable via `tyche plan --brief` |
| 3 Outlook | bullish / bearish / neutral-range | regime → outlook + conviction tier from the 4-check score | **built**: `plan.pipeline.outlook/conviction` + per-order `action` act/wait gate (never blocks de-risking) |
| 4 Vehicle & Edge | ETFs, Stocks (L/S), Options | v0.1 ETFs only; window = ETFs (ballast) + stocks long + **defined-risk options** | vehicle + rationale journaled per order; vehicle choice by edge/cost/liquidity lives in playbook; **deliberate divergence: no direct short** (defined-risk puts instead) |
| 5 Edge/Expectancy | (Win%×AvgWin) − (Loss%×AvgLoss) | per-sleeve fee-net scorecard (expectancy R and %) | matches the formula; **small-n (~7 sessions) → label provisional, show n**; `expected_edge` field exists, stays None until validated — never fabricated |
| Execution | sizing, bracket/trailing, rolling | sizing = risk kernel + vol target + caps; **bracket/trailing impossible on sim** (Limit/Market only) → synthetic protection monitor + defined-risk structures; rolling = options leg-group (P2) | sizing journaled per order; v0.1 protection_type = **rebalance** (honest: drift-band rebalance + drawdown ladder); monitor P2 |

Two honest divergences to state in the report, not hide: the sim path has **no broker-native
stops/trailing**, so protection is a monitor + defined-risk structures; and we **avoid direct shorting**
(margin 60/50 + 6.0% financing + forced-liq risk) in favor of defined-risk puts.

## Per-trade pipeline contract (fields the plan + journal must carry)

So the dashboard can render every stage from data, not prose:

```
thesis_ref        playbook id (PB-xxx) + rules hash        [plan.pipeline, journaled]
inputs_ref        prices sha256 + research brief path      [plan.pipeline.inputs_ref]
outlook           bullish | bearish | range + conviction   [plan.pipeline]
vehicle           etf | stock_long | option_vertical + vehicle_rationale   [order.pipeline]
expected_edge     R and % (pre-trade); None until validated, label provisional
invalidation      explicit rule/price/level/time/event condition            [order.pipeline]
protection_type   synthetic_stop | defined_risk | time_exit | rebalance
roll_plan         for option leg groups (or none)
sizing            qty, effective qty, notional, %NAV, single-asset + sleeve caps
action            act | wait — low-conviction gate on new non-defensive entries
realized          fills, fees, exit kind, realized R and %   (post-trade, journal order events)
```

Legacy plans without `pipeline` render as "derived" on the dashboard; new plans render
"journaled". The gate is enforced in code on both submit paths, not by prompt compliance:
`tyche execute` withholds a `wait` order and journals `gate.wait`, and the lifecycle path blocks a
low-conviction entry before it can reserve (`src/tyche/lifecycle.py:485`, which calls the same
`act_wait` the plan builder stamps at `src/tyche/pipeline.py:148`). The executor's instruction repeats
the rule as a backstop and journals `gate.wait` on the MCP path (docs/agent-engineering.md); a `wait`
order stays unsubmitted even if the model ignores it.

## Panels

1. **Pipeline board** — cards per active idea/trade across stages 1→5, current stage highlighted,
   stage artifacts linked (playbook, research brief, outlook, vehicle rationale, expectancy).
2. **Trade detail** — the contract fields above; expected vs realized edge; invalidation and protection
   state; roll plan.
3. **Expectancy** — per sleeve: (Win%×AvgWin) − (Loss%×AvgLoss), fee-net, with n and a provisional label;
   conviction calibration if tiers are used.
4. **Execution & risk** — positions, exposure vs caps (40% single-asset headroom), drawdown ladder,
   daily-loss block, **kill-switch state**, protection-monitor heartbeat, open orders, **rejection log**.
5. **Equity curve** — fee-net NAV, daily returns, max DD, weekly Friday marks.
6. **Automation / orchestration** — scheduled runs, thread status, delegation + auditor approvals,
   version pins; proves unattended operation.

## Data sources

- **Journal** (`journal/events.jsonl`, hash-chained) = truth for trades, decisions, rejections, risk events.
- **Performance artifacts** (`docs/performance/`) = generated metrics.
- **QCA API** for sessions/threads/events and the scheduled desk cards (automation panel), read
  **server-side** with a PAT. Since 21 Nov both reads are on the **Managed** base:
  `build_automation()` lists the cadence through `cloud_api.cards()` and the runs through
  `cloud_api.sessions()`, and every session row passes `cloud_api.session_view()`, which keeps identity,
  state and credits and drops everything else (a raw session row carries `environment_variables` in
  plaintext - L-050). The panel says what started each run (card-fired, scout, or opened elsewhere), and an
  unreachable API **blinds** it rather than refilling it from an old export or from `plans/`.
  The eight Forward schedules this panel used to enumerate are archived, so they are not read anywhere in
  the running desk. PRD §7 item 14 is closed in code on both halves: `desk-site/functions/handler.ts` now
  fetches `/deployments` and `/sessions` on the Managed base under `TYCHE_CLOUD_PAT`, through `cardView` and
  `sessionView` - the hosted twins of the same two projections, for the same L-050 reason - and the cadence
  rows still ride in on `base.calendar`, so the card list and the cadence table describe the same objects.
  What is left is hosted, not code: the published Function declares `TYCHE_FORWARD_PAT` until the site is
  republished, and that secret stays until nothing declares it.
- **The cards themselves** = the only source for the Strategy view's cadence table. `card_cadence()` expands
  each card's own cron into one row per fire time and asks the kernel gate (`phase_at` → `strategy_for`)
  what that wall-clock hour routes to, so the table reads 08:05 plan / 12:05 monitor / 15:05 active with the
  card's timezone, window and day count beside it. `build_calendar()` stopped emitting
  `generate_hourly_schedules()`: that models the retired six-run hourly design, so the panel was advertising
  09:05/10:05/16:05 ET fires no card makes. Blind stays blind - unreadable cards leave the table empty and
  saying so, rather than drawing a remembered cadence.

## API plumbing (from the conventions overview)

- Gateway: **Managed `https://api.qoder.com/api/v1/cloud`** is where the desk is authored and where its
  agents, skills, cards, sessions, threads and events live.
  `https://api.qoder.com/api/v1/forward` is residue - four templates, the eight archived schedules, their
  own runs - and nothing authors or reads through it any more: see [agent-engineering.md](agent-engineering.md)
  and [tests/test_forward_fence.py](../tests/test_forward_fence.py), which now guards the hosted handler too.
- Auth: `Authorization: Bearer <PAT>`; PAT created at qoder.com/cloud/pat-keys, kept in a gitignored
  `.env`, **server-side only**, never in client code or the repo.
- Cursor pagination (`first_id`/`last_id`/`has_more`); 4 MB body limit; exponential backoff on 429/5xx
  (1s→2s→4s, max 3); beta features need `x-qoder-beta` (e.g. `oss-bucket-2026-09-23` for the persistence mount).
- This page is the reference for reading cloud data; it is **not** a dashboard framework. The dashboard
  is a web app we build (local first per handbook §7, optionally Qoder Sites), with a short screen
  capture for submission.

## Build order

P1: pipeline board + trade detail + expectancy + equity + rejection log from the journal (local).
P1: automation panel from the Managed base through `scripts/cloud_api.py` (PAT server-side) - **landed
21 Nov**, with the hosted `desk-site` Function's matching read landing in code on 22 Nov; what remains of
item 14 is the republish and the retirement of `TYCHE_FORWARD_PAT`, both hosted writes. P2: protection
heartbeat + roll state.
Keep it one page; do not build a platform.