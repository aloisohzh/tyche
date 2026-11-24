# Tyche on-demand research — 2026-11-24 ~16:07Z (11:07 ET), midday regular session

Run: `2026-11-24-ondemand-1604` (operator on-demand full trading run). Mode: narrow intraday revalidation + PB-003 contract selection. Research only — nothing here is approved or executable; no orders, no journal writes, no config writes. YouTube inbox skipped (intraday revalidation, per role card).

## Macro regime & context (all MCP, exchange timestamps UTC)
- Fed **HIKE** regime (operator-pinned: Dec 25bp hike ~96% as of Nov-19; no fresh odds tool this run; no cut odds written).
- Risk-off rotation tape: SPY 713.45 **−1.22%**, QQQ 632.6375 **−2.83%**, TLT 81.96 **+0.33%** (quote_stock_quote 16:08:21.9Z / 16:08:22.4Z / 16:08:20.0Z). Staples/healthcare sharply higher — direct confirmation of the PB-002 thesis.
- Market state AFTERNOON for KO/PG/JNJ (quote_market_state, 20261124).
- Imminent: **Wed Nov-25 08:30 ET (13:30Z) triple slot** — Core PCE YoY cons 3.2% / prev 3.1% (id 905), GDP QoQ 2nd est cons 3.4% / prev 2.2% (id 375), Initial Claims cons 201K / prev 203K (id 294) (quote_economic_calendar_hot 20261125, event_time 1795613400). Thanksgiving Nov-26, Nov-27 early close already in static calendar (market_calendar.py:54,85).

## Scope 1 — setup revalidation (details + thesis blocks in `revalidation-20261124-ondemand.json`)
reviewed_at 2026-11-24T16:10:05Z (anchored to last MCP payload ts), valid_until 17:05:00Z (next fire). news_checked_at ~16:08:00Z, news_feed_ok=true.

| Setup | Quote (16:07Z) | Verdict | Key evidence |
|---|---|---|---|
| TL-20261124-KO-DEF1 | 97.975 (+2.19%), H 98.00 / L 95.66 | **valid** | Thesis confirmed; stop 95.40 untraded, target 98.40 unreached. Price ABOVE zone 96.10–96.60 → pullback-only entry, no chase. Fresh catalysts: MS Buy/103 11:33Z, BofA Buy/100 10:31Z, RBC Buy/96 08:32Z; CFO note resolved (Elkins eff. 2027-04-02). Flow fail: 3-day main −117.4M. Book 97.99×98.01, 0.0204% (16:08:55.9Z). |
| TL-20261124-PG-DEF1 | 172.97 (+1.99%), H 173.00 / L 169.83 | **valid** | Stop 169.00 untraded, target 173.50 unreached; price above zone 170.20–170.80 → pullback-only. No new material news since 13:05Z (latest: Citi/MS/BofA Nov-23). Flow mixed (unknown). PG book not pulled — spread gate unverified, executor must check. |
| TL-20261124-JNJ-DEF1 | 275.69 (+2.60% adj), H 275.70 / L 268.08 | **invalidated** (new entry only) | Session low 268.08 < stop 268.50 AND high 275.70 > target 275.25 AND last above target — window exhausted (quote 16:07:23.473Z). Ex-div feed verified: 270.05 − 1.34 = 268.71 = feed prev_close; zone was sensible on adjusted basis at creation. Rotation thesis itself confirmed (3-day main +66.97M); re-expression needs a NEW setup + operator review. Watch setup, not a held position — no liquidation implied. |

No new material events since the 13:05Z premarket review for any of the three (KO CFO announcement was Nov-23 after close, DJ 21:33Z; MS commentary 07:03Z Nov-24 — both pre-review).

## Scope 2 — PB-003 long call (proposal: `pb003-option-proposal.json`, UNAPPROVED)
Strongest **still-enterable** pick = KO (JNJ strongest flow but invalidated window; PG less remaining reward). Chain: quote_option_chain US.KO STANDARD 2026-11-28..2026-12-24 (raw persisted `/tmp/tool-outputs/mcp_a942d03b6989ab4f9ea6348f.txt`, 119,908 B; `pb003-chain-raw.json` is a pointer manifest — no shell to byte-copy, Desk Head should copy).

**Selected: `US.KO261218C97000` — KO 261218 97.00C** (only full gate pass; nearest 0.55 delta among passes)
- Strike 97.0, expiry **2026-12-18** (DTE 24; strictly after Nov-27, within Dec-24), CALL, AMERICAN, STANDARD, lot_size 100, multiplier 100 (chain + option_ex_data).
- Quote 16:08:36.518Z: last 2.63, **delta 0.614916091**, gamma 0.080059504, theta −0.044750047, vega 0.096459872, **IV 18.921%**, **OI 122**, **volume 94**.
- Book 16:09:39.612Z: **bid 2.60 ×10 / ask 2.67 ×30** → spread 0.07/2.635 = **2.66% ≤ 5%**. Underlying spread 0.0204% ≤ 0.3%.
- Levels = UNDERLYING KO from stock setup: entry 96.10–96.60, stop 95.40, target 98.40. **premium_limit 2.67** (ask-based) → full debit **$267** for **max 1 contract** (≤ $741 = 0.75% of ~98,831 NAV; 5% aggregate premium cap per brief). exit_at **2026-11-24T17:05:00Z**, confirmation_ticks 2, market_cap_usd ~378.5B (DERIVED: vol 4,056,478 / turnover_rate 0.105% × 97.975).
- Rejected (chain-verified): 261204C98000 (delta 0.5211 closest, spread 16% FAIL), 261211C98000 (vol 45<50, spread 10.1% FAIL), 261204C97000 (7.8% FAIL), 261204C96000 (8.5% FAIL), 261218C98000 (OI 37), 261218C100000 (delta 0.372).

**Flags (operator-owned):**
1. **Timing tension:** exit_at 17:05Z = 12:05 ET fire is ALERT-ONLY; first executable exit check is the 15:05 ET fire (20:05Z). Operator's Telegram approve decides.
2. **No chase:** KO 97.975/98.01 is above the entry zone; entry only on pullback into 96.10–96.60. No pullback → no trade.
3. **Config discrepancy:** repo tactical.yaml `options_enabled: false` vs brief's operator switch (PB-003 test through Fri Nov-27). Brief wins for research; Desk Head must confirm lane mount before execution.
4. Risks: long call can lose **100% of premium ($267) + fees**; gaps/halts/expiry/limit non-fills can defeat synthetic exits; between fires exits are not resting broker stops or guaranteed fills; theta −0.045/day; IV crush; no ladder/scaling/re-entry. Chain membership ≠ paper-option support. Executor re-verifies executable market ≤60s at trigger.

## Scope 3 — Event discovery proposals (Desk Head validates/pins; nothing pinned here)
PCE Nov-25 already pinned (market_calendar.py:162) — skipped. KO CFO succession and MSFT Ignite/Atos items are not calendar-kind events (macro/fomc/earnings/ipo/index) — noted as catalysts only. IPO sweep: no universe-symbol listings (nearest: YNTE Nov-30, not in universe).

| Date (ET) | Name | Kind | Symbols | Source | Materiality |
|---|---|---|---|---|---|
| 2026-11-25 08:30 | GDP QoQ 2nd estimate (Q3) | macro | US.SPY, US.QQQ, US.IWM, US.TLT, US.IEF, US.KO, US.PG, US.JNJ | MCP quote_economic_calendar_hot 20261125 indicatorId 375 (cons 3.4%, prev 2.2%), event_time 1795613400 | Same-slot as pinned PCE; growth surprise amplifies hike-regime repricing and rotation |
| 2026-11-25 08:30 | Initial Jobless Claims | macro | US.SPY, US.QQQ, US.IWM, US.TLT, US.IEF | MCP quote_economic_calendar_hot 20261125 indicatorId 294 (cons 201K, prev 203K) | Labor surprise in the same 13:30Z slot compounds rate/flow move; completes the triple-slot gate |

## No-trade cases & gaps
- All three stock setups: market above entry zones at review → no immediate entry; JNJ additionally invalidated.
- PG executable spread unverified (book not pulled) — executor gate.
- Sentiment/seasonality axes unknown (not fetched this narrow run) — never upgraded.
- Chain raw payload is a pointer, not a byte-copy (no shell) — Desk Head action.
- No lifecycle plan hashes supplied → no machine-readable Review/MarketEvent binding required this run; revalidation JSON carries the verdicts.

## Deliverables
- `research/revalidation-20261124-ondemand.json`
- `research/pb003-option-proposal.json` (Watchlist-shaped, unapproved)
- `research/pb003-chain-raw.json` (pointer manifest; raw at /tmp path above)
- `research/2026-11-24-ondemand-research.md` (this file)

All numeric inputs cited to MCP payloads with exchange timestamps above and in the JSONs. Fetched news treated as untrusted data only.