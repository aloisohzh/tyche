"""Export a sanitized charts page from journaled inputs (ADR 0015).

Close-only price CSV -> line series (no fabricated OHLC). Trade markers and
regime/NAV context come from the journal, filtered by --account; the account id
is used for filtering only and never embedded in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REGIME_COLORS = {
    "risk_on": "rgba(38, 166, 154, 0.45)",
    "neutral": "rgba(139, 148, 158, 0.45)",
    "risk_off": "rgba(239, 83, 80, 0.45)",
}
BUY_COLOR = "#26a69a"
SELL_COLOR = "#ef5350"


def _account_matches(event_account: str | None, account: str) -> bool:
    # order.submitted is journaled with the desk mask_id convention (***+last3);
    # plan.created may carry the raw id. Match both forms.
    return event_account == account or event_account == "***" + account[-3:]


def build_payload(prices_path: Path, journal_path: Path, account: str) -> dict:
    frame = pd.read_csv(prices_path, parse_dates=["date"])
    symbols: dict[str, list[dict]] = {}
    for symbol, group in frame.groupby("symbol"):
        group = group.sort_values("date")
        symbols[str(symbol)] = [
            {"time": day.strftime("%Y-%m-%d"), "value": round(float(close), 4)}
            for day, close in zip(group["date"], group["close"])
        ]
    if not symbols:
        raise ValueError(f"no price rows in {prices_path}")
    all_dates = sorted({point["time"] for points in symbols.values() for point in points})
    date_set = {symbol: {point["time"] for point in points} for symbol, points in symbols.items()}

    markers: dict[str, list[dict]] = {}
    omitted = 0
    regime_marks: list[tuple[str, str]] = []
    nav_marks: dict[str, float] = {}
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        payload = event.get("payload", {})
        if event["type"] == "order.submitted" and _account_matches(payload.get("account"), account):
            symbol = payload["symbol"]
            day = event["ts"][:10]
            if symbol not in date_set or day not in date_set[symbol]:
                omitted += 1
                continue
            buy = payload["side"] == "buy"
            markers.setdefault(symbol, []).append(
                {
                    "time": day,
                    "position": "belowBar" if buy else "aboveBar",
                    "color": BUY_COLOR if buy else SELL_COLOR,
                    "shape": "arrowUp" if buy else "arrowDown",
                    "text": f"{payload['side']} {payload['quantity']} @ {payload['limit_price']}",
                }
            )
        elif event["type"] == "plan.created":
            plan = payload.get("plan", {})
            if not _account_matches(plan.get("account_id"), account):
                continue
            regime_marks.append((plan["as_of"], plan["regime"]))
            nav_marks[plan["as_of"]] = float(plan["nav"])

    regime_marks.sort()
    strip = []
    for day in all_dates:
        regime = None
        for as_of, value in regime_marks:
            if as_of <= day:
                regime = value
            else:
                break
        strip.append(
            {
                "time": day,
                "value": 1 if regime else 0,
                "color": REGIME_COLORS.get(regime, "rgba(0,0,0,0)"),
            }
        )

    return {
        "account_label": account if account.startswith("SIM-") else "live sim account (id redacted)",
        "symbols": symbols,
        "markers": markers,
        "omitted_markers": omitted,
        "regime_strip": strip,
        "regimes": [
            {"from": as_of, "regime": value} for as_of, value in regime_marks
        ],
        "nav": [{"time": day, "value": nav_marks[day]} for day in sorted(nav_marks)],
        "prices_sha256": hashlib.sha256(prices_path.read_bytes()).hexdigest()[:12],
    }


def render(payload: dict, template_path: Path, out_path: Path) -> None:
    template = template_path.read_text(encoding="utf-8")
    html = template.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=Path("data/prices.csv"))
    parser.add_argument("--journal", type=Path, default=Path("journal/events.jsonl"))
    parser.add_argument("--account", required=True, help="Filter journal events; never embedded.")
    parser.add_argument("--out", type=Path, default=Path("desk-site/web/charts.html"))
    parser.add_argument(
        "--template", type=Path, default=Path(__file__).resolve().parents[1] / "templates" / "charts.html"
    )
    args = parser.parse_args()
    payload = build_payload(args.prices, args.journal, args.account)
    render(payload, args.template, args.out)
    print(
        f"Wrote {args.out}: {len(payload['symbols'])} symbols, "
        f"{sum(len(m) for m in payload['markers'].values())} markers "
        f"({payload['omitted_markers']} omitted outside price range), "
        f"{len(payload['nav'])} NAV marks, prices {payload['prices_sha256']}"
    )


if __name__ == "__main__":
    main()