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

The clauses are in the researcher and coordinator prompts as retrieved; the text itself is what you edit.
`scripts/deploy_managed_agents.py diff <role> --file <path>` then `apply-system <role> --file <path>` is the
write path (system-only, tools/vault/env/mount never sent, snapshot under gitignored
`plans/managed-migration/`, post-write guard on what moved).

`archive/deploy_event_discovery.py` and `archive/deploy_scout_data_suite.py` are the Forward-template
writers that installed these clauses originally, before the desk was consolidated on the Managed plane. They
are kept for the exact wording and the snapshot discipline, not to run: a template write recompiles the
Managed agent and can surface a tool grant the running pin never had (L-046), which is why
[test_forward_fence.py](../../tests/test_forward_fence.py) keeps them out of `scripts/`.

The child agents run at the roster's `version: "latest"`, so an auditor / researcher / executor prompt write
is live at the next fire. The coordinator needs both desk cards re-pinned (`pin-card`) before its text takes
effect - see [agent-engineering.md](../agent-engineering.md), §Version pins.