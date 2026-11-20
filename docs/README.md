# tyche documentation

Two layers: **living source-of-truth md files** (version-controlled) and **generated review documents**
(dated snapshots read from the corpus + journal). Never hand-edit a generated snapshot.

## Index

| Path | What | Lifecycle |
|---|---|---|
| [competition/rules.md](competition/rules.md) | Distilled competition contract (numbers, fees, limits, judging) | living; verify vs official |
| [competition/scoring-map.md](competition/scoring-map.md) | Criterion → artifact → evidence → status | living |
| [reviews/](reviews/) | Dated design/product reviews (e.g. 2026-11-18 adversarial review) | append-only snapshots |
| [adr/](adr/) | Architecture decision records 0001-0016, one decision per file, status per row in [adr/README.md](adr/README.md) | one decision per file |
| [../playbook/](../playbook/README.md) | One setup per file: thesis, edge, entry, **invalidation**, sizing, exit | living; pre-register before trading |
| [risk-card.md](risk-card.md) | Every cap keyed + asserted by a test | living; doc-as-test |
| [runbooks/](runbooks/) | Operations, daily routine, halt/kill, EOD reconcile, incident | living |
| [validation/](validation/) | Pre-registration convention, NO-GO ledger, parked gauntlet | append-only verdicts |
| [lessons/](lessons/) | Engineering dead ends: failed integrations, deprecated guardrails, reverted mechanisms | append-only rows, evidence-linked |
| [performance/](performance/) | Generated metrics: equity, Sharpe, DD, scorecards, fee reconcile | generated from journal |
| [agent-rules.md](agent-rules.md) | Hard rules every agent and contributor obeys; required lessons reading before significant work | living; enforcement is duplicated in the cloud prompts |
| [agent-engineering.md](agent-engineering.md) | Topology, delegation contract, permissions, version pins, eval loop | living |
| [dashboard.md](dashboard.md) | Pipeline-as-spine dashboard framework, per-trade contract, panels, API plumbing | living |
| [../archive/](../archive/MANIFEST.md) | Superseded/stale artifacts, one manifest row each | frozen |

Top level: [DESIGN.md](../DESIGN.md) (v0.1 baseline, partially superseded - see the review),
[README.md](../README.md).

The old `.qoder/cloud-agent.md` deployment spec was archived to
[archive/cloud-agent-draft-2026-11.md](../archive/cloud-agent-draft-2026-11.md) in `6ee2b28`. It is a
stale draft (its own header says the CLI + OAuth path does not work in a sandbox); the hard rules it
carried now live in [agent-rules.md](agent-rules.md).

## Conventions

- **One decision per ADR**, one setup per playbook. Short files beat sprawling ones.
- Every claim in a report links to evidence: a journal row, a doc section, or a pinned template version.
- **Pre-register** a setup (freeze rules + hash) before it trades; a re-tuned rule is a new hypothesis.
- Record **rejections and vetoes with reasons**, not just fills.
- Engineering dead ends and deprecated guardrails get one row in [lessons/LESSONS.md](lessons/LESSONS.md);
  strategy verdicts stay in validation, live decisions in ADRs.
- No credentials, tokens, or full account identifiers in any committed file.
- Generated artifacts (`performance/`, reports) are readings of the journal; the journal is the truth.

## Iteration loop

1. Change code/config/prompt → 2. run tests + fixed eval prompts → 3. record an ADR or review note →
4. pin the new agent/skill version → 5. only **new sessions** pick it up → 6. journal the outcome.
Mid-window settings changes are logged and treated as a new trial (fortuna lesson).