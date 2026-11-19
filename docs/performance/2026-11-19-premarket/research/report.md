# Tyche Pre-Market Research — 2026-11-19 (VALIDATION MODE, PRODUCTION HOLD)

- Run: `2026-11-19-premarket-1305` · Phase: pre_market · Delegation clock: 2026-11-19T13:08:55Z (08:08:55 ET)
- Role: tyche-researcher (scout). **UNAPPROVED RESEARCH ONLY.** Zero orders, zero approvals, zero config edits. Production orders NOT RELEASED.
- Write scope honored: this directory only. No mcp/, audit/, plan/, state/, journal/, Drive writes.
- Repo: /data/workspace/tyche (HEAD 2181c12; tactical release 7288d68; pinned engine 119d4e5).
- Timing: RTH open 14:30Z; hourly checks 14:05, 15:05, 16:05Z…; last RTH hourly check 20:05Z (15:05 ET).

## Timestamp & persistence limitations (honest disclosure)

- No independent clock tool. All `reviewed_at` / `news_checked_at` / `added_at` values (13:17:00Z / ~13:15Z) are **labeled estimates** anchored to verified MCP feed timestamps: last ticks 13:16:36Z (AMD/MU/SPY), snapshots 13:15:46–13:15:55Z. Exchange timestamps quoted below are from payloads, not estimates.
- Shell-less + write scope restricted to `research/**`: `/tmp/tool-outputs/` persistence not possible this run. Payloads are cited inline as `mcp_<tool>_<symbol>` refs with fetch/exchange timestamps. Deviation recorded, not hidden.
- Delegation said "no option-chain tool"; my registered toolset **does** include `quote_option_chain` / `quote_option_expiration_date` (AMD expiration probe succeeded: weeklies Nov 23/25/27/30, Dec 2/4/11/18 within DTE 2–30). Discrepancy documented; proposals are stock-only on evidence (IV/crush/call-selling), not on a fabricated tool gap.

## 1. Macro regime

**Fed HIKE cycle** (never "cut odds"): Dec 9 FOMC 25bp hike ~96% priced; 50bp tail ~3–4% (a spike toward ~12.7% = hawkish-surprise signal, VNQ/duration headwind); three hikes priced by June. 10y ~5.07%, 2y ~4.83%, DXY 103.70 (19-month high). Nov 18 FOMC minutes hawkish (static anchor). Sources: investingcube 09:11:05Z; Benzinga 09:49:52Z; wallstreetcn 06:01:16Z.

Tape: narrow AI-led risk-on bounce (ANT record-IPO halo) vs weak breadth — Dow 3rd consecutive >1% drop (first since Oct 2008), CNN Fear & Greed 25 (extreme fear), gold −3.2% / silver −4.94% liquidation. Nov 18 close: SPY +0.31%, EFA −1.08% (USD strength), NVDA −2.89% post-earnings fade. Sources: wallstreetcn 3785261 (06:01:16Z), cftime (00:57:39Z), zhitong 1524999 (00:37:07Z), Gelonghui live/2769801 (12:30:57Z). **Two-way risk; not broad risk-on.**

Today's macro: 13:30Z Initial Claims (prev 198K / cons 200K, indicatorId 294) + Philly Fed (20.6 / 20.9, id 236); 15:00Z Leading Index (0.0% / 0.0%, id 1968) — MCP `quote_economic_calendar_hot` 20261119. **All pre-market proposals require post-13:30Z revalidation before any 14:05Z entry consideration.**

## 2. Holdings thesis reviews (PRIORITY) — see thesis-reviews.json

THESIS reviews, **not plan-hash Reviews** (no approved LifecyclePlan hashes exist).

| Holding | Qty | Verdict | reviewed_at (est.) | valid_until | news_feed_ok |
|---|---|---|---|---|---|
| US.SPY | 28 | **valid** | 13:17:00Z | 14:17:00Z | true |
| US.EFA | 142 | **valid** | 13:17:00Z | 14:17:00Z | true |

- SPY: ballast intact; Nov 18 main flow +194M vs negative 5-day cumulative; oversold-rebound technicals (MCP flow_history / unusual_technical, ~13:14Z). Hawkish regime caps upside, no confirmed invalidation.
- EFA: diversifier intact; −1.08% Nov 18 on DXY strength = known headwind, not invalidation; Nov 18 super-large inflow +62.8M. Pre-market flat ~100.26 on **48 shares**, last tick 13:11:17Z → thin price discovery, quote-age risk.
- **Protection gaps for Desk Head:** (a) SPY+EFA ~34.9% NAV > 25% PB-001 sleeve ceiling — existing holdings only, NO adds, over-cap ≠ liquidation permission; (b) no approved lifecycle contracts → stop/target/deadline gap needs adopt_position workflow; this review is not a substitute.

## 3. Ranked tactical candidates (long-only) — see tactical-proposals.json

All proposals: sleeve equity, strategy `tactical-catalyst-long`, direction bullish, option null, expiry 2026-11-19, **exit_at 2026-11-19T20:05:00Z** (last hourly RTH check; satisfies ≤20:45Z delegation bound and config option/session exits), confirmation_ticks 2, status watch, **unapproved**. Price references are PRE-MARKET (labeled); executor must re-verify executable quotes ≤60s / stock spread ≤0.3% at RTH.

### #1 US.AMD — TAC-20261119-AMD-L1
- Entry 538.0–543.5 · stop 535.0 · target 556.5 · R:R at entry_high 1.53 · max_quantity 36 (name-cap bound: 36×543.5=19,566 ≤ 20,037) · stop-risk 36×8.5=306 ≤ 1,001.85.
- Reference: MCP snapshot 13:15:55Z pre 541.50, bid 541.50×1 / ask 541.90×40; pre_high 550.23; AH 536.99; tick 13:16:34Z 540.5792×300.
- Catalyst stack: Jefferies Nov 4 server-CPU guide >100% growth (AASTOCKS NOW.1552931, Nov 4 08:01:31Z); Bernstein PT 650 Nov 16 (Zhitong 1524055, Nov 16 17:34:27Z); Oppenheimer Nov 9 upgrade / Anthropic ramp; OpenAI chip-dev news (Sina 12:35:17Z); Option Mover feed 11:10:58Z.
- Flow confirmation: Nov 18 total +295.0M / main +130.6M (MCP capital_flow_history). Derivatives: P/C 1.08, call OI wall 600, IV 76.83% @ 85th percentile → stock preferred over calls (crush risk).
- Invalidation: loss of 535 pre-market/overnight support on volume; hawkish 50bp-tail spike (>~12.7%); sector reversal (SMH < 466); confirmed negative issuer news.

### #2 US.MU — TAC-20261119-MU-L1
- Entry 728.5–740.0 · stop 728.0 · target 758.5 · R:R 1.54 · max_quantity 27 (27×740=19,980 ≤ 20,037) · stop-risk 324.
- Reference: snapshot 13:15:54Z pre 739.40 (+4.84%), bid 738.75×10 / ask 739.8×14 (spread 0.14%); pre_high 749.20 / pre_low 728.88; tick 13:16:35Z 738.40.
- Catalysts: memory/HBM pricing momentum (Gelonghui live/2769754 09:13:51Z); Appaloosa +28% (1.25M sh) / Altimeter +24% (260K sh) 13F adds (Seeking Alpha 4674605, 12:33:15Z); Futu flash 1005045476 12:41:41Z; Sina 12:35:17Z.
- **Fade risk (ranked below AMD):** 5-day flow −8.4/−337.0/−322.5/−26.1/−55.5M; heavy upside call selling (Feb27 850/920, 8750 lots), OI wall 800, IV 80.59%. Strongest pre-market gain but flow contradicts — smaller conviction.
- Invalidation: break of 728 (below pre_low 728.88); continued main-force outflow at open; hawkish macro surprise.

### #3 US.SMH — TAC-20261119-SMH-L1
- Entry 469.5–474.0 · stop 466.0 · target 486.5 · R:R 1.56 · max_quantity 42 (42×474=19,908 ≤ 20,037) · stop-risk 336.
- Reference: snapshot 13:15:46Z pre 472.8162, bid 472.81×208 / ask 473.22×100 (0.09%); pre_low 469.31; Nov 18 high 469.50; AH 467.2465.
- Thesis: diversified semi vehicle for the AI-halo/oversold-rebound tape; tightest spread; avoids single-name event risk (NVDA fade, MU outflow).
- **SLEEVE AMBIGUITY — kernel decision required:** SMH is in tactical.yaml `etf_symbols` (45% tactical sleeve), NOT PB-001. If the kernel instead counts it toward the 25% PB-001 ETF sleeve (already 34.9%), this proposal is **BLOCKED**.
- Invalidation: SMH < 466; NVDA-led sector reversal; hawkish surprise.

### Caps math (NAV ~100,185, preflight 11:09Z)
- Per-order ≤30% = 30,055.50; name ≤20% = 20,037; stock stop-risk ≤1% = 1,001.85; tactical sleeve ≤45% = 45,083; aggregate option premium ≤25% = 25,046 (per-trade full debit ≤0.75% = 751.39); cash ≥5% = 5,009; gross ≤95%.
- **FLAG:** aggregate max notional of all three proposals = 19,566+19,980+19,908 = **59,454 > 45,083** tactical cap. Quantities are per-name research bounds; **kernel must scale down** if multiple entries are ever approved. Existing holdings also consume gross/cash headroom.

### Rejected / no-trade
- **NVDA — REJECTED long:** verified Q3 (rev $115.84B +103.2% y/y vs cons ~$108.97B; DC $107.61B; GM 74.9%; EPS $2.68; Q4 guide $130B median; FY28 growth 70%→75%) yet −2.89% Nov 18 beat-and-fade; 5-day flow −$5.46B (main −$4.05B); governance overhang (interim CEO Kress, 10-Q delay, BIS/neocloud risks). Broker PTs Citi 225 / MS 260 / BofA 280 noted but flow dominates. Sources: issuer release via news_search (Nov 18 after close), zhitong 00:37:07Z, MCP flow_history.
- **ANT — WATCH-ONLY:** IPO verified ($83 above $70–78 range; upsized ~980M shares; ~$81.3B record raise; FDV ~$1.5T; $26B private placement incl. NVDA/AMD; Entropy prediction-market implied ~$98 ≠ executable market; FDV cooled from >$2T; largest short $42.6M). sec_status LISTING, no trades, last=83 is reference only → **no executable market → cannot source entry/stop/target honestly**. First trade may start well after 09:30 ET (static anchor; SPCX analog +19% day1/−53% 7wks). Re-evaluate after price discovery at 14:05/15:05Z checks. Debut timing unknown → imminent-event block applies near first trade.
- **AVGO — #4 alternate, not proposed:** adequate setup but weaker fresh catalyst vs AMD; three proposals already exceed sleeve cap.
- **Options — none proposed:** AMD IV 76.83% @85th pct, MU IV 80.59%, heavy upside call selling, post-event IV-crush risk; options require their own real entry/exit validation before production release. Chain tool available (see discrepancy note) but evidence favors stock legs. Long options can lose 100% of premium plus fees; gaps/halts/expiry/limit non-fills can defeat synthetic exits; no ladder/re-entry.

## 4. Event discovery proposals — see event-proposals.json

5 NEW: Nov 19 Claims 08:30 ET; Nov 19 Philly Fed 08:30 ET; Nov 19 Leading Index 10:00 ET; Nov 20 PBoC LPR 01:15Z (EFA/EEM); Nov 21 LA/Long Beach port labor risk (**tentative/conditional** — pin only on confirmation). Static-anchor-covered (no re-pin): ANT IPO Nov 19, PCE + Beige Book Nov 25, Thanksgiving Nov 26 closure, Nov 27 13:00 ET early close, ANT index inclusion Dec 4, FOMC Dec 9. Rejected noise: FBLLU SPAC, SNDK split, WMT/BABA/ROST/PANW earnings (not universe), YNTE (outside window). **Researcher does not write config/events.yaml.**

## 5. YouTube inbox hypotheses (ADR 0015) — unvalidated, LEAN lane only

Index: research/youtube/index.json, 8 items fetched 2026-11-18T19:27Z. No scout summaries exist under docs/research/youtube/ (glob empty) — titles-only extraction, gap recorded. Not trading signals, sizing, approvals or claimed backtests.

1. **H1 (unvalidated):** weekend theta drag materially erodes long-premium holds → test optimal DTE/exit-before-weekend rules. Video: https://www.youtube.com/watch?v=HEpPh22pMnI (Option Masterclass S3).
2. **H2 (unvalidated):** single-index concentrated playbook beats multi-name scatter on risk-adjusted return → test concentration vs breadth in LEAN. Video: https://www.youtube.com/watch?v=EirG9pJt7NE (S2).
3. **H3 (unvalidated):** momentum+volume filtered selection improves long-call win rate → test filter thresholds. Video: https://www.youtube.com/watch?v=smfoiVTGcH0 (S4).

Route to operator's local LEAN validation lane. No shell/backtests run here.

## 6. Coverage-gap matrix (recorded, never inferred)

| Item | Status |
|---|---|
| rt_ticker | fetched MU/AMD/SPY/EFA only |
| unusual_capital | fetched SPY/EFA/MU/AMD only |
| unusual_technical | fetched SPY/MU/AMD only (EFA gap) |
| unusual_derivatives | fetched MU/AMD only |
| short_interest / daily_short_volume | not fetched this run |
| MU/AMD next earnings dates | unverified; none today per checked sources — executor must re-check before any entry |
| Fed speakers Nov 19 | no hits in checked sources; not exhaustive |
| /tmp/tool-outputs persistence | not possible (shell-less + write scope); inline payload refs used |
| Independent clock | none; review timestamps labeled estimates |
| Option-chain tool | available contrary to delegation note; discrepancy documented |

## 7. Risk statement (plain language)

Hourly synthetic stops/targets/time exits are **not resting broker stops or guaranteed fills**. Gaps, halts, delayed runs and limit non-fills can exceed planned stop loss. Pre-market prices are references, not executable markets. The 13:30Z macro prints and ANT debut create two-way open risk; any entry before post-event revalidation is blocked. Production remains on hold; nothing here is an approval, an audit, or a fill.

## 8. Artifacts

- `research/tactical-proposals.json` — Watchlist-shaped, as_of 2026-11-19, 3 unapproved entries (AMD/MU/SMH), schema per src/tyche/watchlist.py.
- `research/thesis-reviews.json` — SPY/EFA thesis reviews (valid), protection notes.
- `research/event-proposals.json` — 5 new + covered + rejected lists.
- `research/report.md` — this file.

Desk Head next steps: validate/publish watchlist working copy (never overwrite protected Drive files); resolve SMH sleeve attribution; scale quantities to tactical cap; close SPY/EFA lifecycle-contract gap; post-13:30Z macro revalidation; ANT price-discovery re-check at 14:05/15:05Z.

— tyche-researcher, 2026-11-19 (reviewed_at estimate 13:17:00Z; sources timestamped above)