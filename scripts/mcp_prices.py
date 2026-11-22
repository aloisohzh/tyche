"""Merge persisted Moomoo MCP kline outputs into data/prices.csv.

Cloud path: the researcher calls quote_cur_kline once per symbol (num=370);
large tool outputs are persisted to /tmp/tool-outputs/mcp_*.txt. This script
parses those JSON files directly so bars never round-trip through the model.

Usage: python scripts/mcp_prices.py FILE_OR_DIR [FILE_OR_DIR ...] [--out data/prices.csv]
       python scripts/mcp_prices.py FILE_OR_DIR ... --ohlc --out data/ohlc.csv

`--ohlc` keeps open/high/low/close(/volume) per bar for the swing lanes (PB-007 needs highs
and lows for the swing leg and ATR); the default closes-only output is unchanged for PB-001.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, date, datetime
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
        return datetime.fromtimestamp(stamp / 1000, tz=UTC).date()
    return None


OHLC_FIELDS = (("open", "open_price"), ("high", "high_price"), ("low", "low_price"),
               ("close", "close_price"), ("volume", "volume"))


def parse_file_ohlc(path: Path) -> dict[str, dict[date, dict[str, float]]]:
    """Same walker as parse_file, keeping every OHLC field a bar carries (volume optional)."""
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"skip (not JSON): {path.name}: {exc}")
        return {}
    bars: dict[str, dict[date, dict[str, float]]] = {}
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
                day = bar_date(item)
                if not symbol or day is None:
                    continue
                row: dict[str, float] = {}
                for name, key in OHLC_FIELDS:
                    raw = item.get(key, item.get(name))
                    if raw is None:
                        continue
                    try:
                        row[name] = float(raw)
                    except (TypeError, ValueError):
                        continue
                if not {"open", "high", "low", "close"} <= set(row) or row["close"] <= 0:
                    continue
                if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                    continue  # a bar whose range does not contain its open/close is not a bar
                bars.setdefault(str(symbol), {})[day] = row
    return bars


def write_ohlc(files: list[Path], out: Path, min_bars: int) -> None:
    merged: dict[str, dict[date, dict[str, float]]] = {}
    for path in files:
        for symbol, series in parse_file_ohlc(path).items():
            merged.setdefault(symbol, {}).update(series)
    if not merged:
        raise SystemExit("no OHLC bars found in inputs")
    out.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[tuple[str, date], dict[str, float]] = {}
    if out.exists():
        with out.open(newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    existing[(row["symbol"], date.fromisoformat(row["date"]))] = {
                        name: float(row[name]) for name, _ in OHLC_FIELDS if row.get(name) not in (None, "")}
                except (KeyError, ValueError):
                    continue
    for symbol, series in merged.items():
        for day, row in series.items():
            existing[(symbol, day)] = row
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "symbol", "open", "high", "low", "close", "volume"])
        for (symbol, day), row in sorted(existing.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            writer.writerow([day.isoformat(), symbol] + [f"{row[n]:.4f}" if n in row else "" for n, _ in OHLC_FIELDS])
    for symbol in sorted(merged):
        days = sorted(merged[symbol])
        flag = "" if len(days) >= min_bars else f"  WARNING: <{min_bars} bars, the swing lane will skip this symbol"
        print(f"{symbol}: {len(days)} OHLC bars {days[0]} .. {days[-1]}{flag}")
    print(f"wrote {out} ({len(existing)} rows total)")


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
    parser.add_argument("--out", default=None)
    parser.add_argument("--ohlc", action="store_true", help="write open/high/low/close/volume bars")
    parser.add_argument("--min-bars", type=int, default=None, help="warn below this many bars per symbol")
    args = parser.parse_args()
    if args.ohlc:
        files = iter_files(args.paths)
        if not files:
            raise SystemExit("no input files found")
        write_ohlc(files, Path(args.out or "data/ohlc.csv"), args.min_bars or 260)
        return
    args.out = args.out or "data/prices.csv"

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