# Runbook: record a rules freeze on the Drive ledger

The desk reads one journal: the latest verified run bundle under `/data/drive/tyche-raw/`. A freeze row
anywhere else is not provenance (L-056). Run this between fires (weekday gaps: 04:05-21:05 SGT), from
a session on the desk environment with the Drive mount.

1. Find the live bundle and verify it:
   `tyche journal-verify --path /data/drive/tyche-raw/<latest-run>/journal/events.jsonl`
   (the later bundle must be a byte-prefix descendant of the earlier ones).
2. Never append inside a historical bundle. Copy it into a new one:
   `mkdir -p /data/drive/tyche-raw/<YYYY-MM-DD>-operator-freeze/journal &&
   cp /data/drive/tyche-raw/<latest-run>/journal/events.jsonl /data/drive/tyche-raw/<YYYY-MM-DD>-operator-freeze/journal/`
3. Check what would be written (read-only): `tyche rules-freeze --journal <new copy> --json`.
4. Record one lane at a time, each with the reason that is true for that lane:
   `tyche rules-freeze --record --journal <new copy> --lane PB-007 --reason "initial freeze e26f006da28a"`
   `tyche rules-freeze --record --journal <new copy> --lane PB-002 --lane PB-003 --reason "first row on the Drive ledger at d5ef9567c736 (defensives added 2026-11-23; b6bc571033ac before, recorded only on the laptop drill copy)"`
   `tyche rules-freeze --record --journal <new copy> --lane PB-001 --reason "first row on the Drive ledger; 819ad06e35f0 unchanged since 2026-11-19"`
   `tyche rules-freeze --record --journal <new copy> --lane PB-004 --reason "first row on the Drive ledger; 72077d5d4808 unchanged"`
   The command refuses a journal inside the repo checkout without `--drill`, and stamps rows `ledger: ledger`.
5. Verify the chain again and confirm `tyche rules-freeze --journal <new copy>` exits 0 (registered).
6. Leave the old bundle untouched. The next fire restores the newest verified descendant.

The 2026-11-24 run of this runbook closes the 2026-11-22 finding: five lanes, zero rows on the ledger.
