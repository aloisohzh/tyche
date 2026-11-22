---
name: lifecycle-review
description: Use when the coordinator delegates a stock/ETF lifecycle plan, adoption or replacement for review, and when a held contract's exit is being revalidated. Trigger on every delegation that names a plan hash.
role: auditor
version: 1
---

# Lifecycle review

You judge the lifecycle contract from files. Times and hashes come from the coordinator's brief, never from your own clock, and your verdict is evidence, not operator consent.

## Contract (LifecyclePlan in src/tyche/lifecycle.py)
Check the exact plan hash, account binding and strategy_id. mode adopt_position needs the exact reconciled quantity from the capture, not an old watchlist level. Levels order bullish: stop below entry_low, entry_low at most entry_high, entry_high below take_profit; each trigger names its basis (last or daily_close). entry_expires_at and exit_deadline fall by a scheduled regular-session check with processing margin inside the card's window, early closes included. invalidation_rules are explicit. max_slippage_bps, review_max_age_minutes and quote_max_age_seconds are the plan's own values; compare them with the pinned release's config and record any difference as an activation blocker, never as equivalent policy.

## Evidence
Fresh exact-hash Review inside review_max_age_minutes with real reviewed_at and valid_until, cited sources with timestamps, news_feed_ok true from an actual check, acknowledged event ids for every material MarketEvent since plan creation. Pending orders, sellable quantity, attribution of each lot to one lane. Duplicate ownership between lifecycle and tactical, or unverified shared state, is a blocker. Fees and the estimated stop loss and reward use the configured fee model (docs/risk-card.md); modeled fees are not charged fees.

## Replacements
A replacement or revision needs its own approval and cannot delete or weaken existing protection. Unattended runs may not approve, revoke or amend contracts, and no run may invent an operator or auditor reference.

## Verdict
Write to the supplied path in the shape of templates/prompts/pre-trade-critique.md: APPROVE, APPROVE-WITH-CHANGES or REJECT per plan, each reason beside its rule id, plus UNVERIFIABLE FROM FILES when evidence is absent or stale, saying what would make it verifiable. APPROVE-WITH-CHANGES is not executable approval. Hourly synthetic stops are not broker stops and a submitted exit is not a fill; say so in the risk section.
