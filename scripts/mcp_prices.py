"""Merge persisted Moomoo MCP kline outputs into data/prices.csv.

Cloud path: the researcher calls quote_cur_kline once per symbol (num=370);
large tool outputs are persisted to /tmp/tool-outputs/mcp_*.txt. This script
parses those JSON files directly so bars never round-trip through the model.

Usage: python scripts/mcp_prices.py FILE_OR_DIR [FILE_OR_DIR ...] [--out data/prices.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path


def iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.glob("mcp_*.txt")))
        elif path.is_file():
            files.append(path)
        else:
            print(f"skip (not found): {raw}")
    return files


def bar_date(item: dict) -> date | None:
    raw = item.get("date")
    if isinstance(raw, int) and 19000101 <= raw <= 21000101:
        return date(raw // 10000, raw % 10000 // 100, raw % 100)
    stamp = item.get("time_key")
    if isinstance(stamp, (int, float)) and stamp > 1e11:
        return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).date()
    return None


def parse_file(path: Path) -> dict[str, dict[date, float]]:
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"skip (not JSON): {path.name}: {exc}")
        return {}
    bars: dict[str, dict[date, float]] = {}
    nodes = [payload]
    while nodes:
        node = nodes.pop()
        if isinstance(node, dict):
            nodes.extend(node.values())
        elif isinstance(node, list):
            for item in node:
                if not isinstance(item, dict):
                    nodes.append(item)
                    continue
                symbol = item.get("code") or item.get("symbol")
                close = item.get("close_price", item.get("close"))
                day = bar_date(item)
                if not symbol or close is None or day is None:
                    continue
                try:
                    value = float(close)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    bars.setdefault(str(symbol), {})[day] = value
    return bars


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--out", default="data/prices.csv")
    args = parser.parse_args()

    merged: dict[str, dict[date, float]] = {}
    files = iter_files(args.paths)
    if not files:
        raise SystemExit("no input files found")
    for path in files:
        for symbol, series in parse_file(path).items():
            merged.setdefault(symbol, {}).update(series)
    if not merged:
        raise SystemExit("no kline bars found in inputs")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[tuple[str, date], float] = {}
    if out.exists():
        with out.open(newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    existing[(row["symbol"], date.fromisoformat(row["date"]))] = float(row["close"])
                except (KeyError, ValueError):
                    continue
    for symbol, series in merged.items():
        for day, value in series.items():
            existing[(symbol, day)] = value
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "symbol", "close"])
        for (symbol, day), value in sorted(existing.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            writer.writerow([day.isoformat(), symbol, f"{value:.4f}"])

    for symbol in sorted(merged):
        days = sorted(merged[symbol])
        flag = "" if len(days) >= 258 else "  WARNING: <258 bars, strategy lookbacks will skip this symbol"
        print(f"{symbol}: {len(days)} bars {days[0]} .. {days[-1]}{flag}")
    print(f"wrote {out} ({len(existing)} rows total)")


if __name__ == "__main__":
    main()