MCP anomaly log — scalp-1652 (2026-11-24)

1. sim_trade_order_list is UNREGISTERED in this MCP session (consistent across 8 prior fires).
   Orders were captured via sim_trade_history_order_list, UNFILTERED, single page,
   pagination.has_more=false explicitly returned (next_key "0"). Full account history returned.

2. Timestamp epoch offset anomaly persists: broker create_time/update_time and quote
   data_time / kline time_key carry ~+31.5M s (year-2026 epoch) values relative to wall
   clock expectations used by the kernel staleness gates. Captured verbatim; NOT adjusted.
   Expected consequence: <60s quote gate unsatisfiable -> entries wait "quote stale".

3. tyche-scl incident orders (Nov-19): all 7 already journaled (scalp-1442). SMH 3118500
   (status 5) and VNQ 3116597 (status 5) CLOSED per operator ruling 2026-11-24 — no further
   journaling. No new tyche-scl orders in this history. Fills-first = no-op.
