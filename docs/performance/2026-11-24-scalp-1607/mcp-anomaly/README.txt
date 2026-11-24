MCP feed anomalies observed during PB-004 scalp runs (documentation only, no quarantine this run 2026-11-24-scalp-1607):

1. sim_trade_order_list tool is UNREGISTERED in this session's MCP gateway.
   Workaround (per brief): orders.json built from fully-paginated
   sim_trade_history_order_list instead (has_more=false confirmed, 14 orders).

2. Windowed history queries (time_begin/time_end covering "today") return an
   EMPTY order list due to an epoch-offset bug in the backend window handling.
   Never interpret a windowed-empty result as "no orders"; use unwindowed
   paginated history instead.

3. Health-probe trio this run (cash/positions/history) all ret_code=0 at
   ~16:08Z — no feed outage, no quarantine files needed.

Run 2026-11-24-scalp-1607 notes:
- Cycle run #1 (as_of 16:14:18Z): all five symbols rejected by kernel with
  "entry quote missing/stale" — initial trio read exceeded 120s age and
  quotes/books exceeded 60s at cycle time (batching latency vs hard deadline).
- Single permitted fresh recapture done ~16:14:30Z (quotes+books+trio; bars
  NOT recaptured — 1-min resolution, deadline pressure).
- Cycle re-run (as_of 16:16:02Z): gates passed; decisions NVDA/AMD/AVGO/MU/SMH
  all "wait — no 5-bar breakout"; orders=[]; zero submits; valid all-wait
  outcome. No new tyche-scl- ids in post-run history read; fills-first no-op.
