from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_lifecycle import ACCOUNT, NOW, ROOT, capture_files, setup_case, write_case
from typer.testing import CliRunner

from tyche.cli import app
from tyche.journal import append_event, journal_lock, read_events, verify_chain
from tyche.lifecycle import LifecycleState
from tyche.lifecycle_cli import locked_state


@pytest.fixture
def execution(tmp_path, monkeypatch):
    case = setup_case(price=94)
    paths = write_case(tmp_path, case)
    capture_files(tmp_path)
    payloads = {key: json.loads((tmp_path / f"{key}.json").read_text())
                for key in ("accounts", "cash", "positions", "quotes", "orders")}
    payloads["orders"] = payloads["orders"]["data"]["orders"]
    payloads["observed_at"] = NOW
    payloads["quotes"]["data"]["quote_list"][0]["last_price"] = 94
    payloads["positions"]["data"]["positions"][0]["cur_price"] = 94
    payloads["cash"]["data"]["total_asset"] = 99940
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    args = ["lifecycle", "execute-exit", "--book", paths["book"], "--market", paths["market"],
            "--state", paths["state"], "--plan-id", case[0].plan_id, "--hash", case[0].fingerprint(),
            "--config-root", str(ROOT), "--journal", str(journal)]
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)

    class Broker:
        writes = 0
        reads = 0
        mode = "filled"
        overlap = None

        def read(self, account, symbol, account_types, *, clock):
            assert account == ACCOUNT and symbol == "US.SPY"
            self.reads += 1
            if self.mode == "read_failure" or (self.mode == "post_failure" and self.reads > 1):
                raise OSError("PRIVATE-ACCOUNT TOKEN RAW-PROVIDER-RESPONSE")
            return copy.deepcopy(payloads)

        def submit_exit(self, account, request, *, deadline, clock):
            assert deadline > clock()
            self.writes += 1
            saved = LifecycleState.model_validate_json(Path(paths["state"]).read_text())
            assert saved.reservations[-1].request_id == request.request_id
            assert read_events(journal)[-1]["payload"]["request_id"] == request.request_id
            assert verify_chain(journal)[0]
            assert request.side == "sell" and request.quantity == 10 and request.limit_price == 93.72
            with pytest.raises((RuntimeError, OSError)), journal_lock(journal):
                pytest.fail("journal must remain locked through submission")
            with pytest.raises(ValueError), locked_state(Path(paths["state"])):
                pytest.fail("grant must remain locked through submission")
            if self.overlap:
                self.overlap()
            if self.mode in {"unknown", "rejected"}:
                raise TimeoutError("PRIVATE-ACCOUNT TOKEN RAW-PROVIDER-RESPONSE")
            if self.mode == "receipt_only":
                return "broker-exit"
            filled = 10 if self.mode in {"filled", "lost_reply", "holdings_lag"} else 4
            payloads["orders"].append({
                "order_id": "broker-exit", "symbol": "SPY", "side": 2, "qty": "10",
                "cum_qty": str(filled), "status": 4 if filled == 10 else 2, "price": 93.72,
                "create_time": int(NOW.timestamp() * 1_000_000), "text": request.request_id,
            })
            if self.mode != "holdings_lag":
                positions = payloads["positions"]["data"]["positions"]
                if filled == 10:
                    positions.clear()
                else:
                    positions[0].update(qty=str(10 - filled), qty_avbl=str(10 - filled))
                payloads["cash"]["data"]["balance"] += filled * request.limit_price
                payloads["cash"]["data"]["total_asset"] = (
                    payloads["cash"]["data"]["balance"] + (10 - filled) * 94
                )
            if self.mode == "lost_reply":
                raise TimeoutError("reply lost after broker accepted")
            return "broker-exit"

    broker = Broker()
    monkeypatch.setattr("tyche.lifecycle_cli.MoomooPaperHttp.from_env", lambda: broker)
    return args, broker, payloads, paths, journal, case


def run(execution, submit=True):
    return CliRunner().invoke(app, execution[0] + (["--submit"] if submit else []))


def ledger(execution):
    return LifecycleState.model_validate_json(Path(execution[3]["state"]).read_text())


@pytest.mark.parametrize("mutation", ["journal_pending", "journal_rollback", "competition_cap",
                                      "available", "nav_mismatch", "state_missing"])
def test_mcp_reservation_enforces_execution_guards(execution, mutation):
    args, broker, _, paths, journal, case = execution
    market = case[2]
    if mutation in {"journal_pending", "journal_rollback", "competition_cap"}:
        count = case[4].risk.competition_order_cap if mutation == "competition_cap" else 1
        for index in range(count):
            append_event(journal, "order.requested", {
                "request_id": f"legacy-{index}", "symbol": "US.EFA" if count > 1 else "US.SPY",
                "side": "buy", "quantity": 1, "limit_price": 100,
                "authorization": {"as_of": NOW.date().isoformat(),
                                  "mode": "lifecycle" if mutation == "journal_rollback" else "tactical"},
            })
    elif mutation == "available":
        market.available["US.SPY"] = 4
    elif mutation == "nav_mismatch":
        market.snapshot.cash += 1000
    else:
        Path(paths["state"]).unlink()
    Path(paths["market"]).write_text(market.model_dump_json())
    result = CliRunner().invoke(app, ["lifecycle", "reserve", *args[2:]])
    assert result.exit_code == 1, result.output
    assert not json.loads(result.stdout).get("authorized")
    assert broker.writes == broker.reads == 0


def test_mcp_reservation_holds_journal_lock(execution, monkeypatch):
    from tyche import lifecycle_cli
    original = lifecycle_cli.append_locked

    def append(path, kind, payload):
        with pytest.raises((RuntimeError, OSError)), journal_lock(path):
            pytest.fail("reservation and journal write must share a lock")
        return original(path, kind, payload)

    monkeypatch.setattr(lifecycle_cli, "append_locked", append)
    result = CliRunner().invoke(app, ["lifecycle", "reserve", *execution[0][2:]])
    assert result.exit_code == 0, result.output


def test_exit_dry_run_does_not_mutate_or_submit(execution):
    before = Path(execution[3]["state"]).read_bytes()
    result = run(execution, submit=False)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["dry_run"]
    assert execution[1].writes == 0
    assert Path(execution[3]["state"]).read_bytes() == before
    assert len(read_events(execution[4])) == 1


@pytest.mark.parametrize("mode,outcome", [("filled", "filled"), ("partial", "pending"),
                                          ("lost_reply", "filled"), ("unknown", "unknown"),
                                          ("receipt_only", "unknown")])
def test_exit_once_reconciles_and_never_replays(execution, mode, outcome):
    execution[1].mode = mode
    first = run(execution)
    assert first.exit_code == (1 if outcome == "unknown" else 0), first.output
    response = json.loads(first.stdout)
    assert response["outcome"] == outcome and not response["retry_permitted"]
    assert response["filled"] == (outcome == "filled")
    assert execution[1].writes == 1
    run(execution)
    assert execution[1].writes == 1
    saved = ledger(execution).reservations[0]
    assert saved.complete == (outcome == "filled")
    assert len(ledger(execution).reservations) == 1
    assert "PRIVATE-ACCOUNT" not in first.output
    assert "TOKEN" not in execution[4].read_text()


@pytest.mark.parametrize("mutation", ["unapproved", "revoked", "wrong_hash", "live", "unallowlisted",
                                      "pending", "stale_quote", "stale_broker", "suspended",
                                      "available", "journal_missing", "journal_corrupt", "state_missing",
                                      "read_failure", "nav_mismatch"])
def test_unsafe_exit_never_reaches_broker(execution, mutation):
    args, broker, payloads, paths, journal, case = execution
    state = case[3]
    if mutation == "unapproved":
        state.approvals = []
    elif mutation == "revoked":
        state.approvals[0].revoked = True
    elif mutation == "wrong_hash":
        args[args.index("--hash") + 1] = "0" * 64
    elif mutation in {"live", "unallowlisted"}:
        context = case[2]
        if mutation == "live":
            context.snapshot.env = "live"
        else:
            context.snapshot.account_id = "NOT-ALLOWLISTED"
        Path(paths["market"]).write_text(context.model_dump_json())
    elif mutation == "pending":
        payloads["orders"][0].update(cum_qty="0", status=2)
    elif mutation == "stale_quote":
        payloads["quotes"]["data"]["quote_list"][0]["data_time"] -= 600_000
    elif mutation == "stale_broker":
        payloads["observed_at"] -= timedelta(minutes=3)
    elif mutation == "suspended":
        payloads["quotes"]["data"]["quote_list"][0]["suspension"] = True
    elif mutation == "available":
        payloads["positions"]["data"]["positions"][0]["qty_avbl"] = "3"
    elif mutation == "journal_missing":
        journal.unlink()
    elif mutation == "journal_corrupt":
        journal.write_text('{"bad": "chain"}\n')
    elif mutation == "read_failure":
        broker.mode = "read_failure"
    elif mutation == "nav_mismatch":
        payloads["cash"]["data"]["total_asset"] = 200000
    Path(paths["state"]).write_text(state.model_dump_json())
    if mutation == "state_missing":
        Path(paths["state"]).unlink()
    result = run(execution)
    assert broker.writes == 0, result.output
    assert "TOKEN" not in result.output and "PRIVATE-ACCOUNT" not in result.output


@pytest.mark.parametrize("mode", ["missing_research", "uncertain", "invalidated", "target", "deadline"])
def test_approved_protection_survives_research_gaps(execution, mode):
    broker, payloads, paths = execution[1:4]
    case = execution[5]
    book = case[1]
    if mode == "missing_research":
        Path(paths["book"]).unlink()
    else:
        if mode in {"uncertain", "invalidated"}:
            book.reviews[0].verdict = mode
        if mode in {"invalidated", "deadline"}:
            payloads["quotes"]["data"]["quote_list"][0]["last_price"] = 100
        if mode == "target":
            payloads["quotes"]["data"]["quote_list"][0]["last_price"] = 110
        if mode == "deadline":
            # The approved deadline trigger is independent of refreshed research.
            case[3].latched_exits[case[0].fingerprint()] = "holding_deadline"
            Path(paths["state"]).write_text(case[3].model_dump_json())
        Path(paths["book"]).write_text(book.model_dump_json())
    # Check reservation and eligibility without the fixture's price-specific submit assertion.
    if mode in {"invalidated", "target", "deadline"}:
        result = run(execution, submit=False)
        assert json.loads(result.stdout)["decision"]["action"] == "sell", result.output
    else:
        result = run(execution)
        assert broker.writes == 1, result.output


def test_no_exit_trigger_and_new_entry_never_submit(execution):
    payloads = execution[2]
    payloads["quotes"]["data"]["quote_list"][0]["last_price"] = 100
    result = run(execution)
    assert execution[1].writes == 0, result.output
    case = setup_case(held=0)
    for name, value in zip(("plan", "book", "market", "state"), case[:4], strict=True):
        Path(execution[3][name]).write_text(value.model_dump_json())
    execution[0][execution[0].index("--hash") + 1] = case[0].fingerprint()
    payloads["positions"]["data"]["positions"] = []
    payloads["cash"]["data"]["balance"] = 100000
    payloads["cash"]["data"]["total_asset"] = 100000
    result = run(execution)
    assert execution[1].writes == 0, result.output
    assert not ledger(execution).reservations


@pytest.mark.parametrize("failure", ["state", "journal", "expired_window"])
def test_durable_failure_or_expiry_stops_before_submission(execution, monkeypatch, failure):
    import tyche.lifecycle_cli as module
    original_save = module.save

    def save(path, value):
        if value.reservations and failure == "state":
            raise OSError("disk full")
        original_save(path, value)
        if value.reservations and failure == "expired_window":
            monkeypatch.setattr(module, "now_utc", lambda: NOW + timedelta(minutes=3))

    monkeypatch.setattr(module, "save", save)
    if failure == "journal":
        monkeypatch.setattr(module, "append_locked", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    result = run(execution)
    assert result.exit_code == 1 and execution[1].writes == 0
    if failure != "state":
        assert len(ledger(execution).reservations) == 1
        run(execution)
        assert execution[1].writes == 0


@pytest.mark.parametrize("mode", ["post_failure", "holdings_lag"])
def test_post_send_failure_is_not_reported_as_no_submission(execution, mode):
    execution[1].mode = mode
    result = run(execution)
    assert result.exit_code == 1, result.output
    response = json.loads(result.stdout)
    assert response["attempted"] and response["submitted"] is True
    assert not response["retry_permitted"]
    assert len(ledger(execution).reservations) == 1
    assert "TOKEN" not in result.output


def test_overlapping_exit_run_cannot_send(execution):
    def overlap():
        result = run(execution)
        assert result.exit_code == 1
        assert not json.loads(result.stdout)["attempted"]
    execution[1].overlap = overlap
    result = run(execution)
    assert result.exit_code == 0, result.output
    assert execution[1].writes == 1


def test_unmatched_other_lane_same_symbol_blocks_exit(execution):
    append_event(execution[4], "order.requested", {
        "request_id": "other-lane", "symbol": "US.SPY", "side": "buy",
        "quantity": 1, "limit_price": 100,
        "authorization": {"mode": "tactical", "as_of": NOW.date().isoformat()},
    })
    result = run(execution)
    assert result.exit_code == 1 and execution[1].writes == 0
    assert "unresolved journal" in result.stdout


def test_other_lane_daily_requests_consume_competition_capacity(execution, monkeypatch):
    config = execution[5][4]
    config.risk.competition_order_cap = 2
    monkeypatch.setattr("tyche.lifecycle_cli.load_config", lambda root: config)
    append_event(execution[4], "order.requested", {
        "request_id": "other-lane", "symbol": "US.EFA", "side": "buy",
        "quantity": 1, "limit_price": 100,
        "authorization": {"mode": "tactical", "as_of": NOW.date().isoformat()},
    })
    result = run(execution)
    assert result.exit_code == 1 and execution[1].writes == 0
    assert "across execution lanes" in result.stdout


def test_journal_survives_missing_reservation_state(execution):
    execution[1].mode = "unknown"
    run(execution)
    Path(execution[3]["state"]).write_text(execution[5][3].model_dump_json())
    result = run(execution)
    assert result.exit_code == 1 and execution[1].writes == 1
    assert "missing from lifecycle state" in result.stdout


def test_second_process_cannot_acquire_execution_journal(execution):
    with journal_lock(execution[4]):
        result = subprocess.run(
            [sys.executable, "-c",
             ("from pathlib import Path; import sys; from tyche.journal import journal_lock; "
              "journal_lock(Path(sys.argv[1])).__enter__()"), str(execution[4])],
            capture_output=True, text=True, check=False, timeout=15,
        )
    assert result.returncode != 0 and "journal busy" in result.stderr
    assert execution[1].writes == 0


@pytest.mark.parametrize("failure", ["state", "journal"])
def test_post_submission_persistence_failure_keeps_reservation(execution, monkeypatch, failure):
    import tyche.lifecycle_cli as module
    original_save, original_append = module.save, module.append_locked

    def save(path, value):
        if failure == "state" and value.reservations and value.reservations[-1].order_id:
            raise OSError("receipt persistence failed")
        original_save(path, value)

    def append(path, kind, payload):
        if failure == "journal" and kind == "order.submitted":
            raise OSError("receipt journaling failed")
        return original_append(path, kind, payload)

    monkeypatch.setattr(module, "save", save)
    monkeypatch.setattr(module, "append_locked", append)
    result = run(execution)
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["submitted"] is True
    assert len(ledger(execution).reservations) == 1
    run(execution)
    assert execution[1].writes == 1


def test_halt_does_not_disable_approved_protective_sell(execution):
    from tyche.halt import set_halt
    set_halt(execution[4].parent, True, "synthetic halt")
    result = run(execution)
    assert result.exit_code == 0, result.output
    assert execution[1].writes == 1


def test_after_hours_latches_without_submitting(execution, monkeypatch):
    after_hours = NOW.replace(hour=22)
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda: after_hours)
    execution[2]["observed_at"] = after_hours
    execution[2]["quotes"]["data"]["quote_list"][0]["data_time"] = int(after_hours.timestamp() * 1000)
    result = run(execution)
    assert result.exit_code == 0, result.output
    assert execution[1].writes == 0
    assert ledger(execution).latched_exits[execution[5][0].fingerprint()] == "stop_loss"


def test_read_only_reconciliation_does_not_replay_unknown_order(execution):
    execution[1].mode = "unknown"
    first = run(execution)
    assert json.loads(first.stdout)["submitted"] is None
    request = ledger(execution).reservations[0]
    execution[2]["orders"].append({
        "order_id": "late-broker-receipt", "symbol": "SPY", "side": 2, "qty": "10",
        "cum_qty": "10", "status": 4, "price": request.limit_price,
        "create_time": int(NOW.timestamp() * 1_000_000), "text": request.request_id,
    })
    execution[2]["positions"]["data"]["positions"] = []
    cash = execution[2]["cash"]["data"]
    cash["balance"] += 10 * request.limit_price
    cash["total_asset"] = cash["balance"]
    second = run(execution)
    assert second.exit_code == 0, second.output
    assert ledger(execution).reservations[0].complete
    assert execution[1].writes == 1
