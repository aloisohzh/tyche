# tyche documentation changelog

Version history of the product description, not of the code. `git log` is the code history; this file
records when the **described product** changed, which is what a reader needs to judge whether a claim in
[PRD.md](PRD.md) is still current.

| Date | PRD | Changed | Evidence |
|---|---|---|---|
| 2026-11-20 | v1.1 | Hosted-desk provenance corrected and made safe: `web/vendor/` moved to a real source (`dashboard/static/vendor/`) and `charts.html` is now carried across the exporter's `rmtree`, which had been deleting assets nothing regenerates (L-039). The PRD no longer calls `desk-site/` plain generated output - the Sites Function and the tracked data feed are load-bearing. Capability statuses became machine-checked against the vocabulary in [README.md](README.md). | [../docs/lessons/LESSONS.md](../docs/lessons/LESSONS.md) L-039, `scripts/export_dashboard.py`, `tests/test_docs_consistency.py` |
| 2026-11-20 | v1.0 | First PRD and first current-state architecture. Capability map added with per-item statuses; §7 defect list opened with the two prompt/config disagreements (L-033) and the missing freeze-provenance writer (L-035). Backfilled the v0.1 → v0.2 gap that DESIGN.md never recorded as a product change. | [architecture.md](architecture.md), [../docs/reviews/2026-11-20-platform-refinement-audit.md](../docs/reviews/2026-11-20-platform-refinement-audit.md) |
| 2026-11-20 | - | Desk cadence corrected in [../docs/agent-engineering.md](../docs/agent-engineering.md): the live object is one card per month firing 08:05 / 12:05 (watch-only) / 15:05 ET on trading days, not the six-fire hourly cron the doc still described. Five deploy scripts for the cut cadences moved to [../archive/MANIFEST.md](../archive/MANIFEST.md). | `scripts/deploy_two_fire_automation.py:53-63`, commit `8eb6a64` |
| 2026-11-20 | - | Freeze source fixed: every playbook id now resolves to the file that governs it (`PLAYBOOK_LANES`), and no documentation path sits inside a frozen file. PB-004 gained its first hash. | [../docs/adr/0014-per-strategy-isolation.md](../docs/adr/0014-per-strategy-isolation.md), commit `d2ac6cd` |
| 2026-11-20 | - | Numeric caps removed from [../DESIGN.md](../DESIGN.md)'s "current runtime values" banner (they had drifted to 40 orders/day and 150% turnover against a config of 120 and 300%). `config/risk.yaml` + [../docs/risk-card.md](../docs/risk-card.md) are the only places they are written down. | L-033 |

## How to keep this honest

1. Status changes are edits here, not in passing prose: promote or demote a capability in the PRD table,
   then add a row above with the evidence.
2. Anything that can only be verified against the live platform (agent versions, tool grants, card
   schedules) gets a "verified on <date>" marker, because it silently rots otherwise.
3. Local markdown links are asserted by `tests/test_docs_consistency.py::test_markdown_links_resolve`,
   so a rename cannot leave this tree pointing at nothing (L-038).
4. Statuses are machine-checked, not stylistic: `test_prd_capability_statuses_use_the_fixed_vocabulary`
   reads the vocabulary out of [README.md](README.md) and rejects any PRD capability row that opens with
   another word. A row that cannot be described with one of the five words is a scope question, not an
   editing problem.
