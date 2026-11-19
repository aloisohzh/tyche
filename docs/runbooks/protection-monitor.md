# Runbook: hourly paper trade lifecycles

Status (2026-11-19): **cloud workflow deployed in OBSERVE ONLY; orders NOT armed.**
All four cloud roles and the existing hourly schedule now include the stock/ETF
lifecycle workflow, pinned to release `1e902cf57c26599b69c49496e81b7a493ae5bc49`.
Compiled member pins: researcher 10, auditor 4, executor 10. Trading permissions,
models, credentials, mounts, hourly cadence and concurrency/attempt limits are
unchanged. Existing tactical rollout holds remain in force; no faster schedule
was activated. No production lifecycle approval or broker order was created.

Cloud rehearsal passed 249 tests. A second session verified the same Drive probe
and existing lock directory on `fuse.rclone`; this proves sequential visibility,
NOT distributed locking. Single-writer ownership across both lanes, alignment
with the newer portfolio risk configuration, and exact adoption approvals remain
activation gates. Current observations do not record production latches or grant
order authorization.

The final deployed-coordinator smoke test passed all 69 lifecycle tests using
isolated synthetic state. The researcher checked the review schema and the
independent auditor retained the execution hold. No position-specific approvals
were produced; synthetic test grants are not operator authorization.

Local follow-up (2026-11-19): lifecycle entries now enforce the current total
ballast allocation and per-name strategy/universe caps, including pending and
reserved exposure; protective sells remain possible above those caps. Rule
hashing normalizes CRLF to LF so identical Windows/cloud checkouts agree. These
local changes passed 329 tests but are **not committed or deployed**. Existing
contracts/grants were not rewritten; older rules still require renewed review.

The existing private Tyche Desk has a legacy Functions/Storage allocation. The
supported Sites interface cannot convert it in place to `function_backend`, and
the legacy anonymous adapter cannot enforce the required private database access.
No database, migration, public policy or replacement site was created. A new
database is not required: the existing journal/state can serve one verified durable
execution owner. Cross-session ownership is still an activation check, not something
local file locks prove. The SPY/EFA adoption drafts remain unapproved:
their reviews expired, EFA was uncertain, their rules hash belongs to the older
release, and VNQ status 5 still requires manual classification. Cash release is
not proof that an order is terminal. Fresh evidence and revised audited contracts
are required before operator approval.

This supersedes the minute-level monitor proposal in [ADR 0013](../adr/0013-protection-monitor.md)
for the initial long-stock/ETF implementation only. It does not enable options.

## Operator decisions

- Check once per hour using the existing `tyche-hourly` schedule; do not add a
  parallel five-minute or one-minute schedule. Retain one concurrent run and
  one attempt. Current window: 08:05–17:05 ET on the configured challenge dates,
  ending 2026-11-28 UTC. It is not an around-the-clock monitor.
- Approve a complete lifecycle once: account, symbol, quantity, entry bounds,
  stop and its basis, profit target and its basis, entry expiry, holding deadline,
  thesis-invalidation conditions, and allowed limit-price deviation. Matching
  paper entries and exits then need no additional confirmation. Changes require
  a new preview, auditor review, and explicit operator approval.
- Live orders remain outside this implementation. Cancel/modify actions still
  require per-action confirmation; never assume a cancel is a fill or a terminal
  state. No shorting, option legs, scaling in, or automatic re-entry.

## Lifecycle commands

`tyche lifecycle --help` and `tyche lifecycle schema` describe the exact CLI and
JSON contracts. Core files: `src/tyche/lifecycle.py`, `src/tyche/lifecycle_cli.py`.
All submissions are executor-owned Moomoo MCP. The local `execute-exit` command is
a read-only check of one approved exit; it cannot place, cancel or modify orders.

| Command | Effect |
|---|---|
| `preview --book BOOK --plan-id ID` | Whole contract, immutable hash, planned risk/reward and operational limitations; no approval. |
| `approve --book BOOK --market MARKET --state STATE --plan-id ID --hash HASH --operator-ref REF --auditor-ref REF --yes` | Records explicit operator approval of that exact preview; never run unattended or invent references. |
| `revoke --state STATE --hash HASH --yes` | Disables matching grants; does not cancel existing orders. |
| `capture --dir RAW --account-id ID --observed-at TIME --prior-close-nav NAV --high-water-nav NAV --regime REGIME --conviction TIER --out MARKET` | Normalizes successful MCP reads and retains exchange quote timestamps. TIME is the oldest broker-read timestamp, not the time files are rewritten. NAV references and regime/conviction must come from reconciled records and the current deterministic kernel. |
| `tick --book BOOK --market MARKET --state STATE --record` | Reconciles fills, records hourly heartbeat and latches exits; no submission. Omit `--record` for a dry run. |
| `tick ... --at ISO_TIMESTAMP` | Historical replay only; cannot be combined with `--record`. |
| `reserve --book BOOK --market MARKET --state STATE --plan-id ID --hash HASH --journal JOURNAL` | Rechecks live-clock gates, durably reserves one exact order, then appends `order.requested`. Only successful output authorizes the executor's one attempt. |
| `receipt --state STATE --request-id REQUEST --order-id ORDER` | Attaches the returned broker ID; does not mark a fill. |
| `execute-exit --book BOOK --market MARKET --state STATE --plan-id ID --hash HASH --journal JOURNAL` | Read-only check of one exact approved exit against captured MCP evidence; never writes state, reserves or submits. |

Pass `--config-root` when not running from the repository root. The legacy
`tyche execute` path is disabled for broker accounts; `--yes` cannot bypass the
lifecycle gate. Demo/test identifiers retain the test-only legacy behavior.
Old same-day envelopes are not a substitute for a complete lifecycle grant.

## Contract and review semantics

A plan names the playbook and current rules hash, a specific thesis and explicit
invalidation rules. Each long-stock/ETF plan requires
`stop < entry_low <= entry_high < take_profit`, positive quantity, an entry expiry,
and a holding deadline on a trading day before the session closes. For a position
already held, use `mode: adopt_position` with its exact reconciled quantity; it
cannot buy. Do not invent a missing target/deadline from a generic sizing stop.

The ledger keeps a copy of every approved contract. Deleting a shortlist entry,
replacing its proposal, or losing/corrupting the research book cannot erase an
approved held-position exit. A corrupted ledger or failed broker read, however,
fails closed and requires operator attention. A revoked grant no longer protects
its position; review replacement grants promptly and report that coverage gap.

Before an entry, a review for the exact plan hash must say `valid`, include source
evidence, and be no older than 60 minutes with an unexpired validity period.
News coverage must also be healthy and current. A relevant material event since
plan creation requires a review after that event and explicit acknowledgement
of its ID; a known material event in the next 30 minutes blocks entry.
A confirmed invalidation permanently latches that lifecycle, including before
entry. A later positive review cannot silently rearm it.

An `uncertain` or missing/stale review blocks new entries but does not itself
liquidate a position. A fresh, evidence-backed `invalidated` review triggers the
approved invalidation exit. Stop, target and holding-deadline exits do not depend
on research staying fresh. Existing position protection is checked before new
exposure in the executor workflow. Reviews are research judgments, not an
independent automated proof that a thesis is correct.

For `basis: last`, only a fresh spot quote can trigger a price exit. For
`basis: daily_close`, supply the latest completed regular-session close and its
actual close timestamp; an intraday touch is not a close breach. After-hours
close breaches latch for the next allowed session. A missing quote can prevent
submission without erasing a time/invalidation latch. Stale daily bars are not
substitutes for the latest completed bar.

## Broker capture and one-shot submission

Keep raw `accounts.json`, `cash.json`, `positions.json`, `quotes.json`, and
`orders.json` from successful MCP reads. For paginated history, use consecutive
`orders-1.json`, `orders-2.json`, etc., starting at the first unfiltered page;
never mix this with `orders.json`. Preserve `pagination.has_more` on every page.
The last page must explicitly be false. Filename checks cannot prove that an
executor fetched the first page; actual capture provenance remains mandatory.
Optional `closes.json` maps symbols to `{close, close_at}` from completed bars.
Do not fabricate timestamps, daily NAV references, or feed-completeness flags.

1. Fetch fresh verified US paper account state, quotes and all order-history
   pages. Reconcile the account and refresh deterministic kernel inputs.
2. Run `tick --record`, surface every coverage gap and blocked protection, and
   revalidate relevant market events. Missing research must not stop step 1.
3. For an authorized decision, run `reserve` with its exact ID and hash. It
   checks paper allowlisting, RTH/session directives, ownership, quote/broker
   freshness, pending orders, available shares, current risk limits, and journal
   integrity. Entry checks also retain low-conviction act/wait, sleeve caps,
   pending exposure and daily/phase budgets. Event-caution sessions halve the
   per-trade risk and per-order notional ceilings. The phase count is deliberately
   conservative across that day's entire phase, not reset by each invocation.
4. Only exit code 0 plus `authorized: true` permits ONE MCP limit-order attempt
   with the exact symbol, side, quantity and limit. Use `request_id` as broker
   text. Verify the account matches the grant and submit strictly before the
   returned Unix `submit_before` timestamp. This window is at most 60 seconds,
   shortened by data, entry/review expiry, and the session close. Never replay
   the output or wait for a permission popup: the current input tool executes
   immediately. If the window expires, stop and request operator reconciliation.
5. Record the receipt, journal `order.submitted`, then refetch broker orders and
   positions and run another recorded tick. Submission/receipt is not a fill.
   Confirm cumulative quantities against the broker, including partial fills.
6. Any timeout, unknown outcome, missing receipt or nonterminal order stays
   blocked. Never delete reservations to retry. Only fully-filled status 4 is
   currently verified; canceled/rejected orders also require manual review.
   There is no automatic reservation-release or cancel/retry command.

A ledger write succeeds before authorization is emitted. If the subsequent
journal append fails, the reservation remains blocked and no permission is
emitted. Same-symbol pending entry orders can prevent an exit: alert the operator
for a separately confirmed cancellation rather than submitting opposing orders.
Daily entry budgets preserve capacity for protective sells, but the competition
order ceiling and broker/account safety checks still apply to exits.

## Exit checks and submission

`execute-exit` is a read-only check against a captured `--market` file. It verifies
the journal chain, the exact approval hash, account allowlisting, journal/state
consistency and broker NAV reconciliation, then evaluates the contract and prints
the decision. It never fetches broker data, writes lifecycle state, reserves or
submits. Refresh `--market` with `tyche lifecycle capture` from fresh MCP reads
before relying on the result.

Submission belongs to the single executor:

1. Run `tick --record` and `reserve` with the exact plan ID and hash.
2. Only exit code 0 plus `authorized: true` permits one MCP limit order with the
   exact symbol, side, quantity and limit.
3. Use `request_id` as broker text, submit once before `submit_before`, then
   record the receipt and reconcile broker orders and positions.

A timeout, unknown outcome or missing receipt blocks retry. Receipt is not fill;
only matching cumulative fills and holdings establish completion. A halt still
allows approved de-risking sells. Missing research does not disable an approved
stop, target or deadline. There is no direct broker HTTP token, no second
credential and no local order-writing path.

Local locks prove exclusion only for processes using the same filesystem. Before
arming, route every write through the one durable owner and verify persistence
across its actual scheduled runs. Do not run this beside an independently writing
MCP executor or a second copied journal. No new database or service is needed if
that single-owner arrangement is verified; this implementation does not claim
Drive replicas form a distributed lock.

## Runtime storage and cloud rollout gate

Proposed private state directory: `/data/drive/tyche-raw/lifecycle/`, containing
`book.json`, `state.json`, and raw capture/run files; use the existing persistent
hash-chained journal. Do not commit private captures or operator evidence.
The current directory lock and atomic file replacement protect ONE filesystem
state owner; they are NOT a demonstrated distributed lock across Drive replicas
or independent sandbox copies. Verify storage visibility and atomicity before
arming; if that cannot be established, use a single durable state owner and keep
automatic submissions disabled. Do not copy the ledger into concurrent sessions.

Deployment is not complete until all of these are verified:

- Publish the tested code to the cloud-mounted repository through an authorized
  commit/push. Verify the exact revision and all lifecycle commands in the cloud.
- Update desk, researcher, auditor and executor prompts together; re-pin compiled
  member versions. Preserve vaults, tools, mounts, environment, calendar checks,
  YouTube handling, Telegram delivery, and cancel/modify confirmation policies.
- Update the existing hourly schedule instruction, not its cadence. Remove the
  old envelope/per-order submission bypass. Permit intraday thesis revalidation
  without requiring a fresh broad discovery scan. Unattended runs may never
  approve, revoke or alter approved contracts.
- On each trading-day tick, monitor held positions even when entries are
  prohibited. After-hours runs may latch close breaches and report protection;
  they may not submit. A previous EOD report must not suppress new protection
  evidence. Respect holidays and early closes.
- Dry-run with isolated synthetic state: stop, target, deadline, invalidation,
  missing research, pending/partial order, expired permission, and a failed
  state/journal write. Confirm zero broker writes and no unintended approvals.
- Reconcile current holdings, produce full adoption previews, obtain auditor
  review and explicit operator approval. Prior SPY/EFA research close levels
  alone are not complete approved contracts; VNQ's last observed resting entry
  requires reconciliation. Do not assume old positions are armed.
- Verify durable state across runs, monitor gaps, account-specific grants and
  the actual hourly schedule before reporting automation active.

## Risk and limitations

Hourly synthetic protection is not a broker-native stop or a guaranteed fill.
A breach just after a check can wait roughly an hour plus processing/fill time;
missed runs, trading halts, overnight gaps and limit-order non-fills can extend
that indefinitely. Planned stop loss is a price-based estimate before fees, not
a maximum loss. Daily-close triggers wait for the next permitted session.
Choose deadlines before the final scheduled RTH check and within the schedule's
active window; the system cannot guarantee liquidation at an arbitrary deadline.

A last tick more than 75 minutes ago is reported as a coverage gap (including
overnight gaps); this is not a market-aware uptime metric or an independent
watchdog. A schedule that never runs cannot alert about its own failure.
The MCP route relies on executor compliance; there is no second local write path.
No claim is made of tamper-proof authorization, automatic coverage for all
strategies, options protection, or deployed exits.
