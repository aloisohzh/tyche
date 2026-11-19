from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import UTC, datetime
from urllib.parse import quote

from tyche.broker.mcp_json import build_snapshot
from tyche.broker.moomoo_http import MoomooPaperHttp, PaperApiError
from tyche.lifecycle import Quote
from tyche.models import looks_like_option


class ReadOnlyBroker(MoomooPaperHttp):
    def __init__(self, token, account, symbol, deadline):
        super().__init__(token)
        base = "/api/v1.0/sim-trade/" + quote(account, safe="")
        self.read_paths = {
            "/api/v1.0/sim-trade/accounts", base + "/history-orders", base + "/orders",
            base + "/cash-info", base + "/positions",
        }
        self.symbol = symbol
        self.deadline = deadline
        self.requests = 0

    def _request(self, method, path, body=None, **kwargs):
        allowed = (
            method == "GET" and path.split("?", 1)[0] in self.read_paths and body is None
        ) or (
            method == "POST" and path == "/api/v1.0/quote/stock-quote"
            and body == {"code_list": [self.symbol]}
        )
        if not allowed:
            raise PaperApiError("BENCHMARK_READ_ONLY_ENDPOINT_REQUIRED")
        if time.monotonic() >= self.deadline or self.requests >= 100:
            raise PaperApiError("BENCHMARK_REQUEST_BUDGET_EXHAUSTED")
        self.requests += 1
        return super()._request(method, path, body, **kwargs)


def sample_quality(account, symbol, payloads, now):
    positions = payloads["positions"]["data"]["positions"]
    if any(looks_like_option(row["symbol"]) for row in positions + payloads["orders"]):
        return {"ready": False, "reason": "MIXED_OPTION_ACCOUNT_NOT_SUPPORTED"}
    snapshot = build_snapshot(
        account, payloads["accounts"], payloads["cash"], payloads["positions"],
        captured_at=payloads["observed_at"],
    )
    if (snapshot.account_id != account or snapshot.market_id != 100
            or snapshot.account_type not in (1, 2) or snapshot.source != "sim_list"):
        raise ValueError("unverified account")
    rows = payloads["quotes"]["data"]["quote_list"]
    if len(rows) != 1 or rows[0]["code"] != symbol:
        raise ValueError("exact single-symbol quote required")
    row = rows[0]
    market_quote = Quote(
        symbol=row["code"], last=row["last_price"],
        at=datetime.fromtimestamp(int(row["data_time"]) / 1000, UTC),
        tradable=row.get("sec_status") == "NORMAL" and row.get("suspension") is False,
    )
    account_age = (now - snapshot.captured_at).total_seconds()
    quote_age = (now - market_quote.at).total_seconds()
    reconciled = snapshot.broker_nav is not None and abs(snapshot.nav - snapshot.broker_nav) <= max(
        1.0, snapshot.broker_nav * 0.001,
    )
    fresh = 0 <= account_age <= 120 and 0 <= quote_age <= 60
    return {
        "ready": fresh and reconciled and market_quote.tradable,
        "reason": "OK" if fresh and reconciled and market_quote.tradable else "DATA_QUALITY_BLOCKED",
        "account_age_seconds": round(account_age, 3),
        "quote_age_seconds": round(quote_age, 3),
        "nav_reconciled": reconciled, "tradable": market_quote.tradable,
        "position_count": len(snapshot.positions), "order_count": len(payloads["orders"]),
    }


def benchmark(broker, account, symbol, ticks, interval, *, clock=lambda: datetime.now(UTC),
              monotonic=time.monotonic, sleep=time.sleep):
    if not 1 <= ticks <= 6 or not 30 <= interval <= 120:
        raise ValueError("benchmark requires 1-6 ticks and a 30-120 second interval")
    started = monotonic()
    samples = []
    status = "COMPLETED"
    for index in range(ticks):
        due = started + index * interval
        remaining = due - monotonic()
        if remaining > 0:
            sleep(remaining)
        tick_start = monotonic()
        sample = {"tick": index + 1, "started_at": clock().isoformat(),
                  "lateness_seconds": round(max(0, tick_start - due), 3),
                  "transport_ok": False}
        try:
            payloads = broker.read(account, symbol, [1, 2], clock=clock)
            sample["transport_ok"] = True
            sample.update(sample_quality(account, symbol, payloads, clock()))
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RuntimeError) as exc:
            sample.update(ready=False, reason="READ_OR_VALIDATION_FAILED", error_type=type(exc).__name__)
        sample["latency_seconds"] = round(monotonic() - tick_start, 3)
        samples.append(sample)
        if not sample["ready"]:
            status = "BLOCKED"
            break
        if monotonic() >= due + interval:
            status = "INTERVAL_OVERRUN"
            break
    return {
        "status": status, "submitted": False, "broker_writes": 0,
        "requested_ticks": ticks, "completed_ticks": len(samples),
        "transport_successes": sum(s["transport_ok"] for s in samples),
        "interval_seconds": interval, "elapsed_seconds": round(monotonic() - started, 3),
        "samples": samples, "options_validated": False, "trading_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded paper-broker reads; no trading endpoints.")
    parser.add_argument("--symbol", default="US.SPY")
    parser.add_argument("--ticks", type=int, choices=range(1, 7), default=6)
    parser.add_argument("--interval", type=int, choices=range(30, 121), default=120)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"US\.[A-Z][A-Z0-9.]*", args.symbol) or looks_like_option(args.symbol):
        parser.error("a US stock/ETF symbol is required")
    token = os.environ.get("TYCHE_MOOMOO_ACCESS_TOKEN", "")
    accounts = {item.strip() for item in os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "").split(",")
                if item.strip()}
    reason = None
    if not token:
        reason = "MISSING_DEDICATED_HTTP_AUTH"
    elif len(accounts) != 1:
        reason = "EXACTLY_ONE_INJECTED_PAPER_ACCOUNT_REQUIRED"
    if reason:
        print(json.dumps({"status": "BLOCKED", "reason": reason, "submitted": False,
                          "broker_reads": 0, "broker_writes": 0}))
        return 2
    account = next(iter(accounts))
    try:
        broker = ReadOnlyBroker(token, account, args.symbol,
                                time.monotonic() + (args.ticks - 1) * args.interval + 60)
        report = benchmark(broker, account, args.symbol, args.ticks, args.interval)
        report["http_requests"] = broker.requests
    except (OSError, ValueError, RuntimeError) as exc:
        report = {"status": "BLOCKED", "reason": "BENCHMARK_SETUP_FAILED",
                  "error_type": type(exc).__name__, "submitted": False, "broker_writes": 0}
    print(json.dumps(report, allow_nan=False))
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
