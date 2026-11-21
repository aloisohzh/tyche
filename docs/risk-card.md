# Risk card

Every guard below is enforced in code and asserted by a named test. This card is
the human-readable index of the risk kernel; the tests are the executable proof.
Run `pytest -q` to re-verify. Config keys live in [config/risk.yaml](../config/risk.yaml)
unless noted. See [ADR 0003](adr/0003-risk-kernel.md), [0008](adr/0008-mcp-adapter-allowlist.md),
and [0010](adr/0010-fees-and-caps.md).

## Account guard (conjunction — all must hold)

| Condition | Rule id | Config / source | Test |
|---|---|---|---|
| `env == "paper"` | `account.paper_only` | snapshot `env` | `test_live_env_is_blocked_even_for_allowlisted_id` |
| id in allowlist | `account.paper_only` | `account_allowlist` + `TYCHE_ALLOWED_ACCOUNT_IDS` env | `test_live_account_is_blocked`, `test_numeric_account_outside_allowlist_is_blocked` |
| non-demo source ⇒ `account_type ∈ {1,2}` ∧ `market_id==100` | `account.sim_verified` | `sim_account_types`, `sim_market_id`; sim account list | `test_sim_source_requires_us_paper_market`, `test_sim_source_rejects_unknown_account_type`, `test_personal_paper_type_one_is_allowed`, `test_allowlisted_competition_account_is_allowed` |

Real account ids are injected at load from vault/env and never committed; only
demo ids (`SIM-DEMO-US`, `SIM-TEST`) appear in config. The competition account is
`account_type` 2; the personal US paper account is `account_type` 1 — both are paper
(`market_id` 100), so both pass. The execute command also re-checks allowlist
membership and sim-account-list presence before any submit.

## Order and price guards

| Guard | Rule id | Config key | Test |
|---|---|---|---|
| Market in allowlist | `market.allowed` | `allowed_markets` | `test_disallowed_market_is_blocked` |
| Symbol in universe | `universe.membership` | universe.yaml | `test_outside_universe_is_blocked` |
| Usable last price | `price.available` | — | `test_missing_price_is_blocked` |
| Last price ≥ $1.00 | `price.minimum` | `min_price` | `test_competition_min_price_is_one_dollar` |
| Limit within 3% of last | `price.limit_deviation` | `max_limit_deviation_pct` | `test_limit_price_deviation_is_blocked` |
| Notional ≤ 30% NAV | `order.max_notional` | `max_order_notional_pct` | `test_order_notional_cap`, `test_order_notional_at_cap_is_allowed` |
| Initial risk ≤ 1% NAV per buy (qty × (limit − stop)) | `trade.risk_budget` | `risk_per_trade_pct` | `test_kernel_blocks_initial_risk_above_budget` |
| Notional ≥ $500 (unless closing) | `order.min_notional` | `min_order_notional` | `test_below_min_notional_is_blocked` |
| No short sells | `position.no_short` | `allow_short=false` | `test_sell_beyond_holding_is_blocked` |

## Portfolio and exposure guards (buys; de-risking sells exempt)

| Guard | Rule id | Config key | Test |
|---|---|---|---|
| Single-asset weight ≤ 40% (+0.25% tol) | `position.max_weight` | `max_position_weight`, `cap_tolerance_pct` | `test_single_asset_weight_cap` |
| Position count ≤ 100 | `position.count` | `max_positions` | `test_max_positions_blocks_new_symbol` |
| Gross exposure ≤ 95% (+tol) | `portfolio.gross` | `max_gross_exposure` | `test_projected_sell_frees_capacity_for_later_buy` |
| Cash floor ≥ 5% (no tolerance) | `portfolio.min_cash` | `min_cash_weight` | `test_minimum_cash_floor` |
| Sleeve cap per regime (+tol) | `sleeve.max_weight` | strategies/pb-001.yaml `sleeve_caps` | `test_sleeve_cap_is_enforced` |

## Stateful guards (accumulate within the batch)

| Guard | Rule id | Config key | Test |
|---|---|---|---|
| Halt blocks buys, allows sells | `halt.active` | runtime `halted` | `test_halt_blocks_buys_but_allows_sells` |
| Hard drawdown ≥ 6% blocks buys | `drawdown.hard` | `hard_drawdown_pct` | `test_hard_drawdown_blocks_buys` |
| Soft drawdown ≥ 4% halves qty | (note) | `soft_drawdown_pct` | `test_soft_drawdown_halves_buy_quantity` |
| Daily loss ≤ −2.5% blocks buys | `loss.daily_limit` | `daily_loss_limit_pct` | `test_daily_loss_limit_blocks_buys` |
| Orders/day ≤ internal budget | `orders.daily_count` | `max_orders_per_day` | `test_daily_order_count` |
| Daily turnover ≤ cap (buys) | `turnover.daily` | `max_daily_turnover_pct` | `test_turnover_cap`, `test_turnover_exemption_for_de_risking_sells` |

## Operator authorization: the envelope and the one exit number the operator owns

Autonomy inside this platform is bounded by a dated, signed `ApprovalBatch`
(`data/approvals.json`), never by a model's confidence. Two facts are worth stating
plainly because they decide what the operator is actually agreeing to:

| Fact | Where | Test |
|---|---|---|
| A drafted exit sell sits `exit_collar_pct` = 5% below the stop the plan journaled | `risk.exit_collar_pct` (0 < x <= 0.20), applied in `src/tyche/envelope.py` | `test_the_collar_is_the_only_operator_number_and_it_widens_downward` |
| Only the operator's arm click writes `data/approvals.json`; drafting writes `data/approvals.proposed.json`, which is gitignored | `propose_exit_envelope` (drafts) vs `arm_envelope` (approves) in `dashboard/server.py` | `test_arm_from_draft_is_the_only_writer_of_the_envelope` |

The collar is deliberately the *only* number in that path the operator sets. Stops,
quantities and symbols come from the journal and the broker book; anything the kernel
cannot ground (no journaled stop, an option with no verified contract, a bearish put
that exits by buying back) is refused with a reason rather than filled in with a guess.
An envelope carries no `max_notional` on purpose: a sell that fills *above* its floor
would consume budget an exit note was never measuring, and quantity plus the floor
already bound it. Same-day validity is kept — a note dated yesterday protects yesterday's
book, so arming it is refused.

Related caps: `option_risk_per_trade_pct`, `max_option_premium_pct` (option lanes) and
`max_limit_deviation_pct`, which is entry-limit drift and a different quantity from the
exit collar above.

## Competition maxima vs tyche internal discipline

The kernel enforces tyche's stricter internal budget; the competition maxima are
ceilings we stay well inside.

| Limit | Competition | tyche internal | Where |
|---|---|---|---|
| Min price | $1.00 | $1.00 | `min_price` |
| Single asset | ≤ 40% | ≤ 40% hard, target ≤ 38% | `max_position_weight` + strategy sizing |
| Positions | ≤ 100 | ≤ 100 | `max_positions` |
| Executed orders/day | ≤ 200 | ≤ 120 | `max_orders_per_day` |
| Min market cap | $500M | $500M | `universe.min_market_cap_usd` (research-stage gate) |

The market-cap gate is applied when the universe is built (the kernel has no
market-cap feed), not per order.

## Fee model and EOD reconcile

Fees are modeled from the handbook schedule (`source="model"`) because the sim
MCP exposes no fee fields. See [src/tyche/fees.py](../src/tyche/fees.py).

| Component | Stocks | Options |
|---|---|---|
| Commission | $0 | $0.65/contract (premium > $0.10) else $0.15; min $1.99/order |
| Platform | $0.99/order | $0.30/contract |
| TAF (sells) | $0.000166/share, cap $8.30 | $0.00279/contract |
| Regulatory (sells) | — | $0.015/contract |

Tests: `test_stock_buy_has_platform_fee_only`, `test_stock_sell_taf_is_capped`,
`test_stock_sell_small_taf`, `test_option_buy_commission_floor`,
`test_option_sell_low_premium_components`.

At end of day, `reconcile_cash` compares modeled fill+fee cash impact against the
observed cash delta from MCP funds; a residual beyond tolerance is flagged and
must be explained before the next plan. Tests: `test_reconcile_cash_matches_model`,
`test_reconcile_cash_flags_residual`. Modeled fees stay provisional until reconciled.