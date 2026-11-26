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
| Notional ≥ $500 (unless closing or buying an option) | `order.min_notional` | `min_order_notional` | `test_below_min_notional_is_blocked`, `test_confirmed_setup_produces_bounded_risk_preview` |
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

## Tactical option gates

The 2026-11-26 operator re-freeze relaxed only the two liquidity values that blocked the researched
KO call. Every other gate still has to pass on a fresh quote.

| Gate | Current rule | Source | Test |
|---|---|---|---|
| Bid/ask spread | ≤ 10% | `config/tactical.yaml` `option_spread_pct` | `test_relaxed_option_spread_and_volume_boundaries` |
| Day volume | ≥ 20 contracts | `config/tactical.yaml` `min_option_volume` | `test_relaxed_option_spread_and_volume_boundaries` |
| Open interest | ≥ 100 | `min_option_open_interest` | `test_option_entry_gates` |
| Expiry | 2 to 30 days; never 0DTE | `min_option_dte`, `max_option_dte` | `test_option_entry_gates` |
| Direction and Greeks | absolute delta 0.45 to 0.80; implied volatility present | `tactical.py` option gate | `test_option_entry_gates` |
| Researcher debit limit | ask at or below the setup's premium limit | `WatchlistEntry.premium_limit` | `test_option_entry_gates` |
| Premium risk per trade | ≤ 1.5% of NAV, full debit plus fees | `risk.yaml` `option_risk_per_trade_pct` | `test_full_debit_risk_and_pending_exposure` |
| Aggregate option premium | ≤ 5% of NAV, held plus pending | `risk.yaml` `max_option_premium_pct` | `test_option_allocation_cap_includes_held_and_pending_premiums` |

## Operator authorization: the envelope and the one exit number the operator owns

Autonomy inside this platform is bounded by a dated, signed `ApprovalBatch`
(`data/approvals.json`), never by a model's confidence. Two facts are worth stating
plainly because they decide what the operator is actually agreeing to:

| Fact | Where | Test |
|---|---|---|
| A drafted exit sell sits `exit_collar_pct` = 5% below the stop the plan journaled | `risk.exit_collar_pct` (0 < x <= 0.20), applied in `src/tyche/envelope.py` | `test_the_collar_is_the_only_operator_number_and_it_widens_downward` |
| A contract's floor is a premium, never the underlying's stop: the draft uses a journaled `premium_stop`, or the lane's own 40% premium drawdown measured on the broker's cost basis | `PREMIUM_DRAWDOWN_FLOOR` (`src/tyche/tactical.py`), `ExitLevel.premium_stop` (`src/tyche/envelope.py`) | `test_a_contract_floor_is_never_an_underlying_price` |
| Only the operator's arm click writes `data/approvals.json`; drafting writes `data/approvals.proposed.json`, which is gitignored | `propose_exit_envelope` (drafts) vs `arm_envelope` (approves) in `dashboard/server.py` | `test_arm_from_draft_is_the_only_writer_of_the_envelope` |
| A hand-written entry row gets the executor's own plan fingerprint stamped on it, because a row without one drafts an exit line the tactical lane refuses to arm | `record_order` calling `tactical.setup_hash` (`src/tyche/cli.py`) | `test_record_order_stamps_the_fingerprint_an_exit_note_needs` |
| Old text approvals stay readable as manual notes. They never become structured envelope or Telegram authority, and daily request accounting falls back to the event's New York date | `authorization_fields` (`src/tyche/execution_state.py`) | `test_text_authorization_stays_manual_and_uses_the_event_date`, `test_record_order_normalizes_plain_text_authorization` |
| An intentional rule change rebinds a held setup with `tyche tactical rebind`. It requires a reason and a fresh verified paper snapshot whose broker NAV reconciles, writes `tactical.monitor`, and never creates an order request. Routine ticks cannot replace the trusted hash | `rebind` (`src/tyche/tactical_cli.py`), `MonitorState.protected_hashes`, `envelope.exit_levels` | `test_rebind_updates_a_held_setup_without_requesting_an_order`, `test_routine_ticks_do_not_rebind_a_changed_config`, `test_only_a_deliberate_monitor_event_can_replace_a_trusted_setup_hash` |
| Private paper-account injection changes who may trade, not the trading rules. The account allowlist is therefore excluded from the config fingerprint; the account itself is still hashed separately into each setup | `tactical.config_hash` and `tactical.setup_hash` | `test_private_account_injection_does_not_change_the_rules_fingerprint` |
| Repeated identical request ids describe one request and use one budget slot. A missing setup hash may be filled once; two different hashes, or any changed plan, account, symbol, side, quantity, price, multiplier, option, order type or deadline under the same id, blocks execution and stays visible as a dashboard conflict. Old text approval remains in `authorization_note` | `check_execution_journal` (`src/tyche/lifecycle_cli.py`), `deduplicate_requests` (`src/tyche/execution_state.py`), dashboard `build_orders` | `test_identical_duplicate_request_ids_are_allowed_but_changed_orders_are_not`, `test_identical_duplicate_requests_use_one_envelope_slot`, `test_order_rows_keep_manual_notes_and_merge_only_identical_requests` |
| Receipts the journal never heard about are healed from the broker's order list, not retyped from memory | `tyche sync-receipts` over `receipts_to_journal(days_back=...)` | `test_sync_receipts_heals_the_journal_from_the_broker_list` |

### What the broker itself will not do

Learned on 25 Nov by placing exits by hand, and worth stating before any card promises protection:

| Limit | What it means for a position | Evidence |
|---|---|---|
| The paper bridge has no stop or stop-limit order type | A stop is a rule the desk watches and acts on, so an overnight gap costs the gap price, not the planned one. Take-profit limits *can* rest; protective stops cannot. | `docs/adr/0012-options-protection.md:7` (`order_type` enum is Limit/Market) |
| The order tool has no time-in-force parameter | Every order is a DAY order and dies at the close. Nothing resting protects a swing lot while nobody is watching, which is why a swing exit is re-armed at the first fire of each session. | PRD v1.33; `_order_row` in `src/tyche/cycle.py` |
| One working sell leg locks the lot it sells | While a take-profit rests, the broker reports nothing sellable on those shares: the exit-note draft skips the position and `tyche exit-now` refuses a second reservation on the symbol. Rest the target or stay armable - not both, on the same day. | skip reason in `propose_exit_envelope`, guard in `src/tyche/cli.py` `exit-now` |


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

What the operator actually reads before any of this is spent is the order preview card,
[../templates/order-preview.md](../templates/order-preview.md): product type, price ladder, %NAV and the
plain-language risk block (worst-case loss, halts and gaps, exit, ladder). The card is a convention the
prompts enforce in prose, not a schema the kernel validates, so an audit finding on a missing field is a
first-class defect rather than a formatting complaint.

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