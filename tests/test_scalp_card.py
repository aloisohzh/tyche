"""The scalp card brief: one run at a time, ten minutes at most, and the operator's rulings."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("scalp_card", ROOT / "scripts" / "deploy_scalp_card.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_scalp_run_is_time_boxed_and_locked_so_two_runs_never_overlap():
    mod = _module()
    prompt = mod.card_prompt()
    assert prompt.index("TIME LIMIT") < prompt.index("GATE")
    assert prompt.index("RUN LOCK") < prompt.index("GATE")
    for must in ("at most 10 minutes", "immediately before each", "Never submit an order after",
                 "scalp-lock.json", "under 12 minutes old", "delete it as", "stale: overwrite it"):
        assert must in prompt, must
    assert all(mod.prompt_markers(prompt).values())


def test_the_scalp_card_knows_closed_orders_and_what_counts_as_an_outage():
    prompt = _module().card_prompt()
    for must in ("SMH 3118500 and VNQ 3116597 are closed", "Empty", "positions are broker truth",
                 "only an error code"):
        assert must in prompt, must


def test_apply_update_refuses_anything_but_the_scalp_card():
    source = (ROOT / "scripts" / "deploy_scalp_card.py").read_text()
    assert '"--apply-update" in sys.argv' in source
    assert "refusing to update a deployment that is not the Tyche scalp card" in source
