from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


class MoomooCliError(RuntimeError):
    pass


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _parse_bar_date(raw: Any) -> date | None:
    if isinstance(raw, (int, float)):
        raw = str(int(raw))
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if re.fullmatch(r"\d{13}", text):
        return datetime.fromtimestamp(int(text) / 1000, tz=UTC).date()
    if re.fullmatch(r"\d{10}", text):
        return datetime.fromtimestamp(int(text), tz=UTC).date()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def extract_daily_bars(payload: Any) -> list[tuple[date, float]]:
    """Find the candlestick list inside a moomoo JSON response."""
    candidates: list[list[dict[str, Any]]] = []
    for node in _walk(payload):
        if not isinstance(node, list) or not node:
            continue
        if all(isinstance(item, dict) for item in node) and any(
            "close_price" in item or "close" in item for item in node
        ):
            candidates.append(node)
    if not candidates:
        return []
    bars: dict[date, float] = {}
    for item in max(candidates, key=len):
        close = item.get("close_price", item.get("close"))
        raw_date = (
            item.get("time_key") or item.get("date") or item.get("time") or item.get("k_time")
        )
        if close is None or raw_date is None:
            continue
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        bar_date = _parse_bar_date(raw_date)
        if bar_date is None or value <= 0:
            continue
        bars[bar_date] = value
    return sorted(bars.items())


def extract_last_price(payload: Any, symbol: str) -> float | None:
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        if node.get("code") != symbol:
            continue
        price = node.get("last_price", node.get("lastPrice"))
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def extract_order_id(payload: Any) -> str | None:
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        for key in ("order_id", "orderId"):
            value = node.get(key)
            if isinstance(value, (str, int)) and str(value):
                return str(value)
    return None


class MoomooCli:
    """Thin wrapper over the moomoo CLI; only quote and simulated-trading commands are exposed."""

    def __init__(self, binary: str = "moomoo", timeout: float = 45.0) -> None:
        self.binary = binary
        self.timeout = timeout

    def resolved_binary(self) -> str | None:
        found = shutil.which(self.binary)
        if found:
            return found
        candidate = Path(self.binary).expanduser()
        return str(candidate) if candidate.is_file() else None

    def available(self) -> bool:
        return self.resolved_binary() is not None

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        binary = self.resolved_binary()
        if binary is None:
            raise MoomooCliError(
                f"moomoo CLI not found ({self.binary}). Install it and run 'moomoo auth login'."
            )
        try:
            result = subprocess.run(
                [binary, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MoomooCliError(f"moomoo {' '.join(args)} timed out") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise MoomooCliError(f"moomoo {' '.join(args)} failed ({result.returncode}): {detail}")
        return result

    def _json(self, args: list[str]) -> Any:
        result = self._run(args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            snippet = result.stdout.strip()[:400]
            raise MoomooCliError(f"moomoo returned non-JSON output: {snippet}") from exc

    def version(self) -> str:
        return self._run(["version"]).stdout.strip()

    def auth_status(self) -> Any:
        return self._json(["auth", "status", "--format", "json"])

    def check(self) -> Any:
        return self._json(["check", "--format", "json"])

    def quote(self, symbols: list[str]) -> Any:
        return self._json(["quote", *symbols, "--format", "json"])

    def kline(self, symbol: str, num: int = 370) -> Any:
        return self._json(
            [
                "kline",
                symbol,
                "--ktype",
                "2",
                "--num",
                str(num),
                "--autype",
                "1",
                "--format",
                "json",
            ]
        )

    def sim_accounts(self) -> Any:
        return self._json(["sim", "account", "list", "--format", "json"])

    def sim_funds(self, account: str) -> Any:
        return self._json(["sim", "account", "funds", "--account", account, "--format", "json"])

    def sim_positions(self, account: str, market: str = "US") -> Any:
        return self._json(
            ["sim", "position", "--account", account, "--market", market, "--format", "json"]
        )

    def sim_order_buy(
        self,
        symbol: str,
        quantity: int,
        account: str,
        limit_price: float,
        market: str = "US",
        remark: str = "",
    ) -> Any:
        args = [
            "sim",
            "order",
            "buy",
            symbol,
            str(quantity),
            "--account",
            account,
            "--market",
            market,
            "--type",
            "limit",
            "--price",
            f"{limit_price:.2f}",
            "--format",
            "json",
        ]
        if remark:
            args.extend(["--text", remark[:64]])
        return self._json(args)

    def sim_order_sell(
        self,
        symbol: str,
        quantity: int,
        account: str,
        limit_price: float,
        market: str = "US",
        remark: str = "",
    ) -> Any:
        args = [
            "sim",
            "order",
            "sell",
            symbol,
            str(quantity),
            "--account",
            account,
            "--market",
            market,
            "--type",
            "limit",
            "--price",
            f"{limit_price:.2f}",
            "--format",
            "json",
        ]
        if remark:
            args.extend(["--text", remark[:64]])
        return self._json(args)

    def sim_order_cancel(self, order_id: str, account: str, market: str = "US") -> Any:
        return self._json(
            [
                "sim",
                "order",
                "cancel",
                order_id,
                "--account",
                account,
                "--market",
                market,
                "--format",
                "json",
            ]
        )

    def sim_order_list(self, account: str, market: str = "US") -> Any:
        return self._json(
            ["sim", "order", "list", "--account", account, "--market", market, "--format", "json"]
        )

    def sim_order_history(self, account: str, market: str = "US") -> Any:
        return self._json(
            [
                "sim",
                "order",
                "history",
                "--account",
                account,
                "--market",
                market,
                "--format",
                "json",
            ]
        )
