# Architecture decision records

One decision per file. Format: context → decision → consequences → status.

| id | Title | Status |
|---|---|---|
| [0001](0001-hybrid-architecture.md) | Hybrid architecture (deterministic core + LLM perimeter) | accepted |
| [0002](0002-paper-only.md) | Paper only | accepted (guard mechanism superseded by [0008](0008-mcp-adapter-allowlist.md)) |
| [0003](0003-risk-kernel.md) | Deterministic risk kernel | accepted |
| [0004](0004-regime-etf-rotation.md) | Regime ETF rotation reference strategy | accepted (repositioned as ballast) |
| [0005](0005-audit-journal.md) | Hash-chained audit journal | accepted |
| [0006](0006-llm-perimeter.md) | LLM perimeter contract | accepted |
| [0007](0007-scope-cut.md) | Scope cut for the window | accepted |
| [0008](0008-mcp-adapter-allowlist.md) | MCP adapter + account allowlist + execution split | accepted |
| [0009](0009-persistence.md) | Persistence: raw → bucket, sanitized → git | accepted |
| [0010](0010-fees-and-caps.md) | Fee model + EOD reconcile; competition caps | accepted |
| [0011](0011-topology.md) | 3-role topology + delegation + version pins | accepted |
| [0012](0012-options-protection.md) | Defined-risk options leg groups + synthetic protection | accepted |
| [0013](0013-protection-monitor.md) | Intraday protection monitor (watchlist, cadence, heartbeat) | proposed (design draft) |
| [0014](0014-per-strategy-isolation.md) | Per-strategy isolation (config, hash, code entry per playbook) | accepted (implemented 2026-11-19) |
| [0015](0015-external-research-perimeter.md) | External research perimeter: local LEAN validation lane + journaled charting | accepted (amended: hosted QC MCP needs paid node) |

Parked decisions (post-window) are listed in the
[2026-11-18 review](../reviews/2026-11-18-design-review.md), not written as ADRs yet.