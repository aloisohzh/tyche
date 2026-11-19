"""Convert the research OHLCV CSV into LEAN local daily equity data (ADR 0015).

Writes Data/equity/usa/daily/<symbol>.zip per LEAN's daily bar format
(`yyyyMMdd 00:00,open,high,low,close,volume`). Prices are deci-cent integers
(LEAN's equity storage unit at every resolution); volume is share count.
Bars are total-return adjusted (yfinance auto_adjust); no map/factor files are
written because adjustments are already baked in — disclosed in the validation
note.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=ROOT / "data" / "research" / "ohlcv.csv")
    parser.add_argument("--data-folder", type=Path, default=ROOT / "research" / "lean" / "data")
    args = parser.parse_args()

    frame = pd.read_csv(args.prices, parse_dates=["date"])
    daily = args.data_folder / "equity" / "usa" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    for symbol, group in frame.groupby("symbol"):
        group = group.sort_values("date")
        name = symbol.replace("US.", "").lower()
        lines = [
            f"{day:%Y%m%d} 00:00,{round(row.open * 10000)},{round(row.high * 10000)},"
            f"{round(row.low * 10000)},{round(row.close * 10000)},{int(row.volume)}"
            for day, row in zip(group["date"], group.itertuples(index=False))
        ]
        with zipfile.ZipFile(daily / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{name}.csv", "\n".join(lines) + "\n")
        print(f"{name}: {len(lines)} bars {group['date'].min():%Y-%m-%d}..{group['date'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main()