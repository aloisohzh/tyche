# ADR 0014: Per-strategy isolation — one config, one hash, one code entry per playbook

Status: Accepted, 19 November 2026 (operator decision; implemented same day,
ahead of PB-002 — see implementation note).

## Context

Playbooks are already isolated: one file per setup in `docs/playbooks/`
(`PB-001-*.md`), a template, and a README index. Adding or retiring a thesis is
a file operation. The executable side is not:

- `src/tyche/strategy.py` implements exactly one algorithm (regime ETF rotation)
  with no id, registry, or dispatch.
- `config/strategy.yaml` is a single flat file; `AppConfig.strategy` holds one
  `StrategyConfig`. There is no `enabled` flag and no playbook reference.
- `pipeline.py` hardcodes `PLAYBOOK = "PB-001"`, and `rules_hash()` hashes the
  entire `strategy.yaml` + `universe.yaml`.

The hash coupling is the concrete defect: pre-registration freezes a playbook's
rules by hash (PB-001 is pinned at `946b3ef31a3d`). The moment a second
strategy's parameters land in the same yaml, PB-001's frozen hash breaks even
though its rules never changed. "What worked / what didn't" cannot be isolated
if every edit invalidates every freeze. The 2026-11-18 review already settled
the direction: strategies are in-process plugins behind a contract; containers
are post-window.

## Decision

One id (`PB-xxx`) links three artifacts, each independently addable/removable:

| Layer | Artifact | Isolation unit |
|---|---|---|
| Thesis | `docs/playbooks/PB-xxx-*.md` | one file (already done) |
| Rules | `config/strategies/pb-xxx.yaml` | one file per strategy |
| Code | registry entry in `src/tyche/strategies/` | one module per algorithm |

1. **Per-strategy config.** `config/strategies/<id>.yaml` carries `id`,
   `enabled`, `playbook` (doc path), and the strategy's parameters. Each file
   validates against its own pydantic model. `config/strategy.yaml` migrates to
   `config/strategies/pb-001.yaml` unchanged in content; shared universe and
   risk stay global (`universe.yaml`, `risk.yaml`) — the risk kernel is never
   per-strategy.
2. **Per-strategy freeze.** `rules_hash(id)` hashes that strategy's yaml plus
   `universe.yaml`. Editing or retiring PB-002 can never invalidate PB-001's
   pre-registered hash. A universe edit legitimately re-freezes all strategies
   (it changes every strategy's tradeable set) and must be journaled.
3. **Registry, not a framework.** A plain dict mapping id → target function
   (`{"PB-001": rotation_targets}`) behind the existing
   `histories × config → RotationResult` contract. No dynamic imports, no entry
   points, no plugin discovery. `pipeline.py` takes the playbook id from the
   strategy config instead of the `PLAYBOOK` constant.
4. **Removal semantics.** Retiring a strategy = `enabled: false` (keeps the
   freeze and journal attribution intact) or deleting the file post-window.
   Disabled strategies are skipped by the runner but their configs still
   validate, so a broken freeze is caught even while parked.

**Deferred until two strategies run simultaneously:** capital allocation
between strategies and position netting when two strategies want the same
symbol. Until then the runner executes the enabled strategies sequentially
against the shared risk kernel, and the second strategy must trade symbols
disjoint from the first (enforced by a config-load check). This keeps the
window deliverable per ADR-0007 while making the allocator a pure addition
later.

## Consequences

- Pre-registration hashes become per-playbook; the audit trail can attribute
  performance and rule changes to one strategy without touching another.
- Adding PB-002 is three files (md, yaml, module) plus one registry line;
  removing it never perturbs PB-001.
- Migration cost is small but real: `AppConfig`, `load_config`, `rules_hash`,
  `pipeline.py`, and the CLI/dashboard callers change shape once. Do it in the
  same change that introduces PB-002, not as a standalone refactor.
- The disjoint-symbol constraint is a temporary limitation, stated honestly in
  the playbook, not a hidden one.
- Journal entries and plan artifacts gain the strategy id explicitly (today
  it is implied by the hardcoded constant).

## Alternatives considered

- **Keep one yaml, namespace keys per strategy inside it:** rejected — same
  hash-coupling defect, and merge conflicts on every strategy edit.
- **Full plugin framework now (dynamic loading, per-strategy capital sleeves,
  netting):** rejected — repeats the fortuna machinery-over-edge failure mode
  (ADR-0007); only one strategy is executable today.
- **Playbook md as the single source of truth, parsed for parameters:**
  rejected — prose is for judges, yaml is for the kernel; parsing markdown into
  trading rules is fragile and unauditable.

## Implementation note (19 November 2026)

Migration landed with PB-001 as the only strategy: `config/strategies/pb-001.yaml`
(parameter bytes unchanged, id/enabled/playbook metadata added),
`src/tyche/strategies/` package with `REGISTRY = {"PB-001": rotation_targets}`,
`rules_hash(root, strategy_id)`, and `tyche plan --strategy` (defaults to the
sole enabled strategy; explicit id required once several are enabled).

- **Freeze migration:** PB-001 re-frozen `946b3ef31a3d` → `569eb2c341e0`.
  Trading parameters are byte-identical; only file location and metadata
  changed. Recorded in the playbook's freeze history and journaled as
  `rules.refrozen`.
- **Deferred to PB-002:** the disjoint-symbol config-load check — it needs a
  per-strategy symbol scope, which only exists once a second strategy defines
  its tradeable set. The capital allocator and position netting stay deferred
  as decided above.

## Amendment (2026-11-20, refinement audit)

Two claims in the migration note above are wrong and are corrected here rather
than silently rewritten:

- `569eb2c341e0` **never matched the committed files.** Recomputing
  `rules_hash` at `010cd9b` yields `6d991165fa64`. The re-freeze was
  mis-recorded when it was written, not drifted afterwards, so the ADR 0014
  freeze contract did not actually hold for PB-001 at any point after the split.
- The `rules.refrozen` journal entry exists, but **no producer for it exists in
  the codebase**, and none of the later PB-001 rules changes raised one. PB-001's
  parameters then changed twice for real - `initial_stop_pct` at `43b85ca` and
  `allocation_cap: 0.25` at `7f61baf` - taking the hash to `7799974f9fd0` and
  `4105d7a680a3` with no re-registration.

The mechanism this ADR assumed (an automatic re-freeze record on every rules or
universe edit) is therefore still unbuilt, and is logged as required work in
[LESSONS.md L-030](../lessons/LESSONS.md). Until it lands, per-strategy isolation
holds for *file layout and hashing inputs* but not for *freeze provenance*.
`tests/test_docs_consistency.py` now asserts a declared playbook hash equals the
kernel's, which catches drift at the doc boundary but cannot reconstruct a
freeze event that was never written.