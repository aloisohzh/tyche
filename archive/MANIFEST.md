# Archive manifest

Superseded work kept for reuse, not deletion. Every entry says what it was, why it stopped, what
replaced it, and what would have to change to revive it. If an entry has no "replaced by", it was
abandoned, not finished - read the linked lesson before spending another window on it.

Nothing here is imported by the live system. `test_no_archived_code_is_imported` enforces that, so a
revival is a deliberate move back out of this directory plus a manifest update, not a silent import.

This is the **only** archive in the repo. It absorbed `docs/archive/` and `scripts/archive/` on
2026-11-20; three superseded-work dumps meant every future move had to ask which one it belonged in.

| Artifact | Era | Why it is here | Replaced by | Lesson |
|---|---|---|---|---|
| [bridge-site/](bridge-site/) | 2026-11-18 | Qoder Sites Edge Function meant to receive inbound Telegram/Forward webhooks. The gateway enforces same-origin on POST, so server-to-server deliveries with no `Origin` header were rejected | Outbound-only sentinel (`scripts/telegram.py`); no-PC inbound would need a cron poller | [L-003](../docs/lessons/LESSONS.md) |
| [cloud_bridge.py](cloud_bridge.py) | 2026-11-18 | Wiring for the same bridge: endpoint creation, `setWebhook`, PAT from `.env`. Dead with its target, but it is the only working example of Sites secret + webhook plumbing in the repo | - (kept as a how-to for any future inbound receiver) | [L-003](../docs/lessons/LESSONS.md) |
| [deploy_phase_schedules.py](deploy_phase_schedules.py) | 2026-11-19 | Deploy script for the hourly, then six-gate-fire desk cadence. Both cadences were cut the same day, and running it would overwrite the live cards | `deploy_two_fire_automation.py` (now three fires) | [L-019](../docs/lessons/LESSONS.md), [L-020](../docs/lessons/LESSONS.md) |
| [fix_executor_gate_wording.py](fix_executor_gate_wording.py) | 2026-11-19 | One-off exact-string edit to the executor prompt's confirmation wording | Re-pin through the API with the corrected prompt | [L-014](../docs/lessons/LESSONS.md), [L-021](../docs/lessons/LESSONS.md) |
| [cloud-agent-draft-2026-11.md](cloud-agent-draft-2026-11.md) | v0.1 | Draft Cloud Agent deployment spec. Its own header says the CLI + OAuth path cannot work in a cloud sandbox and "do not deploy from it as-is". Moved here from `.qoder/cloud-agent.md` in `6ee2b28` - a pure rename, byte-identical | The four live pinned agents, plus [agent-rules.md](../docs/agent-rules.md) for the repo-side rules | [L-009](../docs/lessons/LESSONS.md) |
| [evaluation-v0.1.md](evaluation-v0.1.md) | v0.1 | The original evaluation write-up, superseded by the journal-derived reports under `docs/performance/` | `docs/performance/` | - |
| [demo-plan-2026-11-16.json](demo-plan-2026-11-16.json) / [.md](demo-plan-2026-11-16.md) | 2026-11-16 | Pre-competition demo plan kept to show the plan schema's origin | Real plans under `/plans` (gitignored) | [L-025](../docs/lessons/LESSONS.md) |
| [deploy_hourly_schedule.py](deploy_hourly_schedule.py), [deploy_hourly_workflow.py](deploy_hourly_workflow.py), [arm_hourly_desk.py](arm_hourly_desk.py) | 2026-11-19 | The hourly / six-fire cadence family: create `tyche-hourly`, pause the phase anchors, then lift the validation hold and resume it. Every object it mutates is paused or cut, and `--apply` would rewrite live desk templates to a cadence the desk abandoned the same day | `deploy_two_fire_automation.py` for the cards; releasing the executor's rollout hold is a template edit plus a re-pin, not a schedule resume | [L-019](../docs/lessons/LESSONS.md), [L-020](../docs/lessons/LESSONS.md) |
| [deploy_et_header.py](deploy_et_header.py) | 2026-11-19 | One-off two-string patch that inserted ET into the digest header of the live *schedule* content. The header is now built by the card prompt and `scripts/telegram.py` | `deploy_two_fire_automation.py` + [sentinel runbook](../docs/runbooks/sentinel-telegram.md) | [L-005](../docs/lessons/LESSONS.md) |
| [deploy_envelope_sgt.py](deploy_envelope_sgt.py) | 2026-11-19 | One-off executor-prompt patch that moved `sim_trade_input_order` from `always_ask` to `always_allow` inside the operator envelope and added SGT headers. **Its effect is still live** (L-014 records the surprise that the tool now executes immediately); only the script is dead - its exact-match edits target a template captured at v12 | Dashboard arm/disarm plus `tyche authorize`; prompt changes go through the API and a new pin | [L-014](../docs/lessons/LESSONS.md), [L-021](../docs/lessons/LESSONS.md) |
| [deploy_event_discovery.py](deploy_event_discovery.py), [deploy_scout_data_suite.py](deploy_scout_data_suite.py), [deploy_youtube_clause.py](deploy_youtube_clause.py) | 2026-11-18/19 | One-off clause writers that patched the researcher and desk **Forward templates** (event discovery, the fixed-core/deep-dive data suite, the YouTube inbox). Each one is, by construction, a template write - the edit the desk stopped making when it moved to Managed-only, because a template write recompiles and can materialise a tool grant nobody asked for | [scripts/deploy_managed_agents.py](../scripts/deploy_managed_agents.py) `apply-system`, and the clause text itself now lives in the role skills under `skills/`, which the prompts point at instead of restating | [L-046](../docs/lessons/LESSONS.md), [L-048](../docs/lessons/LESSONS.md) |
| [deploy_role_skills.py](deploy_role_skills.py), [deploy_token_policy.py](deploy_token_policy.py) | 2026-11-20/21 | The Phase-2 role-skills driver (`pack`/`create`/`attach`/`roster`/`cards`/`grant`/`verify`) and the deny-by-default MCP allowlist tool. The subcommands survived; the target did not - they wrote `/forward/templates`, and `roster`/`cards` moved the same objects the Managed driver now owns directly | `deploy_managed_agents.py`, same shape and the same "one named target per call, reads first" rule, on one plane: agent, skill version, card pin | [L-046](../docs/lessons/LESSONS.md), [L-047](../docs/lessons/LESSONS.md) |
| [repin_stale_caps.py](repin_stale_caps.py) | 2026-11-21 | The chain walker that closed L-033 - auditor and researcher templates, then the desk template *and* its roster pins in one write, then the scheduled cards. Ran twice before the cutover; its first step is precisely what the Forward fence now forbids | `deploy_managed_agents.py apply-system` + `pin-card`, keeping what made this script trustworthy: byte-exact OLD assertions, a pre-change snapshot, and a post-write check that nothing outside the named field moved | [L-033](../docs/lessons/LESSONS.md), [L-045](../docs/lessons/LESSONS.md), [L-046](../docs/lessons/LESSONS.md) |
| [deploy_calendar_check.py](deploy_calendar_check.py), [verify_envelope_deploy.py](verify_envelope_deploy.py) | 2026-11-19 | Both are keyed to the **`tyche-hourly` Forward schedule**: one installed the calendar-drift clause into the `initial_events` of an object that fires nothing, the other reads that schedule plus the executor template back as "verification". A green run here never meant the desk was doing anything | The `CALENDAR DRIFT` paragraph in the authored card brief ([scripts/deploy_two_fire_automation.py](../scripts/deploy_two_fire_automation.py)), pushed to both scheduled cards with `--apply-update`; envelope state is read off the Managed agent | [L-019](../docs/lessons/LESSONS.md), [L-020](../docs/lessons/LESSONS.md) |

The first seven were live in `scripts/` until 2026-11-20. The last batch (2026-11-21, twelve files) left
when the desk was consolidated onto the Managed plane. All of them `import forward` from their own
directory, so a revival has to move them back under `scripts/` before the import resolves - which is the
point, and it is why `test_no_live_script_authors_a_forward_template` can be strict about `scripts/`.

## Deliberately not archived

- **`/plans/*.prompt.txt` and the cloud-desk JSON payloads.** Agent prompt and schedule snapshots that
  predate the current pins. They are informative but sit in a gitignored tree because raw plan payloads
  embed the paper account id (L-031); bulk-moving them into a tracked directory trades a hygiene rule
  for a convenience. Current prompts are authoritative in the platform and readable via `list_agents`.
- **Superseded cadences** (hourly, six-fire). Only the *decision* matters and it is recorded in
  [L-019](../docs/lessons/LESSONS.md) and [L-020](../docs/lessons/LESSONS.md); the JSON that expressed
  them is regenerable from the deploy scripts.

## Revival checklist

1. `git mv` the artifact out of `archive/` (keep history; never copy and re-add).
2. Update this manifest: move the row to whatever documents it now, or delete it with a note.
3. Re-read the linked lesson and state in the PR/commit why the original blocker no longer applies.
