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

Two further findings from the same pass, neither of which changes the decision:

- **The thesis layer moved** to `/playbook` on 2026-11-20, so the isolation-unit table above
  reads `docs/playbooks/PB-xxx-*.md` where the files are now `playbook/PB-xxx-*.md`.
  `docs/playbooks/README.md` remains as a pointer. Because the `playbook:` path lives inside
  the hashed yaml, the move re-froze PB-001 to `becd112bcac8` with trading parameters
  byte-identical - a third "new hash, same rules" entry in a lineage that has no journal
  producer, which is the cost of putting a documentation pointer under a rules hash.
- **The contract covers one lane, not three.** `tactical.py` and `scalp.py` stamp
  `PB-002`/`PB-003`/`PB-004` onto intents, but only `pb-001.yaml` exists, so `rules_hash()`
  raises for the others and the re-freeze discipline this ADR mandates cannot be enforced on
  the two live short-horizon lanes. See
  [audit §3.8](../reviews/2026-11-20-platform-refinement-audit.md) and L-036.

## Resolution of the freeze source (2026-11-20)

Both findings above are closed at the rules layer; neither is closed at the provenance layer.

- **Every emittable id now resolves to the bytes that govern it.** `PLAYBOOK_LANES` in
  `src/tyche/config.py` maps id -> (rules file, enabling switch): PB-001 to
  `config/strategies/pb-001.yaml`, PB-002 and PB-003 to `config/tactical.yaml`, PB-004 to
  `config/scalp.yaml`. `rules_hash()` resolves through it instead of assuming the
  `config/strategies/<id>.yaml` convention, and an unmapped id with no file raises a message
  naming both fixes rather than a bare `FileNotFoundError`. PB-002/PB-003 share one hash by
  construction: they are one lane with one parameter file, so a tactical edit re-registers the
  pair. That is stated in the roster, not discovered in an incident.
- **The doc pointer left the frozen bytes.** The `playbook:` key is gone from
  `StrategyConfig` and from `pb-001.yaml`; id -> thesis now lives in `playbook/INDEX.yaml`.
  Moving the library can no longer re-freeze a strategy (L-037). PB-001's hash moved a fourth
  time to `819ad06e35f0`, mechanically computed and recorded with its cause; every trading
  parameter is byte-identical to `becd112bcac8`.
- **The enabled check reads the lane, not one config shape.** `lifecycle.decide()` called
  `strategy_by_id()`, which only knows rotation strategies - the tactical and scalp lanes would
  have looked up an id that is not in `config.strategies`. `AppConfig.strategy_enabled()` and
  `enabled_playbook_ids()` now own that question, and they are what the desk and Scout will ask.

Still open, and deliberately not papered over: there is **no `rules.refrozen` producer**, so the
four PB-001 hashes above are git archaeology rather than journal records (L-035). The CI assertion
that a declared hash equals the kernel's is the guarantee that the doc and the bytes agree; the
journal row would be the guarantee that the change was *registered when it happened*, and that one
is still not enforceable.

## Amendment (2026-11-21, the producer landed)

`src/tyche/freeze.py` and `tyche rules-freeze` (`src/tyche/cli.py:1360`, 18 tests in
`tests/test_rules_freeze.py`) are the writer this ADR assumed, so the paragraph above is no longer the last word.
What it does and does not buy:

- A row states the lane's `new_hash`, the full sha256 of both hashed sources, the playbook's `declared` hash, and an
  `old_hash` taken **from the chain alone** (`previous_from: "journal"`; `null` and `rules.frozen` for a lane the
  chain has never held). A record therefore cannot assert a lineage the journal does not contain. The mis-recorded
  `569eb2c341e0` was written by hand with no producer to compute it from the bytes; nothing can do that again
  through this command.
- Registering is refused for the whole run - not just for the offending lane - when a playbook declares a hash the
  kernel computes differently. The tool will not journal a freeze over a document that disagrees (L-030).
- Still not enforceable: **timing**. Nothing intercepts a rules edit; the comparison runs when someone runs it, and
  CI only proves the doc and the bytes agree. The PB-001 hashes before `819ad06e35f0` stay git archaeology - this
  records today's state, it does not backfill.
- What it did on landing: with the operator's approval the command registered all four hashable lanes on
  2026-11-21 (`rules.refrozen` PB-001 as event `5f1b2b82b48a`, `rules.frozen` for PB-002 `1664156d6346`, PB-003
  `4f3e84d163ec` and PB-004 `5f6d8ab3cc1d`; chain 89 -> 93 events). From the next rules edit onward, a re-freeze is
  journaled with its cause, its sources and the previous hash the chain actually held.
