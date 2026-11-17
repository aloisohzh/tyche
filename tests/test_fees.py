from __future__ import annotations

from tyche.fees import estimate_fees, reconcile_cash


def test_stock_buy_has_platform_fee_only() -> None:
    fee = estimate_fees("US.SPY", "buy", 10, 600.0)
    assert fee.components == {"platform": 0.99}
    assert fee.total == 0.99
    assert fee.source == "model"


def test_stock_sell_taf_is_capped() -> None:
    fee = estimate_fees("US.SPY", "sell", 100_000, 600.0)
    assert fee.components["taf"] == 8.30
    assert fee.total == 9.29


def test_stock_sell_small_taf() -> None:
    fee = estimate_fees("US.SPY", "sell", 100, 600.0)
    assert fee.components["taf"] == 0.0166


def test_option_buy_commission_floor() -> None:
    fee = estimate_fees("US.SPY241129C600", "buy", 2, 0.50, asset_class="option")
    assert fee.components["commission"] == 1.99
    assert fee.components["platform"] == 0.60
    assert "taf" not in fee.components
    assert fee.total == 2.59


def test_option_sell_low_premium_components() -> None:
    fee = estimate_fees("US.SPY241129P600", "sell", 10, 0.05, asset_class="option")
    assert fee.components["commission"] == 1.99
    assert fee.components["platform"] == 3.00
    assert fee.components["taf"] == 0.0279
    assert fee.components["regulatory"] == 0.15


def test_reconcile_cash_matches_model() -> None:
    fee = estimate_fees("US.SPY", "buy", 10, 600.0)
    recon = reconcile_cash(
        cash_before=100_000.0,
        cash_after=100_000.0 - 6_000.0 - fee.total,
        fills=[(10, 600.0)],
        fees=[fee],
    )
    assert recon.ok
    assert recon.residual == 0.0
    assert recon.fee_total == 0.99


def test_reconcile_cash_flags_residual() -> None:
    fee = estimate_fees("US.SPY", "buy", 10, 600.0)
    recon = reconcile_cash(
        cash_before=100_000.0,
        cash_after=100_000.0 - 6_000.0 - 5.0,
        fills=[(10, 600.0)],
        fees=[fee],
    )
    assert not recon.ok
    assert recon.residual < 0