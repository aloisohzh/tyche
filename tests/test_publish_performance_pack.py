"""The publish step builds the day's performance pack from files only, and never at the feed's expense."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("publish_desk_data", ROOT / "scripts" / "publish_desk_data.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("publish_desk_data", module)
    spec.loader.exec_module(module)
    return module


def test_no_journal_means_no_pack(tmp_path: Path):
    assert _module().performance_args(tmp_path, "2026-11-23") is None


def test_args_name_only_the_price_files_that_exist_and_date_the_output(tmp_path: Path):
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "performance" / "2026-11-18-eod" / "data").mkdir(parents=True)
    (tmp_path / "docs" / "performance" / "2026-11-18-eod" / "data" / "prices.csv").write_text("date,symbol,close\n")
    (tmp_path / "docs" / "performance" / "spy-closes.csv").write_text("date,symbol,close\n")
    args, out = _module().performance_args(tmp_path, "2026-11-23")
    assert out == tmp_path / "docs" / "performance" / "2026-11-23-metrics.md"
    assert args[:2] == ["performance", "report"]
    assert args[args.index("--journal") + 1] == str(tmp_path / "journal" / "events.jsonl")
    prices = [args[i + 1] for i, a in enumerate(args) if a == "--prices"]
    assert prices == [str(tmp_path / "docs" / "performance" / "*" / "data" / "prices.csv"),
                      str(tmp_path / "docs" / "performance" / "spy-closes.csv")]


def test_pack_failure_is_reported_not_raised(tmp_path: Path, monkeypatch, capsys):
    module = _module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "events.jsonl").write_text("not json\n", encoding="utf-8")
    assert module.performance_pack() is None
    assert "PERFORMANCE PACK FAILED" in capsys.readouterr().out
