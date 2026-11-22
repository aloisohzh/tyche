---
name: midday-watch
description: Use when the scheduled card fires at 12:05 ET, the midday protection fire. Trigger as soon as the calendar gate reports the midday phase, before delegating anything.
role: coordinator
version: 1
---

# Midday watch

The 12:05 fire checks and shouts. That it submits nothing is a rule in your prompt and the card; this is the checklist for doing the check.

## 1. Fresh reads
Delegate the executor for reads only: positions, every order-history page until has_more is false, quotes and books for every held symbol, saved as raw MCP JSON in the private run directory with the oldest read time recorded.

## 2. Evaluate, dry run
`tyche lifecycle capture` into the run directory, then `tyche lifecycle tick`, `tyche tactical tick` and, when config/scalp.yaml has the lane enabled, `tyche tactical scalp` - all WITHOUT --record. These evaluate; they latch nothing and reserve nothing (src/tyche/lifecycle_cli.py, src/tyche/tactical_cli.py).

## 3. Report every lot
For each open position, lot and lifecycle grant: whether a live exit request exists, its submit_before, stop, target and deadline versus the current quote, and the outcome of the most recent exit request in the journal.

## 4. One gap per request
When an approved exit has no live request and its window has passed, journal exactly one protection.gap for that request_id with `tyche record-order protection.gap --data '{...}'`, resolution gate.wait or expired, never invented. If the broker still shows that order live, journal nothing and say so. Check the journal for an existing gap first; a second gap for the same request_id is a defect.

## 5. Shout or stay quiet
A breached level or an uncovered lot sends the urgent digest first, through the `sentinel-digest` skill with urgent set: the Protection section names symbol, quantity, level versus quote and the exact operator action. Then stop; the close fire and the operator decide the exit. With nothing open and nothing wrong, record the reconciliation in the journal only and send no message.

## Never at this fire
Reserve, submit, cancel, modify, approve, revoke, write or edit an envelope or config, run `tyche lifecycle approve`, `tyche lifecycle revoke`, `tyche lifecycle reserve`, `tyche lifecycle execute-exit`, `tyche tactical reserve` or `tyche tactical scalp` with --record; propose an entry, plan or candidate; run discovery; delegate the researcher or auditor; revalidate a thesis; re-arm an exit; widen a level; or send the example template as a live report.
