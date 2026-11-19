# Halt / kill-switch runbook

The kill-switch blocks buys but always allows de-risking sells. Every transition is
journaled. `tyche halt` writes both flags, never edit them by hand:

- `journal/halt.json` - desk-local, persisted on Drive.
- `data/halt.json` - shared, committed so cloud sessions see it through the git mount.

Either flag halts. Agents and operators should read the merged state with
`tyche halt-status --json` rather than opening one file.

## Commands

```bash
tyche halt --reason "stale feed / drawdown / operator veto"
tyche resume
tyche halt-status --json
```

- `halt-status` prints the effective halt (`halted`, `reason`, `ts`, `source`).
- `plan` reads the flag and sets `RiskState.halted`, so buys are blocked at planning.
- `execute` reads the flag and withholds buys (journaling `halt.skip`), submitting only
  approved sells. A halted plan with no sells submits nothing.
- Journal events: `halt.engaged`, `halt.released`, `halt.skip`.

## When to halt

- Stale or missing prices; auth failure; journal chain invalid.
- Drawdown at the soft ladder and deteriorating, or any hard-limit breach.
- Anomalous fills, repeated rejects, or a monitor cadence miss.
- Operator veto for any reason — no justification required to stop.

## Kill-switch drill (G10)

Run the drill on the **personal paper account** before the competition account is
armed. The competition account cannot be reset, so never drill on it.

### Local deterministic drill (no broker, run any time)

```bash
.venv/Scripts/python.exe -m pytest tests/test_halt.py -q
```

Proves: engage → buy blocked (`halt.active`) → sell allowed → release, with an
intact journal chain (`halt.engaged` then `halt.released`).

### Live paper drill (operator-authorized, personal paper account)

1. Confirm the account is the personal US paper account (`account_type` 1,
   `market_id` 100), id injected via `TYCHE_ALLOWED_ACCOUNT_IDS`. Never the
   competition account.
2. Build a small plan with one approved buy and one approved sell; review the preview.
3. `tyche halt --reason "kill-switch drill"`.
4. `tyche execute --plan <plan> --account-id <personal-paper-id> --yes`.
   Expect: the buy is withheld (`halt.skip` journaled), only the sell submits.
5. Reconcile via the executor (`sim_trade_order_list`); confirm no buy order exists.
6. `tyche resume`; verify `halt.released` and `tyche journal-verify`.
7. Persist the drill artifacts (see [persistence.md](persistence.md)) and record the
   outcome in `docs/validation/`.

A submit is not a fill. The drill passes only when broker order state confirms the
buy never reached the market and the sell did.

### Live paper drill via MCP (no moomoo CLI needed)

`tyche execute` shells out to the official moomoo CLI binary (local-only path). If
it is not installed, run the same drill through the authenticated Moomoo MCP
connector with the operator-side agent acting as executor — the same submission
path the cloud desk uses:

1. Same account rule: personal US paper account only (`account_type` 1,
   `market_id` 100), id via gitignored local `.env` / `TYCHE_ALLOWED_ACCOUNT_IDS`.
2. Fetch accounts/cash/positions via `sim_trade_*` MCP reads into a run dir; run
   `tyche snapshot --dir <run> --account-id <personal-id>`.
3. Build a small plan with one approved buy and one approved sell of a held
   position via `tyche plan`; review the preview. If the account holds nothing,
   seed one small position first (unhalted, paper, operator-authorized).
4. `tyche halt --reason "kill-switch drill"`.
5. Withhold the buy and journal it: `tyche record-order halt.skip --data '{...}'`.
   Submit ONLY the sell via `sim_trade_input_order` after the operator preview;
   journal `order.requested` before and `order.submitted` after via
   `tyche record-order`.
6. Reconcile via `sim_trade_history_order_list`: no buy order exists; the sell is
   present.
7. `tyche resume`; `tyche journal-verify`; persist the drill artifacts and record
   the outcome in `docs/validation/`.

The kernel's halt-withholding logic is proven deterministically by
`tests/test_halt.py`; this variant additionally proves broker-side behavior on
the MCP submission path.

## Veto

The human operator may veto any plan before arming. A veto is a halt with reason
"operator veto"; the agent does not override it or re-plan around it without review.