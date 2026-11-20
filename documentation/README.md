# tyche product documentation

This directory holds the **descriptive** layer: what the platform is, what it does today, and how that
changed over time. The **prescriptive and evidentiary** layers stay where they are:

| Question | Where it is answered |
|---|---|
| What is the product, and which features actually exist? | [PRD.md](PRD.md) |
| How is it built, and how does data and control flow? | [architecture.md](architecture.md) |
| Why was it built this way? | [../docs/adr/](../docs/adr/) - one decision per file |
| How do I run it, halt it, or recover it? | [../docs/runbooks/](../docs/runbooks/) |
| What did the last review find? | [../docs/reviews/](../docs/reviews/) |
| What broke before, so we do not repeat it? | [../docs/lessons/LESSONS.md](../docs/lessons/LESSONS.md) |
| What happened on the desk (fills, vetoes, halts)? | `journal/events.jsonl`, read through [../docs/performance/](../docs/performance/) |

## Rules for this directory

- **Current state, not intention.** Every capability carries a status from the fixed vocabulary below.
  A planned feature in the present tense is a defect in this directory, not a roadmap item.
- **No mechanism prose.** Architecture detail lives in [architecture.md](architecture.md); a PRD section
  that starts describing *how* a component is implemented has drifted and should move there.
- **Version on substance.** [CHANGELOG.md](CHANGELOG.md) gains an entry when the described product
  changes, not when prose is polished. The PRD header carries the version; the changelog carries history.
- **Links over copies.** Caps belong to `config/risk.yaml` and [../docs/risk-card.md](../docs/risk-card.md);
  roster entries belong to [../playbook/INDEX.yaml](../playbook/INDEX.yaml). Quote a number here only if a
  test asserts it matches the source, which is why [../tests/test_docs_consistency.py](../tests/test_docs_consistency.py)
  exists.

## Status vocabulary (fixed)

| Status | Means |
|---|---|
| **implemented** | Runs in the paper desk; covered by a test or a journal record |
| **partial** | The mechanism exists but a named condition, lane, or consumer is missing |
| **experimental** | Built to answer a question; not relied on and expected to be cut or promoted |
| **planned** | Agreed scope, no code |
| **deprecated** | Superseded and kept for context; moved to [../archive/](../archive/MANIFEST.md) when inert |

Promoting or demoting a status is a documentation change with a changelog entry, because it changes
what a reader may assume the desk will do unattended.
