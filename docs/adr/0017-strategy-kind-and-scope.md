# ADR 0017: Strategy kind and per-strategy symbol scope

- Status: Accepted (implemented 2026-11-22 with PB-007)
- Date: 2026-11-22
- Deciders: operator (accepted the PB-007 configuration plan), desk-head
- Related: ADR 0014 (per-strategy isolation), ADR 0016 (R budget), playbook PB-007

## Context

ADR 0014 deferred two things "until the second strategy": a per-strategy symbol scope, and the
disjoint-symbol check that needs it. PB-007 (fib 50% pullback) is that second strategy, and it is
not a rotation: it is a swing trade with a stop, a target and a holding deadline, which is the
lifecycle contract, not target weights. Wiring it exposed three facts about the kernel:

1. `load_config` validated every `config/strategies/*.yaml` against the rotation model, so a file
   with different parameters could not load at all.
2. The lifecycle lane's buy path passed the ballast universe to the risk kernel as the membership
   set (`universe.membership`), summed the allocation cap over the universe, and looked sleeves up
   in the universe. A symbol outside `universe.yaml` could never be bought, and adding PB-007's
   names to the universe would have handed them to the rotation and re-frozen PB-001.
3. The tactical lane forces a same-day `exit_at`, so it cannot carry a multi-day swing.

## Decision

1. **`kind` discriminator.** A strategy yaml declares `kind` (`rotation` by default, so
   `pb-001.yaml` is byte-identical and its hash `819ad06e35f0` survives; `fib_pullback` for PB-007).
   `load_config` picks the pydantic model by kind. Both models carry the cap fields the lifecycle gate
   reads (`enabled`, `allocation_cap`, `max_weight`, `sleeve_caps`), so one `decide()` serves both.
2. **Per-strategy scope.** A scoped strategy lists its own `symbols` and a `sleeve`.
   `AppConfig.scope_symbols(id)` returns that set (the universe for an unscoped rotation), and
   `sleeve_map(id)` the matching sleeves. `lifecycle.decide` uses the scope for membership, the
   allocation sum, the per-name cap and the sleeve passed to the risk kernel and the calendar gate.
   `tyche expectancy` and `tyche strategy-score` read `sleeve_map()` over every lane so fills attribute.
3. **One lane owns a symbol.** `load_config` refuses an enabled scoped strategy whose symbols overlap
   the universe, the enabled tactical lane, the enabled scalp lane or another scoped strategy. This
   is the ADR 0014 deferred check, now real.
4. **Lifecycle generators are registered, not framework-loaded.** `LIFECYCLE_GENERATORS` in
   `src/tyche/strategies/__init__.py` names the scanner module per id beside the rotation `REGISTRY`;
   `tyche fib-scan` is the only caller. `tyche plan` runs rotation strategies only.
5. **PB-007 rides the lifecycle lane.** The scanner emits complete `LifecyclePlan` proposals;
   preview, researcher review, exact-order audit, operator approval, reserve and executor submission
   are the existing path. Nothing in the approval or execution contract changed.

## Consequences

- Adding a scoped strategy is a yaml with `kind`, a scanner module, a registry line and a playbook,
  with `universe.yaml` untouched; PB-001's freeze is never disturbed by it.
- The allocation-cap sum check (`rotation caps + tactical stock + option premium <= gross`) now counts
  an enabled scoped strategy. Enabling PB-007 at 20% with the tactical stock cap at 45% exceeds 95%,
  so the operator must lower the tactical cap (the 20% is carved from it) before flipping the switch.
  That is a rules change to `config/tactical.yaml` and re-freezes PB-002/PB-003; it is deliberately
  not done in the same change as this ADR.
- `playbook_switches()` labels a scoped lane by its kind; `PLAYBOOK_LANES` maps PB-007 explicitly so
  the "every stamped id has a lane" guard holds.
- The sleeve cap for a scoped lane equals its allocation cap in every regime over its own symbols; the
  ballast's regime sleeve caps do not apply to it, and vice versa.

## Alternatives considered

- **Add PB-007's names to `universe.yaml` with a `sleeve`:** rejected - the rotation would trade them,
  PB-001 would re-freeze, and the rotation would then need its own scope filter anyway.
- **Run PB-007 through the tactical watchlist:** rejected - the planner rejects any entry without a
  same-day exit and stamps PB-002 on every stock intent.
- **A generic strategy plugin loader:** rejected again (ADR 0007, 0014) - two kinds and a dict are
  enough, and the second kind reuses the whole lifecycle contract.
