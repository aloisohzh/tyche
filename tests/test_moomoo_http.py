from __future__ import annotations

import copy
import http.client
import json
from datetime import timedelta

import pytest
from test_lifecycle import ACCOUNT, NOW, capture_files, setup_case

from tyche.broker.moomoo_http import MoomooPaperHttp, PaperApiError, complete_order_rows
from tyche.lifecycle import Reservation, account_hash


@pytest.fixture
def wire(monkeypatch):
    calls, responses = [], []

    class Connection:
        def __init__(self, host, timeout):
            assert host == "webapi.moomoo.com" and timeout == 15

        def connect(self):
            pass

        def request(self, method, path, *, body, headers):
            calls.append((method, path, body, headers))

        def getresponse(self):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            self.status, self.body = value
            return self

        def read(self, maximum):
            return self.body

        def close(self):
            pass

    monkeypatch.setattr("tyche.broker.moomoo_http.http.client.HTTPSConnection", Connection)
    return MoomooPaperHttp("synthetic-test-token"), calls, responses


def request():
    plan = setup_case()[0]
    return Reservation(request_id="tyche-lc-test", plan_hash=plan.fingerprint(),
                       account_hash=account_hash(ACCOUNT), symbol="US.SPY", side="sell",
                       quantity=10, limit_price=93.72, reason="stop_loss", reserved_at=NOW)


def response(data, **extra):
    return 200, json.dumps({"ret_code": 0, "data": data, **extra}).encode()


def test_exact_paper_limit_rth_body_and_preserved_zero_fields(wire):
    broker, calls, replies = wire
    replies.append(response({"order_id": "9223372036854775701"}))
    order_id = broker.submit_exit(ACCOUNT, request(), deadline=NOW + timedelta(seconds=60), clock=lambda: NOW)
    assert order_id == "9223372036854775701"
    assert len(calls) == 1
    method, path, body, headers = calls[0]
    assert method == "POST" and path == f"/api/v1.0/sim-trade/{ACCOUNT}/orders"
    assert json.loads(body) == {
        "market": 100, "symbol": "SPY", "order_side": 2, "order_type": 1,
        "qty": "10", "price": "93.72", "order_trade_time_type": 1, "text": "tyche-lc-test",
    }
    assert headers["Authorization"] == "Bearer synthetic-test-token"
    replies.append(response({"positions": [], "hold": 0}, pagination={"has_more": False}))
    raw = broker._request("GET", "/api/v1.0/sim-trade/accounts")
    assert raw["ret_code"] == 0 and raw["data"] == {"positions": [], "hold": 0}


@pytest.mark.parametrize("reply", [
    (302, b"redirect"), (307, b"redirect"), (401, b"PRIVATE-TOKEN"), (500, b"PRIVATE-TOKEN"),
    (503, b"PRIVATE-TOKEN"), TimeoutError("PRIVATE-TOKEN"),
    http.client.RemoteDisconnected("PRIVATE-TOKEN"), (200, b"not JSON PRIVATE-TOKEN"),
    (200, b'{"data": {"order_id": "1"}}'),
    (200, b'{"ret_code": 1, "data": {"order_id": "1"}}'),
    (200, b'{"ret_code": false, "data": {"order_id": "1"}}'),
    (200, b'{"ret_code": 0, "data": {}}'),
])
def test_order_errors_never_retry_or_expose_provider_response(wire, reply):
    broker, calls, replies = wire
    replies.append(reply)
    with pytest.raises(PaperApiError) as caught:
        broker.submit_exit(ACCOUNT, request(), deadline=NOW + timedelta(seconds=60), clock=lambda: NOW)
    assert len(calls) == 1
    assert "PRIVATE-TOKEN" not in str(caught.value)
    assert ACCOUNT not in str(caught.value)


@pytest.mark.parametrize("mutation", ["buy", "wrong_account", "option", "fractional_cent", "expired"])
def test_transport_rejects_invalid_exit_before_order_write(wire, mutation):
    broker, calls = wire[:2]
    reserved = request()
    if mutation == "buy":
        reserved.side = "buy"
    if mutation == "wrong_account":
        reserved.account_hash = account_hash("OTHER")
    if mutation == "option":
        reserved.symbol = "US.SPY261120C600000"
    if mutation == "fractional_cent":
        reserved.limit_price = 93.721
    deadline = NOW if mutation == "expired" else NOW + timedelta(seconds=60)
    with pytest.raises(PaperApiError):
        broker.submit_exit(ACCOUNT, reserved, deadline=deadline, clock=lambda: NOW)
    assert not calls


@pytest.mark.parametrize("pagination", [None, {"has_more": False}])
def test_read_verifies_account_reads_history_current_and_exchange_times(wire, tmp_path, pagination):
    broker, calls, replies = wire
    data = capture_files(tmp_path)
    replies.extend([
        response(data["accounts"]["data"]),
        response(data["orders"]["data"], pagination={"has_more": False}),
        response(data["orders"]["data"], pagination={"has_more": False}),
        response(data["cash"]["data"], pagination=pagination),
        response(data["positions"]["data"], pagination=pagination),
        response(data["quotes"]["data"], pagination=pagination),
    ])
    result = broker.read(ACCOUNT, "US.SPY", [2], clock=lambda: NOW)
    assert result["observed_at"] == NOW
    assert len(result["orders"]) == 1
    assert result["quotes"]["data"]["quote_list"][0]["data_time"] == int(NOW.timestamp() * 1000)
    assert len(calls) == 6
    assert calls[1][1].endswith("/history-orders?market=100")
    assert calls[2][1].endswith("/orders?market=100")


@pytest.mark.parametrize("mutation", ["wrong_account", "wrong_market", "wrong_type", "duplicate_account"])
def test_account_verification_stops_read_pipeline(wire, mutation):
    broker, calls, replies = wire
    account = {"account_id": ACCOUNT, "market_id": 100, "account_type": 2}
    if mutation == "wrong_account":
        account["account_id"] = "OTHER"
    elif mutation == "wrong_market":
        account["market_id"] = 1
    elif mutation == "wrong_type":
        account["account_type"] = 99
    accounts = [account, account] if mutation == "duplicate_account" else [account]
    replies.append(response({"accounts": accounts}))
    with pytest.raises(PaperApiError):
        broker.read(ACCOUNT, "US.SPY", [2], clock=lambda: NOW)
    assert len(calls) == 1


def test_pagination_follows_exact_opaque_cursor(wire):
    broker, calls, replies = wire
    cursor = "opaque+cursor/=x"
    replies.extend([response({"orders": []}, pagination={"has_more": True, "next_key": cursor}),
                    response({"orders": []}, pagination={"has_more": False})])
    assert broker._orders("/api/v1.0/sim-trade/test/history-orders") == []
    assert calls[1][1].endswith("market=100&next_key=opaque%2Bcursor%2F%3Dx")


@pytest.mark.parametrize("pagination", [{}, {"has_more": "false"}, {"has_more": True},
                                        {"has_more": True, "next_key": "repeated"}])
def test_incomplete_or_repeated_pagination_blocks(wire, pagination):
    broker, calls, replies = wire
    replies.extend([response({"orders": []}, pagination=pagination)] * 2)
    with pytest.raises(PaperApiError):
        broker._orders("/api/v1.0/sim-trade/test/history-orders")
    assert len(calls) <= 2


def test_conflicting_history_and_current_order_does_not_silently_merge(wire, tmp_path):
    broker, calls, replies = wire
    data = capture_files(tmp_path)
    current = copy.deepcopy(data["orders"]["data"])
    current["orders"][0]["cum_qty"] = "9"
    replies.extend([response(data["accounts"]["data"]),
                    response(data["orders"]["data"], pagination={"has_more": False}),
                    response(current, pagination={"has_more": False})])
    with pytest.raises(PaperApiError, match="changed during capture"):
        broker.read(ACCOUNT, "US.SPY", [2], clock=lambda: NOW)
    assert len(calls) == 3


def test_missing_auth_never_uses_cli_or_host_credentials(monkeypatch):
    monkeypatch.delenv("TYCHE_MOOMOO_ACCESS_TOKEN", raising=False)
    with pytest.raises(PaperApiError, match="Moomoo OAuth"):
        MoomooPaperHttp.from_env()


def test_duplicate_ids_and_unproven_completeness_fail():
    page = {"ret_code": 0, "data": {"orders": [{"order_id": "1"}, {"order_id": "1"}]},
            "pagination": {"has_more": False}}
    with pytest.raises(PaperApiError):
        complete_order_rows([page])
    with pytest.raises(PaperApiError):
        complete_order_rows([])
