# PG-terminal operations

This runbook covers the local research workspace only. It does not enable
recommendations, autonomous trading or broker execution.

## Start and health check

From the repository root:

```bash
python3 server.py
curl --fail http://127.0.0.1:8510/api/health
```

The health endpoint performs no provider requests. A ready response requires:

- SQLite `PRAGMA quick_check(1)` returns `ok`;
- the database remains in WAL journal mode;
- `index.html`, `styles.css`, `reference-universes.js` and
  `earnings-template.csv` exist in `dist/`;
- the v23 EOD retry and backup contracts are active.

A degraded response uses HTTP 503 and lists every failed asset or database
check. Do not replace a missing dataset with a neutral value to make health pass.

## EOD update behaviour

The browser runs 15 named stages in a fixed order. Progress and the active stage
remain visible on the EOD button. Each failed stage is attempted once more. A
stage that fails both attempts remains in the completion notice; unrelated
stages continue so one external source cannot silently block all local refreshes.

After the data stages, every workspace and any in-memory portfolio analysis are
refreshed. Stale, partial and missing evidence remains visible in its owning
workspace.

## Verify the local store

```bash
python3 scripts/backup_eod_store.py --verify-only
```

The command prints the integrity result, journal mode, schema version, database
size, table inventory and row counts. It does not contact external providers.

## Create a backup

Choose an explicit new destination outside the live database path:

```bash
python3 scripts/backup_eod_store.py \
  --destination /absolute/path/pg_terminal_eod-YYYY-MM-DD.sqlite3
```

The command uses SQLite's online backup API, verifies the completed copy with
`PRAGMA quick_check(1)` and refuses to overwrite an existing file. Never copy
only a live WAL file or use the live database path as the destination.

## Recovery drill

1. Stop the local server.
2. Verify the candidate backup with `--source BACKUP --verify-only`.
3. Preserve the current live database separately; do not overwrite the only
   available copy.
4. Copy the verified backup to a new test path.
5. Start a disposable server checkout pointing at that restored copy, or create
   an `EODStore` against it and rerun `--verify-only`.
6. Confirm `/api/health`, representative index coverage and the latest stored
   session before making the restored copy live.

The supported backup command is intentionally create-only. Choosing which file
becomes the live store is a manual recovery decision.

## Release checklist

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

Then verify:

- `/api/health` reports `ready`;
- a clean browser load has no console errors;
- an EOD update shows stage progress and final failures or recovered retries;
- stale source data remains marked stale after refresh;
- no recommendation, target, position size, order or broker action is emitted;
- the working tree contains only intentional release changes.

