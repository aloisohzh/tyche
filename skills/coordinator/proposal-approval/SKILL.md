---
name: proposal-approval
description: Use when the 08:05 or 15:05 fire has an entry proposal that passed preview and needs the operator's Telegram approval before the envelope, audit, reserve and order. Trigger before any entry at those fires; never at 12:05.
role: coordinator
version: 1
---

# Proposal approval

Only an approved number on Telegram authorizes an entry; that rule is in the card. This is how to ask and how to read the answer. Implementation: scripts/telegram.py (wait_for_reply, wait_result).

## 1. Build the file
Copy templates/proposal-approval.example.json to a private run-local file and replace every value; the example declares itself EXAMPLE ONLY and is never sent. Each proposal carries n, lane, action, symbol, qty, entry, value, stop, target, exit_by, risk, direction, horizon, thesis, invalidation and notes. Numbers n are unique within the fire and never reused.

## 2. Preview, then wait
`python scripts/telegram.py render-proposal <file>` is offline; read it. Then `python scripts/telegram.py wait-for-reply <file>` sends the previews once and waits ten minutes. Never pass a longer --timeout. Running the same command again resumes the same window without a second preview; a rebuilt file starts a fresh window.

## 3. Read the JSON result, nothing else
outcome decided, reply, timeout or conflict; lists approved, denied, timed_out, pending; reply holds the last free text. Only a number under approved authorizes the existing envelope, exact-order audit, reserve and ONE paper order for exactly that proposal. denied, timed_out, pending, conflict, a non-zero exit (conflict exits 2: another program is reading the bot) or any free text is a no.

## 4. Questions and changes
outcome reply with a question: answer it with `python scripts/telegram.py send` and run the same wait-for-reply command again. A requested change is a no: record it, rebuild the proposal under a new number, re-audit and send the fresh preview.

## 5. After the window
Never submit after the deadline in the result, never approve on the operator's behalf, and list every proposal with its decision in the digest's Proposals section. Cancel and modify asks stay on the console path.
