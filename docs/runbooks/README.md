# Runbooks

| File | What | Status |
|---|---|---|
| [operations.md](operations.md) | v0.1 setup + daily routine (Moomoo **CLI** path) | stale in part: cloud execution moves to MCP (review G1); `^SIM` guard superseded (G2) |
| daily-runbook.md | Window routine: pre-market plan → arm → monitor → EOD reconcile → persist | to write (P1) |
| [halt-kill.md](halt-kill.md) | Halt / kill-switch / veto procedure + the journaled drill | written (P0/G10); live drill pending operator authorization |
| [persistence.md](persistence.md) | Raw → bucket, sanitized → git; `tyche persist`; provisioning | written; bucket + PAT provisioning pending |
| [protection-monitor.md](protection-monitor.md) | Intraday synthetic protection: watchlist, triggers, cadence, heartbeat, drill ([ADR 0013](../adr/0013-protection-monitor.md)) | design draft; implementation pending — hard prerequisite for options |
| incident.md | Stale feed, auth failure, partial fill, restart reconcile, journal break | to write |

The daily runbook must end with **persistence** (raw → bucket, sanitized → git) — the sandbox is
ephemeral and the evidence is 60% of the score.