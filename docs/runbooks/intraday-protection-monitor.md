# Runbook: intraday protection monitor (ADR 0013) - draft contract

**Status (2026-11-21): PARTLY DECIDED, PARTLY BUILT. Read §0 first.** The operator picked the pre-armed bounded
exit (rung 1.5) and that piece is now in the code: the kernel drafts an exit note from the open book, the desk
arms it. What is *not* built is the detector: [ADR 0013](../adr/0013-protection-monitor.md) is still `Proposed`,
there is no `tyche monitor` command (verified: `src/tyche/cli.py` contains no `monitor` registration), no monitor
schedule, no cadence ladder and no drill. Nothing in §2-§9 has been deployed, and writing §0 changed no cloud
object, created no schedule and granted no submission rights. What actually protects open lots today is the three
desk fires documented in [protection-monitor.md](protection-monitor.md) (08:05 / 12:05 / 15:05 ET, the 12:05 fire
watch-and-shout only), plus - for a lot the desk is looking at - an armed note the operator signed in advance.
Read §2 onward as the contract to approve *before* anything is built, not as an operational instruction.

Scope boundary, unchanged by anything proposed here: the platform is paper-only (
[ADR 0002](../adr/0002-paper-only.md)), research and idea generation stay separate from paper execution, and
paper execution stays separate from live execution. **No tier of the monitor gets a live path, and Level 2
(automatic exit submission) is out of scope for this draft.** The env/allowlist/order-type gate in `risk.py` is
the same gate a monitor-queued intent would have to pass; the monitor does not widen it.

## 0. Decided on 2026-11-21: the operator chose the pre-armed bounded exit (rung 1.5)

The ladder discussed with the operator, in the order a lot "grows up":

| Rung | What happens on a confirmed breach | Status after 2026-11-21 |
|---|---|---|
| 0 | The tick evaluates and journals; nothing leaves the journal | not built - still needs `tyche monitor tick` (§2, §9 step 1) |
| 1 | Plus an urgent Telegram bark | not built (needs rung 0 to detect anything) |
| 1.5 | Plus a bounded exit note the operator signed **in advance**, executed without a per-order tap | **built** - the part that did not need a new detector |
| 2 | The system decides and submits on its own | declined, as Level 2 is in §4 |

The reason for 1.5 rather than 1 is availability, not ambition: the operator is not near a phone all day and
should not have to invent numbers for a plan they did not write. And "in advance" cannot mean a broker-side stop,
because the sim offers Limit/Market only and a resting limit sell placed below the market fills immediately at
market ([ADR 0012](../adr/0012-options-protection.md)). So the pre-placed order has to live inside the platform,
as an armed operator envelope (`src/tyche/approvals.py`) rather than as a resting broker order.

**What is now in the code** (`src/tyche/envelope.py`, `tyche propose-envelope` at `src/tyche/cli.py:1231`,
`/api/approvals/propose` and `arm_envelope({"use_draft": true})` in `dashboard/server.py`, covered by
`tests/test_envelope_proposal.py` and the drafting block of `tests/test_desk_controls.py`):

- The kernel **proposes**: one sell line per open paper position, quantity from the broker book the desk is
  already showing, floor from the stop the plan journaled at entry (`payload.protected_setup`, else
  `payload.stop_price`, else the watchlist level), widened by `risk.exit_collar_pct`.
- The operator **arms**: the desk's Arm click re-dates the draft, relabels it
  `operator (dashboard, drafted from open positions)` and writes `data/approvals.json`. Nothing else writes that
  file, and a draft older than today's ET date is refused - so the numbers always come from the book and levels
  on screen now.
- The operator owns exactly one number: the collar (`config/risk.yaml`, `exit_collar_pct: 0.05`, valid 0-0.20).
  The plan owns every stop. That split is the whole point - the human sets tolerance, not price levels.
- Refusals are reported, not guessed. No journaled level and no watchlist level means no line; an option position
  means no line (there is no verified contract to sell against at this layer); a bearish put means no line
  because it exits by buying back. `setup_hash` is copied verbatim from the journal because it folds in the
  account id and the config hash (`src/tyche/tactical.py:72`), and a line whose hash is missing is flagged
  *unbound* - the tactical lane refuses an unbound line (`src/tyche/tactical_cli.py:265`).
- Drafting is a **local desk and CLI action only**. The hosted Sites Function has no Python and no journal, so the
  buttons do not appear on the hosted console. A hosted draft would have to be published into the feed by
  `scripts/publish_desk_data.py`, and `test_every_feed_file_the_hosted_function_reads_is_published` is the guard
  that would catch that omission.

**What rung 1.5 does not do.** It shortens the *human-confirm* leg, not the *detection* leg. Until rung 0 exists,
detection is still the three desk fires (08:05 / 12:05 / 15:05 ET), so an armed note only helps for a breach the
desk happens to be looking at - which is why the build order below still starts with the tick. Arming a note also
grants nothing new: it is the same envelope the Pre-approve path already writes, with sell lines only, and the
kill switch still outranks it.

**Sequencing the operator agreed to**: propose-and-arm card (done) -> Level 0 monitor tick at the 5-minute tier ->
synthetic-breach drill (§8) -> only then discuss Level 1 bark routing and any queueing behaviour.

## 1. The gap this closes, and the pieces that already exist

The blind window on an open lot is the distance between checks: up to ~4 h intraday (08:05 -> 12:05) and ~17 h
overnight (15:05 -> next 08:05). Detection is not protection, and more LLM runs do not shorten the window
cheaply - a deterministic tick does. Verified as already present in the kernel:

| Piece | Where | State |
|---|---|---|
| Dry-run tactical tick with quote-confirmation state machine | `src/tyche/tactical_cli.py:112` (`tyche tactical tick`), `plan_tick` at `src/tyche/tactical.py:126` | implemented, run only when a card is told to |
| Cadence field the tick itself recommends | `monitor_interval_seconds: 30` at `config/tactical.yaml:14`, surfaced as `interval_seconds`/`next_check` (`tactical.py:225`) | implemented, unused intraday |
| Heartbeat-gap detection (observations cleared after 2x the interval) | `src/tyche/tactical.py:154` | implemented |
| `protection.gap` producer + per-request de-duplication | `src/tyche/tactical_cli.py:387`, `_gap_recorded` at `:452` | implemented on the PB-004 arm path |
| Lifecycle coverage-gap string (last tick older than 75 min) | `src/tyche/lifecycle.py:603` | implemented, reported only |
| Research failure keeps approved exits alive | `monitoring_book` at `src/tyche/lifecycle_cli.py:57` | implemented |
| Cross-process, nonblocking journal lock | `journal_lock` at `src/tyche/journal.py:35`, `append_locked` at `:69` | implemented - **ADR 0013's "kernel change, small" is already done** |

Missing, and the actual build: a `tyche monitor tick` kernel command with `monitor.heartbeat` /
`monitor.breach` / `monitor.clear` / `monitor.gap` events, something that invokes it more often than three times
a day, alert de-duplication by transition, and heartbeat coverage reported in every EOD digest.

## 2. Tick contract (what runs, what it reads, what it emits)

```
tyche monitor tick --book data/watchlist.json --quotes <run-dir>/quotes.json \
                   [--positions <run-dir>/positions.json] --journal journal/events.jsonl \
                   [--config-root .] [--record] [--at ISO_TIMESTAMP]
```

- **Inputs are files, never MCP calls.** The kernel cannot call MCP (see
  [agent-engineering.md](../agent-engineering.md), "Snapshot file contract"); the executor writes the read JSON
  and the tick consumes it. Quote freshness is checked, not assumed (`max_quote_age_seconds: 120`,
  `max_snapshot_age_seconds: 120` at `config/tactical.yaml:12-13`).
- **The watchlist is the same book the lanes already use** - `Watchlist`/`WatchlistEntry` at
  `src/tyche/watchlist.py:95,34`: `symbol`, `sleeve`, `strategy`, `entry_low/entry_high`, `stop`, `target`,
  `expiry`, `status`, `invalidation`, `exit_at`, `option`, `direction`, `reviewed_at`, `confirmation_ticks`.
  Its validators are load-bearing for the monitor: levels must be ordered (`:73`), timestamps must be
  timezone-aware (`:89`), symbols and `setup_id`s must be unique (`:99`). A book that fails validation is a
  **no-go state, not a safe state**: the tick emits no verdict and shouts.
- **Per-trade protection identity comes from the plan contract**, not from the watchlist: `OrderPipeline` at
  `src/tyche/models.py:254` carries `invalidation` (`:260`), `protection_type` (`:261`, one of
  `synthetic_stop | defined_risk | time_exit | rebalance`), `roll_plan` (`:262`) and `action` (`:264`).
- **Exit codes.** `0` evaluated; `1` the calendar gate says do not run (weekend, holiday, outside the regular
  session - `tyche calendar --json`, `is_trading_day`); `2` inputs unreadable or invalid. Code `2` must never be
  reported as "no breaches".
- **`--at` is replay only** and cannot combine with `--record` (same rule as `tactical tick`,
  `tactical_cli.py:122`). A naive clock raises; the tick requires a timezone-aware clock (`tactical.py:130`).
- **Output events** (free-form types, hash-chained like everything else):

| Event | Payload | Emitted when |
|---|---|---|
| `monitor.heartbeat` | `tick_at`, `cadence_seconds`, `watched`, `breached`, `coverage_ok`, `quote_age_seconds`, `phase` | every tick that evaluated |
| `monitor.breach` | `symbol`, `strategy_id`, `protection_type`, `level`, `observed_price`, `observed_at`, `episode_id`, `exit_ref` | a level transitions clear -> breached (once per episode) |
| `monitor.clear` | same identity + `episode_id`, `duration_seconds` | the price returns inside the level, closing the episode |
| `monitor.gap` | `last_heartbeat_at`, `missed_seconds`, `cadence_seconds` | a tick finds the previous heartbeat older than 2x the active cadence |
| `monitor.error` | `reason`, `input_path` | unreadable/invalid book, stale quote, clock problem - **fail closed, shout** |

The tick **never sizes an order and never decides to submit**. At Level 1 it may only reference an exit that is
already covered by an approved lifecycle grant, and record that a confirmed exit is due.

## 3. Trigger kinds and the cadence ladder

| `protection_type` | Trigger the tick evaluates | Cadence | Unattended action (proposed) |
|---|---|---|---|
| `synthetic_stop` | last/quote <= `stop` (long) or >= `stop` (long-put hedge leg) | 1-2 min | alert; Level 1 queues the granted exit |
| `defined_risk` | underlying stop, `option_exit_minutes_before_close`, DTE floor | 2 min | alert; loss already capped by structure |
| `time_exit` | `exit_at`, scalp `deadline`/flatten (`src/tyche/scalp.py:152`) | 2 min | alert; a missed flatten is an incident (section 6) |
| `rebalance` (PB-001 ballast) | regime/vol drift versus the frozen rotation rules | 5 min, **alert-only** | never exits; the next rebalance does |

- Cadence = the strictest type on the watch. Empty watchlist or no open lot => the tick exits `1` and burns
  nothing, which is what keeps ballast-only days cheap.
- ~195 ticks/day at 2 min over a full session; ~78 at 5 min. **While `options_enabled: false`
  (`config/tactical.yaml:3`) the 1-2 min tiers buy nothing**, so the build starts at the 5-min alert-only tier.
  Cadence is the first knob to turn down if runs cost more than expected.

## 4. What the monitor may and may not do

Levels are cumulative; only Level 0 is described as buildable now, Level 1 needs its own approval, Level 2 stays
off until options are enabled *and* a drill has passed.

| | Level 0 (alert) | Level 1 (queue) | Level 2 (submit) |
|---|---|---|---|
| Read broker state via executor captures | yes | yes | yes |
| Journal `monitor.*` events | yes | yes | yes |
| Send an urgent Telegram digest | yes | yes | yes |
| Reference / revalidate a lifecycle grant | no | yes | yes |
| Authorize a submission | no | no | yes - **not in this draft** |

Never, at any level: new entries (the act/wait gate only ever withholds entries; a defensive exit is the only
thing the monitor may make more urgent); sizing; approving, revoking or widening a level; writing config or
envelope files; touching a live account; assuming a cancel or a receipt is a fill
(L-012/L-015/L-016, `docs/lessons/LESSONS.md`). A halt blocks new buys, never an exit, so a halted account
still gets its monitor alerts - and the alert must say the account is halted.

## 5. Contention and single-writer rules

- The monitor shares one hash-chained journal with the desk runs. `journal_lock` is **nonblocking**
  (`src/tyche/journal.py:35-66`): a tick that cannot take the lock skips its tick rather than waiting, so it can
  never delay a desk run's check-and-reserve. A skipped tick is a `monitor.gap`, not a silent no-op.
- The lock proves exclusion **on one filesystem only**. It is not a distributed Drive lock, and the sandbox is
  ephemeral (see [protection-monitor.md](protection-monitor.md), "Runtime storage and cloud rollout gate"). Two
  sandboxes with two journal copies must never both run the monitor.
- `max_concurrent_runs: 1`, `max_attempts: 1`; one monitor schedule overlapping the desk card is already the
  maximum - a second monitor card is not acceptable.
- Ownership stays with the desk card: **the monitor is not an execution owner.** The 12:05 fire's "may not open,
  change or close any position" rule is not relaxed by this document; a fine-grained tick does not acquire the
  rights the midday fire was denied.
- Cross-process ownership must be demonstrated on the real schedule before arming, not inferred from a local lock.

## 6. How a missed exit becomes an incident

Today's verified path for a PB-004 exit that never reaches the broker:

1. An exit request is journaled as `order.requested` with a `submit_before` window - 900 s for a scalp exit
   (`exit_submit_window_seconds` at `src/tyche/config.py:229`, applied at `src/tyche/scalp.py:164`), 30 s tactical
   / 90 s scalp for entries.
2. At the next arm cycle, `_latest_scalp_request` + `_request_resolution` (`tactical_cli.py:426-450`) look for a
   resolving event (`order.submitted|filled|rejected|cancelled` or `gate.wait`). No resolution and an expired
   window => the lane journals **one** `protection.gap` for that `request_id`
   (`tactical_cli.py:387-392`, reason "exit request never reached the broker; re-arming with fresh quotes") and
   re-arms. `_gap_recorded` guarantees one gap per request; if the broker still shows the order live, nothing is
   journaled and nothing is re-submitted (`_live_broker_order`, `tactical_cli.py:459`).
3. The gap payload is attached to the arm result (`tactical_cli.py:403,421`) so it cannot be lost in prose.

That is a *detect-and-retry* loop, and its detection clock is the next fire. The monitor's whole value here is
shrinking that clock from hours to the cadence.

**Incident definition:** any lot whose approved exit window lapsed without a broker-visible order, or whose level
breached with no confirmed exit at EOD, or any `monitor.error` / `monitor.gap` older than one session. Each
becomes a dated write-up in [`../validation/`](../validation/README.md) recording: symbol, quantity, the level
and its basis, breach time, detection time, alert time, operator confirmation time, submission/fill time (or that
it never filled), the unprotected interval in minutes, and the fee-net P&L effect. A stop is a price estimate
before fees, not a maximum loss; the write-up must state the latency honestly rather than implying a resting
broker stop.

Non-scalp caveat the monitor must not paper over: **a tactical exit has no automatic re-arm.** The card prompt
says a human re-arms it at the next fire with a fresh quote, audit and reserve
(`scripts/deploy_two_fire_automation.py`, PROTECTION section). So on that lane a breach that nobody confirms
stays an open gap and must appear in the EOD report until closed.

## 7. Alert format and de-duplication

- One urgent digest per episode, through `scripts/telegram.py send-digest` with the renderer's `urgent: true`
  field, which puts ` - URGENT RISK ALERT` in the title (`scripts/telegram.py:192-207`). The renderer's required
  keys are `phase, timestamp, mode, stance, orders_summary, orders, account, protection, problems`; the
  `protection` lines must name the symbol, quantity, level versus current quote and the exact operator action.
  Delivery stays at-least-once (a socket timeout exits `2` as UNCONFIRMED, never a silent retry - L-004) and
  stays **outbound-only**: no inbound approval path (L-003, L-006).
- De-duplicate by transition, not by tick: alert on clear -> breach once per `(symbol, episode_id)`, close the
  episode on `monitor.clear`, treat a new breach after a clear as a new episode. A volatile day without
  de-duplication buries the operator and gets alerts ignored.
- No routine digest when nothing is open and nothing is wrong; a heartbeat nobody needs is noise (the same rule
  the midday fire already follows).
- Every EOD digest states the age of the last heartbeat and the coverage ratio (heartbeats x cadence / session
  minutes), because a schedule that never ran cannot alert about its own failure.

## 8. Acceptance test (pre-options drill)

Local, deterministic, zero broker writes first; the cloud rehearsal is a separate approval.

1. **Unit** (`tests/test_monitor_tick.py`, new): a breached stop with a fresh quote emits exactly one
   `monitor.breach`; the second tick at the same price emits nothing; returning inside the level emits
   `monitor.clear`; a stale quote or invalid book exits `2` and emits `monitor.error`, not "no breaches"; a
   naive clock and `--at` + `--record` both raise; the empty-watchlist tick emits no heartbeat.
2. **Gap**: a heartbeat older than 2x cadence emits `monitor.gap` and one urgent alert, and a lock-contended
   tick skips without writing to the chain out of order (`tyche journal-verify` green).
3. **Replay**: `--at` over a journaled day reproduces the same breach set - the guard is a pure function of its
   inputs, which is what makes an LLM-free breach decision reviewable.
4. **Synthetic-breach drill** (recorded under `../validation/`, the gate ADR 0013 imposes before options):
   a synthetic lot on a synthetic quote, timed end to end - breach -> detection -> alert delivered -> operator
   confirmation -> exit reserved (never submitted in the drill). Pass criteria: measured latency stated;
   `protection.gap` count zero for a handled episode; **zero broker writes proven** by diffing broker order
   history before and after plus a journal fingerprint before and after; no envelope, config or approval file
   touched; digest text reviewed for the exact fields above.
5. **Prompt/CI coupling**: extend `tests/test_desk_card_prompt.py` so a future edit cannot hand the guard card
   submission rights, and keep `prompt_markers()` true on the desk card. The existing guard that fails if a feed
   file stops being published (`tests/test_docs_consistency.py`) is the pattern to follow: the test must be able
   to fail on the defect it names.

Failing any of 1-4, the monitor is not deployed and options stay blocked. This draft deliberately stops short of
implementation: the operator reviews the contract first, then decides whether to build Level 0 at the 5-minute
tier.

## 9. Build order (with what is already settled)

| # | Step | State |
|---|---|---|
| 0 | Make the suite trustworthy evidence again (scalp clock bomb) | done 2026-11-20 |
| 0b | Rung 1.5: draft the bounded exit note from the open book, arm it from the desk (§0) | done 2026-11-21 - detector-independent, so it shipped first |
| 1 | `tyche monitor tick` + `monitor.*` events, `--dry-run` default | open - this document is its spec |
| 2 | Bind the tick to the existing quote path so a tick stays cheap and bounded | open; **note** `scripts/mcp_prices.py` merges *daily klines* into `data/prices.csv` and is not an intraday quote source - a 1-minute path is new work |
| 3 | Alert through `scripts/telegram.py send-digest` with tick-attributed delivery state | partly done as the 12:05 dry-run fire; per-tick attribution and delivery-failure handling open |
| 4 | Confirm the cross-process journal lock before the first scheduled tick | code exists (`journal.py:35`); demonstration on the real schedule still open |
| 5 | Alert de-duplication by transition | open (section 7) |
| 6 | Synthetic-breach drill under `../validation/` | open (section 8) |
| 7 | Heartbeat coverage in the EOD digest and last-tick age stated at every fire | open |

The decision record behind sections 3, 4 and 9 is
[docs/reviews/2026-11-20-protection-guard-plan.md](../reviews/2026-11-20-protection-guard-plan.md): cadence
option b was built, ownership stayed inside the existing card, Level 0 is the approved behaviour and Level 2 was
explicitly declined.

## 10. Out of scope for this draft

Creating or editing any schedule, card, agent pin or vault. Level 2 automatic submission. Options enablement
(needs [ADR 0012](../adr/0012-options-protection.md) *and* this one closed). Broker-native stops - unavailable on
the sim, which is the entire reason this document exists. Any live trading. Reopening the paused Forward
schedules or the inbound Telegram bridge.
