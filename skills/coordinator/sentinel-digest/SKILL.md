---
name: sentinel-digest
description: Use when writing or sending any Telegram output for a tyche desk run - routine digest, no-order note, or urgent risk alert. Trigger at the end of a fire and immediately when a level is breached or a lot has no live exit.
role: coordinator
version: 1
---

# Sentinel digest

Presentation only. Grants no extra run, message or trade, and never touches a gate, recipient, schedule or secret binding.

## Facts first
Every line is backed by this run's journal, a plan file, or a broker read taken in this run. Unverified is written `Not verified`, never `None`, never blank. A held position is not a new order. Explain codes in ordinary words first ("another process placed orders", "no shares filled"), then keep the short rule, audit and reserve references. Use hyphens, not em dashes.

## Fill the JSON
Copy `templates/sentinel-digest.example.json` to a private run-local file and replace every value; never send the example, it declares itself `EXAMPLE ONLY`. Fields: `phase`, `timestamp` (UTC/ET/SGT), `urgent`, `mode` (verified armed, observe-only or kill-switch state), `stance` (one sentence of mood and what the desk did), `orders_summary`, `orders[]` as action/symbol/qty/value/status/reason, `account` as nav/cash/positions/kill_switch, `protection[]`, `problems[]`, `proposals[]` (keep each one-line thesis and invalidation), `next_check` (verified, never promised). The renderer rejects multi-line and over-long values.

Sections print in this order: Orders, Account, Protection, Problems, then Proposals and Next check when relevant. Only ACTION SYMBOL QTY goes in the monospace table; value, status and reason are grouped below it. No rows means drop the table, keep the summary. Set `urgent` only for a breach or an uncovered lot; the title then carries ` - URGENT RISK ALERT`.

## Preview, send, interpret
`python scripts/telegram.py render-digest <file>` and read it, then `python scripts/telegram.py send-digest <file>`. A render error means nothing was sent: shorten prose while keeping every material risk fact, then validate again; the renderer enforces the length cap. Exit 0 is delivered. Exit 2 is UNCONFIRMED, so the chat may already have the message: never retry blindly, record the uncertainty in the run report and in Problems, and retry only once non-delivery is proven. Delivery failure never blocks risk work.

## If the renderer is not in the mounted repo
Compose the identical layout as escaped Telegram HTML (`<b>` headings, one `<pre>ACTION SYMBOL QTY</pre>` table) and call `python scripts/telegram.py send` through a Python argument array. Never raw curl, never shell-interpolated text, never plain text as a fallback.
