---
name: lifecycle-contract
description: Use when a run touches the stock/ETF lifecycle lane - restoring journal state, building or checking a LifecyclePlan, running capture or tick, or revalidating a held contract. Trigger before any lifecycle command and whenever the run brief names a plan hash.
role: shared
version: 1
---

# Lifecycle contract

How the pinned stock/ETF lane runs; permissions stay in your prompt.

## Engine
Use the release commit the brief names for BOTH lanes. A clean HEAD containing it is LC_ROOT; otherwise one isolated clone at that commit, never a reset. Pass the same absolute LC_ROOT and config root to every command. Option holdings need verified metadata in contracts.json or capture refuses (src/tyche/broker/mcp_json.py).

## State
State lives under the Drive raw root in lifecycle/; the journal lineage is the path the brief gives, later descendants first. Missing state is a reconciliation task, not an empty ledger: never initialize a journal or ledger outside an operator-run bootstrap, never create adoption grants from holdings alone, and keep unowned holdings visible as gaps. Drive visibility, mkdir, flock and fsync are not distributed locks.

## Contract shape (LifecyclePlan in src/tyche/lifecycle.py)
plan_id, revision, symbol, strategy_id, rules_hash, thesis, invalidation_rules, mode (new_entry, or adopt_position with the exact reconciled quantity), entry_low, entry_high, stop and take_profit with a basis each, entry_expires_at, exit_deadline, review_max_age_minutes, quote_max_age_seconds, max_slippage_bps. A missing target or deadline is a gap to report, never a default to invent. Any change is a new revision and hash with a full `tyche lifecycle preview`, an independent audit and explicit operator approval. Deadlines fall by the last scheduled regular-session check, early closes included.

## Revalidation (Review in lifecycle.py)
Every scheduled check reviews each held contract and open proposal: plan_hash, real reviewed_at and valid_until inside review_max_age_minutes, verdict valid, uncertain or invalidated, reason, cited evidence, acknowledged event ids. No news coverage means news_feed_ok=false, never a fabricated review. A material event since plan creation needs a post-event review; one due within 30 minutes blocks entries. Stale or uncertain research blocks NEW entries only; approved stop, target and deadline checks still run. Cited invalidation latches the authorized exit and blocks re-entry; replacements stay unapproved. Protection work comes before new exposure; an earlier EOD marker never suppresses it.

## Tick
`tyche lifecycle tick` without --record is inspection: report per-symbol coverage, missing plan or grant, stale review, pending orders, unsupported exposure and would-exit triggers. Synthetic stops are not broker orders.
