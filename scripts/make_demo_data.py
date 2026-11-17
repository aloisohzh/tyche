"""Generate deterministic synthetic ETF prices for offline demos."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

START = "2023-01-02"
END = "2026-11-16"

SPECS = {
    "US.SPY": (380.0, 1.00, 0.00012, 0.0040),
    "US.QQQ": (280.0, 1.15, 0.00016, 0.0060),
    "US.IWM": (180.0, 1.05, 0.00005, 0.0060),
    "US.EFA": (70.0, 0.85, 0.00005, 0.0050),
    "US.EEM": (40.0, 0.95, 0.00003, 0.0070),
    "US.TLT": (100.0, -0.20, 0.00002, 0.0070),
    "US.IEF": (95.0, -0.10, 0.00001, 0.0030),
    "US.GLD": (180.0, 0.10, 0.00008, 0.0060),
    "US.DBC": (25.0, 0.30, 0.00002, 0.0070),
    "US.VNQ": (85.0, 0.80, 0.00005, 0.0060),
    "US.HYG": (75.0, 0.45, 0.00006, 0.0025),
}


def main() -> None:
    days = pd.bdate_range(START, END)
    rng = np.random.default_rng(20261117)
    market = rng.normal(0.00035, 0.0080, len(days))

    drawdown_2024 = (days >= "2024-08-01") & (days <= "2024-10-15")
    market[drawdown_2024] -= 0.0035
    drawdown_2025 = (days >= "2025-03-01") & (days <= "2025-05-15")
    market[drawdown_2025] -= 0.0025
    volatility_2025 = (days >= "2025-10-01") & (days <= "2025-12-01")
    market[volatility_2025] = rng.normal(0.0002, 0.0140, int(volatility_2025.sum()))
    recovery = days >= "2026-06-01"
    market[recovery] += 0.00045

    rows: list[tuple[str, str, float]] = []
    for symbol, (base, beta, drift, idio_vol) in SPECS.items():
        returns = drift + beta * market + rng.normal(0.0, idio_vol, len(days))
        prices = np.maximum(base * np.cumprod(1.0 + returns), 1.0)
        for day, close in zip(days, prices, strict=True):
            rows.append((day.date().isoformat(), symbol, round(float(close), 2)))

    frame = pd.DataFrame(rows, columns=["date", "symbol", "close"])
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    prices_path = out_dir / "demo_prices.csv"
    account_path = out_dir / "demo_account.json"
    frame.to_csv(prices_path, index=False)
    account_path.write_text(
        json.dumps(
            {
                "account_id": "SIM-DEMO-US",
                "cash": 100_000.0,
                "positions": [],
                "prior_close_nav": 100_000.0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {prices_path} ({len(frame):,} rows) and {account_path}")


if __name__ == "__main__":
    main()
