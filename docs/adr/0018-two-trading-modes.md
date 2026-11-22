# ADR 0018: Two trading modes - Ask me, or Within my bounds

- Status: Accepted (implemented 2026-11-22; card brief write pending the operator's go between fires)
- Date: 2026-11-22
- Deciders: operator ("let's simplify to two modes"), desk-head
- Related: ADR 0014 (per-strategy isolation), runbook sentinel-telegram ("Proposal approval from Telegram")

## Context

The desk had three operator modes - Manual, Auto, Pre-approve - all of them views of one file,
`data/approvals.json` (the same-day envelope). Then the Telegram approval step landed (22 Nov): during a
fire the desk previews each entry proposal and waits for `/approve N`. The card brief required BOTH a
same-day envelope AND that `/approve`, which produced a two-yes gap the operator could not reason
about: in Manual nothing submitted even after a Telegram yes, Pre-approve and Manual looked the same
from the phone, and the 15:05 ET fire (04:05 SGT) always timed out as a no while he slept. The cloud
desk also cannot write `data/approvals.json` (push-back is 403), so a Telegram yes could never become
an envelope on its own.

## Decision

There are exactly two modes, decided by one fact at the fire: does a same-day envelope exist?

- **Ask me** (no envelope; the default). During the 08:05 and 15:05 fires the desk sends each
  proposal to Telegram with an `order` block (symbol, side, qty, limit, exit floor, setup hash when
  bound) and waits for `/approve N`. That approve is the whole yes: `wait-for-reply` writes it to
  `<file>.approved.json`, `tyche approve-telegram <file>` journals it as `approval.telegram`, and
  `telegram_batch()` turns today's journaled approvals into an `ApprovalBatch` of exactly those
  orders. The unchanged `authorize_order` gate, the exact-order audit and `reserve` then run as before.
  Nothing is written to `data/approvals.json`.
- **Within my bounds** (same-day envelope). The operator arms bounds from the desk - re-arm last
  bounds in one click, define fresh ones, or arm the drafted exit note. The desk submits inside them
  with no Telegram ask. For fires while the operator sleeps.

`resolve_batch()` is the single chooser: a valid same-day envelope wins, otherwise today's Telegram
approvals, otherwise nothing is authorized. The kill-switch overrides both. The run may read the
envelope and never author it, so only the operator can change the mode.

## Consequences

- One yes per entry, never two. The Telegram preview now states what the approve authorizes.
- Usage (`envelope_usage`, `envelope_totals`) counts both authorization kinds, so a day that
  switches mode midway cannot exceed either budget.
- An approved proposal without an `order` block authorizes nothing and is reported as such.
- The brief's ORDERS and PROPOSAL APPROVAL paragraphs name the two modes; that write happens on the
  permanent card between fires with the operator's explicit go, and `tests/test_desk_card_prompt.py`
  pins the wording.
