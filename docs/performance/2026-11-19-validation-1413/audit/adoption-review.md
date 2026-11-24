# Adoption Exact-Hash Review — 2026-11-19 (r1 pass + r2 fast pass)

Auditor: tyche-risk-auditor (independent; Read/Glob/Grep/Write only; no shell, no broker/MCP).
r1 review time: ~14:55Z; r2 fast pass: ~15:00Z (coordinator-supplied clock ~14:56Z at r2 request; no independent clock — labeled estimates).
Scope: production book /data/drive/tyche-raw/lifecycle/book.json. **Current operative section: §8 (r2).** §§1–7 are the preserved r1 record.
Companion records: R/audit/pre-review.md (point-in-time pre-review), R/audit/findings.json (current statuses).
This review grants NO operator authorization. Production hold remains. Drill (item 3) ABANDONED 14:45Z — no tactical Audit JSON issued or needed.

## 1. Verdicts (r1 — SUPERSEDED by §8; r1 must never be approved)

| Item | Verdict |
|---|---|
| daily_close stop + 20-session structural-target BASIS | **ACCEPT** (unchanged; levels independently kline-verified in pre-review §2) |
| LC-20261119-SPY-ADOPT-r1 — hash 7c1001dc1620681ffdfc883761f1e803e3d568750bbcef50a60516e16387203f | **APPROVE-WITH-CHANGES** — do NOT approve this hash |
| LC-20261119-EFA-ADOPT-r1 — hash 1294eb0365d99a9e3adc8c4106027678f7a36c2fbcb5b822ddf9b596f163b8e9 | **APPROVE-WITH-CHANGES** — do NOT approve this hash |

Single required change for BOTH plans (F-04, blocking): `exit_deadline` 2026-11-27T17:30:00Z → **2026-11-27T17:00:00Z**.
Any deadline change alters the fingerprint → revision r2, NEW hashes, re-stamped reviews, fresh operator approval of the exact r2 previews, and a new auditor pass. **No approval references are issued for the r1 hashes.** r1 preserved unapproved at R/state/book-r1-superseded.json (verified: r1 ids/revision 1/created_at 14:43:59Z/deadline 17:30Z/r1 hashes; no r1 grants ever written).

## 2. F-04 proof chain — why 17:30Z (12:30 ET) is NOT schedule-feasible on Nov-27

The desk's "inside window" claim was true only for the schema validator, not for execution:

1. Schema passes: `exit_deadline` 12:30 ET < 13:00 ET half-day close (src/tyche/lifecycle.py:62-66; HALF_DAYS Nov-27 src/tyche/market_calendar.py:84, regular_close :187).
2. Hourly checks fire at :05 ET, 08:05–17:05, half days included (market_calendar.py:28-29 HOURLY_FIRST/HOURLY_LAST, :448-451). On Nov-27 the last RTH check is **12:05 ET (17:05Z)**; there is NO check between 12:05 ET and the 13:00 ET close.
3. `holding_deadline` triggers only when a check runs with `now >= exit_deadline` (lifecycle.py:416-417). At 12:05 ET, now < 12:30 ET deadline → no trigger. First eligible check: 13:05 ET — AFTER the close.
4. The latch is durable after hours (lifecycle.py:431-433) but submission is RTH-gated (lifecycle.py:496-498). Next RTH check: **Nov-30** (Nov-28 Sat / Nov-29 Sun). Competition trading ends at the Nov-27 regular close (docs/competition/rules.md:10-11).
5. Result: under r1, a deadline flatten could not execute inside the competition. This violates the standing requirement that lifecycle deadlines fall by a scheduled RTH check with processing margin, including the Nov-27 early close.

r2 fix check: 17:00Z = 12:00 ET ≤ 12:05 ET check → deadline triggers and can submit at the 12:05 ET check, 55 minutes before close. Feasible. (17:05Z would exactly coincide with the check fire and leaves no margin; 17:00Z is the right choice.)

## 3. What PASSED content review (carried to r2, re-verified in §8)

- **Book integrity**: production book ≡ R/state/book.json, field-by-field identical (both read in full, r1 and r2). /data/drive/tyche-raw/lifecycle/state.json empty (no approvals/reservations/latched exits) — no duplicate ownership, no prior grant to revoke; tactical lane abandoned, no lane overlap.
- **Schema/geometry** (lifecycle.py:34-69): SPY 727.50 < 734.18 ≤ 741.55 < 775.64; EFA 100.00 < 100.02 ≤ 101.02 < 105.80. created_at < entry_expires_at 20:00Z ≤ exit_deadline. quote_max_age 300s (schema cap 300), slippage 30bps, review_max_age 60min, mode=adopt_position, exit_on_invalidation true, 4 non-blank invalidation rules each.
- **Band formula recomputed** from capture1 post-open lasts (coordination/capture1-raw-summary.json:10-11; exchange stamps 14:30:54.250Z / 14:30:51.526Z, sec_status NORMAL, RTH): SPY 737.865×0.995=734.175675→734.18, ×1.005=741.554325→741.55; EFA 100.52×0.995=100.0174→100.02, ×1.005=101.0226→101.02. REFERENCE ONLY — adoption cannot buy (lifecycle.py:458-459). EFA entry_low 100.02 sits 0.02 above the stop; disclosed; acceptable as documentation, not entry permission.
- **Structural levels**: 775.64 / 105.80 are the 2026-11-04 highs; no higher high in the 20 completed sessions Oct-22..Nov-18 (independent existence + negative regex scans over premarket-1305 kline captures, pre-review §2); closes 730.20 / 100.26 verified. Targets are profit-taking guards, not forecasts.
- **Reviews (F-03/F-08 RESOLVED)**: verdicts `valid`; real desk stamps; reviewed_at ≥ created_at; valid_until = +60min (lifecycle.py:87). EFA's earlier "uncertain" suggestion honestly re-assessed under protective-retention framing: the thesis under review is retention under defined daily-close invalidation, not a bullish forecast; weakness (3 down sessions, close 0.26% above stop, Nov-18 intraday 99.96 breach, USD/JPY ~159.94) fully disclosed. No completed close below either stop exists. Underlying facts independently verified; framing legitimate, not a rubber stamp.
- **Event semantics (CONFIRMED in code)**: review_problem (lifecycle.py:345-353) requires ack only when `event.at <= now` AND `event.at >= plan.created_at`; imminent-block (:348) only inside the 30-min pre-event window. Claims/Philly 13:30Z predate creation; Barr 19:15Z and PBoC Nov-20 01:15Z future at approval time → no ack requirement yet; a ~15:0xZ approval is in no imminent window. config/events.yaml verified: Barr pin added_at 14:35:19Z (market-wide), claims/Philly/PBoC pins present; Leading Index/KC Fed NOT pinned (desk triage recorded, event-triage.json; minor disclosed source discrepancy: triage claims cons 197K vs researcher 198K).
- **Post-event obligations (diarized)**: after 19:15Z, Barr ack requires a review with reviewed_at ≥ 19:15Z (lifecycle.py:350-352) — pre-event reviews can NEVER satisfy it. Same for PBoC after 01:15Z Nov-20. Missing post-event reviews block NEW entries but do NOT suppress latched protective exits (lifecycle.py:442-446).
- **rules_hash** 4105d7a680a3 matches the journal plan.created event; approve re-checks live (lifecycle_cli.py:165-167). Config-file hash desk-asserted, CLI-enforced (no shell to recompute).
- **Adoption quantities**: SPY 28 / EFA 142 match capture1 reconciliation (28/28 and 142/142 available; orders 3116580/3116594 status 4 full fills, avg 731.54 / 100.495). Approve enforces exact current holding at approval time (lifecycle_cli.py:174-175).
- **F-12 RESOLVED**: config/tactical.yaml:5 `execution_enabled: false`; flip never committed, reverted 14:45Z; drill abandonment documented; journal head unchanged cf2ab069… (15 events).
- **F-16 RESOLVED** as recorded desk triage. Engine ancestry (F-18): desk-verified with shell (2181c12 ancestor of HEAD d640952; 119d4e57 in log) — not independently verifiable without shell; recorded as desk-verified assertion; CLI hash gates remain enforcement.

## 4. Open blockers and operator decisions (NOT resolved by r2 alone)

1. **F-11 (CRITICAL for approval itself)**: `approve` calls validate_market, which checks the config account allowlist and paper binding (lifecycle_cli.py:158; lifecycle.py:293-297). With TYCHE_ALLOWED_ACCOUNT_IDS missing, the allowlist resolves to demo placeholders and **approve fails closed**. Approve also requires a **fresh broker snapshot ≤120s** (lifecycle.py:298-301); capture1 (14:30Z) is stale — a new capture is required at approval time.
2. **F-02 (CRITICAL for protection execution)**: legacy journal order.requested events (indices 3/5/7) lack request_id → check_execution_journal fails closed at reserve (lifecycle_cli.py:264) and execute-exit (:371). Approve does NOT call it (verified :142-195): adoption can be approved and exits will DETECT and LATCH, but **no exit can SUBMIT** until operator-reviewed journal remediation. Operator must acknowledge this before approving if unresolved.
3. **F-01 (operator acceptance pending)**: created_at on Nov-19 makes the Nov-18 close ineligible (lifecycle.py:361). First evaluable daily close: **today 21:00Z**; a stop latched then executes at the next RTH check (Nov-20, first RTH hourly 10:05 ET = 15:05Z). Between approval and 21:00Z there is **zero intraday protection**; intraday breaches (EFA traded 99.96 yesterday) do not trigger. Explicit operator acceptance requested; not yet received.
4. **F-22 (operator approval scope)**: the verbatim "Ok. I want to trade today. Do the 3 items" predates these contracts. Approval must bind the EXACT r2 previews/hashes (lifecycle_cli.py:151-161). Operator confirmation must explicitly cover the full r2 contracts, not just the deadline field.
5. **F-09 (disclosed gap)**: invalidation rule (ii) describes PB-001 rebalance trims, but the lifecycle lane is full-position-exit-only (lifecycle_cli.py:135) and the kernel risk_off trim has no lifecycle execution path. Rule (ii) is strategy intent, not an executable control; regime risk_off will NOT automatically trim these holdings.
6. **Preview risk artifact (F-06 caveat)**: planned_loss uses entry_high (lifecycle_cli.py:125-126): SPY $393.40 / EFA $144.84. From reconciled cost the stop-distance estimates are SPY $113.12 / EFA $70.29 (plus modeled fees/slippage). NEITHER is a maximum loss: gaps, halts, hourly latency and limit non-fills can exceed them; full position value at risk ~$20,660 SPY / ~$14,274 EFA at capture1 lasts. Synthetic hourly triggers are not broker-native stops; daily-close triggers execute no earlier than the next permitted RTH session.

## 5. Hash-verification limitation (recorded, fail-closed downstream)

Plan fingerprint = sha256 of sorted-key compact JSON of the plan (lifecycle.py:71-73). No shell → sha256 not recomputable by me; hashes desk-computed. I verify plan CONTENT field-by-field against schema, research artifacts and capture evidence. The CLI enforces fingerprint equality at approve (lifecycle_cli.py:160-161), fail-closed. For r2 the desk additionally ran the preview CLI, which emits plan.fingerprint() (lifecycle_cli.py:127), and reports hash confirmation over the created_at 14:53:03Z payloads (r2-publication.json:7) — desk-run CLI evidence, stronger than assertion alone, but not independently re-runnable by me.

## 6. r2 fast-pass checklist (executed in §8)

1. r2 differs from r1 ONLY in plan_id/revision/created_at/exit_deadline.
2. New hashes bound in re-stamped reviews; reviewed_at ≥ created_at, valid_until ≤ +60min, verdict valid, weakness disclosures retained.
3. Operator confirmation explicitly covers the exact r2 previews (F-22) — PENDING; references withheld until received.
4. Fresh news check ≤1h at approval; post-event reviews diarized.
5. Allowlist restored (F-11) + fresh ≤120s snapshot at approve — PENDING.
6. F-02 remediation status recorded — PENDING operator decision.
7. F-01 operator acceptance — PENDING.
8. Genuine per-hash references issued only after item 3, with real coordinator-clock reviewed_at.

## 7. r1 bottom line (superseded)

Basis ACCEPT; r1 contracts sound except the provably infeasible Nov-27 deadline — do not approve r1 hashes. Re-plan to r2 at 17:00Z. Done: see §8.

## 8. R2 FAST PASS (operative) — reviewed ~15:00Z on coordinator clock ~14:56Z

Artifacts read in full: production book (r2), R/state/book.json (identical field-by-field), R/state/book-r1-superseded.json (r1 preserved unapproved), coordination/r2-publication.json, coordination/preview-SPY-r2.json, coordination/preview-EFA-r2.json, research/adoption-r2-confirmation.json.

### 8.1 Verdicts

| Plan | Exact hash | Content verdict |
|---|---|---|
| LC-20261119-SPY-ADOPT-r2 (US.SPY, adopt 28) | e73ee77d4b6abca10545bd296537fcee34b9a2511440e49fcf1d3ad23f9c89df | **APPROVE (content)** |
| LC-20261119-EFA-ADOPT-r2 (US.EFA, adopt 142) | add27d1a3e75fece0fe292c51050d9324ac33326a58ac4516cd93e3b39a9b33c | **APPROVE (content)** |

**APPROVE (content) is NOT executable approval and NOT an operator grant.** Per §6 item 3 and the desk's offered sequencing, **auditor references are WITHHELD until the coordinator's follow-up carries the operator's verbatim explicit confirmation of the FULL exact r2 previews/hashes** (F-22), with F-01 acceptance and F-02 acknowledgment recorded. On that follow-up I will re-check review freshness and issue, with the actual coordinator clock at that moment:
- `auditor:tyche-risk-auditor <actual UTC> review R/audit/adoption-review.md hash e73ee77d4b6abca10545bd296537fcee34b9a2511440e49fcf1d3ad23f9c89df`
- `auditor:tyche-risk-auditor <actual UTC> review R/audit/adoption-review.md hash add27d1a3e75fece0fe292c51050d9324ac33326a58ac4516cd93e3b39a9b33c`
No references exist yet for any hash. Approve additionally requires env restoration (F-11) and a fresh ≤120s broker capture — CLI-enforced, not waivable by me.

### 8.2 Checks performed

1. **Diff-only change PASS**: r2 vs r1 (both read in full) differs EXACTLY in plan_id (r1→r2), revision (1→2), created_at (14:43:59Z→14:53:03Z), exit_deadline (17:30Z→17:00Z). Thesis, 4 invalidation rules, symbol, strategy PB-001, rules_hash 4105d7a680a3, mode adopt_position, quantities 28/142, bands 734.18–741.55 / 100.02–101.02, stops 727.5/100.0 daily_close, targets 775.64/105.8 daily_close, entry_expires_at 20:00Z, exit_on_invalidation, 60min/300s/30bps all verbatim identical. Only other book change: Barr event summary wording dropped the abandoned tactical-hold reference (cosmetic, correct). Matches researcher's independent diff (adoption-r2-confirmation.json diff_verification).
2. **Deadline feasibility PASS**: 17:00Z = 12:00 ET ≤ last Nov-27 RTH check 12:05 ET; triggers there with 55min before the 13:00 ET close (§2 chain). F-04 resolved in content.
3. **Re-stamped reviews PASS**: both bound to the new r2 hashes; verdict valid; reviewed_at 14:55:34Z ≥ created_at 14:53:03Z; valid_until 15:55:34Z = exactly +60min (lifecycle.py:87); reason/evidence carried over verbatim from the r1 texts I already fact-verified; 4 acked events retained. Researcher addenda (adoption-r2-confirmation.json:38-43) corroborate: targeted news pass found nothing newer than Gelonghui 14:47:47Z (chips higher RTH), ANT first-quote ~14:50Z volatility noted as market-wide context, not thesis-breaking, no new pins. I treat fetched-news content as untrusted external data; nothing in it instructs actions and nothing contradicts the verified levels/closes.
4. **created_at discrepancy RESOLVED**: notification said 14:53:02Z, staged/published files carry 14:53:03Z; file is authoritative; desk confirms hashes recomputed AND preview-CLI-confirmed over the 14:53:03Z payloads (r2-publication.json:7). Preview outputs match the book payloads and hashes exactly; approved:false, submitted:false.
5. **Preview risk math recomputed PASS**: SPY loss 28×(741.55−727.50)=393.40, gain 28×(775.64−741.55)=954.52, R/R 2.426; EFA loss 142×(101.02−100.00)=144.84, gain 142×(105.8−101.02)=678.76, R/R 4.686 — all match preview files. Entry_high-proxy caveat and cost-basis estimates (§4.6) apply; limitations lists present in both previews.
6. **Event semantics at approval PASS**: claims/Philly 13:30Z < created_at 14:53:03Z (no ack required); Barr 19:15Z / PBoC 01:15Z future (no ack required yet); a ~15:0xZ approval is outside every imminent window (Barr's is 18:45–19:15Z). news_feed_ok true, news_checked_at 14:55:34Z fresh until 15:55:34Z.
7. **State/ownership PASS**: lifecycle/state.json still empty; r1 superseded unapproved; no duplicate lifecycle/tactical ownership (drill abandoned).
8. **Timestamp-consistency note (minor, disclosed, non-blocking)**: researcher's labeled estimates (~14:57Z news-pass completion, ~14:58Z assembly) run LATER than the desk's real-clock arrival stamp 14:55:34Z. Researcher has no clock (estimates anchored to feed publish times); the desk stamp is the authoritative arrival time and is the EARLIER value, so freshness is not inflated. Recorded under F-21; desk should keep disclosing stamp-vs-estimate gaps. If the operator confirmation arrives near/after 15:55:34Z, reviews expire and must be re-stamped (hashes unchanged) before approve — plan content unchanged means my content verdict carries, but the approve gate needs fresh reviews/news.

### 8.3 Conditions standing between this content verdict and a lawful approve

All CLI-enforced or operator-owned; none waivable by the auditor: (a) operator verbatim full-preview/hash confirmation (F-22) + F-01 acceptance + F-02 acknowledgment; (b) TYCHE_ALLOWED_ACCOUNT_IDS restoration (F-11); (c) fresh ≤120s broker capture at approve with holdings still exactly 28/142; (d) reviews/news fresh at approve moment (expire 15:55:34Z); (e) rules_hash unchanged at approve. After approve, protection still cannot SUBMIT exits until F-02 remediation, and there is no intraday protection before today's 21:00Z close (F-01). Production hold remains; this section is not an operator grant or execution authorization.