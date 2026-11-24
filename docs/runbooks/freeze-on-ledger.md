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

## 2026-11-23 evening: PB-002/PB-003 cap cut (one lane pair only)

The tactical stock cap went 0.45 -> 0.25 on main, which re-hashes `config/tactical.yaml` and so the
PB-002/PB-003 pair (`d5ef9567c736` -> `a1d9df1c687c`). The other lanes are unchanged and need no row.
From a console session on `tyche-desk-drive`, between fires, with the repo on main at or after the cap commit:

```
cd /workspace/tyche && git checkout main && git pull
LATEST=$(ls -d /data/drive/tyche-raw/*/journal/events.jsonl | sort | tail -1)
tyche journal-verify --path "$LATEST"
NEW=/data/drive/tyche-raw/2026-11-23-cap-cut-freeze/journal
mkdir -p "$NEW" && cp "$LATEST" "$NEW/events.jsonl"
tyche rules-freeze --journal "$NEW/events.jsonl" --json
tyche rules-freeze --record --journal "$NEW/events.jsonl" --lane PB-002 --lane PB-003 --reason "stock_allocation_cap 0.45 -> 0.25 (d5ef9567c736 -> a1d9df1c687c), operator decision 2026-11-23 evening"
tyche journal-verify --path "$NEW/events.jsonl"
tyche rules-freeze --journal "$NEW/events.jsonl"
```

Expected: the check-only run reports PB-002 and PB-003 as drift (declared `a1d9df1c687c`, recorded
`d5ef9567c736`) and every other lane registered; the record run appends one `rules.refrozen` row per lane
(two events); the final verify is `ok` and the final `rules-freeze` exits 0. If the repo path differs,
substitute the checkout the desk uses.


## 2026-11-24 night: PB-002/PB-003 resting-order settings (one lane pair only)

Four keys joined `config/tactical.yaml` (`resting_entries`, `resting_reach_pct`, `resting_cutoff_minutes`,
`resting_take_profit`), which re-hashes the PB-002/PB-003 pair (`a1d9df1c687c` -> `58a3ce686238`). The
other lanes are unchanged and need no row. From a console session on `tyche-desk-drive`, between fires,
with the repo on main at or after the resting-orders commit:

```
cd /workspace/tyche && git checkout main && git pull
LATEST=$(ls -d /data/drive/tyche-raw/*/journal/events.jsonl | sort | tail -1)
tyche journal-verify --path "$LATEST"
NEW=/data/drive/tyche-raw/2026-11-24-resting-orders-freeze/journal
mkdir -p "$NEW" && cp "$LATEST" "$NEW/events.jsonl"
tyche rules-freeze --journal "$NEW/events.jsonl" --json
tyche rules-freeze --record --journal "$NEW/events.jsonl" --lane PB-002 --lane PB-003 --reason "resting-order settings added (a1d9df1c687c -> 58a3ce686238), operator direction 2026-11-24"
tyche journal-verify --path "$NEW/events.jsonl"
tyche rules-freeze --journal "$NEW/events.jsonl"
```

Expected: the check-only run reports PB-002 and PB-003 as drift (declared `58a3ce686238`, recorded
`a1d9df1c687c`); the record run appends one `rules.refrozen` row per lane; the final verify is `ok` and the
final `rules-freeze` exits 0. Until this runs, the kernel still trades (the freeze guard is a ledger check,
not an order gate) and the drift shows on the desk's rules panel.
