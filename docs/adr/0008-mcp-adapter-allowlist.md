# ADR 0008: MCP broker adapter, account allowlist, and the cloud execution split

Status: Accepted, 18 November 2026. Supersedes the guard mechanism in 0002 and
the CLI transport in 0001.

## Context

The v0.1 broker shells out to the Moomoo CLI and authenticates via OAuth. Neither
works in a Cloud Agent sandbox: there is no interactive browser login and the CLI
binary is not the cloud path. The `^SIM` account regex also rejects the real
competition account, which is a numeric paper id (`account_type` 2, `market_id`
100), not a `SIM-` prefixed id.

## Decision

Split execution by capability:

- The **executor agent** calls the Moomoo MCP sim tools. It fetches read JSON
  (accounts, funds, positions, quotes, klines, today's orders) and submits
  approved orders **verbatim** — exact symbol, side, quantity, limit price,
  remark — with no discretion to alter a plan.
- The **Python core** stays deterministic. It consumes MCP JSON through the
  payload-agnostic `extract_*` walkers, builds the account snapshot, plans, and
  runs the risk kernel. It reconciles fills from MCP order JSON. A submit is not
  a fill.

Replace the regex guard with an allowlist conjunction:

- `env == "paper"` (a live env is always refused);
- `account_id` is in `RiskPolicy.account_allowlist`. Demo ids are committed;
  real ids are injected at load from `TYCHE_ALLOWED_ACCOUNT_IDS` (vault/env) and
  never written to the repo;
- when the snapshot `source` is not `demo`, require `account_type == 2` and
  `market_id == 100`, verified against the sim account list.

MCP submit is non-idempotent. On timeout or unknown outcome, query today's orders
before any further write; never retry a submission blindly.

## Consequences

- The kernel remains pure and unit-testable; the executor is a thin relay.
- Live reuse later is an adapter swap plus an env change, not a rewrite — but
  live is out of scope for this agent and remains refused by the guard.
- Full account ids never appear in committed files, reports, or the journal.

## Alternatives considered

- Keep the CLI and run it locally only: rejected — the cloud path is the scored
  path, and a local-only agent forfeits the Qoder-usage criterion.
- Let the LLM executor size or adjust orders: rejected — determinism and the
  auditor approval gate must sit in code, not in model discretion.