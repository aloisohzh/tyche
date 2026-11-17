# Runbooks

| File | What | Status |
|---|---|---|
| [operations.md](operations.md) | v0.1 setup + daily routine (Moomoo **CLI** path) | stale in part: cloud execution moves to MCP (review G1); `^SIM` guard superseded (G2) |
| daily-runbook.md | Window routine: pre-market plan → arm → monitor → EOD reconcile → persist | to write (P1) |
| halt-kill.md | Halt / kill-switch / veto procedure + the journaled drill | to write (P0/G10) |
| incident.md | Stale feed, auth failure, partial fill, restart reconcile, journal break | to write |

The daily runbook must end with **persistence** (raw → bucket, sanitized → git) — the sandbox is
ephemeral and the evidence is 60% of the score.