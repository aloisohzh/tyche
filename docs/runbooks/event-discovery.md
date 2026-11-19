# Event discovery loop

Runbook for the scout-proposes / Desk-Head-pins catalyst pipeline. Extends the
static market calendar (`src/tyche/market_calendar.py`) with discovered events
without weakening any gate.

## Loop

1. **Scout (hourly pre-market research)** runs a fixed core Moomoo MCP scan -
   `news_search`, `quote_ipo_list_us`, market state, economic calendar, quotes,
   live ticker, capital-flow history and the three unusual-activity tools - then
   deep-dives at most five candidates (option chain/volatility/screen, top
   brokers, insiders, short interest, analyst consensus, financials, holders,
   corporate actions). Large payloads are persisted to files, not model context.
   It looks for catalysts over the next 14 days affecting `config/universe.yaml` /
   `config/tactical.yaml` symbols: IPOs, index inclusions, earnings dates,
   guidance changes, halts, macro surprises.
   It skips anything already pinned and writes up to five candidates into an
   "Event discovery proposals" section of `reports/<date>-research.md`:
   date, name, kind, symbols, source, one-line materiality rationale.
   The scout never writes config - proposals are not pins.
2. **Desk Head triage** validates each proposal against the cited source or a
   second MCP payload, then pins material ones:

   ```
   tyche events add --date 2026-11-19 --name "Anthropic (ANT) Nasdaq IPO debut" \
     --kind ipo --symbol US.ANT --source "https://finance.yahoo.com/..."
   ```

   Rejections are logged with reasons (noise control: universe symbols only,
   plausible price/flow impact, no unverified rumors).
3. **Gate consumes automatically.** `config/events.yaml` merges into
   `events_on()`; any event on a date makes it an event day, so opening/closing
   drives halve `max_orders` and lifecycle `decide()` halves risk-per-trade and
   max-order-notional. Dashboard calendar chips render the new kinds
   (ipo=violet, index=green) with no extra wiring.
4. **Persistence.** `config/events.yaml` rides the sanitized git persist, so
   pins reach every cloud run and the operator's local checkout. A material
   event touching a held/planned symbol is also written into the lifecycle
   book as a `MarketEvent`; `review_problem` then blocks entries until the
   review acknowledges it.

## Commands

- `tyche events list [--json]` - static anchors + pinned discoveries.
- `tyche events add ...` - validate + atomically pin one event (dedupes on
  date+name against both overlay and static anchors; refuses to overwrite a
  broken overlay).
- `tyche calendar` - gate view; prints an explicit red warning if the overlay
  is invalid.

## Failure modes

- **Invalid overlay**: the gate never crashes - it falls back to static
  anchors and surfaces `overlay_error` in the gate JSON / CLI. Fix the file;
  `events add` refuses to write until it parses.
- **Missed discovery**: the static anchors (FOMC, macro, earnings seasons,
  pinned catalysts) still apply. Discovery is additive, never a replacement.
- **Kill-switch**: independent of this loop; `data/halt.json` / journal halt
  still block buys regardless of event state.

## Deployment

`scripts/deploy_event_discovery.py` applies the scout + desk-head clauses
(system-only edits, tools/vault/env/mount preserved, roster re-pinned,
idempotent, snapshots under gitignored `plans/`). Schedules reference the desk
template by id, so the triage clause reaches all hourly runs without schedule
changes.

`scripts/deploy_scout_data_suite.py` applies the fixed-core/deep-dive data-suite
clause to the researcher and re-pins the desk roster the same way. Run it after
compiling the edited researcher template, passing the version reported by QCA
`list_agents` when the REST agent route is unavailable.

The Forward REST `/agents/{id}` route is gone, so read the compiled researcher
version with the QCA `list_agents` tool first and pass it as the script's
argument (after a template edit it is the previous pin + 1).