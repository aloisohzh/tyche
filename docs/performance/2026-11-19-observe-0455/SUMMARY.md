# Run 2026-11-19-observe-0455 — READ-ONLY observe/proposals run (FINAL SUMMARY)

Window: 2026-11-19 04:55–05:28 UTC (Nov 19 00:55–01:28 ET; market CLOSED, after-hours end).
Mode: OBSERVE ONLY. Zero broker writes, zero orders, zero approvals/reservations/receipts,
no tick --record, no config/schedule/cloud changes, no Telegram, no git push, no public publish.
execution_enabled=false hold intact. Hourly lifecycle monitoring deployed; orders UNARMED.

## Results
1. EXECUTOR (mcp/): challenge paper account [REDACTED] verified vs single-entry allowlist
   (account_type=2, market_id=100). Reads 04:59:07–05:00:11Z. NAV 99,927.13; cash 65,244.61
   (65.29%); frozen 0. SPY 28/28 @731.54 (MV 20,445.60, 20.46% NAV, uP&L −37.52);
   EFA 142/142 @100.495 (MV 14,236.92, 14.25% NAV, uP&L −33.37). No option/short/fractional
   exposure. All 3 orders ever reconciled: SPY/EFA status 4 = full fills; VNQ 83 @94.98
   status 5 cum 0 = never filled, frozen 7,884.33 released exactly; canceled-vs-expired
   semantics UNKNOWN (labeled, not guessed). No pending orders. History time-window params
   appear unhonored (anomaly logged); completeness via unfiltered has_more=false.
   Journal chain + 12 event hashes verified; NAV refs 99,914.93 / 100,000.00 confirmed;
   drift +12.20 / −72.87, far inside DD limits.
2. RESEARCHER (research/): fresh quotes stamped Nov 18 21:00:00(.268)Z regular close;
   15 completed daily bars each; hawkish FOMC minutes re-verified (3 timestamped sources);
   Dec 9 25bp HIKE >95% priced (second-hand, labeled); EFA fresh news missing → uncertain.
   11 sourced events; Nov 25 Core PCE/GDP = biggest scheduled risk; calendar empty days
   labeled coverage gap. All proposals PENDING-REFRESH (reviews expire 06:10Z < 13:05Z run).
3. COORDINATOR (plan/): book.json schema-validated on pinned engine 1e902cf5; previews exit 0
   (approved=false); capture exit 0; live tick exit 1 (stale closed-market snapshot, honest);
   replay tick on isolated synthetic EMPTY state (no --record) → both holdings "no approved
   lifecycle ownership", authorized=false, nothing latched. Cap semantics verified in code:
   allocation_cap 0.25 whole-sleeve vs max_weight per-name (SPY 0.30/EFA 0.20) — not conflated.
   Ballast 34.71% MV > 25% current sleeve budget (existing holdings; exits verified reachable).
   Release vs current config divergence documented (rules hashes 7799974f9fd0 vs 4105d7a680a3).
4. AUDITOR (audit/): DRAFT — NOT AN APPROVAL. Both plans APPROVE-WITH-CHANGES; C1–C6 PASS
   (C3 with sourced gaps); every risk number recomputed exactly; exit reachability line-verified;
   all activation blockers independently confirmed.

## Draft plan hashes (unapproved)
- LC-20261119-SPY-ADOPT-r1 8ca9176daf7d09b4030cc15cf5460896fd871ef2c66b48db60fc6f886fbdd954
- LC-20261119-EFA-ADOPT-r1 237408a874860bebfe8731bbfec7742d18f42e2dc717646b24afa46600903395
- book.json c710ffe137b968479694c4f34da7420a6ea1ad7beae3061700f5da8de342d166

## Operator decisions pending
- EFA anchor R/R 0.701 (<1; cost-basis 1.283) + uncertain verdict; stop tightness vs 8%
  initial_stop_pct design; SPY entry_low 726.80 vs observed 726.795 rounding (accept or r2).
- Sleeve-budget breach handling (34.71% vs 25% current-root budget) and reviewed config
  reconciliation before any activation.

## Activation blockers (all open)
Rollout hold/operator release; no production lifecycle ledger; durable single cross-lane
writer unproven (FUSE locks ≠ distributed); config/rules-hash reconciliation; fresh reviews +
quotes at check time; option round-trip + 120s tactical validation; broker drill; explicit
operator approval of exact previews/hashes.

## Next scheduled check
2026-11-19 13:05 UTC (08:05 ET) tyche-hourly: recapture fresh broker snapshot/quotes,
re-review both exact hashes, surface retained-exit coverage gap (no broker-native stops,
no approved ownership). Protection currently UNARMED.

## Directory map
mcp/ raw broker captures + logs + reconciliation.md + SHA256SUMS (PRIVATE, full IDs)
research/ drafts + raw quote/kline/calendar/news payloads + review-report.md
plan/ book.json, market.json (PRIVATE), previews, tick replay, risk-numbers.json,
      risk-report.md, coordinator-config-caps.md, capture/ (normalization inputs)
audit/ draft-audit.md, findings.json
reporting/ sanitized mirrors (account IDs masked) of all reports + book + market