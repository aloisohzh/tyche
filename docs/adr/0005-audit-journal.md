# ADR 0005: Hash-chained JSONL audit journal

Status: Accepted, 17 November 2026.

## Context

The agent runs unattended on a schedule. Judges and operators need to answer
what was decided, on what data, and in what order. Plain logs are mutable and
easy to edit after the fact, while a database adds operational weight for a
two-week paper-trading project.

## Decision

Write events to `journal/events.jsonl` as append-only JSON Lines. Each event
contains a UTC timestamp, type, payload, the previous event's hash, and its own
SHA-256 hash computed over canonical JSON (sorted keys, compact separators).
The first event uses a fixed genesis hash. `journal-verify` recomputes the chain
and reports the first record that does not match.

Plans, approvals, submissions, fills, rejections, reports, and run failures are
journaled with enough detail to reconstruct the decision.

## Consequences

- Tampering with any record invalidates all later hashes.
- The journal is human-readable and trivially archived.
- There is no deletion or redaction path; secrets must never enter it.
- Concurrent writers could interleave appends. The current design assumes a
  single scheduled writer; scaling out would need a lock or a database.
- The chain proves internal consistency, not external timestamping. A future
  improvement is to publish the latest hash to an external location once a day.

## Alternatives considered

- Plain text logs: rejected because they are mutable and unstructured.
- SQLite: rejected for operational simplicity and diffability.
- External ledger: rejected as unnecessary for the scope.
