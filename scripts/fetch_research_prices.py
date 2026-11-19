"""Fetch research-only daily OHLCV for the configured universe (ADR 0015 lane).

Runs in the isolated research venv (.venv-lean), never in the kernel path.
Output is a local research dataset; it is not committed and never feeds
signals, sizing or orders in the tyche kernel (which uses moomoo prices).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "research" / "ohlcv.csv")
    args = parser.parse_args()

    symbols: list[str] = []
    for line in (ROOT / "config" / "universe.yaml").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- symbol:"):
            symbols.append(line.split(":", 1)[1].strip().strip('"').replace("US.", ""))
    if not symbols:
        raise SystemExit("no symbols parsed from config/universe.yaml")

    frame = yf.download(
        symbols, start=args.start, interval="1d", auto_adjust=True, progress=False, group_by="ticker"
    )
    rows = []
    for symbol in symbols:
        block = frame[symbol].dropna(how="all")
        for day, row in block.iterrows():
            if pd.isna(row["Close"]):
                continue
            rows.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "symbol": f"US.{symbol}",
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                }
            )
    out = pd.DataFrame(rows, columns=["date", "symbol", "open", "high", "low", "close", "volume"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"Wrote {args.out}: {len(out)} rows, {out['symbol'].nunique()} symbols, {out['date'].min()}..{out['date'].max()}")


if __name__ == "__main__":
    main()