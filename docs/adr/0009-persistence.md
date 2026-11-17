# ADR 0009: Persistence — raw to a bucket, sanitized to git

Status: Accepted, 18 November 2026.

## Context

A Cloud Agent sandbox is ephemeral. The journal, plans, receipts, and MCP
payloads are the primary evidence for the 30% Qoder-usage and 30% design
criteria; if they vanish at session end, the work cannot be scored or audited.
At the same time, full account ids, tokens, and raw payloads must not land in a
public repository.

## Decision

Two sinks, written every run:

- **Raw → object storage.** Journal, MCP read/write payloads, plans, and receipts
  go to an OSS bucket mounted via the `oss-bucket-2026-09-23` beta. This is the
  append-only system of record.
- **Sanitized → git.** Id-free, token-free artifacts (plans, risk verdicts,
  fee-net performance, playbooks, reviews, the dashboard data) are committed and
  pushed so the repo is a reproducible public record.

A sanitize step strips full account identifiers and credentials before anything
reaches git. The PAT used for pushes and bucket access is least-privilege and
held server-side in a gitignored `.env` / vault, never in the repo or chat.

## Consequences

- Durable evidence survives sandbox teardown; the public repo stays clean.
- Requires provisioning a bucket and a scoped PAT (tracked as the persistence
  task) before the first cloud run.
- The sanitize step is a hard gate: a run that cannot sanitize must not push.

## Alternatives considered

- Git only: rejected — raw payloads and ids would either leak or be lost.
- Bucket only: rejected — forfeits the public, version-controlled reproducibility
  the documentation criterion rewards.