# Halt / kill-switch runbook

The kill-switch blocks buys but always allows de-risking sells. Every transition is
journaled. The flag is `journal/halt.json`, written only by the CLI — never by hand.

## Commands

```bash
tyche halt --reason "stale feed / drawdown / operator veto"
tyche resume
```

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

## Veto

The human operator may veto any plan before arming. A veto is a halt with reason
"operator veto"; the agent does not override it or re-plan around it without review.