# shadow-db-swap.ps1
#
# Zero(near-zero)-downtime database refresh: build a new "shadow" copy of a
# database alongside the live one, validate it, then swap names in a single
# instant. The live database is untouched until the final rename, and any
# OTHER database in the same cluster is never touched at all — Postgres has
# no cross-database locking, so this only affects connections to -TargetDb.
#
# Confirmed from the actual project config (2026-08-01):
#   - The importer (interlinear-bible-importer) writes to TWO databases:
#       interlinear_bible_reader_content_dev
#       interlinear_bible_lexis_dev
#     Both are static/rebuildable — safe targets for this script.
#   - interlinear_bible_reader_user_dev is the LIVE database (reader
#     service's separate "user" datasource, per interlinear-bible-reader's
#     application-dev.yml). The importer never writes to it. NEVER pass
#     this as -TargetDb.
#   - All databases live in one Postgres cluster (StatefulSet "postgres",
#     Service "postgres-service", port 5432 — k8s/base/20-postgres.yaml).
#
# Since content and lexis each have their own dump file, run this script
# TWICE — once per database — back to back:
#   .\shadow-db-swap.ps1 -TargetDb interlinear_bible_reader_content_dev -DumpFile D:\path\to\reader_content.dump
#   .\shadow-db-swap.ps1 -TargetDb interlinear_bible_lexis_dev          -DumpFile D:\path\to\lexis.dump
#
# PREREQUISITE — run in a separate terminal and leave it open the whole time:
#   kubectl port-forward svc/postgres-service 5433:5432 -n interlinear-bible-dev
#
# DumpFile must be a custom-format dump (pg_dump -F c ...), matching the
# convention in backup-dev-to-test.ps1 — NOT the plain-format .sql output
# from dump_all_dbs.py/.ps1 (pg_restore can't read plain-format dumps).
#
# This is a DRAFT — per project DB rules, do not run this against the cluster
# without explicit go-ahead. It prompts for confirmation before the cutover
# step regardless.

param(
    [Parameter(Mandatory=$true)]
    [string]$TargetDb,

    [Parameter(Mandatory=$true)]
    [string]$DumpFile,

    [string]$PgHost = "localhost",
    [int]$PgPort = 5433,
    [string]$PgUser = "postgres"
)

$PSQL       = "D:\PostgreSQL\18\bin\psql.exe"
$PG_RESTORE = "D:\PostgreSQL\18\bin\pg_restore.exe"
$CREATEDB   = "D:\PostgreSQL\18\bin\createdb.exe"

if (-not $env:PGPASSWORD) {
    $env:PGPASSWORD = $env:DB_PASS
}
if (-not $env:PGPASSWORD) {
    Write-Error "No password set. Set `$env:DB_PASS or `$env:PGPASSWORD before running."
    exit 1
}

$NewDb = "${TargetDb}_new"
$OldDb = "${TargetDb}_old"

Write-Host "=== [1/5] Create shadow database: $NewDb ==="
& $CREATEDB -h $PgHost -p $PgPort -U $PgUser $NewDb
if ($LASTEXITCODE -ne 0) { Write-Error "createdb failed"; exit 1 }

Write-Host ""
Write-Host "=== [2/5] Restore dump into shadow database ==="
& $PG_RESTORE -h $PgHost -p $PgPort -U $PgUser -d $NewDb $DumpFile
# pg_restore exits non-zero on warnings (e.g. role ownership) — only fail on hard errors
if ($LASTEXITCODE -gt 1) { Write-Error "pg_restore failed (exit $LASTEXITCODE)"; exit 1 }

Write-Host ""
Write-Host "=== [3/5] VALIDATE ==="
Write-Host "Shadow database '$NewDb' is loaded and NOT yet live. Point a local app"
Write-Host "instance or run spot-check queries against it now, in another window."
$confirm = Read-Host "Type 'yes' to proceed with the cutover, anything else to abort"
if ($confirm -ne "yes") {
    Write-Host "Aborted. '$NewDb' left in place for inspection. Nothing live was touched."
    exit 0
}

Write-Host ""
Write-Host "=== [4/5] Cutover (atomic rename) ==="
& $PSQL -h $PgHost -p $PgPort -U $PgUser -d postgres -c `
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TargetDb';"

& $PSQL -h $PgHost -p $PgPort -U $PgUser -d postgres -c `
    "ALTER DATABASE $TargetDb RENAME TO $OldDb;"
if ($LASTEXITCODE -ne 0) { Write-Error "Rename of live DB to _old failed — aborting before touching $NewDb"; exit 1 }

& $PSQL -h $PgHost -p $PgPort -U $PgUser -d postgres -c `
    "ALTER DATABASE $NewDb RENAME TO $TargetDb;"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Rename of shadow DB to live name failed — rolling back old name so the app isn't left without a database"
    & $PSQL -h $PgHost -p $PgPort -U $PgUser -d postgres -c "ALTER DATABASE $OldDb RENAME TO $TargetDb;"
    exit 1
}

Write-Host ""
Write-Host "=== [5/5] Done ==="
Write-Host "'$TargetDb' now serves the new data. '$OldDb' is kept for rollback."
Write-Host ""
Write-Host "Rollback if something's wrong:"
Write-Host "  psql -h $PgHost -p $PgPort -U $PgUser -d postgres -c ""ALTER DATABASE $TargetDb RENAME TO ${TargetDb}_bad;"""
Write-Host "  psql -h $PgHost -p $PgPort -U $PgUser -d postgres -c ""ALTER DATABASE $OldDb RENAME TO $TargetDb;"""
Write-Host ""
Write-Host "Once confirmed good, drop the old copy:"
Write-Host "  dropdb -h $PgHost -p $PgPort -U $PgUser $OldDb"
