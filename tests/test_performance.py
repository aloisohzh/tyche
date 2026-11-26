"""The fee-net performance pack: a reading of the record, never an invention.

The properties worth guarding: the EOD reconcile beats a published mark for the same day; a day
with no mark is left out rather than carried forward; a missing SPY close is reported, not
interpolated; the statistics match hand arithmetic; and the same inputs render the same bytes.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.journal import append_event
from tyche.performance import (
    account_days_from_feed,
    account_days_from_journal,
    account_key,
    benchmark_closes,
    build_pack,
    fees_from_journal,
    mark_basis_from_journal,
    max_drawdown,
    orders_per_day,
    rejections,
    render_markdown,
    to_json,
)

D17, D18, D19, D20, D25 = (date(2026, 11, d) for d in (17, 18, 19, 20, 25))


def events() -> list[dict]:
    blocked = {"intent": {"symbol": "US.SPY", "side": "buy"},
               "verdict": {"allowed": False, "breaches": [{"rule": "order.max_notional", "detail": "too big"}]}}
    allowed = {"intent": {"symbol": "US.EFA", "side": "buy"}, "verdict": {"allowed": True, "breaches": []}}
    return [
        {"ts": "2026-11-17T13:00:00+00:00", "type": "plan.created",
         "payload": {"plan": {"as_of": "2026-11-17", "nav": 100000.0, "orders": [blocked, allowed]}}},
        {"ts": "2026-11-18T14:40:00+00:00", "type": "order.submitted", "payload": {"symbol": "US.SPY"}},
        {"ts": "2026-11-18T14:41:00+00:00", "type": "order.submitted", "payload": {"symbol": "US.EFA"}},
        {"ts": "2026-11-18T17:07:00+00:00", "type": "order.rejected",
         "payload": {"symbol": "US.DBC", "decision_by": "operator", "reason": "withdrawn"}},
        {"ts": "2026-11-18T21:11:00+00:00", "type": "eod.reconcile",
         "payload": {"date": "2026-11-18", "nav": 99000.0, "fees_modeled": 1.98, "fees_implied": 2.0,
                     "reconcile_ok": True}},
        {"ts": "2026-11-19T13:00:00+00:00", "type": "plan.created",
         "payload": {"plan": {"as_of": "2026-11-19", "nav": 99500.0, "orders": []}}},
        {"ts": "2026-11-20T14:00:00+00:00", "type": "order.submitted", "payload": {"symbol": "US.QQQ"}},
    ]


def feed() -> dict:
    return {
        "feed": {"primary_account": "***598"},
        "nav_marks": {
            "***598": [
                {"ts": "2026-11-18T18:00:00+00:00", "as_of": "2026-11-18", "nav": 99974.12},
                {"ts": "2026-11-18T22:00:00+00:00", "as_of": "2026-11-18", "nav": 99930.67},
                {"ts": "2026-11-21T03:00:00+00:00", "as_of": "2026-11-20", "nav": 98000.0},
                {"ts": "2026-11-21T04:00:00+00:00", "as_of": "snapshot", "nav": 1.0},
            ],
            "SIM-DEMO-US": [{"ts": "2026-11-18T00:00:00+00:00", "as_of": "2026-11-18", "nav": 100000.0}],
        },
        "expectancy": {"fee_net_series": [{"date": "2026-11-19", "trades": 3, "gross": 72.34, "fees": 5.95,
                                           "net": 66.39, "cumulative_net": 66.39}]},
    }


def prices_csv(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path = tmp_path / "prices.csv"
    path.write_text("date,symbol,close\n" + "".join(f"{d},{s},{c}\n" for d, s, c in rows), encoding="utf-8")
    return path


def test_reconcile_beats_published_mark_and_plan_nav_is_only_a_fallback():
    days = account_days_from_feed(feed(), "***598")
    assert days == {D18: 99930.67, D20: 98000.0}  # last mark per day wins; "snapshot" is skipped
    days.update(account_days_from_journal(events()))
    assert days[D18] == 99000.0  # eod.reconcile over the published mark
    assert days[D19] == 99500.0  # plan nav stands in for a day that never reconciled
    assert days[D20] == 98000.0  # no journal row for the 20th, so the feed mark stays


def test_pack_statistics_match_hand_arithmetic(tmp_path: Path):
    closes = benchmark_closes([prices_csv(tmp_path, [
        ("2026-11-17", "US.SPY", "700"), ("2026-11-18", "US.SPY", "693"), ("2026-11-18", "US.QQQ", "1"),
        ("2026-11-20", "US.SPY", "707"),
    ])])
    assert closes == {D17: 700.0, D18: 693.0, D20: 707.0}
    pack = build_pack(account="***598", start_day=D17, start_nav=100000.0,
                      account_days={D18: 99000.0, D19: 99500.0, D20: 98000.0},
                      benchmark=closes, events=events())
    assert [r.day for r in pack.rows] == [D17, D18, D19, D20]
    r18, r19, r20 = pack.rows[1:]
    assert round(r18.daily_return, 9) == -0.01 and round(r18.benchmark_return, 6) == -0.01
    assert round(r18.active_return, 9) == 0.0
    assert r19.benchmark_close is None and r19.active_return is None
    assert pack.missing_benchmark_days == [D19]
    assert round(r20.cumulative_return, 4) == -0.02 and round(r20.benchmark_return, 4) == 0.01
    assert round(r20.active_return, 4) == -0.03
    assert pack.max_drawdown == max_drawdown([100000.0, 99000.0, 99500.0, 98000.0])
    assert round(pack.max_drawdown, 4) == -0.02
    assert round(r20.drawdown, 4) == -0.02 and round(r19.drawdown, 4) == -0.005
    assert pack.n_returns == 3 and pack.realized_vol is not None and pack.sharpe is not None
    assert pack.sharpe < 0  # three down-leaning marks


def test_failed_reconcile_is_not_reported_as_reconciled():
    rows = events() + [{
        "ts": "2026-11-25T21:00:00+00:00", "type": "eod.reconcile",
        "payload": {"date": "2026-11-25", "nav": 99284.768, "fees_modeled": 5.26,
                    "fees_implied": 7.365, "reconcile_ok": False},
    }]
    fees = fees_from_journal(rows)
    assert fees == {"modeled": 7.24, "implied": 9.365, "unreconciled": 2.125,
                    "recorded_days": 2, "reconciled_days": 1, "unresolved_days": 1}
    pack = build_pack(account="***598", start_day=D17, start_nav=100000.0,
                      account_days={D18: 99000.0, D25: 99284.768}, benchmark={}, events=rows)
    text = render_markdown(pack)
    assert "Modelled fees over 2 recorded reconcile day(s)" in text
    assert "1 reconciled; 1 unresolved" in text


def test_max_drawdown_is_from_the_running_peak():
    assert max_drawdown([100, 110, 99, 120, 90]) == 90 / 120 - 1
    assert max_drawdown([100, 101, 102]) == 0.0
    assert max_drawdown([]) == 0.0


def test_activity_and_rejection_log_read_the_journal():
    assert orders_per_day(events()) == {D18: 2, D20: 1}
    rows = rejections(events())
    kinds = [(r["kind"], r["rule"]) for r in rows]
    assert ("kernel.blocked", "order.max_notional") in kinds
    assert ("order.rejected", "operator") in kinds
    assert all(r["symbol"] != "US.EFA" for r in rows)  # an allowed order is not a rejection


def test_no_benchmark_means_no_baseline_not_a_guess():
    pack = build_pack(account="a", start_day=D17, start_nav=100000.0, account_days={D18: 99000.0},
                      benchmark={}, events=[])
    assert pack.benchmark_base_day is None and pack.rows[1].benchmark_return is None
    text = render_markdown(pack)
    assert "no baseline" in text and "n=1" in text and "not computable" in text


def test_weekend_start_uses_the_nearest_earlier_close():
    pack = build_pack(account="a", start_day=date(2026, 11, 15), start_nav=1.0, account_days={D17: 1.1},
                      benchmark={date(2026, 11, 13): 50.0, D17: 55.0}, events=[])
    assert pack.benchmark_base_day == date(2026, 11, 13)
    assert round(pack.rows[-1].benchmark_return, 6) == 0.1


def test_render_is_deterministic_and_carries_the_provisional_label(tmp_path: Path):
    closes = benchmark_closes([prices_csv(tmp_path, [("2026-11-17", "US.SPY", "700"), ("2026-11-18", "US.SPY", "693")])])
    kwargs = {"account": "***598", "start_day": D17, "start_nav": 100000.0,
                  "account_days": {D18: 99000.0, D19: 99500.0}, "benchmark": closes, "events": events(),
                  "fee_net_series": feed()["expectancy"]["fee_net_series"], "sources": ["x"]}
    one, two = render_markdown(build_pack(**kwargs)), render_markdown(build_pack(**kwargs))
    assert one == two
    assert "Provisional" in one and "SPY close missing for: 2026-11-19" in one
    assert "| 2026-11-18 | 2 | 1.0% |" in one
    assert "| 2026-11-19 | 3 | 72.34 | 5.95 | 66.39 | 66.39 |" in one
    assert "T" not in one.split("as of ")[1][:10]  # the as-of is a date, never a timestamp
    data = json.loads(json.dumps(to_json(build_pack(**kwargs))))
    assert data["rows"][1]["nav"] == 99000.0 and data["orders_per_day"] == {"2026-11-18": 2, "2026-11-20": 1}


def test_cli_verifies_the_chain_reads_feed_and_prices_and_writes_both_files(tmp_path: Path):
    journal = tmp_path / "journal" / "events.jsonl"
    journal.parent.mkdir()
    for ev in events():
        append_event(journal, ev["type"], ev["payload"])
    feed_path = tmp_path / "state.json"
    feed_path.write_text(json.dumps(feed()), encoding="utf-8")
    prices = prices_csv(tmp_path, [("2026-11-17", "US.SPY", "700"), ("2026-11-18", "US.SPY", "693")])
    out = tmp_path / "docs" / "performance" / "metrics.md"
    result = CliRunner().invoke(app, [
        "performance", "report", "--journal", str(journal), "--feed", str(feed_path),
        "--prices", str(prices), "--out", str(out), "--json-out", str(tmp_path / "pack.json"),
    ])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "Account ***598" in text  # the feed's primary account, not asked for on the command line
    assert "| 2026-11-18 | 99,000.00 |" in text  # the reconcile, not the published 99,930.67
    pack = json.loads((tmp_path / "pack.json").read_text(encoding="utf-8"))
    assert pack["benchmark"]["base_close"] == 700.0
    assert "SPY close missing" in result.output


def test_cli_refuses_a_broken_chain_unless_told_it_is_a_sanitized_copy(tmp_path: Path):
    journal = tmp_path / "events.jsonl"
    journal.write_text(json.dumps({"ts": "2026-11-18T00:00:00+00:00", "type": "eod.reconcile", "hash": "bad",
                                   "prev_hash": "", "payload": {"date": "2026-11-18", "nav": 1.0}}) + "\n",
                       encoding="utf-8")
    refused = CliRunner().invoke(app, ["performance", "report", "--journal", str(journal), "--feed", "none.json"])
    assert refused.exit_code == 2 and "FAILED" in refused.output
    allowed = CliRunner().invoke(app, ["performance", "report", "--journal", str(journal), "--feed", "none.json",
                                       "--skip-verify", "--start", "2026-11-17", "--start-nav", "1.0"])
    assert allowed.exit_code == 0 and "| 2026-11-18 | 1.00 |" in allowed.output


def test_journal_rows_for_another_account_are_dropped_by_masked_id():
    """The laptop journal holds plans for the personal paper account (~999k) beside the challenge
    account; one of those rows read as the 17 Nov mark put a -90% drawdown on the challenge book."""
    rows = [
        {"ts": "2026-11-17T13:00:00+00:00", "type": "plan.created",
         "payload": {"plan": {"as_of": "2026-11-17", "nav": 999056.26, "account_id": "123456748", "orders": []}}},
        {"ts": "2026-11-17T14:00:00+00:00", "type": "plan.created",
         "payload": {"plan": {"as_of": "2026-11-17", "nav": 100000.0, "account_id": "123456598", "orders": []}}},
        {"ts": "2026-11-18T21:00:00+00:00", "type": "eod.reconcile",
         "payload": {"date": "2026-11-18", "nav": 999100.0, "account": "...748"}},
        {"ts": "2026-11-18T21:30:00+00:00", "type": "eod.reconcile",
         "payload": {"date": "2026-11-18", "nav": 99914.93, "account": "...598"}},
        {"ts": "2026-11-19T13:00:00+00:00", "type": "plan.created",
         "payload": {"plan": {"as_of": "2026-11-19", "nav": 99927.13, "account_id": "[REDACTED]", "orders": []}}},
    ]
    assert account_key("123456598") == "***598" and account_key("...598") == "***598"
    assert account_key("***598") == "***598" and account_key("[REDACTED]") == "[REDACTED]"
    assert account_days_from_journal(rows, "***598") == {D17: 100000.0, D18: 99914.93, D19: 99927.13}
    assert account_days_from_journal(rows, "***748") == {D17: 999056.26, D18: 999100.0, D19: 99927.13}
    assert account_days_from_journal(rows)[D18] == 99914.93  # no filter: last row wins, as before


def test_each_mark_says_what_it_is_and_feed_rows_carry_the_intraday_caveat():
    basis = mark_basis_from_journal(events(), "***598")
    assert basis == {D17: "plan", D18: "close", D19: "plan"}
    pack = build_pack(account="***598", start_day=D17, start_nav=100000.0,
                      account_days={D18: 99000.0, D19: 99500.0, D20: 98000.0},
                      benchmark={D17: 700.0, D20: 707.0}, events=events(), mark_basis=basis)
    assert [r.basis for r in pack.rows] == ["start", "close", "plan", "feed"]
    text = render_markdown(pack)
    assert "| 2026-11-20 | 98,000.00 | feed |" in text
    assert "a `feed` row (2026-11-20) compares an intraday desk mark" in text
    pack2 = build_pack(account="a", start_day=D17, start_nav=1.0, account_days={D18: 1.0}, benchmark={}, events=[],
                       mark_basis={D18: "close"})
    assert "Mark basis" not in render_markdown(pack2)
