# Runbook: Phoenix database backup and restore

| | |
|---|---|
| Backup | CronJob `phoenix/timescale-backup`, nightly 21:15 (zone in the manifest), `pg_dump -Fc` of database `phoenix` |
| Where | PVC `timescale-backups` (local-path-retain), mounted at `/backups` in the backup Job and in `timescale-0` |
| Retention | 14 days on the PVC. Weekly: copy the newest dump off the box (below) |
| RPO / RTO | 24 h / about 15 min for a restore |

## Check the last backup
```bash
kubectl -n phoenix get cronjob timescale-backup
kubectl -n phoenix get jobs --sort-by=.metadata.creationTimestamp | tail -3
kubectl -n phoenix exec timescale-0 -c timescale -- ls -lh /backups
```

## Back up now
```bash
J=backup-manual-$(date +%Y%m%d%H%M)
kubectl -n phoenix create job --from=cronjob/timescale-backup "$J"
kubectl -n phoenix wait --for=condition=complete "job/$J" --timeout=300s
kubectl -n phoenix logs "job/$J"
```

## Restore test (into a scratch database; production data untouched)
```bash
kubectl -n phoenix exec -i timescale-0 -c timescale -- sh -s <<'SH'
set -eu
export PGPASSWORD="$POSTGRES_PASSWORD" PGHOST=127.0.0.1 PGUSER=postgres
latest=$(ls -1t /backups/phoenix-*.dump | head -1); echo "restoring $latest"
psql -q -c "DROP DATABASE IF EXISTS phoenix_restore_test" -c "CREATE DATABASE phoenix_restore_test"
psql -q -d phoenix_restore_test -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()"
pg_restore --no-owner --role=postgres -d phoenix_restore_test "$latest"
psql -q -d phoenix_restore_test -c "SELECT timescaledb_post_restore()"
for t in $(psql -Atd phoenix -c "select tablename from pg_tables where schemaname='public' order by 1"); do
  a=$(psql -Atd phoenix -c "select count(*) from public.\"$t\""); b=$(psql -Atd phoenix_restore_test -c "select count(*) from public.\"$t\"")
  [ "$a" = "$b" ] && echo "OK   $t $a" || echo "DIFF $t live=$a restored=$b"
done
psql -q -c "DROP DATABASE phoenix_restore_test"
SH
```
Expected: every table `OK` (a `DIFF` is only acceptable for rows written after the dump).

## Real restore (database "phoenix" lost or corrupted)
1. Stop writers: set `replicaCount: 0` and the worker `replicas: 0` in `apps/command-center/overlays/halo/values.yaml`, push.
2. Run the restore block above with `phoenix` instead of `phoenix_restore_test` (DROP/CREATE with `OWNER phoenix`).
3. Revert the replica change (git revert), push; check `/readyz`.

## Copy off the box (weekly)
```bash
f=$(kubectl -n phoenix exec timescale-0 -c timescale -- sh -c 'ls -1t /backups/phoenix-*.dump | head -1')
kubectl -n phoenix cp -c timescale "timescale-0:$f" "/mnt/d/lab-backups/$(basename "$f")"
```

## Drill log
| Date | Test | Result | Notes |
|---|---|---|---|
| YYYY-MM-DD | restore test | | |
