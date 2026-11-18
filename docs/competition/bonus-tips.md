# Bonus tips & scoring-maximization note (living document)

Companion to [scoring-map.md](scoring-map.md) (criterion → artifact → evidence) and
[rules.md](rules.md). Every tip here is either an explicit handbook recommendation or a
hard-won operational lesson from building tyche. Keep appending as we learn; mark status
`done` / `in progress` / `todo` so the final submission pass can audit it.

Weights: risk-adjusted return 25% · Qoder & Cloud Agent usage 30% · strategy & risk
design 30% · reusability & documentation 15%.

## 1. Explicit handbook tips

| # | Tip (handbook ref) | Why it scores | Status |
|---|---|---|---|
| H1 | 🎥 Record a short **screen capture of the dashboard in action** and submit it with the entry (§7) | Explicit bonus; proves unattended operation visually | todo (after dashboard P1) |
| H2 | Build the dashboard **locally first**, then optionally host on Qoder Sites (§7, FAQ) | Local is sufficient; publishing not required — screenshots or a generated HTML report also accepted | in progress (task #9) |
| H3 | Dashboard reads Cloud Agents via **PAT, server-side only**, in gitignored `.env` (§7) | Security discipline judges can verify; never client-side | todo |
| H4 | Keep **local version history of agent configs** with timestamped comments: retrieval time, agent id, QCA-returned version, change summary; verify after each update; carry over tool/MCP/skill bindings when replacing arrays (§8.1) | Reusability + reproducibility; cloud template must never be the only record | done (templates/cloud-export-2026-11-18.md) — keep refreshing |
| H5 | **Subagents, not one big agent**: researcher / executor / risk auditor; auditor in its own session so it cannot be talked into agreeing; orchestrator prompt: "never let the executor act on the researcher's output without the auditor's approval" (§8.2) | The exact topology the rubric rewards | done (roster 4/2/4 + advisor, prompt carries the sentence) |
| H6 | **Version everything you tune**: re-run 3–4 fixed eval prompts after each prompt/skill change, diff outputs before promoting; **pin versions** on the trading agent — unpinned `latest` is a real risk when judges replay runs (§8.2, §9) | Reproducibility under replay | partial — pins done; fixed eval-prompt suite todo |
| H7 | **Log decisions AND rejections as first-class artifacts** — one structured line per decision incl. rejected ones and why (§8.2) | Judges ask "what failed and why"; rejection log answers better than slides; gives the dashboard something real to chart | done (hash-chained journal, order.blocked/halt.skip rows) |
| H8 | Collaboration best practices (§9): one role per agent; **file ownership** stated; delegation criteria + output formats in the coordinator prompt (selecting agents does not force delegation); credentials only to agents that need them; advisor advises only | Orchestration quality is scored, not just presence | done (delegation contract + file ownership in desk prompt) |
| H9 | Channels: **Pairing mode** when others shouldn't task your agent; tokens only in token fields; first message = harmless connection check ("Say hello… Do not place any trades.") (§5) | Safe automation surface | pivoted to Telegram outbound push (WeChat abandoned 2026-11-18; Telegram not a Forward channel type); token server-side in template env vars with explicit operator authorization; runbook docs/runbooks/sentinel-telegram.md |
| H10 | Schedules: **test before long-term operation**; verify data permissions, output content, delivery destination; dedup/idempotency for external operations (§6) | Unattended runs must be provably safe | in progress — smoke-1/smoke-2 PASS; max_attempts 1; non-idempotent submit rule; rehearsal 1 `srun_843b2035dbc452e2b7848c06` FAILED at 30-min timeout (slow data path), remediated via researcher v5 + scripts/mcp_prices.py + 60-min timeout; digest verification pending re-rehearsal |
| H11 | Keep **everything in one project folder** — skills, code, dashboards, decision logs (§2) | Packaging the submission is much easier | done |
| H12 | FAQ: usage/credits view in the dashboard (Observability data); demo dashboard prompt in the Qoder Deck; final presentation may include screenshots instead of a hosted dashboard | Cheap extra polish | todo |

## 2. Our scoring playbook (mapped to weights)

**25% risk-adjusted return** — ~7 session marks make Sharpe noisy; the honest play is a
**smooth fee-net equity curve** (low-vol ETF ballast + small defined-risk event sleeves),
not heroic returns. Label small-n metrics provisional and show n. Evidence: fee-net NAV
curve, drawdown ladder actually firing (journal rule ids), turnover discipline (200/day
is a ceiling, not a target).

**30% Qoder & Cloud Agent usage** — pinned multi-agent roster with advisor; scheduled
pre-market/EOD runs with run history; **channel delivery (IM sinks or Telegram push)** so outputs land
in chat; dashboard + screen capture; reusable skills/scripts/typed core; rejection log;
least-privilege matrix (only executor holds trade tools, always_ask per order).

**30% strategy & risk design** — playbooks with thesis + edge + **explicit invalidation**;
risk card with every cap keyed and test-asserted; **kill-switch drill PASS record**
(deterministic tests + live broker-state evidence); fee model + EOD cash reconcile;
defined-risk options only (no naked short — margin/financing/forced-liq risk stated
honestly); pre-registration and "unvalidated" labeling in docs/validation/.

**15% reusability & documentation** — exported pinned templates; README quick start;
runbooks another operator can follow; final report + **Qoder-generated deck**; this note
+ scoring-map as the evidence index; live-reusable "flip switch" design (paper guard is
config, not code forks).

## 3. Hard-won operational lessons (keep these out of the submission's failure modes)

- **Reset Card = disqualification.** Never reset/revive the challenge account; drills go
  on the PERSONAL paper account only. Challenge account stays pristine for scored days.
- **Console Save strips roster pins** → re-pin via API after any console edit; template
  system/tools edits bump the compiled version (re-pin), env/vault edits do not.
- `update_forward_template` requires `name`; roster entries need the hybrid
  `{"type":"agent","template_id":…,"version":N}` shape for console ticks + pins.
- **Cloud sandbox has no moomoo CLI binary** → MCP-only path: researcher klines →
  data/prices.csv; executor snapshot JSONs → `tyche snapshot`; submissions via MCP with
  `tyche record-order` journaling. `tyche execute`/`fetch` are local-only.
- **Paper market orders are rejected while the market is closed** (backend biz error);
  use a marketable limit instead. A submit is not a fill; reconcile from broker state.
- **QR binding ≠ pairing** (two independent steps): QR scan authorizes the channel
  (`binding_status=bound`); in pairing mode the first real message generates a **Pairing
  Code prompt and NO session**; admin pairs code + identity + template; the original
  message is **not replayed** — resend after pairing. Mode is permanent per channel.
- **Personal WeChat binding failed in practice (2026-11-18):** the QR encodes a
  `liteapp.weixin.qq.com` mini-program URL; 5 sessions (4 API + 1 console) all expired at
  ~180 s TTL with **zero `scanned` events** even though the phone showed terms + bot chat.
  Abandoned; prefer a provider whose native client reports scans, or outbound push.
- **Forward channel types are only `wechat`, `wecom`, `feishu`, `dingtalk` (+ `teams`
  Global)** — no Telegram/Slack in the Channel API. A Telegram sentinel is still possible
  as outbound push: schedule runs call the Telegram Bot API with a vault-held token.
- Chat commands worth knowing: `/status`, `/clear`, `/cancel`, `/btw <question>`, and
  **`/target`** — returns the push-target JSON needed to wire **schedule sinks**.
- Auto-mode gates non-idempotent order submissions: inspect broker order state first,
  get explicit operator affirmation, never blind-retry.
- Full account ids never in committed files/chat/reports (masked …598/…748); ids live
  server-side in template env vars; raw payloads stay in gitignored run dirs.
- **Schedule attempt timeout is a hard wall.** Rehearsal 1 died at `timeout_ms` 1800000
  (30 min) with the researcher still fetching klines — no plan/verdict/digest. Two fixes:
  (a) raise `execution.timeout_ms` to 3600000 (60 min) via merge-patch; (b) remove the
  real bottleneck — the researcher was hand-transcribing each kline chunk into CSV through
  the model. `quote_cur_kline` accepts `num` up to **370** (one call covers the 252-bar
  lookback); large outputs auto-persist to `/tmp/tool-outputs/mcp_*.txt`, and
  `scripts/mcp_prices.py` parses them straight to `data/prices.csv`. Researcher prompt v5
  mandates this fast path; roster re-pinned to v5. Budget the slowest member, not the mean.

## 4. Submission checklist (deadline 30 Nov 2026, 23:59 SGT)

- [ ] Public repo with sanitized artifacts + journal evidence (switch to private after).
- [ ] Final report (docs/report.md) linking the scoring-map evidence.
- [ ] Qoder-generated deck explaining how the agent works.
- [ ] Dashboard screen capture (H1).
- [ ] Kill-switch drill PASS record in docs/validation/.
- [ ] Exported, pinned template configs with timestamped retrieval comments (H4).
- [ ] Fee-net performance pack from the journal (docs/performance/).
- [ ] Run history + channel delivery screenshots (automation evidence).
- [ ] No credentials/tokens/full account ids anywhere in the package (grep pass).