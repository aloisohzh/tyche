---
name: paper-submit-protocol
description: Use before any broker write on a tyche paper run - entry, exit, cancel, modify or reconciliation - and whenever a submit timed out or came back with an uncertain status. Trigger on every approved order the desk is about to act on.
role: executor
version: 1
---

# Paper submit protocol

Envelopes, audits and arms are permissions you check, never grant. Read numbers from `config/tactical.yaml`, the envelope and this run's capture output.

## 1. Capture and normalize
Write fresh broker reads into the run directory as `accounts.json`, `cash.json`, `positions.json` (plus quotes) in the snapshot file contract of docs/agent-engineering.md. Then `tyche tactical capture --dir <run>` or `tyche lifecycle capture`, and the lane's `tyche tactical schema` / `tyche tactical tick` or `tyche lifecycle tick`. Take caps, `submit_before` and `pipeline.action` from that output.

## 2. Reserve the exact request
`tyche lifecycle reserve` or `tyche tactical reserve` for the one request. Exit 0 with `authorized=true` is necessary, never sufficient: submit only the order matching the audited, reserved `request_id`. Journal `tyche record-order order.requested --data '{...}'`.

## 3. Honor the act/wait gate
`pipeline.action == wait` means no submit on either path. `tyche execute` withholds it; on the MCP path journal `tyche record-order gate.wait --data '{...}'` and move on. The gate withholds only new non-defensive entries; sells and defensive entries act.

## 4. Submit one order, verbatim, in the window
Submit with `sim_trade_input_order` only while `now < submit_before`. It is always_allow: the call executes at once, no popup, so a second call is a second order. Cancel and modify are always_ask and need their own per-action operator approval; an envelope never approves them. Journal `tyche record-order order.submitted --data '{...}'`, reconcile fills from `sim_trade_history_order_list`, journal `order.filled` or `order.rejected`, and let the core reconcile cash (`tyche.fees.reconcile_cash`).

## 5. An uncertain outcome blocks retry
On a timeout, transport error or unclear status, read `sim_trade_history_order_list` before any further write; if the broker shows the order, submit nothing and journal what you found. Status 4 and status 5 are terminal for that request_id: journal `order.rejected` with the broker reason and report the lot as unprotected.

## 6. Exactly one gap per request_id
When an approved exit cannot be armed, journal one `protection.gap` for that request_id via `tyche events add`, resolution `gate.wait` or `expired`, never invented. Before re-arming, check journal and broker history; if still live, journal nothing.

## 7. Hand back evidence
Return paths and hashes for capture, plan, reserve, receipt and rows.
