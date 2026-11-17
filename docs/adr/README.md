# Architecture decision records

One decision per file. Format: context → decision → consequences → status.

| id | Title | Status |
|---|---|---|
| [0001](0001-hybrid-architecture.md) | Hybrid architecture (deterministic core + LLM perimeter) | accepted |
| [0002](0002-paper-only.md) | Paper only | accepted (guard mechanism superseded — see proposed 0008) |
| [0003](0003-risk-kernel.md) | Deterministic risk kernel | accepted |
| [0004](0004-regime-etf-rotation.md) | Regime ETF rotation reference strategy | accepted (repositioned as ballast) |
| [0005](0005-audit-journal.md) | Hash-chained audit journal | accepted |
| [0006](0006-llm-perimeter.md) | LLM perimeter contract | accepted |

## Proposed (from the 2026-11-18 review — write on operator approval)

| id | Decision |
|---|---|
| 0007 | Scope cut for the window: park gauntlet/Docker/6-agent/live-flip governance/rubrics |
| 0008 | MCP broker adapter + account allowlist (replaces CLI + `^SIM`) |
| 0009 | Persistence: raw → bucket, sanitized → git |
| 0010 | Fee model + EOD reconcile; competition cap deltas |
| 0011 | 3-role topology + delegation contract + version pins |
| 0012 | Defined-risk options leg groups + synthetic protection |

Parked decisions (post-window) are listed in the review, not written as ADRs yet.