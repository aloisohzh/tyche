# Runbooks

| File | What | Status |
|---|---|---|
| [operations.md](operations.md) | v0.1 setup + daily routine (Moomoo **CLI** path) | stale in part: cloud execution moves to MCP (review G1); `^SIM` guard superseded (G2) |
| daily-runbook.md | Window routine: pre-market plan → arm → monitor → EOD reconcile → persist | to write (P1) |
| [halt-kill.md](halt-kill.md) | Halt / kill-switch / veto procedure + the journaled drill | written (P0/G10); live drill pending operator authorization |
| [persistence.md](persistence.md) | Raw → bucket, sanitized → git; `tyche persist`; provisioning | written; bucket + PAT provisioning pending |
| [protection-monitor.md](protection-monitor.md) | What protects an open lot **today**: the 08:05/12:05/15:05 desk fires, the lifecycle commands they run, `protection.gap` | deployed path; checks are hours apart, not an around-the-clock monitor |
| [intraday-protection-monitor.md](intraday-protection-monitor.md) | The [ADR 0013](../adr/0013-protection-monitor.md) monitor contract: tick I/O, trigger kinds, cadence ladder, contention, alert de-dup, drill | **draft for review, nothing deployed**; hard prerequisite for options |
| incident.md | Stale feed, auth failure, partial fill, restart reconcile, journal break | to write |

The daily runbook must end with **persistence** (raw → bucket, sanitized → git) — the sandbox is
ephemeral and the evidence is 60% of the score.