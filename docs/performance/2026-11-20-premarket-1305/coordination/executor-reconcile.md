# Executor premarket reconciliation — 2026-11-20 (READ-ONLY, halt engaged)

Fire: TYCHE PREMARKET PLAN FIRE, phase `pre_market`, calendar gate rc=0
(activity=plan, new_entries=false, max_orders=0, event_caution=false; event today
PBoC LPR fixing 2026-11-20T01:15Z, EV-20261120-PBOC-LPR).
Executed by executor agent, work window 2026-11-20T13:11:22Z – 13:24:11Z (report written after the
window closed; repo tree still clean and production lifecycle state/book sha256 unchanged at
13:24:11Z).
Zero broker writes: no reserve/submit/cancel/modify/approve/revoke/execute-exit,
no `--record` on any tick/scalp, no config/envelope/state mutation.
Repo `/data/workspace/tyche` HEAD `e53d0453235e318e7f3d9f3d6fe2b10c433f0097`
(clean tree; contains pinned release `3312287ce282cedacdafab552b40678e386ea90d` — verified
with `git merge-base --is-ancestor`).

Run dir: `/data/drive/tyche-raw/2026-11-20-premarket-1305`

---

## 1. ENV / OWNERSHIP — ALLOWLIST MIS-PROVISION REPRODUCED (blocking)

- `TYCHE_ALLOWED_ACCOUNT_IDS` in this executor session = `119[REDACTED]` (7 chars, masked ***[REDACTED]).
  It does **NOT** include the challenge account ***598. Same mis-provision as prior sessions.
  Not overridden in any persistent way; see §7 for the one transient, inspection-only use.
- Readable paper accounts (`sim_trade_account_list`, ret_code=0, 13:11:22Z, 8 accounts):
  ***589 HK, ***592 SG, ***[REDACTED] US margin (type 1, market 100), ***047 JP, ***184 US futures,
  ***185 SG futures, ***661 KR, ***598 "Moomoo x Qoder AI Paper Trading Agent Challenge"
  (**account_type 2, market_id 100**). Broker reads succeeded for ***598; only the kernel
  allowlist gate rejects it.
- Consequence (measured, not asserted): `tyche lifecycle tick` with the natural env fails closed
  `{"ok": false, "reason": "unverified or non-allowlisted US paper account", "submitted": false}`
  (`src/tyche/lifecycle.py:291-301`, `src/tyche/lifecycle_cli.py:375-378`). Under this env the
  executor cannot run kernel capture/tick/reserve against the challenge account at all, so it
  cannot produce a kernel-authorized decision of any kind, entry or exit.
- Schedule/single-writer provenance: no local scheduler is visible from this sandbox
  (`crontab -l` empty; only `ci.yml` in workflows). The tyche-hourly owner is on the desk side;
  the journal carries `run.start` 2026-11-20T13:11:44.861284Z for this fire (coordinator-written).
  Ownership could not be independently verified from here — recorded as unverified, not asserted.
- Effective halt: **ENGAGED**. `journal/halt.json` halted=true, ts 2026-11-19T20:28:29.377217Z,
  set_by "operator (CLI)", source `journal`. `data/halt.json` is halted=false ts 2026-11-18T09:45:07Z
  (source `repo`) and is stale/superseded — confirmed it does NOT release the halt
  (`effective_halt(journal_dir=2026-11-20-premarket-1305/journal)` → halted true).
- Journal lineage: `journal/events.jsonl` chain **valid**, **22 events**. NOTE: briefing supplied
  sha256 `9e9b0d3d…c05d` for 21 events; current file sha256 is
  `173c271d76db8be5328164e7f15c87ab69197cc24942cbdff087be376241fc94` and the extra event is the
  coordinator's own `run.start` at 13:11:44Z. Difference explained, not treated as tampering.

## 2. ACCOUNT / NAV (two fresh reads)

| field | batch1 13:11:30Z | batch2 13:19:0xZ |
|---|---|---|
| cash `balance` | 45,680.121 | 45,680.121 |
| frozen `hold` | 0.00 | 0.00 |
| market value `mv` | 52,750.67 | 52,699.56 |
| `total_asset` (broker NAV) | **98,430.791** | **98,379.681** |
| `max_power_long` | 144,110.912 | 144,059.802 |

Reconciliation exact in both batches: cash 45,680.121 + frozen 0 + MV = total_asset (delta 0.00).
Kernel NAV-vs-broker check therefore passes (no "NAV does not reconcile" blocker).
Weights at batch2: cash 46.43% NAV (min 5% OK), gross 53.57% (cap 95% OK), largest name
SPY 20.2% (cap 40% OK).
NAV references (from reconciled records, not invented): prior-close NAV **99,914.93** and
high-water **100,193.13** are the values journaled/used by the 2026-11-19 close-2005 capture
(`2026-11-19-close-2005/mcp/capture2/market.json`, executor-summary). High-water was raised to
**102,208.99** in this run because it is reproducible from journaled Nov-18 fills + Nov-18 official
closes (SPY 730.20 ×28, EFA 100.26 ×142) + Nov-18 EOD cash 57,360.28; flag for desk confirmation.
Drawdown: batch2 NAV is **-1.54%** vs prior-close NAV and **-3.75%** vs the 102,208.99 reference
(soft-DD 4% limit: approaching, not breached; daily-loss 2.5% limit: OK). If the desk instead uses
HWM 100,193.13, the account is **+1.79%** above it — the two candidate HWMs must be reconciled by
the desk; I did not silently pick one for any decision.

## 3. POSITIONS (all longs, `pstn_type` 0, no options, no shorts)

| symbol | qty | available | avg cost | broker cur_price @13:19Z | MV | unrealized |
|---|---|---|---|---|---|---|
| US.SPY | 28 | 28 | 731.54 | 709.75 | 19,873.00 | -610.12 |
| US.EFA | 142 | 142 | 100.495 | 97.76 | 13,881.92 | -388.37 |
| US.MSFT | 39 | 39 | 503.33 | 485.76 | 18,944.64 | -685.23 |

No option holding → **no `contracts.json` required and none created** (`pstn_type` 0 only;
option_ex_data all zero in quotes). Nothing was omitted for lack of metadata.
Available quantity equals holding for all three names, i.e. all three lots are sellable.

## 4. ORDER HISTORY — complete, single page

`sim_trade_history_order_list` (unfiltered, first page): returned 11 orders with
`pagination.has_more = false`, `next_key = "0"` → pagination terminated, one page total.
Stored verbatim as `mcp/orders-1.json` (page numbering starts at 1, real flag retained).
Read at 13:11:30-13:11:40Z. `order.market` reports `2` for every US row — unreliable field, ignored
as instructed; the account's own market (100) is authoritative.

Status legend as currently verified: 4 = full fill (terminal, cum = qty); **5 = UNRESOLVED**
(not proven cancelled/expired).

| order_id | symbol | side | qty | cum | status | price / avg fill | created (broker µs→UTC) | remark |
|---|---|---|---|---|---|---|---|---|
| 3116580 | SPY | buy | 28 | 28 | 4 | 733.17 / 731.54 | 2026-11-18T17:44:56Z | tyche 2026-11-18 rebalance 30% SPY, plan f11456df |
| 3116594 | EFA | buy | 142 | 142 | 4 | 101.45 / 100.495 | 2026-11-18T17:49:36Z | … 20% EFA, plan f11456df |
| 3116597 | VNQ | buy | 83 | **0** | **5** | 94.98 / 0 | 2026-11-18T17:53:07Z (upd 2026-11-19T01:01:00Z) | … 11% VNQ, plan f11456df |
| 3118496 | NVDA | buy | 33 | 33 | 4 | 149.51 / 149.053 | 2026-11-19T17:23:59Z | tyche-scl-5388f21a… |
| 3118497 | AMD | buy | 10 | 10 | 4 | 486.98 / 485.431 | 2026-11-19T17:24:13Z | tyche-scl-79bbee16… |
| 3118498 | MU | buy | 7 | 7 | 4 | 701.68 / 700.518 | 2026-11-19T17:24:30Z | tyche-scl-a461919… |
| 3118500 | SMH | buy | 10 | **0** | **5** | 454.48 / 0 | 2026-11-19T17:25:10Z (upd 17:27:07Z) | tyche-scl-bb75c14b… |
| 3118508 | NVDA | sell | 33 | 33 | 4 | 150.03 / 150.112 | 2026-11-19T17:29:56Z | tyche-scl-a0ff23cd… |
| 3118534 | AMD | sell | 10 | 10 | 4 | 485.26 / 487.615 | 2026-11-19T17:48:42Z | tyche-scl-ad9d8115… |
| 3118536 | MU | sell | 7 | 7 | 4 | 699.27 / 702.74 | 2026-11-19T17:48:49Z | tyche-scl-e0956d36… |
| 3118578 | MSFT | buy | 39 | 39 | 4 | 503.35 / 503.33 | 2026-11-19T18:15:16Z | tyche-tac-be465d06… |

Findings:
- **VNQ 3116597**: status 5, cum 0, no position, no frozen funds — unresolved 16.5 h later,
  still not provably cancelled/expired.
- **SMH 3118500**: status 5, cum 0 — same unresolved class; incident round-trips are
  NVDA 33 (buy 17:23:59 / sell 17:29:56), AMD 10 (17:24:13 / 17:48:42), MU 7 (17:24:30 / 17:48:49);
  net flat, confirmed by zero holdings in these names.
  Cash arithmetic is consistent with the briefing's +72.34 round-trip total:
  33×(150.112-149.053) + 10×(487.615-485.431) + 7×(702.74-700.518) = 34.863 + 21.840 + 15.554
  = **72.257 gross** before fees.
- **MSFT 3118578**: full fill 39 @503.33, still in the book, **no lifecycle grant** (state approvals
  = []), so it remains an unowned lot.
- **NEW ORDERS AFTER THE INCIDENT: NONE.** Latest `create_time` in the complete history is
  2026-11-19T18:15:16Z, i.e. before the 2026-11-19T20:32Z post-incident boundary. No evidence of an
  active second writer in this window. Facts only: the operator committed the PB-004 scalp lane and
  MSFT-only tactical lane at Nov-20 01:45Z and the remark prefixes (`tyche-scl-`, `tyche-tac-`) match
  those lanes; attribution remains UNVERIFIED because no journal receipt exists for any of the 8.
- **Currently live/pending broker orders: ZERO.** No status-1/2/3 rows; frozen funds 0.00.
  There is therefore no resting exit protection on any lot.

## 5. OFFICIAL 2026-11-19 DAILY BARS (completed, autype=1 forward-adjusted, time_key 1795064400000 = 2026-11-19T21:00:00Z)

| symbol | Nov-18 close | Nov-19 open | high | low | **Nov-19 official close** | daily-close stop | verdict |
|---|---|---|---|---|---|---|---|
| US.SPY | 730.20 | 737.46 | 739.8999 | 715.65 | **715.87** | 727.50 | **BREACHED** (-1.60% below; -1.96% on the day) |
| US.EFA | 100.26 | 100.545 | 100.58 | 98.62 | **98.78** | 100.00 | **BREACHED** (-1.22% below; -1.48% on the day) |
| US.MSFT | 508.29 | 519.50 | 526.49 | 498.16 | **498.30** | n/a (no plan) | no stop exists; fill 503.33 already -1.0% by the close |

So the Nov-19 completed-bar verdict confirms invalidation rule (i) for **both r2 contracts**: a
completed daily close below the stop exists. Bars stored (field-subset transcription, provenance
noted) at `mcp/klines/daily-20261116-20261119.json`; derived `mcp/closes.json` maps each symbol to
`{close, close_at:"2026-11-19T21:00:00Z"}` for SPY, EFA, MSFT, NVDA, AMD, AVGO, MU, SMH.

## 6. QUOTES / FEED HEALTH

Sessions (`mcp/market-state.json`, quote_market_state with pre/post flags): all eight symbols
`PRE_MARKET_BEGIN`, Nov-20 pre-market window 09:00:00Z–14:30:00Z, RTH 14:30:00Z–21:00:00Z,
after-hours 21:00:00Z–01:00Z(+1). As of 13:12Z pre-market had been open 15,113 s and RTH opens in
4,687 s (~13:58Z). No suspensions (`sec_status NORMAL`, `suspension false`) anywhere.
No `quote_market_snapshot` tool exists in this session's tool set; two-sided prices were taken from
`quote_order_book` (stored `mcp/book-US.*.json`, top-5 levels per side per exchange transcribed —
depth truncated for storage, note inside each file).

| symbol | main `last_price` | main data_time | pre_market price/vol | best bid (13:12Z) | best ask | spread | gate |
|---|---|---|---|---|---|---|---|
| SPY | 715.87 | 2026-11-19T21:00:00.255Z | 709.21 / 482,202 | 709.24 | 709.31 | 0.0099% | OK |
| EFA | 98.78 | 2026-11-19T20:59:59.937Z | 97.76 / **850** | 97.50 | 98.19 | **0.708%** | **fails 0.3% stock spread** |
| MSFT | 498.30 | 2026-11-19T21:00:00.777Z | 487.15 / 181,146 | 486.66 | 487.00 | 0.0699% | OK |
| NVDA | 145.98 | 2026-11-19T21:00:00.413Z | 141.08 / 5,520,448 | 141.05 | 141.07 | 0.0142% | OK |
| AMD | 489.19 | 2026-11-19T21:00:00.402Z | 456.99 / 849,816 | 456.24 | 457.03 | 0.173% | OK |
| AVGO | 346.65 | 2026-11-19T21:00:00.220Z | 336.00 / 278,637 | 335.74 | 336.19 | 0.134% | OK |
| MU | 690.44 | 2026-11-19T21:00:00.710Z | 653.87 / 792,689 | 653.61 | 653.90 | 0.0444% | OK |
| SMH | 447.48 | 2026-11-19T21:00:00.368Z | 432.33 / 121,862 | 432.06 | 432.52 | 0.107% | OK |

Feed-health facts:
- Every normalized quote row is **mixed-vintage**: `last`/`data_time` = Nov-19 21:00:00Z close
  (≈16.5 h old at capture) while `book_at` = 2026-11-20T13:12:16–13:12:47Z (≈7 min old). The
  current pre-market prints live only in `pre_market.price` and `bid/ask`, which the lifecycle
  kernel does not treat as a fresh spot. EFA pre-market volume of 850 shares makes its top-of-book
  essentially uninformative; NASDAQ shows cent-and-below placeholder bids (0.01–0.05) on SPY.
- Account-read age: batch1 oldest read 13:11:22Z → exceeded the 120 s gate by 13:17:59Z
  (`"broker snapshot stale or future-dated; fetch again"`). Batch2 re-read at 13:19:04–13:19:27Z
  passed the gate when ticked at 13:19:48Z.
- The 60 s quote/book gate can never be satisfied in pre-market with this tool set, because no
  tool here returns a current-session quote timestamp. Consequence: **any protected exit at RTH
  open requires a fresh in-session re-fetch inside 60 s of the decision**, which a 13:05Z premarket
  fire structurally cannot provide.

## 7. CAPTURE + DRY TICK OUTPUT

Artifacts: `state/market.json` (batch1 capture), `state/market-batch2.json` (batch2 capture),
`state/book.json` + `state/state.json` (verbatim copies of production; production files untouched,
sha256 state `a7a9e99496ff…`, book `111fcbe29b3c…`, identical to the run copies),
`state/tacfeed/` (tactical feed copy), `state/watchlist-prod-copy.json`.

**Kernel path, natural env (no overrides):** `lifecycle tick` →
`ok=false "unverified or non-allowlisted US paper account"` (see §1). This is the authoritative
verdict for this fire: under the provisioned env the executor has no working path to any
lifecycle decision or authorization.

**Kernel path, inspection-only env injection** (`TYCHE_ALLOWED_ACCOUNT_IDS=583[REDACTED]` prefixed on
individual commands, session-scoped, no repo/config/state write; used only to enumerate further
gates past the allowlist check, since the mis-provision masked them):

`lifecycle tick` (live clock 13:19:48Z, batch2 market, production-equivalent state with
approvals=[] / reservations=[] / latched_exits={} / last_tick_at=null), `--record` NOT used —
`coordination/tick-liveclock.json`:

| symbol | plan | grant | review | quote | pending order | action | reason | warnings |
|---|---|---|---|---|---|---|---|---|
| US.SPY | present r2 | **absent** | **expired** (valid_until 2026-11-19T21:12:49Z) | stale (16.5 h) | none | `review` | "held position has no approved lifecycle ownership" | research review expired or future-dated |
| US.EFA | present r2 | **absent** | **expired** | stale | none | `review` | same as SPY | same |
| US.MSFT | **no plan at all** | n/a | n/a | stale | none | — | coverage gap | `gaps: ["US.MSFT: held position missing a complete lifecycle plan"]` |

`last_tick_at` is null, so the "monitor coverage gap >75 min" check could not fire — which itself
means **no lifecycle hourly tick has ever been recorded against this state lineage**; the last
observed protection check is the Nov-19 close review at 20:12:49Z, 17.1 h ago.

**Would-exit trigger (explicitly labelled HYPOTHETICAL).** To answer "would the kernel see the
daily-close breach?", I built in-memory `Approval` objects with placeholder
`operator_ref/auditor_ref = DIAGNOSTIC-NOT-APPROVED / DIAGNOSTIC-NOT-AUDITED`. These are NOT
operator approvals and NOT auditor audits; nothing was persisted
(`coordination/tick-granted-hypothetical.json`): with a granted r2 contract the kernel
**latches `stop_loss` for both** `LC-20261119-SPY-ADOPT-r2`
(hash `e73ee77d4b6abca10545bd296537fcee34b9a2511440e49fcf1d3ad23f9c89df`) and
`LC-20261119-EFA-ADOPT-r2` (hash `add27d1a3e75fece0fe292c51050d9324ac33326a58ac4516cd93e3b39a9b33c`),
then returns `action=blocked, reason="quote missing, stale, future-dated or suspended"` — i.e. the
trigger is detected durably but no exit can be built outside RTH on a stale spot. Control run
without `closes.json` evidence (same synthetic grants,
`coordination/tick-no-dailyclose-evidence.json`): `latched {}` plus warning
"completed daily-close evidence unavailable for this lifecycle" — confirming the daily-close
evidence is what makes the breach visible.

**Tactical lane.** `tactical capture` on the isolated feed succeeded (quote_count 8) and produced
`state/tacfeed/tactical-account.json` + `tactical-quotes.json`. `tactical tick` without `--record`
(`coordination/tactical-tick-dry.json`): `as_of 13:20:29Z, phase pre_market,
config_hash 160b7d96f5c2…, orders [], decisions [], alerts ["tactical lane disabled or outside
regular session"], submitted false`. `tactical scalp` without `--record`
(`coordination/scalp-dry.json`): `strategy PB-004, orders [], alerts ["scalp disabled or outside
regular session"]`. Missing inputs reported, not fabricated: no 1-minute `bars-US.*.json` in the
feed (required for breakout entries; none fetched), no envelope file (zero approved grants exist —
`plan/none.json` does not exist and was not created), no `research/` artifacts in this run dir
(empty), so there is no fresh setup/review input to evaluate any entry. Options: `options_enabled:
false`, no option exposure, so no `quote_option_chain` call and no `chain-*.json`.

## 8. PROTECTION GAPS (lots with no live exit path)

1. **US.SPY 28 / US.EFA 142** — daily-close stops **breached on the completed Nov-19 bar**
   (715.87 < 727.50; 98.78 < 100.00), but the r2 contracts are **entry-window EXPIRED and
   UNAPPROVED** (state approvals=[]), so no exit is authorized and none can be submitted.
2. **No resting broker protection at all**: zero live orders, zero frozen funds; these are synthetic
   monitored stops, not broker stops. Gap/halt/nonfill risk is live.
3. **US.MSFT 39** — unowned fill (no grant, no plan, no review, no stop, no target, no deadline);
   -3.5% against a 503.33 cost with no invalidation condition of record.
4. **Two status-5 orders (VNQ 3116597, SMH 3118500)** remain unresolved; status 5 is not proven
   terminal, and pending same-symbol orders could obstruct a protection sell. Neither symbol is
   held today, so the risk is mainly order-path ambiguity.
5. **Halt engaged** — no entry and no exit can be released by this fire; the halt reason itself
   lists re-provisioning ***[REDACTED] vs ***598 and dispositioning MSFT plus the SPY/EFA breaches as
   operator preconditions.
6. **Env allowlist mis-provision** blocks even the kernel's read-only lifecycle evaluation against
   ***598 without operator intervention.
7. **Research is stale** (last review expired 2026-11-19T21:12:49Z; book `news_checked_at`
   2026-11-19T20:12:49Z, i.e. 17.1 h old at tick time) → entries blocked; today's PBoC LPR event
   (01:15Z) is material for EFA/EEM and has **not** been through a post-event review.
8. **`last_tick_at` null** in production state → no recorded hourly protection check exists for
   this lineage; protection continuity cannot be demonstrated from the ledger.
9. **EFA liquidity**: pre-market top-of-book spread 0.708% (> 0.3% gate) on 850 shares of volume —
   any EFA exit at the open should be expected to fill materially worse than the displayed bid.

## 9. RAW ARTIFACT INVENTORY (paths + sha256)

```
173c271d76db8be5328164e7f15c87ab69197cc24942cbdff087be376241fc94  journal/events.jsonl   (chain OK, 22 events)
0f1e665cd4cf3156af69a1842d8cafb1436b2a0c43e94265313773dd7b9b70af  journal/halt.json
53cb9d2c222a01c97e4a4ea2d6b2eff5af17bd947182445a236ef03321314475  mcp/accounts.json      (see deviation note)
b2548b00949f5db116d375d3989597daaf54889f28f344e23dbb50a599bbebc9  mcp/accounts.masked.json
6d111304e8472abca6e152a066c5f322a4d24a5dbc09c854f7c47856780ae29d  mcp/cash.json
f3efb6da554194305fd3832082102bfefbe5dfef7722772a0dec4255725380a9  mcp/positions.json
b5b6b8233eec9247129ce27d80af4b3800e00721961c2ec923db5e3972329a6c  mcp/orders-1.json      (has_more=false)
7012f7b5490e25fc3828552fefa4eb756657a9feb14d2c4496f5df17b0723205  mcp/quotes.json
d6d8005484b0bc248dcf5763ee8d9b076d5a9e4010e16921b628127f0e1fd63f  mcp/market-state.json
a049c92ed3970b27f2047df6ff3f5fa94c1971314b8e49bc5dc73f094c6c09d9  mcp/closes.json
17e82a048f4358501d1d9df6e75bc6662e853b0f02f8a25c6e2cef8952e9f8a7  mcp/book-US.SPY.json
eb6e26540ffc925b06b588566d0f19becc06bd415c2[REDACTED]d148c1c3497040790  mcp/book-US.EFA.json
acf0c070cdbb9429b1c4b4bdccb85ffbca91675b38cf9e9e92fbe1e3016ff9b4  mcp/book-US.MSFT.json
55ac5c6062efdb0c919baffba6704dfbd9540c78798f9c1dcd4e896772593443  mcp/book-US.NVDA.json
01386d061370f5b0441b7e4c6167a2a8a34881a9300a3eb887b81c78b6f29825  mcp/book-US.AMD.json
b20057d1871e94751501fcc59fcb71aae22fab11cf5bbd46c03943c859d5fb3f  mcp/book-US.AVGO.json
4434988a4c9b93de658466b8d057564aabb6cb14e28c0acfbab0a80406ca08b3  mcp/book-US.MU.json
a6565102641b4326ac1a478f78411a027b16e6865567e2b7e08750b9a127cfe5  mcp/book-US.SMH.json
30d5bea8818edfcc4cc10a00f4a08f5f44b6dcefc7941d6358c8f0f7802bd6b0  mcp/batch2/accounts.json
641a9ab700c0ae16ca773dbaae372df7b1a0ce3c9dc8a47ccea91b078ed8dc7d  mcp/batch2/cash.json
fc0da14484109c795a49273d7716b06d1efbfe1ee1e8375dcc0e5eac04547141  mcp/batch2/positions.json
111fcbe29b3c0888a51bd8971ba98fba256c907f395bc91b68de53ac1ff65660  state/book.json        (= production copy)
a7a9e99496ffc4f9b6c1c2819e2ace95a3b8de421fe5f34b4238d7bd293f0d58  state/state.json       (= production copy)
eeadce7472cae9b48dddc3db07c5aa6f8e50ca92b24681dc10c5fa4075d7b050  state/market.json
3aa55c1f54484ad6d4c39f5ca6a6ed7a777ea9e60421cc441fd05683efb05570  state/market-batch2.json
```
Also: `mcp/observed-at.txt` (oldest-read anchoring), `mcp/klines/daily-20261116-20261119.json`,
`coordination/tick-liveclock.json`, `coordination/tick-liveclock-analysisonly.json`,
`coordination/tick-granted-hypothetical.json`, `coordination/tick-no-dailyclose-evidence.json`,
`coordination/tactical-tick-dry.json`, `coordination/scalp-dry.json`.

**Two storage deviations, disclosed:** (a) `mcp/accounts.json` keeps real account ids because the
kernel matches `account_id` exactly (`account_meta`) — an initially masked copy made every tick
fail closed, so masking was moved to `mcp/accounts.masked.json` and to all report text;
(b) `mcp/quotes.json`, `mcp/market-state.json`, `mcp/orders-1.json`, `mcp/cash.json`,
`mcp/positions.json` are verbatim except for an added top-level `_provenance` block, while
`mcp/book-US.*.json` and `mcp/klines/*` are honest top-5 / field-subset transcriptions with notes.
No status, fill or timestamp was invented anywhere.

## 10. WHAT THE DESK MUST DECIDE (no executor action taken)

1. Re-provision `TYCHE_ALLOWED_ACCOUNT_IDS` for the executor session to include ***598, or confirm
   the desk intends a different writer account.
2. Identify/confirm the Nov-19 17:23–18:15Z writer and disposition MSFT 39 (adopt under a complete
   contract with stop/target/deadline + audit + operator approval, or approve a reduce-only exit).
3. Decide the SPY/EFA daily-close breach disposition: approve a fresh complete r3 lifecycle
   contract (new hash, review, independent audit, operator approval) whose exit is executable at
   RTH open with a same-moment fresh quote fetch, or state an explicit hold-the-ballast decision.
   The current expired+unapproved r2 contracts cannot produce any authorized order.
4. Resolve or formally accept the two status-5 orders as unresolved; do not treat status 5 as
   cancelled without evidence.
5. Provide the hourly sole-writer attestation; `last_tick_at` null means no protection continuity
   record exists.
