# TYCHE MIDDAY PROTECTION FIRE — EXECUTOR REPORT (READ-ONLY)
2026-11-20, fire clock 17:05Z (12:05 ET). NYSE full day, regular session OPEN (verified: quote_market_state AFTERNOON, trade_section 1795185000-1795208400 = 13:30-20:00Z core; close 21:00Z).
Repo/LC_ROOT: /data/workspace/tyche HEAD e53d045 (contains pinned release 3312287). No production state, journal, config, envelope or broker writes. NO orders submitted/canceled/modified.

## ENV-PREFIX DISCLOSURE
Session env TYCHE_ALLOWED_ACCOUNT_IDS remains mis-provisioned (***4748). Per established read-only workaround, the following commands were run with a session-scoped prefix `TYCHE_ALLOWED_ACCOUNT_IDS=[REDACTED]` (env-only, no file/config/state write):
1. lifecycle capture + lifecycle tick (first cycle, 17:12Z)
2. lifecycle tick (final production cycle, 17:17:22Z)
3. lifecycle diagnostic tick (17:17:23Z)
4. tactical tick (2nd attempt onward; 17:14:55Z, 17:15:30Z)
5. tactical scalp dry (17:15:38Z)
One un-prefixed tactical tick at 17:14:06Z fail-closed with alert "paper account verification failed" — correct gate behavior, no output used. The env injection changes the tactical config_hash (2e9832fd… without vs 160b7d96… with), so any exact-order grant bound to a config hash must pin the intended injection state.
Note: lifecycle capture/tick does not apply the halt flag (halted=false in the capture market file; the stale repo data/halt.json is NOT a release — halt remains ENGAGED via journal events and the halt.json copy staged at run-dir journal/ and tacfeed/ and scalpdry/ for the tactical lane, which consumes halt from journal.parent).

## (a) HOLDINGS RECONCILIATION
Broker positions (final read 17:16:40Z batch), ALL match expected, no surprises:
| symbol | qty | qty_avbl | cost | cur_price (17:17 batch) |
|---|---|---|---|---|
| US.SPY | 28 | 28 | 731.54 | 701.90 |
| US.EFA | 142 | 142 | 100.495 | 97.01 |
| US.MSFT | 39 | 39 | 503.33 | 489.48 |
No change vs expected SPY 28 / EFA 142 / MSFT 39. No options/futures/shorts (all pstn_type 0).

## (b) LIVE QUOTES vs STOPS (final batch, quotes at 17:16:32-17:16:40Z; production tick evaluated 17:17:22-23Z; ages ~43-51s, all sec_status NORMAL, suspension false, tradable true)
- SPY last 701.899 (data_time 1795195000307). Daily-close stop 727.50 basis daily_close: Nov-19 completed close 715.87 BREACHED (-1.60% below stop); today's close (21:00Z) not yet available; intraday 701.9 is ~3.5% further below the stop.
- EFA last 97.0078 (data_time 1795194992206). Daily-close stop 100.00: Nov-19 close 98.78 BREACHED (-1.22% below stop); intraday 97.01 ~3.0% below stop.
- MSFT last 489.48 (data_time 1795195000224). No stop exists (no lifecycle grant). vs cost 503.33: -2.75% (-541.71 unrealized at broker cur_price 489.44).
Earlier batch at 17:08:33Z: SPY 702.84, EFA 97.075, MSFT 488.455 (data_time 1795194512-513s, age <60s at read).

## (c) EXIT-PATH STATUS PER OPEN LOT
- US.SPY 28: live exit request: NO. Production lifecycle tick (isolated state, approvals=[]): action=review, reason "held position has no approved lifecycle ownership", warning "research review expired or future-dated" (r2 reviews INVALIDATED, valid only to 14:15:49Z). No grant, no reservation, no submit_before, nothing latched. BREACHED daily-close stop has NO executable protection path — operator decision required (r3 adoption or directed exit).
- US.EFA 142: identical status to SPY (action=review, same reason/warning).
- US.MSFT 39: reported as gap "US.MSFT: held position missing a complete lifecycle plan" — unowned incident fill, no grant of any kind.
DIAGNOSTIC (synthetic in-memory approvals + contract copies in run-dir state/diag-book.json / diag-state.json, refs literally "DIAGNOSTIC-NOT-APPROVED"; NOT approvals, nothing recorded, nothing submitted; production decision above is what governs): with the r2 hashes approved, the engine evaluates SPY 28 sell @699.80 reason stop_loss and EFA 142 sell @96.72 reason stop_loss (authorized=true inside the sandbox only, daily-close basis using close evidence 715.87/98.78 at 2026-11-19T21:00:00Z); synthetic MSFT adoption showed action=review "missing review for this exact plan revision" + warning "completed daily-close evidence unavailable for this lifecycle" (engine demands a fresh review even when the stop anchor is evaluable). This demonstrates the would-exit logic exists; it is UNREACHABLE in production because approvals=[] and halt is ENGAGED.

## (d) PENDING / UNRESOLVED ORDERS
Full unfiltered history: single page orders-1.json, pagination.has_more=false, next_key "0". 11 orders total ever. No order is pending-open:
- VNQ buy 83 @94.98, order_id …6597, status 5, cum_qty 0, created 2026-11-18T17:53:07Z, updated 2026-11-19T01:01:00Z — status5 REMAINS UNRESOLVED (not proven terminal); manual-review flag preserved. Frozen cash 0 consistent with inactivity.
- SMH buy 10 @454.48, order_id 3118500, status 5, cum_qty 0, created 2026-11-19T17:25:10Z, updated 17:27:07Z — status5 UNRESOLVED.
- All other 9 orders status 4 (fully filled, cum == qty), incl. MSFT 39 @503.33 fill (3118578, 2026-11-19T18:15:21Z, text tyche-tac-…, the unowned incident fill) and the Nov-19 round-trip set.
Most recent exit-request outcome: NONE — no sell order of any kind exists in the full history for SPY/EFA/MSFT; zero live exit requests anywhere.

## (e) WRITER CHECK
Latest order create_time in the account = 2026-11-19T18:15:21Z. NO new orders since 2026-11-20 14:00Z (nor since the Nov-19 incident window). No evidence of an active second writer this session.

## (f) VERBATIM ENGINE OUTPUTS
Production lifecycle tick (17:17:22Z, isolated state copies, no --record): gaps ["US.MSFT: held position missing a complete lifecycle plan"]; decisions: LC-20261119-SPY-ADOPT-r2 action=review reason="held position has no approved lifecycle ownership" warnings ["research review expired or future-dated"] authorized=false; LC-20261119-EFA-ADOPT-r2 identical. Full JSON in this report's tool transcript; hash confirmed nothing latched (see state note).
Tactical tick dry (17:15:30Z, RTH midday phase, halt-aware journal): orders []; decisions AMD/MU/SMH each action=wait reason="outside tactical universe; ETF ballast has its own planner"; alerts ["monitor starting or heartbeat gap; rebuild entry confirmations", "unprotected tactical positions: US.MSFT; block new entries"]; submitted false. MSFT itself produced NO entry decision (watchlist Nov-19 entries expired; universe=[US.MSFT] only; options_enabled=false; execution blocked by halt + unprotected-position guard).
Tactical scalp PB-004 dry (--record omitted; 17:15:38Z): orders []; decisions NVDA/AMD/AVGO/MU/SMH each action=wait reason="entry quote missing/stale"; alerts []; submitted false. NOTE: config/scalp.yaml symbols are NVDA,AMD,AVGO,MU,SMH — NOT MSFT; the briefed bars-US.MSFT.json was fed but is outside the scalp symbol set, and no quotes/books exist for the five scalp symbols, so all wait on missing/stale entry quotes. Nothing was sized, latched or reserved.

## (g) NAV RECONCILIATION (account ***598)
Final 17:16:40Z batch: total_asset 98,194.731 = balance(cash) 45,680.121 + frozen 0.00 (hold=0) + broker MV 52,514.610. Per-position MV / %NAV: SPY 19,653.20 = 19.99%; EFA 13,775.42 = 14.01%; MSFT 19,088.16 = 19.43%. Cash 46.52%. Weights sum 99.96% (MV-vs-quote rounding; engine snapshot.nav 98,196.90 computed from live last prices vs broker total_asset 98,194.73 — 0.002% drift, normal tick jitter).
Drawdown vs HWM pin 102,208.99 = -3.93% (SOFT drawdown 4% approached; hard 6%); vs prior_close_nav 99,914.93 = -1.72%. Earlier reads this fire: 98,116.95 (17:07Z), 98,248.99 (17:12Z), 98,143.22 (17:14Z), 98,169.07 (17:14:17Z) — intraday MV jitter only.

## (h) GATE FAILURES / GLITCHES (exact strings)
1. lifecycle capture --out must be a FILE: first attempt at directory failed "[Errno 21] Is a directory: 'state-tick.<uuid>.tmp' -> 'state-tick'"; retried with --out state-tick/market-US.json — OK.
2. tactical tick un-prefixed: alert "paper account verification failed" (allowlist gate; expected).
3. tactical snapshot freshness: captured_at = min mtime of accounts/cash/positions; stale 17:11 accounts.json tripped "stale/missing account snapshot; no orders"; fixed by re-reading the FULL batch incl. account list (no mtime touching), then clean.
4. tactical scalp feed: "feed missing accounts.json" on scalpdry (accounts not staged); fixed by copying REAL payloads, then clean.
5. lifecycle diagnostic tick on the 17:12 capture: "broker snapshot stale or future-dated; fetch again" (>120s); re-read batch then OK.
6. state.json hash changed after production tick WITHOUT --record (02f…-era file rewritten by locked_state); content diff vs pre-tick copy shows SEMANTICALLY IDENTICAL (approvals=[], reservations=[], latched_exits={}, last_tick_at=null; only serialization whitespace). Isolated run-dir copy only; production untouched. Flagging as an engine quirk: dry tick does rewrite the state file bytes.
7. quote_stock_quote provides no bid/ask; two-sided data came from quote_order_book (NASDAQ+ARCA, LV2, timestamps 1795194522-523ms and 1795194806ms).

## (i) ARTIFACTS
run-dir /data/drive/tyche-raw/2026-11-20-midday-1705/
- mcp/: accounts.json (REAL ids), accounts.masked.json, cash.json, positions.json, orders-1.json (top-level pagination.has_more=false), quotes.json, book-US.{SPY,EFA,MSFT}.json, bars-US.MSFT.json (10x 1-min, 16:59-17:08Z), market-state.json — verbatim MCP responses; oldest broker read 2026-11-20T17:07Z batch.
- capture/ (final 17:17 batch + closes.json US.SPY 715.87 / US.EFA 98.78 / US.MSFT 498.30 @2026-11-19T21:00:00Z); state-tick/market-US.json sha 5822450471e7221b8e7c0fbe0057f77e8fa3dd05161852ff7fcb68c3110e04c2.
- state/: book.json sha 02f781288ba113d3729cece98b7399821c4afbe56385be7d94927208fad243a6 (unchanged); state.json semantically unchanged (see h.6), pre-tick copy state-before.json; DIAGNOSTIC artifacts diag-book.json sha 398c6ffc…, diag-state.json sha 3344c673… (NOT grants); watchlist-copy.json (from premarket production copy), scalp-envelope-placeholder-UNUSED.json (empty {}; never read — --record omitted).
- tacfeed/, scalpdry/: raw + normalized tactical payloads (tactical-account.json / tactical-quotes.json produced by capture; capture rewrites these normalized views from raw inputs each run).
- journal/events.jsonl sha 9c1cfd659c8ff2a03f332b518fe212c79ce512b4bbac512528ebb63e10c3eb66 (29 events, verify_chain OK in tactical tick/scalp paths; NOT appended). halt.json copied from premarket journal dir (evidence staging only).

## PROTECTION GAPS (SHOUT)
1. SPY 28 + EFA 142: daily-close stops BREACHED on completed Nov-19 bars; r2 INVALIDATED; NO approved lifecycle ownership, NO live exit, NO broker-native stop. Exposure 34.0% NAV with no executable protection path; further ~3% below stops intraday. Operator exit-vs-hold decision still pending; close fire needs fresh reviews + r3/directed-exact-grant path.
2. MSFT 39 (~19.4% NAV): unowned incident fill, no grant, no stop, no review; flagged by both lanes ("unprotected tactical positions: US.MSFT; block new entries" tactical alert is a hard block).
3. Two unresolved status5 orders (VNQ …6597, SMH 3118500) remain manual-review flags with no engine clear path.
4. Soft drawdown -3.93% vs HWM pin approaches the 4% soft limit; hard 6% at ~96,076 NAV — today's tape is moving toward it.
5. Halt remains ENGAGED per journal; repo data/halt.json stale-resume (Nov-18) is not a release. No entries permitted regardless of the above.
