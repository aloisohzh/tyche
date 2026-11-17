# ADR 0002: Paper-only by construction

Status: Accepted, 17 November 2026.

## Context

The challenge provides a simulated US$100,000 account. Live orders need an
order preview and explicit confirmation every time, and a misrouted order
cannot be undone. The `moomoo sim order` path is not gated by the CLI's
dry-run confirmation, so the application must provide its own guardrail.

## Decision

Enforce paper-only in the risk kernel and in the broker adapter.

- The account ID must match `^SIM`; anything else is a breach.
- Only `moomoo sim` subcommands are exposed by the adapter. There is no live
  order method.
- Symbol markets are restricted to the configured allow-list (US).
- The adapter never reads or logs token files. Authentication is delegated to
  `moomoo auth login`.
- Execution requires a separate explicit step with confirmation. A plan is
  never submitted automatically by the planning command.

## Consequences

- A configuration mistake cannot route an order to a live account.
- Adding live support later requires a new ADR and a new adapter, not a flag.
- Operators must keep the Moomoo CLI authenticated; expiry stops the run.

## Alternatives considered

- A `--live` flag: rejected because a single typo is catastrophic.
- Relying on the CLI's dry-run gate: rejected because the simulation path is
  not gated and the gate can change between CLI versions.
