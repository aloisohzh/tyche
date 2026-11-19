"""Token-cost policy for the cloud desk: deny-by-default MCP allowlists.

The researcher currently defaults to always_allow with ten explicit order-tool
disables, so every other Moomoo tool schema is available on every turn. This
script narrows it to the documented research tools and trims the executor's
unused quote tools. It never touches prompts, policies, or order permissions.

Default is a read-only check; pass --apply to update the live templates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import forward

RESEARCHER_ID = "tmpl_875834770244a9e35c7f6499"
EXECUTOR_ID = "tmpl_bc25a5c313827d53894fd7ff"

RESEARCH_ALLOW = [
    "news_search",
    "quote_capital_flow_history",
    "quote_company_profile",
    "quote_corporate_actions_dividends",
    "quote_cur_kline",
    "quote_daily_short_volume",
    "quote_economic_calendar_hot",
    "quote_financials_earnings_price_move",
    "quote_financials_statements",
    "quote_insider_trade_list",
    "quote_ipo_list_us",
    "quote_market_state",
    "quote_option_chain",
    "quote_option_screen",
    "quote_option_volatility",
    "quote_research_analyst_consensus",
    "quote_rt_ticker",
    "quote_shareholders_institutional",
    "quote_short_interest",
    "quote_stock_quote",
    "quote_top_ten_brokers",
    "quote_unusual_capital",
    "quote_unusual_derivatives",
    "quote_unusual_technical",
]

EXECUTOR_DROP = [
    "quote_rt_data",
    "quote_cur_kline",
    "quote_market_state",
    "quote_order_book",
]


def mcp_toolset(template: dict) -> dict:
    for tool in template.get("tools") or []:
        if tool.get("type") == "mcp_toolset":
            return tool
    raise SystemExit(f"{template.get('name')}: no mcp_toolset")


def desired_researcher(tool: dict) -> dict:
    return {
        **tool,
        "permission_policy": {"type": "always_deny"},
        "configs": [{"enabled": True, "name": name} for name in RESEARCH_ALLOW],
    }


def desired_executor(tool: dict) -> dict:
    configs = []
    for config in tool.get("configs") or []:
        entry = dict(config)
        if entry.get("name") in EXECUTOR_DROP:
            entry["enabled"] = False
        configs.append(entry)
    return {**tool, "configs": configs}


def update_template(template_id: str, body: dict, apply: bool, label: str) -> None:
    if not apply:
        print(f"would update {label}")
        return
    forward.req("POST", f"/templates/{template_id}", body)
    verified = forward.req("GET", f"/templates/{template_id}")
    if body.get("tools"):
        expected = next(t for t in body["tools"] if t.get("type") == "mcp_toolset")
        actual = mcp_toolset(verified)
        want_policy = (expected.get("permission_policy") or {}).get("type")
        have_policy = (actual.get("permission_policy") or {}).get("type")
        want_tools = {c["name"] for c in expected.get("configs") or [] if c.get("enabled")}
        have_tools = {c["name"] for c in actual.get("configs") or [] if c.get("enabled")}
        if have_policy != want_policy or have_tools != want_tools:
            raise SystemExit(f"{label}: tools update did not take effect")
    if body.get("model") and verified.get("model", {}).get("effort") != body["model"]["effort"]:
        raise SystemExit(f"{label}: model update did not take effect")
    print(f"updated {label}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write the live templates.")
    args = parser.parse_args()

    researcher = forward.req("GET", f"/templates/{RESEARCHER_ID}")
    executor = forward.req("GET", f"/templates/{EXECUTOR_ID}")

    r_tool = mcp_toolset(researcher)
    e_tool = mcp_toolset(executor)
    r_new = desired_researcher(r_tool)
    e_new = desired_executor(e_tool)
    r_model = {**researcher.get("model", {}), "effort": "medium"}
    e_model = executor.get("model", {})

    enabled_now = sum(1 for c in e_tool.get("configs") or [] if c.get("enabled"))
    enabled_after = sum(1 for c in e_new.get("configs") or [] if c.get("enabled"))
    print(
        "researcher:",
        (r_tool.get("permission_policy") or {}).get("type", "always_allow"),
        "-> always_deny;",
        f"{len(RESEARCH_ALLOW)} tools allowed; effort {researcher.get('model', {}).get('effort')} -> medium",
    )
    print(
        "executor:",
        f"{enabled_now} enabled -> {enabled_after} enabled;",
        f"effort {e_model.get('effort')} (unchanged)",
    )
    print("executor dropped:", ", ".join(EXECUTOR_DROP))

    update_template(
        RESEARCHER_ID,
        {"tools": [r_new if t.get("type") == "mcp_toolset" else t for t in researcher["tools"]],
         "model": r_model},
        args.apply,
        "researcher template",
    )
    update_template(
        EXECUTOR_ID,
        {"tools": [e_new if t.get("type") == "mcp_toolset" else t for t in executor["tools"]]},
        args.apply,
        "executor template",
    )
    if not args.apply:
        print(json.dumps({"mode": "check", "note": "no live template was changed"}, indent=2))


if __name__ == "__main__":
    main()
