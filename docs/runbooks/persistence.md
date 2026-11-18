# Persistence runbook

The Cloud Agent sandbox is ephemeral. Raw evidence is load-bearing for judging;
without a durable sink it is lost at session end. Two sinks, written every run
(ADR 0009, amended 2026-11-18: Drive primary, OSS deferred).

## Sinks

- **Raw → Qoder Drive locker.** Journal, MCP payloads, plans, receipts. Append-only
  system of record at `/data/drive/tyche-raw/<run>/`. Identity-private, persistent
  across sessions, zero provisioning (operator decision 2026-11-18).
- **Sanitized → git.** Id-free, token-free copies pushed to `origin/main` so the repo
  is a public, reproducible record for the submission window.
- **Operator copies → DeliverArtifacts.** After persist, deliver the raw run bundle
  and the EOD report; they appear in console Files for download. The console Files
  tab is NOT a Drive browser: it shows uploaded inputs and delivered artifacts.

`tyche persist` performs both sinks and applies the sanitize gate:

```bash
tyche persist --raw <run-dir> --git <git-out-dir> --bucket /data/drive/tyche-raw
```

- Raw files are copied to the bucket dir unchanged. Any mounted path works; an OSS
  bucket mount (`/mnt/buckets/<name>`, beta `oss-bucket-2026-09-23`) can replace
  Drive later with no code change.
- Text files are sanitized (full account ids and `Bearer` tokens replaced with
  `[REDACTED]`) and written to the git dir; binary files are bucket-only.
- Account ids to redact come from `account_allowlist` plus `TYCHE_ALLOWED_ACCOUNT_IDS`.
- After persist, commit and push the git dir, then DeliverArtifacts the raw bundle
  and the EOD report. A run that cannot sanitize must not push.

## Provisioning (operator action, before the first cloud run)

1. Raw sink: nothing to provision for Drive. Optional later: create an OSS bucket
   (+ RAM role/AccessKey) and attach the mount in Environment settings; then switch
   the `--bucket` path.
2. Create a **least-privilege PAT** (repo push only) at qoder.com/cloud/pat-keys.
   Store it server-side in a gitignored `.env` / vault. Never commit it or paste it
   into chat, logs, or the journal. (Done 2026-11-18 via the console Repositories tab.)
3. Set `TYCHE_ALLOWED_ACCOUNT_IDS` to the challenge paper account id only, on the
   desk and executor templates. (Done 2026-11-18 via API at operator request.)
   Personal paper account ids stay out of the cloud allowlist; local drills use a
   gitignored local `.env`.
4. Verify with a dry run: `tyche persist` on a sample dir, confirm the bucket copy is
   raw and the git copy is redacted, then `tyche journal-verify`.

## Verify

```bash
tyche journal-verify
grep -R "<full-account-id>" <git-out-dir>   # must return nothing
```

The sanitize gate is tested in `tests/test_persist.py`.