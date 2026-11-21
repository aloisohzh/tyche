# Synthetic-breach drill - 2026-11-21 - PASS (pinned rehearsal); live-session run still owed

The gate [ADR 0013](../adr/0013-protection-monitor.md) puts between the monitor and options
enablement: [runbook §8.4](../runbooks/intraday-protection-monitor.md) demands a synthetic lot walked
end to end - breach -> detection -> alert -> operator confirmation -> exit reserved, never submitted -
with zero broker writes. This is that run, driven by
[`scripts/drill_synthetic_breach.py`](../../scripts/drill_synthetic_breach.py), which is the artifact
the drill leaves behind: it is re-runnable, it fails loudly, and it can only write inside `data/drill/`.

| Criterion (runbook §8.4) | Result | Evidence |
|---|---|---|
| Breach detected and journaled | **PASS** | 1 `monitor.breach` on the breach tick, `synthetic_stop`, level 470.00 vs quote 455.00 |
| De-duplication by transition | **PASS** | repeat tick at the same price emitted `monitor.heartbeat` only; `duplicate_on_repeat: 0` |
| Alert text | **PASS (rendered, not delivered)** | `render-digest` accepted the urgent digest: 1,160 chars, ref `63faf7ea`, all §7 fields present |
| Alert delivered to Telegram | **NOT RUN** | rung 1 bark routing is not approved; the drill calls `render-digest`, never `send-digest` |
| Operator confirmation step | **NOT RUN** | needs the operator at the desk; the drill renders what they would read |
| Exit reserved, never submitted | **PASS** | `tactical reserve` -> `authorized: true`, `submitted: false`, request `tyche-tac-f0b0...`, `submit_before` +30s |
| Retry cannot double-book | **PASS** | second reserve exits `1`: "unresolved/resting order; reconcile before any further write" |
| Episode closes with a duration | **PASS** | `monitor.clear`, `duration_seconds: 135.0` |
| `protection.gap` zero for a handled episode | **PASS** | `gap_events: 0`, `coverage_ok: true` on every heartbeat |
| Measured latency stated | **PASS, with the caveat below** | detection tick 97.4 ms, digest render 576.4 ms, reserve 129.7 ms |
| Zero broker writes | **PASS** | order history on both US paper accounts identical before/after; no broker import in the code path |
| Journal fingerprint before/after | **PASS** | real journal 89 events, `sha256 bb8252dd...a806` unchanged, `journal-verify` OK |
| No envelope/config/approval file touched | **PASS** | 11 protected files hashed (`data/approvals.json`, the draft, the halt flag, every `config/*.yaml`): `protected_files_changed: []` |

## Legs, as the drill recorded them

Clock pinned to Wednesday 2026-11-25, one leg per minute, so the fixture behaves like a morning
instead of a burst.

| # | Leg | Exit | Measured | What landed on the scratch chain |
|---|---|---|---|---|
| 0 | Calendar gate, real process at the real clock (2026-11-21T03:15Z = Fri 22:15 ET) | 1 | 4,232.8 ms | nothing - "NOT RUN outside the regular session (closed)" |
| 1 | Tick, quote 490.00 | 0 | 103.0 ms | `monitor.heartbeat` |
| 2 | Tick, quote 455.00 (through the stop) | 0 | 97.4 ms | `monitor.breach`, `monitor.heartbeat` |
| 3 | Tick, same price | 0 | 119.8 ms | `monitor.heartbeat` only |
| 4 | Urgent digest, rendered | 0 | 576.4 ms | not a journal event; text + ref recorded in the report |
| 5 | `tactical reserve` | 0 | 129.7 ms | `tactical.monitor`, `order.requested` (2 total incl. the seeded entry) |
| 6 | `tactical reserve` again | 1 | 83.1 ms | refused; event count unchanged |
| 7 | Tick, quote back to 490.00 | 0 | 98.9 ms | `monitor.clear` (135.0 s), `monitor.heartbeat` |

Scratch chain after the run: 9 events, chain valid. Submission-shaped events anywhere in it: none
(`order.submitted`, `order.receipt`, `order.filled` all absent).

## What the drill cannot measure, and did not pretend to

- **Schedule latency.** Legs 1-7 run the desk's own command objects in-process with a pinned clock, so
  the numbers above are *judge-and-journal* times, not "how long after the market moved did the desk
  know". Wake-up latency belongs to runbook §9 step 4 (the cross-process lock on a real schedule),
  which is still open. The report carries this in `not_measured`.
- **Delivery and human reaction.** No Telegram send (rung 1 unapproved), no operator present.
- **The pinned clock itself.** The chain stamps the real wall clock while the commands judge on the
  rehearsal clock, which is exactly why the §8.3 replay rule matters - see the defect below.

Re-run without `--at` inside a regular session and legs 1-7 execute on the wall clock; that run is
what closes §8.4, and it should be done with the operator present so the confirmation leg is real.

## Fixture disclosure (honesty)

`US.MSFT` is a real tactical-universe symbol, but the lot is not real: 10 shares nobody holds, stop
470.00, a quote pushed from 490.00 to 455.00 by the fixture files, account id `SIM-DEMO-US` (the
committed demo id - a real account id never enters a drill file), NAV 30,000 synthetic. The
envelope is kernel-generated for the drill and lives on `data/drill/envelope.json`; it is not an
operator approval and is never copied to `data/approvals.json`. The collar, the universe, the
quote/snapshot freshness limits and every authorization rule are the desk's real config, loaded
from `config/`.

## The defect the drill found (and fixed)

`monitor.open_episodes` and `monitor.last_heartbeat_at` measured from the journal's **append stamp**
rather than the market time carried in the event payload. On the first rehearsal that produced
`duration_seconds: 386832.1` - 4.5 days of exposure for a 135-second breach - because the fixture
judged on a pinned clock while the writer stamped the real one. In production the two clocks
coincide, which is why 22 unit tests missed it; under §8.3 replay, which is how any breach decision
gets reviewed, it would have been wrong. Both functions now prefer the payload's `observed_at` /
`tick_at` and fall back to `ts` only for events written before those fields existed.

Guard: `tests/test_monitor_tick.py::test_exposure_is_measured_from_the_print_not_from_the_append`.
Logged as [L-043](../lessons/LESSONS.md).

## Alert text the operator would have read

```text
TYCHE OPENING_DRIVE - URGENT RISK ALERT
2026-11-25T14:38:05+00:00
PAPER - Level 0 protection monitor (synthetic drill)

One journaled level breached. Nothing here is a live position.

Orders
10 US.MSFT shares reserved for exit; zero orders submitted.
ACTION   SYMBOL   QTY
RESERVE  US.MSFT  10

US.MSFT: limit 455.00, floor 446.50 | reserved, never submitted by this drill
synthetic_stop: quote at or below the journaled stop 470.00 (source journal_contract, exit DRILL-...125-MSFT-SYNTH)

Account
NAV: 30,000.00 (synthetic) / Cash: 25,450.00 (synthetic)
Positions: 1 synthetic lot, 10 shares / Kill-switch: not engaged

Protection
- US.MSFT 10 shares: last 455.00 vs stop 470.00; armed floor 446.50 (stop widened by 5.0%).
- Episode b679e39220db7f8f opened 2026-11-25T14:36:55+00:00.
- Do: confirm or cancel the reserved exit on the desk. The kernel will not submit it.
- Setup DRILL-...125-MSFT-SYNTH, expiry 2026-12-25, sleeve equity.

Problems
- Synthetic drill fixture: lot, quote and account id are not real.
```

(HTML tags stripped here; the renderer emitted `<b>`/`<pre>` markup and masked nothing because no
7-digit id appeared.)

## Evidence pointers

- Reproduce: `.venv/Scripts/python.exe scripts/drill_synthetic_breach.py --at 2026-11-25T14:35:00+00:00`
  -> exit 0, `verdict: PASS`. Off-session without `--at` -> exit 1, `verdict: INCOMPLETE` with the
  refusal reason, never a silent pass.
- Raw run artifacts (gitignored scratch, regenerated on every run): `data/drill/drill-report.json`
  `sha256 6129c171b5ab734b12c874adebf6b41d812e84b5bd7225b121fd1b264653b265`, `data/drill/digest.json`
  `sha256 87dd751cb8da6c8c3008e52cc2d1857762ffb7c8f6744f95988eb7c4bf2963ef`.
- Broker reads (MCP, read-only): `sim_trade_history_order_list` on …748 newest order `3115472`
  (2026-11-18 drill sell) and on …598 newest `3118578` (2026-11-20 MSFT buy 39) - both before and
  after the drill, byte-identical.
- Kernel and tests: [../../src/tyche/monitor.py](../../src/tyche/monitor.py),
  [../../src/tyche/monitor_cli.py](../../src/tyche/monitor_cli.py),
  [../../tests/test_monitor_tick.py](../../tests/test_monitor_tick.py) (23 tests), suite 553 passed.
