"""Cloud-run feed: challenge-account-first ingestion of docs/performance bundles."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE_CHALLENGE_ID = "9999598"  # synthetic; masks to ***598


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("desk_server_cloud_test", ROOT / "dashboard" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_bundle(perf: Path, run: str, *, nav: float, cash: float, account_type: int = 2,
                positions: list[dict] | None = None, orders: list[dict] | None = None,
                names: dict[str, str] | None = None, mtime: float | None = None) -> Path:
    d = perf / run
    (d / "mcp").mkdir(parents=True, exist_ok=True)
    positions = positions if positions is not None else [
        {"symbol": "US.SPY", "quantity": 28, "avg_cost": 731.54, "last_price": 730.94, "market_value": 20466.32},
    ]
    snap = {
        "account_id": "[REDACTED]", "cash": cash, "positions": positions, "env": "paper",
        "account_type": account_type, "market_id": 100, "source": "sim_list",
        "gross_exposure": sum(p["market_value"] for p in positions), "nav": nav,
    }
    (d / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    if names is not None:
        raw = {"data": {"positions": [{"symbol": s.replace("US.", ""), "stock_name": n} for s, n in names.items()]}}
        (d / "positions.json").write_text(json.dumps(raw), encoding="utf-8")
    if orders is not None:
        (d / "mcp" / "sim_trade_history_order_list.json").write_text(
            json.dumps({"ret_code": 0, "data": {"orders": orders}}), encoding="utf-8")
    if mtime is not None:
        os.utime(d / "snapshot.json", (mtime, mtime))
    return d


@pytest.fixture
def feed_env(srv, tmp_path, monkeypatch):
    perf = tmp_path / "performance"
    perf.mkdir()
    drill = tmp_path / "drill"
    drill.mkdir()
    (drill / "accounts.json").write_text(json.dumps({"data": {"accounts": [
        {"account_id": FAKE_CHALLENGE_ID, "account_type": 2, "market_id": 100},
        {"account_id": "9999748", "account_type": 1, "market_id": 100},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(srv, "PERF_DIR", perf)
    monkeypatch.setattr(srv, "DRILL_DIR", drill)
    return perf


def test_challenge_mask_from_accounts(srv, feed_env):
    assert srv.challenge_mask() == "***598"


def test_challenge_mask_fallback(srv, feed_env):
    (feed_env.parent / "drill" / "accounts.json").unlink()
    assert srv.challenge_mask() == "challenge"


def test_latest_challenge_snapshot_leads(srv, feed_env):
    make_bundle(feed_env, "2026-11-18-early", nav=100000.0, cash=100000.0, positions=[], mtime=1000)
    make_bundle(feed_env, "2026-11-18-late", nav=92089.79, cash=57360.28,
                names={"US.SPY": "SPDR S&P 500 ETF"}, mtime=2000)
    make_bundle(feed_env, "2026-11-18-personal", nav=999101.96, cash=900000.0, account_type=1, mtime=3000)
    runs = srv.load_cloud_runs()
    assert len(runs) == 3
    snap = srv.cloud_snapshot(runs)
    assert snap["account"] == "***598"
    assert snap["nav"] == 92089.79
    assert snap["run"] == "2026-11-18-late"
    assert snap["positions"][0]["name"] == "SPDR S&P 500 ETF"
    assert snap["positions"][0]["weight"] == pytest.approx(20466.32 / 92089.79)
    assert snap["cash_weight"] == pytest.approx(57360.28 / 92089.79)
    assert "cloud run 2026-11-18-late" in snap["source"]


def test_no_challenge_bundle_falls_back(srv, feed_env):
    make_bundle(feed_env, "2026-11-18-personal", nav=999101.96, cash=900000.0, account_type=1)
    assert srv.cloud_snapshot(srv.load_cloud_runs()) is None
    assert srv.cloud_orders(srv.load_cloud_runs()) == []
    assert srv.cloud_nav_marks(srv.load_cloud_runs()) == {}


def test_empty_feed(srv, feed_env):
    assert srv.load_cloud_runs() == []
    assert srv.cloud_snapshot([]) is None


def test_order_status_mapping(srv, feed_env):
    orders = [
        {"order_id": "3116597", "symbol": "VNQ", "side": 1, "qty": "83", "price": "94.98",
         "status": 2, "cum_qty": "0", "avg_fill_price": "0", "create_time": "1795024387000000",
         "update_time": "1795024387000000", "text": "tyche rebalance 11% VNQ"},
        {"order_id": "3116594", "symbol": "EFA", "side": 1, "qty": "142", "price": "101.45",
         "status": 4, "cum_qty": "142", "avg_fill_price": "100.495", "create_time": "1795024176000000",
         "update_time": "1795024185000000", "text": "tyche rebalance 20% EFA"},
        {"order_id": "3116500", "symbol": "SPY", "side": 2, "qty": "5", "price": "730",
         "status": 6, "cum_qty": "0", "avg_fill_price": "0", "create_time": "1795023000000000",
         "update_time": "1795023000000000", "text": None},
    ]
    make_bundle(feed_env, "2026-11-18-midday2", nav=92089.79, cash=57360.28, orders=orders)
    out = srv.cloud_orders(srv.load_cloud_runs())
    by_id = {o["order_id"]: o for o in out}
    resting = by_id["3116597"]
    assert resting["status"] == "submitted"
    assert resting["fill_price"] is None and resting["fill_qty"] is None
    assert resting["symbol"] == "US.VNQ" and resting["side"] == "buy"
    assert resting["quantity"] == 83 and resting["limit_price"] == 94.98
    assert resting["account"] == "***598"
    assert resting["requested_ts"].startswith("2026-")
    filled = by_id["3116594"]
    assert filled["status"] == "filled"
    assert filled["fill_price"] == 100.495 and filled["fill_qty"] == 142
    cancelled = by_id["3116500"]
    assert cancelled["status"] == "cancelled" and cancelled["side"] == "sell"


def test_nav_marks_prefer_broker_total_asset(srv, feed_env):
    # A resting order makes the CLI snapshot nav read low; the bundle's cash.json carries the broker's
    # own total, and that is the account value the desk should chart.
    d = make_bundle(feed_env, "2026-11-18-midday2", nav=92089.79, cash=57360.28, mtime=1000)
    (d / "cash.json").write_text(json.dumps({"data": {"total_asset": 99974.12, "hold": 7884.33}}), encoding="utf-8")
    make_bundle(feed_env, "2026-11-18-nocash", nav=92047.05, cash=57360.28, mtime=2000)
    series = srv.cloud_nav_marks(srv.load_cloud_runs())["***598"]
    assert [m["nav"] for m in series] == [99974.12, 92047.05]


def test_nav_marks_series_and_dedupe(srv, feed_env):
    make_bundle(feed_env, "2026-11-18-a", nav=100000.0, cash=100000.0, positions=[], mtime=1000)
    make_bundle(feed_env, "2026-11-18-b", nav=92089.79, cash=57360.28, mtime=2000)
    make_bundle(feed_env, "2026-11-18-c", nav=92089.79, cash=57360.28, mtime=3000)
    marks = srv.cloud_nav_marks(srv.load_cloud_runs())
    series = marks["***598"]
    assert [m["nav"] for m in series] == [100000.0, 92089.79]
    assert series[-1]["count"] == 2
    assert series[0]["source"] == "cloud:2026-11-18-a"


def test_run_order_uses_broker_timestamps(srv, feed_env):
    # git checkout resets mtimes; the newer broker update_time must win.
    make_bundle(feed_env, "2026-11-18-zname", nav=100000.0, cash=100000.0, positions=[], mtime=5000,
                orders=[{"order_id": "1", "symbol": "SPY", "side": 1, "qty": "1", "price": "1",
                         "status": 4, "cum_qty": "1", "avg_fill_price": "1",
                         "create_time": "1795000000000000", "update_time": "1795000000000000"}])
    make_bundle(feed_env, "2026-11-18-aname", nav=92089.79, cash=57360.28, mtime=5000,
                orders=[{"order_id": "2", "symbol": "SPY", "side": 1, "qty": "1", "price": "1",
                         "status": 4, "cum_qty": "1", "avg_fill_price": "1",
                         "create_time": "1795024387000000", "update_time": "1795024387000000"}])
    runs = srv.load_cloud_runs()
    assert runs[-1]["run"] == "2026-11-18-aname"
    assert srv.cloud_snapshot(runs)["run"] == "2026-11-18-aname"


def test_scrubbed_feed_never_leaks_full_id(srv, feed_env, monkeypatch):
    monkeypatch.setattr(srv, "SENSITIVE", {FAKE_CHALLENGE_ID, "9999748"})
    make_bundle(feed_env, "2026-11-18-x", nav=92089.79, cash=57360.28,
                orders=[{"order_id": "9", "symbol": "SPY", "side": 1, "qty": "28", "price": "733.17",
                         "status": 4, "cum_qty": "28", "avg_fill_price": "731.54",
                         "create_time": "1795023896000000", "update_time": "1795023900000000",
                         "text": f"account {FAKE_CHALLENGE_ID}"}])
    runs = srv.load_cloud_runs()
    blob = json.dumps(srv.scrub({"snapshot": srv.cloud_snapshot(runs), "orders": srv.cloud_orders(runs)}))
    assert FAKE_CHALLENGE_ID not in blob
    assert "***598" in blob


def test_malformed_bundle_skipped(srv, feed_env):
    d = feed_env / "2026-11-18-broken"
    d.mkdir()
    (d / "snapshot.json").write_text("{not json", encoding="utf-8")
    make_bundle(feed_env, "2026-11-18-good", nav=92089.79, cash=57360.28)
    runs = srv.load_cloud_runs()
    assert [r["run"] for r in runs] == ["2026-11-18-good"]

def test_secret_guard_covers_the_repo_token_from_the_process_environment(monkeypatch):
    """The desk pushes the feed with a repo token held as an environment variable, not a .env line; the
    export's guard must refuse to write a feed that contains it."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_dashboard_test", ROOT / "scripts" / "export_dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TYCHE_GITHUB_PAT", "github_pat_test_value_123456")
    values = module.env_values()
    assert values["TYCHE_GITHUB_PAT"] == "github_pat_test_value_123456"

    class _Srv:
        SENSITIVE = frozenset()

        @staticmethod
        def mask_id(value):
            return value

    with pytest.raises(SystemExit, match="SECRET GUARD FAILED"):
        module.assert_no_secrets('{"x": "github_pat_test_value_123456"}', _Srv, values)
    module.assert_no_secrets('{"x": "clean"}', _Srv, values)


def test_challenge_mask_from_allowlist_when_bundle_ids_are_redacted(srv, feed_env, monkeypatch):
    (feed_env.parent / "drill" / "accounts.json").unlink()
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", FAKE_CHALLENGE_ID)
    assert srv.challenge_mask() == "***598"
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", FAKE_CHALLENGE_ID + ",9999748")
    assert srv.challenge_mask() == "challenge"  # ambiguous: never guess which one is the challenge


def test_account_value_counts_cash_on_hold(srv, feed_env):
    d = make_bundle(feed_env, "2026-11-18-midday3", nav=92047.11, cash=57360.28, positions=[
        {"symbol": "US.SPY", "quantity": 28, "avg_cost": 731.54, "last_price": 730.94, "market_value": 34686.83},
    ])
    (d / "cash.json").write_text(json.dumps({"data": {"hold": "7884.33", "total_asset": "99931.44"}}), encoding="utf-8")
    (d / "accounts.json").write_text(json.dumps({"data": {"accounts": [
        {"account_id": "[REDACTED]", "account_title": "US Margin Account [Paper Trading]", "account_type": 1, "market_id": 100},
        {"account_id": "[REDACTED]", "account_title": "Moomoo x Qoder AI Paper Trading Agent Challenge",
         "account_type": 2, "market_id": 100},
    ]}}), encoding="utf-8")
    snap = srv.cloud_snapshot(srv.load_cloud_runs())
    assert snap["nav"] == 99931.44
    assert snap["account_title"] == "Moomoo x Qoder AI Paper Trading Agent Challenge"
    assert snap["positions"][0]["weight"] == pytest.approx(34686.83 / 99931.44)
    # no broker total: free cash + held cash + holdings
    assert srv.account_value(57360.28, 7884.33, 34686.83, None) == 99931.44
    assert srv.account_value(100.0, None, 50.0, 0) == 150.0


def test_cloud_orders_read_history_orders_json(srv, feed_env):
    d = make_bundle(feed_env, "2026-11-18-midday3", nav=92047.11, cash=57360.28)
    (d / "mcp" / "history_orders.json").write_text(json.dumps({"data": {"orders": [
        {"order_id": "3116597", "symbol": "VNQ", "side": 1, "qty": "83", "price": "94.98", "status": 2,
         "cum_qty": "0", "avg_fill_price": "0", "create_time": "1795024387000000",
         "update_time": "1795024387000000", "text": "tyche rebalance"},
    ]}}), encoding="utf-8")
    orders = srv.cloud_orders(srv.load_cloud_runs())
    assert [o["order_id"] for o in orders] == ["3116597"]
    assert orders[0]["symbol"] == "US.VNQ"
