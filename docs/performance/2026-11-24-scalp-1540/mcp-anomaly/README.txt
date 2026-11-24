Anomalies recorded 2026-11-24T15:45:39Z (scalp-1540 fire, acct ***598, US margin paper):
1) sim_trade_order_list (today-orders live poll) remains UNREGISTERED in the MCP toolset for the 5th
   consecutive fire. Reconciliation relied solely on fully-paginated sim_trade_history_order_list
   (has_more=false explicitly, next_key "0"), per brief. Impact: no same-day-only cross-check available.
2) quote_order_book at default depth returned gateway-truncated payloads (head+tail only, mid-section
   elided) on the 15:44 batch of this fire; truncated content was NOT written. Books were re-read with
   num=5 (5 levels/exchange) and only intact responses were persisted verbatim. Note: default-depth
   Round A reads at 15:41 were complete (10-14 levels); truncation appears intermittent, likely load-
   related to the flapping account/feed service.
3) Context-compaction data loss between 15:42 and 15:44 forced one additional full recapture beyond
   the single STEP-1 allowance; the STEP-3 stale-snapshot re-run allowance covered the final re-read.
   No stale payload was used and no freshness value was fabricated; all persisted payloads are verbatim
   intact MCP responses with genuine broker timestamps.
