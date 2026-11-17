# ADR 0006: LLM output is commentary, not control

Status: Accepted, 17 November 2026.

## Context

The Cloud Agent can read market news and reason about context in a way a fixed
rule set cannot. It can also be wrong, prompt-injected by external text, or
unavailable. If its output influences order construction, every failure becomes
a trading failure.

## Decision

Constrain the LLM to three jobs: pre-market research brief, pre-trade critique,
and end-of-day narrative. Each job has a strict template and a maximum length.
The critique receives the immutable plan artifact and may only return concerns
and a confidence note. It cannot edit the plan, and an empty or malformed
response changes nothing.

External content (news, web pages, social posts) is treated as untrusted data,
never as instructions. The agent ignores any directive embedded in fetched
content. No LLM output is executed as code or shell input.

## Consequences

- Prompt injection cannot move money.
- LLM value is visible in reports and journal entries but is not load-bearing.
- The critique is advisory; a human or the scheduled run must decide whether a
  concern warrants changing parameters in configuration before the next plan.
- Templates must be versioned alongside code so outputs stay comparable.

## Alternatives considered

- LLM critique with veto: rejected because it adds latency and nondeterminism
  without a testable safety benefit.
- LLM-generated targets: rejected under ADR 0001.
- No LLM: rejected; it weakens the Qoder and documentation criteria.
