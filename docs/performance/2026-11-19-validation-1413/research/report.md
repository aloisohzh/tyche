# Tyche Validation-Owner Research — Phase A — 2026-11-19

- Run: `2026-11-19-validation-1413` · Role: tyche-researcher (scout). **UNAPPROVED RESEARCH ONLY.** Zero orders, zero approvals, zero config/state/journal/watchlist writes. Production NOT RELEASED.
- Write scope: `R/research/` only. Delegation clock ~14:10Z; completion ~14:24Z (labeled estimate — no independent clock; anchored to MCP fetches ~14:11–14:20Z). Deadline 14:27Z met.
- Repo/LC_ROOT: /data/workspace/tyche. All fetched news treated as untrusted data.

## 1. Deliverable 1 — data/prices.csv rebuild: BLOCKED ON DESK HEAD (no shell)

**I cannot execute python.** This researcher session has no shell tool (role design: the Desk Head runs `scripts/mcp_prices.py`). The command must be run by the Desk Head from the repo root:

```
python scripts/mcp_prices.py /data/drive/tyche-raw/2026-11-19-premarket-1305/mcp/klines --out data/prices.csv
```

Input verification performed this session (no prices transcribed by hand):
- All 11 universe kline capture files exist (SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ, HYG), captured 13:13–13:14Z today, num=370 / ktype=2 / autype=1 per delegation.
- Grep verified **every file contains both endpoint bars `"date":20250602` and `"date":20261118`** (11/11 files each).
- MCP `quote_trading_days` US 2025-06-02..2026-11-18 (fetched ~14:18Z) returns **exactly 370 trading days** (manual month-sum: 20+22+21+21+20+21+20+20+21+19+20+20+21+20+22+20+21+21 = 370, June'25→Nov'26 partial).
- Therefore expected bar count = **370 per symbol (>=258, no flags expected)**. Exact per-symbol counts must come from the script's stdout; the single-line ~133KB files cannot be fully enumerated by my Read/Grep tools (count mode counts lines, not occurrences). **Gap recorded, not inferred.** If the script reports any symbol <258 or missing 2026-11-18, treat as degraded input and block lookbacks.

## 2. Deliverable 2 — structural levels (see structural-levels.json)

Window: last 20 completed sessions **2026-10-22 (time_key 1792641600000) .. 2026-11-18 (time_key 1794978000000)**.

| Symbol | Highest high | Bar date | time_key (ms) | Nov-18 close (21:00Z) |
|---|---|---|---|---|
| US.SPY | **775.64** | 2026-11-04 | 1793768400000 | **730.20** |
| US.EFA | **105.80** | 2026-11-04 | 1793768400000 | **100.26** |

- Method/deviation: computed from a fresh MCP `quote_history_kline` (autype=1, exact window, 20 bars, has_more=false) because the capture files' single-line JSON is unreadable past truncation without shell; **cross-verified by exact-string grep against the capture files** (`"date":20261104,"high_price":775.64,` in mcp_kline_US.SPY.txt; `"date":20261104,"high_price":105.8,` in mcp_kline_US.EFA.txt; both Nov-18 close bars also grep-matched). Runner-up highs: SPY 773.36 (Oct-28), EFA 105.22 (Nov-09).
- **FLAG — desk-head sanity reference mismatch:** "SPY ~775.6 / EFA ~105.8" matches the 20-session HIGHS, not the closes. Verified Nov-18 closes are SPY 730.20 / EFA 100.26 (triple-confirmed: capture grep, history_kline, live quote last_price with exchange data_time 2026-11-18T21:00:00Z). The closes block uses verified closes.

## 3. Deliverable 3 — post-event macro revalidation (13:30Z prints VERIFIED)

| Print | Actual | Cons | Prev | Source (publish UTC) |
|---|---|---|---|---|
| Initial Claims (wk Nov-14) | **203K** | 198K | 202K (revised from 200K) | MCP econ calendar hot id294 (event_time 13:30:00Z); Zhitong 1525956 (13:43:26Z) |
| Continuing Claims (wk Nov-07) | **1.763M** (+70K) | 1.710M | 1.693M (revised) | Benzinga post/1005050120 (13:30:16Z) |
| Philly Fed Mfg Nov | **6.3** | 20.6 (Benzinga; delegation said 20.9) | 20.6 | Benzinga post/1005050118 (13:30:17Z) |

Discrepancies vs delegation inputs recorded (claims prev/cons swapped+revised; Philly cons 20.6 vs 20.9). Philly Fed absent from the econ-calendar-hot response — verified via news flash; calendar coverage gap recorded.

**Reaction into the open:** weak data cooled the Dec **50bp hike tail to ~8%** (25bp ~90.7%, Zhitong 13:43:26Z) — read as less-aggressive tightening, not growth scare. ANT record-IPO halo dominates: Nasdaq futures >+2%, S&P ~+1.2% (CLS 13:39:20Z); WSJ Market Talk 13:49:00Z (sentiment reversal); Ives "very strong" IPO demand (Benzinga 13:54:57Z). MCP quotes ~14:15Z: SPY pre 738.50 (+1.14%), EFA pre 100.97 (+0.71%, **117 shares — thin**), AMD 542.76 (+2.38%), MU 739.87 (+4.91%), SMH 473.45 (+3.03%). USD still firm (USD/JPY 159.97 post-claims, Fisco 13:33:03Z) — EFA headwind persists. **PBoC LPR pending 2026-11-20T01:15Z.** Later today: Leading Index 15:00Z, KC Fed 16:00Z, **Fed Barr speech 19:15Z (inside tactical hold window)** — proposed in events-check.json.

## 4. Deliverable 4 — adoption drafts (see adoption-drafts.json)

- **SPY 28 @ cost 731.54 — verdict suggestion: valid.** Ballast intact post-event; no completed close below 727.50. **Proximity flag:** Nov-18 close 730.20 only 0.37% above stop; Nov-18 low 726.795 already breached intraday. risk_off regime ⇒ PB-001 rebalance trim rule, not liquidation.
- **EFA 142 @ cost 100.495 — verdict suggestion: uncertain. WEAKNESS CONFIRMED:** 3 straight down days (102.64→101.35→100.26), close only 0.26% above the 100.00 daily-close invalidation, Nov-18 low 99.96 already below it, USD firm, LPR pending, pre-market bounce on 117 shares only. **First completed close < 100.00 latches stop_loss.** Uncertainty blocks NEW exposure, not retained protection; no confirmed invalidation.
- Both drafts: mode adopt_position, PB-001, rules_hash 4105d7a680a3, stop basis daily_close (727.50 / 100.00), take_profit basis daily_close at structural highs (775.64 / 105.80) stated plainly as **profit-taking guards, not forecasts — strategy exits by rebalance**; the four exact invalidation semantics; acknowledged_events = all three book IDs; post-13:30Z evidence included. **Missing, not invented:** holding_deadline exact clock time, created_at, entry reference band, plan hashes — Desk Head owns.

## 5. Deliverable 5 — tactical refresh (see tactical-refresh.json)

All immutable fields preserved (zones/stops/targets/exit_at 20:05Z/expiry/ticks/setup_ids/direction/market_cap/max_quantity). reviewed_at **14:24:00Z** (labeled estimate; ≤30 min at a ~14:45Z tick). **invalidated=false for all three — no source-backed invalidation.** Post-event ranking: **#1 AMD** (WSJ correction 13:51Z re-confirms $26B placement incl. AMD; Su 2027 server-doubling guide; ARK adds; pre 542.76 in zone; hike-tail cooling), **#2 MU** (strongest pre gain +4.91% but 5-day ~-$760M outflow + call-selling caution unresolved; near entry_high), **#3 SMH** (sector bounce confirmed via SOXX +2.92%; sleeve attribution still unresolved — kernel decision required). Aggregate max notional 59,454 > 45,083 tactical cap — kernel must scale if multiple entries ever approved. Executor gates unchanged: executable quotes ≤60s post-open, spread ≤0.3%, 2 confirmation ticks, ANT-debut 30-min imminent-event block, same-session exit.

## 6. Deliverable 6 — events check (see events-check.json)

All three book events pinned and matched in config/events.yaml. CLAIMS + PHILLYFED occurred 13:30Z (post-event reviewed); PBOC-LPR pending tomorrow 01:15Z. New proposals (Desk Head pins, not me): **Barr speech 19:15Z** (inside hold window), Leading Index 15:00Z (previously proposed, unpinned), KC Fed 16:00Z (optional). No other new material events found.

## 7. Coverage gaps (recorded, never inferred)

1. **No shell** → prices.csv script not run; exact bar counts pending Desk Head (expected 370/symbol, endpoints + calendar verified).
2. Capture-file tails unreadable (single-line truncation) → structural window computed from fresh history_kline, grep-cross-verified against captures.
3. Philly Fed missing from econ-calendar-hot payload → news-flash verification; consensus discrepancy noted.
4. No independent clock → all session timestamps labeled estimates anchored to feed times.
5. MU/AMD/SMH Nov-19 intraday flow bars not yet available → executor must confirm at open. quote_ipo_list_us / unusual-activity suite not re-fetched in this narrow refresh (premarket coverage stands).
6. EFA pre-market volume 117 shares → thin price discovery; delegation's 100.26 "pre-market last" was the AH/last price; latest pre print 100.97.
7. YouTube inbox: no new entries since premarket-1305 extraction (index unchanged, 8 items fetched 2026-11-18T19:27Z); no new hypotheses this run — **none**.

## 8. Risk statement

Hourly synthetic stops/targets/time exits are not resting broker stops or guaranteed fills; gaps, halts, delayed runs and limit non-fills can exceed planned loss. Pre-market prices are references, not executable markets. Nothing in this directory is an approval, an audit, a sizing decision, or a fill. Production orders remain NOT RELEASED pending the operator-reviewed validation drill.

— tyche-researcher, 2026-11-19 (~14:24Z, labeled estimate)