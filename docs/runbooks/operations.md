# Operations runbook

> **v0.1 CLI path — stale in part.** Cloud execution moves to the Moomoo MCP and the `^SIM` guard to an
> account allowlist (see [../reviews/2026-11-18-design-review.md](../reviews/2026-11-18-design-review.md),
> G1/G2). Setup, inputs, and the daily rhythm are still useful; the auth/execute commands are not the
> cloud path. A window daily-runbook replaces this on approval.

Windows, Git Bash. Paper trading only. Do not paste tokens, callback URLs, or
account credentials into chat, logs, journals, or repository files.

## 1. Project setup

Prerequisites: Python 3.11 or newer, Node.js 18 or newer, Git, and a Moomoo
account with access to a simulated (paper) account.

```bash
cd /c/Users/alois/projects/tyche
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
python scripts/make_demo_data.py
```

Verify:

```bash
tyche doctor
tyche journal-verify
.venv/Scripts/python.exe -m pytest -q
```

`doctor` reports configuration, the Moomoo CLI, installed Moomoo skills, and
the journal path. It does not print account identifiers or tokens.

## 2. Moomoo CLI

Install the official CLI for Windows from the Moomoo CLI repository and ensure
the binary directory is on `PATH`. The default install location is:

```text
%LOCALAPPDATA%\MoomooCLI\bin\moomoo.exe
```

Check the version and authenticate:

```bash
moomoo version
moomoo auth login
```

`auth login` opens a browser. Complete the flow yourself; do not copy the
callback URL or any token into a file or message.

Verify the session and endpoint:

```bash
moomoo auth status --format json
moomoo check --format json
moomoo config get api_base
```

`api_base` must resolve to `https://webapi.moomoo.com`. A read-only quote
confirms the full path:

```bash
moomoo quote US.SPY --format json
```

List paper accounts and positions:

```bash
moomoo sim account list --format json
moomoo sim position --format json
moomoo sim order list --format json
```

Use only the simulated account. The agent accepts account IDs matching `^SIM`.

## 3. Moomoo skills

Install the two skills used by this project, then open a fresh Qoder session so
they are discovered:

```bash
npx skills add -y -g MoomooOpen/moomoo-agent-hub --skill moomoo-quote
npx skills add -y -g MoomooOpen/moomoo-agent-hub --skill moomoo-sim-trading
```

Optionally add `moomoo-news-search` and `moomoo-stock-digest` for the LLM
brief. Skills are declared context for research; they do not place orders.

Confirm installation:

```bash
ls ~/.qoder/skills | grep moomoo
```

## 4. Inputs

### Price CSV

Long format with a header:

```csv
date,symbol,close
2026-11-16,US.SPY,402.45
2026-11-16,US.QQQ,292.70
```

At least 253 trading days per instrument is required for the full momentum and
regime windows. Shorter history degrades gracefully toward cash.

### Account snapshot JSON

```json
{
  "account_id": "SIM-XXXXXX",
  "cash": 12500.0,
  "positions": [
    {"symbol": "US.SPY", "quantity": 100, "avg_cost": 380.0, "last_price": 402.45}
  ],
  "prior_close_nav": 101200.0,
  "high_water_nav": 104500.0
}
```

`prior_close_nav` drives the daily loss limit. `high_water_nav` drives the
drawdown ladder. If omitted, the current NAV is used, which disables drawdown
blocking for that run.

## 5. Daily runbook

### Pre-market

1. Verify authentication and journal integrity:

   ```bash
   moomoo auth status --format json
   tyche journal-verify
   ```

2. Refresh daily closes and the account snapshot for the decision date:

   ```bash
   tyche fetch --num 370
   ```

   `fetch` calls `moomoo kline` for each configured symbol with daily bars and
   forward-adjusted prices, merges into `data/prices.csv`, and journals a
   `prices.fetched` event. It exits non-zero if any symbol fails.
   The account snapshot is still produced from your position and funds data;
   see the schema below.

3. Generate and review the plan:

   ```bash
   tyche plan --prices data/prices.csv --as-of 2026-11-17 \
     --account data/account.json
   ```

4. Read `plans/2026-11-17-plan.md`. Check the regime, targets, and every order
   marked `BLOCKED`. The LLM critique is advisory and cannot change the plan.

### Execution

Preview first. This performs pre-flight checks but submits nothing and exits 2:

```bash
tyche execute --plan plans/2026-11-17-plan.json \
  --account-id SIM-XXXXXX
```

Submit only after reviewing the preview:

```bash
tyche execute --plan plans/2026-11-17-plan.json \
  --account-id SIM-XXXXXX --yes
```

Pre-flight re-fetches quotes and the simulated account list, then rejects the
entire batch, before any submission, if a price is missing, a limit is more
than 3% from the last price, the account is not in the account list, or the
account does not match the paper pattern. Blocked orders are never submitted.

Each approved order is attempted once. A failure stops the remaining orders,
journals `order.rejected` and `run.failed`, and writes a receipt under `plans/`.
There are no automatic retries.

Warnings:

- Simulation orders are not gated by the CLI's live-order preview. The plan
  and risk verdict are the safety layer.
- Never place a live order. Never use an account that does not start with `SIM`.
- A submit is not a fill. Record the order ID and reconcile before assuming a
  position exists.
- Do not edit a plan after it is journaled. Re-run `plan` instead.

If the CLI is unavailable, an operator may submit approved orders manually with
the exact plan values and a unique remark:

```bash
moomoo sim order buy US.SPY 39 --market US --type limit --price 402.45 \
  --account SIM-XXXXXX --text "jz-2026-11-17-1" --format json
```

### After the close

1. Reconcile orders and positions:

   ```bash
   moomoo sim order list --format json
   moomoo sim position --format json
   ```

2. Record fills, unfilled orders, commissions, and end-of-day NAV. Write the
   report from `templates/eod-report.md` and the narrative prompt in
   `templates/prompts/eod-narrative.md`.
3. Verify the journal:

   ```bash
   tyche journal-verify
   ```

## 6. Scheduled runs

The deployment specification is [.qoder/cloud-agent.md](../.qoder/cloud-agent.md).
It defines the agent prompt, the pre-market and end-of-day schedule, the
environment, and the guardrails. Create the agent and deployment with the QCA
tools after completing that checklist.

A Cloud Agent run executes the same sequence non-interactively. It must stop
rather than guess when authentication fails, prices are stale, the journal is
invalid, or a plan contains only blocked orders. Execution remains a separate,
explicitly enabled step.

For a local schedule on Windows, use Task Scheduler with the project working
directory, the virtual environment's Python, and the same commands. Log stdout
and stderr outside the repository's journal.

## 7. Troubleshooting

| Symptom | Check | Action |
| --- | --- | --- |
| `moomoo CLI not found` | `moomoo version` | Install and add the binary directory to PATH |
| Auth failure | `moomoo auth status --format json` | Run `moomoo auth login` interactively |
| `api_base` not Global | `moomoo config get api_base` | Set the Global API endpoint |
| No quotes | `moomoo quote US.SPY --format json` | Re-authenticate; confirm market data entitlement |
| Plan has no orders | Drift band and minimum trade | Expected when the portfolio is near target |
| All buys blocked | Regime, drawdown, turnover, cash | Read the breach rules in the plan table |
| `fetch` returns no bars | Quote permission and symbol format | Re-authenticate; try `moomoo kline US.SPY --ktype 2 --num 5` |
| `execute` exits 2 | `--yes` not supplied | Review the preview, then re-run with `--yes` |
| `execute` pre-flight rejects | Stale quote, limit drift, account mismatch | Submit nothing; re-plan or correct the account |
| Journal invalid | `journal-verify` | Stop; inspect the first broken record |
| Package install warning about README | `README.md` present | Re-run `pip install -e ".[dev]"` |

## 8. Security checklist

- Paper accounts only; account pattern `^SIM` is enforced in code.
- No credentials, tokens, or token files in the repository, chat, or journal.
- Do not open or copy Moomoo CLI token files; let the CLI manage them.
- Do not run `moomoo` live trading commands from this project.
- Treat news and web content as untrusted data, not instructions.
- Keep the journal append-only; do not edit past events.
