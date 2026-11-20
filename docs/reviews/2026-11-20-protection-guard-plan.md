# Protection guard: plan and decisions taken (2026-11-20)

Status: **partly decided and implemented; the deterministic guard is still open.** On 2026-11-20 the
operator took decisions 1 and 3 and overrode decision 2: a 12:05 ET watch-and-shout fire now runs on
both desk cards at Level 0, inside the existing execution owner rather than in a separate card. See
"Decisions taken" below. [ADR 0013](../adr/0013-protection-monitor.md) stays `Proposed`: no `monitor`
module, schedule, cadence ladder or drill exists yet, and Level 2 (automatic exit submission) stays
off. Nothing in this work placed an order, started a cloud run or sent a Telegram message. The
scalp-test defect named below is fixed and the two stale lifecycle-runbook lines are corrected.

## Decisions taken (2026-11-20)

- **Cadence: option b.** `desk_cron()` returns `5 8,12,15 <trading days> <month> *`, so each card now
  fires 08:05, 12:05 and 15:05 ET. Verified on the live cards: Nov
  `5 8,12,15 19-20,23-25,27,30 11 *`, Dec `5 8,12,15 1-4,7-11,14-18,21-24,28-31 12 *`, both
  `America/New_York`, both `status: active`.
- **Ownership: implemented inside the existing owner card, not a separate card** (the operator chose
  the smaller change; `scripts/deploy_two_fire_automation.py` stays the only deployment builder and the
  "never run two writers" rule needs no new schedule family). The midday fire is therefore the one
  place where the card instruction must forbid every write, and it does.
- **Behavior: Level 0.** Fresh executor-owned reads, `lifecycle capture`, then `lifecycle tick`,
  `tactical tick` and `tactical scalp` with `--record` omitted (dry run), a `protection.gap` journal
  event when an approved exit has no live request, and an urgent digest when a level is breached or a
  lot is uncovered. Explicitly never: reserve, submit, cancel, modify, approve, revoke, envelope or
  config writes, `lifecycle approve/revoke/reserve/execute-exit`, `tactical reserve`,
  `tactical scalp --record`, new proposals, broad discovery, researcher/auditor delegation, re-arming,
  widening a level, or a routine digest with nothing open. Level 1 and Level 2 were not built.
- **Evidence**: prompt grew 9403 -> 11757 characters on each card; all ten markers in
  `prompt_markers()` are true including the new `has_midday_watch`; each live instruction was
  re-fetched and compared byte-for-byte with the repo-generated text (equal); agent pin (v28),
  environment, vault, GitHub mount `/data/workspace/tyche`, memory store, schedule type, timezone and
  card names/status unchanged; `metadata.profile` moved from `two-fire` to `three-fire`, which is the
  only metadata edit. Suite: 429 passed before, 432 after adding `tests/test_desk_card_prompt.py`.
- **First scheduled midday fire**: `2026-11-20T17:05:00Z` (12:05 ET) on the November card, per the
  scheduler's own `upcoming_runs_at`. Whether that run behaves as intended is unverified until it
  runs; the close fire at `2026-11-20T20:05:00Z` follows it.
- **Honest cost of the gap**: detection is still not protection. A breach just after 08:05 ET waits
  about 4 hours; just after 15:05 ET it waits until the next morning. Adding the real deterministic
  guard (decision: build later) is what shortens this, not more LLM runs.

## What is actually true today

- The only active execution owners are the two Cloud Automation cards: `dep_00vzb9h4ezawwl4thnva`
  (Nov) and `dep_00vzd8d5rdfr4w0denqh` (Dec). Verified by
  `list_deployments` - it returned exactly these two, both `active`. When this was written each fired
  08:05 and 15:05 ET; the 12:05 ET midday check described above was added the same day.
- All eight Forward schedules are `paused`, including `tyche-hourly` and `tyche-midday-monitor`.
  Verified by `scripts/forward.py get /schedules`.
- The guard code exists and is not the missing piece: `tyche lifecycle tick` and its read-only
  `execute-exit` (`src/tyche/lifecycle_cli.py`, `monitoring_book` at line 57), the tactical monitor
  with `monitor_interval_seconds: 30` (`src/tyche/tactical_cli.py:113`, `config/tactical.yaml:14`),
  heartbeat-gap detection (`src/tyche/tactical.py:153-157`) and the 75-minute coverage-gap string
  (`src/tyche/lifecycle.py:603`).
- But no live instruction ran any of it between the two fires when this was written: searching the
  card prompt for `lifecycle tick`, `tactical monitor` or `monitor tick` returned zero matches. So
  protection was two checks a day, and nothing at all between 15:05 ET and 08:05 ET next day. The
  MIDDAY section now calls `lifecycle tick`, `tactical tick` and `tactical scalp` in dry-run form at
  12:05 ET; the overnight gap and the intraday cadence ladder are still open.
- The ADR's own `tyche monitor tick` (heartbeat / breach / clear events) is still unimplemented; the
  pieces above are the lifecycle and tactical lanes, which a run must be told to invoke.

## Doc and test drift found while checking (all three fixed the same day)

- [../runbooks/protection-monitor.md](../runbooks/protection-monitor.md) line 5 pinned the cloud
  workflow to release `1e902cf57c...`. That commit is **not an ancestor of `main`** and no branch
  contains it, and `scripts/deploy_hourly_workflow.py:97` says "Do not use old lifecycle-hourly-release
  1e902cf". The pin is stale and points at a deprecated build.
  Fixed: the status block now records that the lifecycle workflow runs inside the two desk cards,
  that those cards mount `https://github.com/aloisohzh/tyche` with no release pin (verified from the
  deployment resources: only `mount_path` and `url`), and that a run must confirm the revision it
  actually checked out before relying on a code path.
- The same runbook said the 2026-11-19 follow-up (strategy, asset and sleeve caps, CRLF rule
  hashing) "is not committed or deployed". That was wrong: the caps are on `main`
  (`src/tyche/lifecycle.py:551-564`, with event caution and sleeve caps to line 577) and the CRLF
  normalization is `src/tyche/pipeline.py:52`, both introduced by commit `965c06b` on 2026-11-19.
  Fixed in the same status block, including the stale `329 tests` count.
- `tests/test_scalp.py::test_state_rebuilds_lots_cooldown_and_today_round_trips` **failed**. It is a
  clock bomb, not a broker bug: the file hardcodes `NOW = 2026-11-19 15:30 UTC` (line 24) while
  `append_event` stamps the real wall clock, so the ET-date filter in `src/tyche/scalp.py:114-117`
  drops the request and `last_request` comes back empty. It had been failing every day since 19 Nov.
  Fixed by replacing the journal round trip with inline explicitly-stamped events, the same shape the
  sibling replay tests already use. `append_event` has no timestamp parameter, so no journal write can
  be dated deterministically; the replay is a pure function of its input list, so nothing was lost.
  Mutation-checked: with `today` shifted to 20 Nov the rebuild returns no cooldown, so the assertion
  still bites.
- Suite green after the fix: 429 passed at the moment of correction, then 432 with
  `tests/test_desk_card_prompt.py`, which pins the three fires and the midday limits so an edit cannot
  quietly hand the 12:05 check submission rights.

## Three decisions (all taken 2026-11-20; see the record above)

### 1. Cadence. DECIDED: option b, built as the 12:05 ET midday fire

| Option | Blind window after a breach | Cloud cost | Notes |
|---|---|---|---|
| a. keep two fires | up to ~6h intraday, ~17h overnight | none | current state, honestly labelled |
| b. add a midday fire (12:05 ET) | ~4h | 1 extra LLM run/day | smallest real improvement; no new schedule family, no new writer |
| c. dedicated deterministic guard every 5 min | ~5 min | ~78 thin runs/session day | ADR 0013's alert-only tier; 1-2 min tiers are irrelevant while `options_enabled: false` |

Recommendation: **b now, then c** as the real build. Do not start at 1-2 min; nothing on the book needs
that speed yet, and the cost is ~195 runs a day.

### 2. Where it runs. DECIDED: inside the existing desk card, not a new one

Cloud card is the only option consistent with unattended operation - the operator PC is not always on,
which is exactly why the inbound listener was stopped (`docs/lessons/LESSONS.md` L-006). A local
runner is cheaper and can tick at 30s, but a switched-off PC is a silent protection gap, and the
competition requires automation that survives it.

Recommendation: **cloud, as a separate card, never an execution owner**, `max_concurrent_runs: 1`,
`max_attempts: 1`, calendar-gated so holidays and weekends cost nothing, and skipped when the
watchlist is empty. The two-fire card keeps sole execution ownership and its "never run two writers"
rule stays intact.

### 3. What it may do unattended. DECIDED: Level 0 built, Level 2 stays off

- Level 0: journal a heartbeat, and on breach send one urgent Telegram alert. No orders, no intent.
- Level 1: additionally queue a defensive exit intent that a human confirms in the console.
- Level 2: submit an approved exit automatically under an existing lifecycle grant.

Recommendation: **ship Level 0, then Level 1. Keep Level 2 off** until options are enabled and a
synthetic-breach drill has passed. This matches the standing rule that an order needs a preview and an
explicit confirmation, and that paper submission still needs an approved exact grant.

## Build order (step 0 done 2026-11-20; step 3 taken in a smaller form; the rest still open)

0. Done. Fix the scalp test's clock dependence so the suite is trustworthy evidence again.
1. Implement `tyche monitor tick` per ADR 0013: watchlist plus fresh quote JSON in,
   `monitor.heartbeat` / `monitor.breach` / `monitor.clear` out, no broker access, `--dry-run` default,
   unit-tested. This is the piece that removes the LLM from the breach decision.
2. Wire the quote fetch to the existing fast path (`scripts/mcp_prices.py`, one kline call per symbol)
   so a tick stays cheap and bounded.
3. Partly taken 2026-11-20: the midday fire's instruction runs the dry-run ticks and demands the
   urgent digest through `scripts/telegram.py send-digest`, inside the existing desk card instead of a
   new guard card. A dedicated guard card, the tick-attributed delivery state and delivery-failure
   handling remain open.
4. Confirm the cross-process journal lock before the first scheduled tick - the guard appends to the
   same hash chain as desk runs, so this is a prerequisite, not a follow-up (ADR 0005, ADR 0013).
5. Alert de-duplication by transition: alert on clear-to-breach once per symbol per episode, not every
   tick, or a volatile day buries the operator.
6. Drill, recorded under `docs/validation/`: synthetic breach end to end, measuring detection-to-alert
   and alert-to-confirmation latency, with zero broker writes proven.
7. Report heartbeat coverage in every EOD digest, and make both fires state the age of the last tick,
   because a schedule that never ran cannot alert about its own failure.

## Risks the operator is accepting

Protection stays synthetic: detection, alert, queued intent, human confirmation. It is not a resting
broker stop and the honest latency must appear in every drill report. A 5-minute guard on a volatile
day can still alert repeatedly if transition de-duplication is skipped. Cloud spend rises with each
tick, so cadence is the first knob to turn down if runs cost more than expected. None of this enables
options; that still waits on ADR 0012 and 0013 both closing.

## Out of scope

Options trading. Broker-native stops. Reopening the inbound Telegram bridge or the paused Forward
schedules. Any change to the two-fire cards' trading gates, envelopes, caps or approval rules.
