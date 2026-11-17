# Persistence runbook

The Cloud Agent sandbox is ephemeral. Raw evidence is 60% of the score; without a
durable sink it is lost at session end. Two sinks, written every run (ADR 0009).

## Sinks

- **Raw → OSS bucket.** Journal, MCP payloads, plans, receipts. Append-only system
  of record. Mounted in the cloud via the `oss-bucket-2026-09-23` beta at
  `/mnt/buckets/<name>`.
- **Sanitized → git.** Id-free, token-free copies pushed to `origin/main` so the repo
  is a public, reproducible record.

`tyche persist` performs both and applies the sanitize gate:

```bash
tyche persist --raw <run-dir> --git <git-out-dir> --bucket /mnt/buckets/<name>
```

- Raw files are copied to the bucket unchanged.
- Text files are sanitized (full account ids and `Bearer` tokens replaced with
  `[REDACTED]`) and written to the git dir; binary files are bucket-only.
- Account ids to redact come from `account_allowlist` plus `TYCHE_ALLOWED_ACCOUNT_IDS`.
- After persist, commit and push the git dir. A run that cannot sanitize must not push.

## Provisioning (operator action, before the first cloud run)

1. Create an OSS bucket for raw artifacts; note its mount name.
2. Create a **least-privilege PAT** (repo push + bucket write only) at
   qoder.com/cloud/pat-keys. Store it server-side in a gitignored `.env` / vault.
   Never commit it or paste it into chat, logs, or the journal.
3. Attach the bucket mount (`oss-bucket-2026-09-23`) and the PAT to the executor /
   coordinator environment as appropriate (credentials only to roles that need them).
4. Set `TYCHE_ALLOWED_ACCOUNT_IDS` in the cloud vault to the paper account id(s).
5. Verify with a dry run: `tyche persist` on a sample dir, confirm the bucket copy is
   raw and the git copy is redacted, then `tyche journal-verify`.

## Verify

```bash
tyche journal-verify
grep -R "<full-account-id>" <git-out-dir>   # must return nothing
```

The sanitize gate is tested in `tests/test_persist.py`.