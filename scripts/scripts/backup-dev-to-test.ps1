# backup-dev-to-test.ps1
# Snapshots interlinear_bible_dev into interlinear_bible_test.
# Run before integration tests to ensure test DB has current dev data and correct Flyway checksums.

$PSQL      = "D:\PostgreSQL\18\bin\psql.exe"
$PG_DUMP   = "D:\PostgreSQL\18\bin\pg_dump.exe"
$PG_RESTORE = "D:\PostgreSQL\18\bin\pg_restore.exe"
$DUMP_FILE = "$env:TEMP\interlinear_bible_dev_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump"

$env:PGPASSWORD = "letttech"

Write-Host "=== [1/4] Dump interlinear_bible_dev ==="
& $PG_DUMP -U postgres -F c -d interlinear_bible_dev -f $DUMP_FILE
if ($LASTEXITCODE -ne 0) { Write-Error "pg_dump failed"; exit 1 }
Write-Host "Dump written to: $DUMP_FILE"

Write-Host ""
Write-Host "=== [2/4] Drop interlinear_bible_test ==="
& $PSQL -U postgres -d postgres -c "DROP DATABASE IF EXISTS interlinear_bible_test WITH (FORCE);"
if ($LASTEXITCODE -ne 0) { Write-Error "DROP DATABASE failed"; exit 1 }

Write-Host ""
Write-Host "=== [3/4] Recreate interlinear_bible_test ==="
& $PSQL -U postgres -d postgres -c "CREATE DATABASE interlinear_bible_test OWNER postgres;"
if ($LASTEXITCODE -ne 0) { Write-Error "CREATE DATABASE failed"; exit 1 }

Write-Host ""
Write-Host "=== [4/4] Restore to interlinear_bible_test ==="
& $PG_RESTORE -U postgres -d interlinear_bible_test $DUMP_FILE
# pg_restore exits non-zero on warnings (e.g. role ownership) — only fail on hard errors
if ($LASTEXITCODE -gt 1) { Write-Error "pg_restore failed (exit $LASTEXITCODE)"; exit 1 }

Write-Host ""
Write-Host "=== Done ==="
Write-Host "interlinear_bible_test is now a clone of interlinear_bible_dev."
Write-Host "Flyway checksums for all versions match the current migration files."
Write-Host ""
Write-Host "Next: mvn test -Dtest=CorpusSenseSelectionServiceE2eTest -Dspring.profiles.active=integration,admin"
