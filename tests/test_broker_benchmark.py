from __future__ import annotations

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_lifecycle import ACCOUNT, NOW, capture_files

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import benchmark_broker_reads as module


@pytest.fixture
def sample(tmp_path):
    data = capture_files(tmp_path)
    data["orders"] = data["orders"]["data"]["orders"]
    data["observed_at"] = NOW
    return data


class Clock:
    elapsed = 0.0

    def now(self):
        return NOW + timedelta(seconds=self.elapsed)

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


def test_six_ticks_use_one_loop_without_trading_or_raw_output(sample):
    clock = Clock()
    starts = []

    class Broker:
        def read(self, account, symbol, account_types, *, clock):
            assert account == ACCOUNT and symbol == "US.SPY" and account_types == [1, 2]
            starts.append(clock())
            data = copy.deepcopy(sample)
            data["observed_at"] = clock()
            data["quotes"]["data"]["quote_list"][0]["data_time"] = int(clock().timestamp() * 1000)
            return data

    report = module.benchmark(Broker(), ACCOUNT, "US.SPY", 6, 120,
                              clock=clock.now, monotonic=clock.monotonic, sleep=clock.sleep)
    assert report["status"] == "COMPLETED" and report["transport_successes"] == 6
    assert [(at - NOW).total_seconds() for at in starts] == [0, 120, 240, 360, 480, 600]
    assert not report["submitted"] and not report["trading_ready"]
    assert ACCOUNT not in json.dumps(report) and "filled-entry" not in json.dumps(report)


@pytest.mark.parametrize("mutation", ["stale", "future", "nav", "suspended", "option", "option_order"])
def test_bad_or_mixed_data_blocks_without_omitting_exposure(sample, mutation):
    if mutation == "stale":
        sample["quotes"]["data"]["quote_list"][0]["data_time"] -= 61000
    elif mutation == "future":
        sample["observed_at"] += timedelta(seconds=1)
    elif mutation == "nav":
        sample["cash"]["data"]["total_asset"] += 1000
    elif mutation == "suspended":
        sample["quotes"]["data"]["quote_list"][0]["suspension"] = True
    elif mutation == "option":
        sample["positions"]["data"]["positions"][0]["symbol"] = "SPY261120C600000"
    else:
        sample["orders"][0]["symbol"] = "SPY261120C600000"
    result = module.sample_quality(ACCOUNT, "US.SPY", sample, NOW)
    assert not result["ready"]
    if mutation.startswith("option"):
        assert result["reason"] == "MIXED_OPTION_ACCOUNT_NOT_SUPPORTED"


def test_read_error_stops_after_one_attempt_and_redacts_exception():
    class Broker:
        reads = 0

        def read(self, *args, **kwargs):
            self.reads += 1
            raise OSError("PRIVATE TOKEN ACCOUNT RAW RESPONSE")

    broker = Broker()
    report = module.benchmark(broker, ACCOUNT, "US.SPY", 6, 120)
    assert broker.reads == 1 and report["status"] == "BLOCKED"
    assert "PRIVATE" not in json.dumps(report) and "TOKEN" not in json.dumps(report)


def test_overrun_stops_without_catchup_reads(sample):
    clock = Clock()

    class Broker:
        def read(self, *args, **kwargs):
            clock.elapsed += 31
            return sample

    report = module.benchmark(Broker(), ACCOUNT, "US.SPY", 6, 30,
                              clock=clock.now, monotonic=clock.monotonic, sleep=clock.sleep)
    assert report["status"] == "INTERVAL_OVERRUN" and report["completed_ticks"] == 1


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1.0/sim-trade/test/orders", {}),
    ("DELETE", "/api/v1.0/sim-trade/test/orders/1", None),
    ("PATCH", "/api/v1.0/sim-trade/test/orders/1", {}),
    ("GET", "/api/v1.0/sim-trade/other/orders", None),
    ("POST", "/api/v1.0/quote/stock-quote", {"code_list": ["US.NVDA"]}),
])
def test_endpoint_allowlist_stops_writes_before_transport(monkeypatch, method, path, body):
    monkeypatch.setattr(module.MoomooPaperHttp, "_request", lambda *a, **k: pytest.fail("network call"))
    broker = module.ReadOnlyBroker("synthetic-token", "test", "US.SPY", float("inf"))
    with pytest.raises(module.PaperApiError, match="READ_ONLY"):
        broker._request(method, path, body)
    assert broker.requests == 0


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/v1.0/sim-trade/accounts", None),
    ("GET", "/api/v1.0/sim-trade/test/orders?market=100&next_key=opaque", None),
    ("GET", "/api/v1.0/sim-trade/test/history-orders?market=100", None),
    ("GET", "/api/v1.0/sim-trade/test/cash-info", None),
    ("GET", "/api/v1.0/sim-trade/test/positions?market=100", None),
    ("POST", "/api/v1.0/quote/stock-quote", {"code_list": ["US.SPY"]}),
])
def test_only_approved_reads_reach_transport(monkeypatch, method, path, body):
    calls = []
    monkeypatch.setattr(module.MoomooPaperHttp, "_request", lambda *a, **k: calls.append(a))
    broker = module.ReadOnlyBroker("synthetic-token", "test", "US.SPY", float("inf"))
    broker._request(method, path, body)
    assert len(calls) == 1 and broker.requests == 1


@pytest.mark.parametrize("exhausted", ["time", "requests"])
def test_request_budget_is_bounded(monkeypatch, exhausted):
    monkeypatch.setattr(module.MoomooPaperHttp, "_request", lambda *a, **k: pytest.fail("network call"))
    broker = module.ReadOnlyBroker("synthetic-token", "test", "US.SPY", 0 if exhausted == "time" else float("inf"))
    broker.requests = 100 if exhausted == "requests" else 0
    with pytest.raises(module.PaperApiError, match="BUDGET_EXHAUSTED"):
        broker._request("GET", "/api/v1.0/sim-trade/accounts")


@pytest.mark.parametrize("token,accounts,reason", [
    ("", "private-account", "MISSING_DEDICATED_HTTP_AUTH"),
    ("synthetic-token", "", "EXACTLY_ONE_INJECTED_PAPER_ACCOUNT_REQUIRED"),
    ("synthetic-token", "one,two", "EXACTLY_ONE_INJECTED_PAPER_ACCOUNT_REQUIRED"),
])
def test_main_requires_explicit_auth_and_unique_account(monkeypatch, capsys, token, accounts, reason):
    monkeypatch.setenv("TYCHE_MOOMOO_ACCESS_TOKEN", token)
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", accounts)
    monkeypatch.setattr(module.MoomooPaperHttp, "_request", lambda *a, **k: pytest.fail("network call"))
    assert module.main([]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["reason"] == reason
    assert "private-account" not in output and "synthetic-token" not in output


@pytest.mark.parametrize("args", [["--ticks", "0"], ["--ticks", "7"], ["--interval", "0"],
                                 ["--interval", "121"], ["--symbol", "US.SPY261120C600000"]])
def test_main_rejects_unbounded_or_option_inputs(args):
    with pytest.raises(SystemExit) as exc:
        module.main(args)
    assert exc.value.code == 2
