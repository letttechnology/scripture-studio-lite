# compare-ai-content.ps1  (story #284, Phase A)
#
# Compares the three AI content-cache tables in interlinear_bible_ai_dev between
# the LOCAL Postgres (port 5432) and the K8S cluster Postgres (port-forwarded to
# 5433), reporting row counts and keys present on one side only. With -Sync, also
# merges k8s rows into local via INSERT ... ON CONFLICT DO NOTHING — safe because
# all three tables use their natural keys as PRIMARY KEY (V1__ai_cache_tables.sql),
# so existing local rows are never overwritten and nothing is deleted.
#
# Also spot-checks row counts of the lexis/content source tables both sides, since
# local target discovery (PopulateAiContentCheck) depends on those being current.
#
# PREREQUISITE — run in a separate terminal and leave it open:
#   kubectl port-forward svc/postgres-service 5433:5432 -n interlinear-bible-dev
#
# Usage:
#   .\compare-ai-content.ps1           # compare only (read-only on both sides)
#   .\compare-ai-content.ps1 -Sync     # compare, then merge k8s -> local
#   .\compare-ai-content.ps1 -Push     # compare, then merge local -> k8s
#
# Credentials: $env:DB_USER/$env:DB_PASS, falling back to the workspace .env
# (same convention as shadow-db-swap.ps1 / the populate scripts).

param(
    [switch]$Sync,
    [switch]$Push,
    [int]$LocalPort = 5432,
    [int]$K8sPort = 5433
)

if ($Sync -and $Push) {
    Write-Error "Use -Sync (k8s -> local) or -Push (local -> k8s), not both in one run."
    exit 1
}

$PSQL = "D:\PostgreSQL\18\bin\psql.exe"
$AI_DB = "interlinear_bible_ai_dev"

# --- credentials -------------------------------------------------------------
if (-not $env:DB_USER -or -not $env:DB_PASS) {
    $envFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ".env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*(DB_USER|DB_PASS)\s*=\s*(.+?)\s*$') {
                $name = $Matches[1]; $value = $Matches[2].Trim('"').Trim("'")
                if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) {
                    Set-Item "env:$name" $value
                }
            }
        }
    }
}
if (-not $env:DB_USER -or -not $env:DB_PASS) {
    Write-Error "DB_USER/DB_PASS not set and not found in workspace .env"
    exit 1
}
$env:PGPASSWORD = $env:DB_PASS
$PgUser = $env:DB_USER

# table -> ordered key column list (natural PK per V1__ai_cache_tables.sql)
$Tables = [ordered]@{
    "word_breakdown"          = @("strongs_id", "morph_code")
    "morph_suffix_explanation" = @("morph_code")
    "word_insight"            = @("strongs_id")
}

function Invoke-Psql([int]$Port, [string]$Db, [string]$Query) {
    $out = & $PSQL -h localhost -p $Port -U $PgUser -d $Db -t -A -F "|" -c $Query 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "psql (port $Port, db $Db) failed: $out"
    }
    return $out
}

function Test-Side([int]$Port, [string]$Label) {
    try {
        Invoke-Psql $Port $AI_DB "SELECT 1" | Out-Null
        return $true
    } catch {
        Write-Error "$Label Postgres not reachable on port $Port. $_"
        if ($Port -eq $K8sPort) {
            Write-Host "Start the port-forward first:"
            Write-Host "  kubectl port-forward svc/postgres-service ${K8sPort}:5432 -n interlinear-bible-dev"
        }
        return $false
    }
}

if (-not (Test-Side $LocalPort "LOCAL")) { exit 1 }
if (-not (Test-Side $K8sPort  "K8S"))   { exit 1 }

# --- compare AI content tables ----------------------------------------------
Write-Host ""
Write-Host "=== AI content tables: $AI_DB (LOCAL :$LocalPort vs K8S :$K8sPort) ==="
$totalOnlyK8s = 0
$totalOnlyLocal = 0

foreach ($table in $Tables.Keys) {
    $keyCols = $Tables[$table] -join ", "
    $localCount = [int](Invoke-Psql $LocalPort $AI_DB "SELECT count(*) FROM $table")
    $k8sCount   = [int](Invoke-Psql $K8sPort  $AI_DB "SELECT count(*) FROM $table")

    $localKeys = Invoke-Psql $LocalPort $AI_DB "SELECT $keyCols FROM $table ORDER BY $keyCols"
    $k8sKeys   = Invoke-Psql $K8sPort  $AI_DB "SELECT $keyCols FROM $table ORDER BY $keyCols"
    $localSet = [System.Collections.Generic.HashSet[string]]::new([string[]]@($localKeys))
    $k8sSet   = [System.Collections.Generic.HashSet[string]]::new([string[]]@($k8sKeys))

    $onlyK8s   = @($k8sSet   | Where-Object { -not $localSet.Contains($_) })
    $onlyLocal = @($localSet | Where-Object { -not $k8sSet.Contains($_) })
    $totalOnlyK8s += $onlyK8s.Count
    $totalOnlyLocal += $onlyLocal.Count

    Write-Host ""
    Write-Host "--- $table (key: $keyCols) ---"
    Write-Host ("  rows: local={0}  k8s={1}  only-in-k8s={2}  only-in-local={3}" -f
        $localCount, $k8sCount, $onlyK8s.Count, $onlyLocal.Count)
    if ($onlyK8s.Count -gt 0) {
        Write-Host "  only-in-k8s sample: $(($onlyK8s | Select-Object -First 5) -join '; ')"
    }
    if ($onlyLocal.Count -gt 0) {
        Write-Host "  only-in-local sample: $(($onlyLocal | Select-Object -First 5) -join '; ')"
    }
}

# --- spot-check source DBs (discovery inputs) --------------------------------
Write-Host ""
Write-Host "=== Source DB spot-checks (row counts, local vs k8s) ==="
$SourceChecks = @(
    @{ Db = "interlinear_bible_lexis_dev";          Table = "lexeme" },
    @{ Db = "interlinear_bible_lexis_dev";          Table = "token_morphology" },
    @{ Db = "interlinear_bible_lexis_dev";          Table = "lexeme_meaning" },
    @{ Db = "interlinear_bible_reader_content_dev"; Table = "verse_word" }
)
foreach ($check in $SourceChecks) {
    try {
        $l = [int](Invoke-Psql $LocalPort $check.Db "SELECT count(*) FROM $($check.Table)")
        $k = [int](Invoke-Psql $K8sPort  $check.Db "SELECT count(*) FROM $($check.Table)")
        $flag = if ($l -eq $k) { "match" } else { "MISMATCH" }
        Write-Host ("  {0}.{1}: local={2}  k8s={3}  [{4}]" -f $check.Db, $check.Table, $l, $k, $flag)
    } catch {
        Write-Host "  $($check.Db).$($check.Table): check failed - $_"
    }
}

# --- optional merge: -Sync (k8s -> local) or -Push (local -> k8s) ------------
if (-not $Sync -and -not $Push) {
    Write-Host ""
    if ($totalOnlyK8s -gt 0 -or $totalOnlyLocal -gt 0) {
        Write-Host "Compare only (no changes made). -Sync merges $totalOnlyK8s k8s-only row(s) into local; -Push merges $totalOnlyLocal local-only row(s) into k8s."
    } else {
        Write-Host "Compare only (no changes made). Both sides already match."
    }
    exit 0
}

if ($Sync) {
    $srcPort = $K8sPort;   $dstPort = $LocalPort; $srcName = "k8s";   $dstName = "local"
} else {
    $srcPort = $LocalPort; $dstPort = $K8sPort;   $srcName = "local"; $dstName = "k8s"
}

Write-Host ""
Write-Host "=== Merging $srcName rows into $dstName (INSERT ... ON CONFLICT DO NOTHING) ==="
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
foreach ($table in $Tables.Keys) {
    $csv = Join-Path $env:TEMP "ai_sync_${table}_$stamp.csv"
    $sql = Join-Path $env:TEMP "ai_sync_${table}_$stamp.sql"

    & $PSQL -h localhost -p $srcPort -U $PgUser -d $AI_DB `
        -c "\copy (SELECT * FROM $table) TO '$csv' WITH (FORMAT csv)"
    if ($LASTEXITCODE -ne 0) { Write-Error "export of $table from $srcName failed"; exit 1 }

    @"
CREATE TEMP TABLE tmp_sync (LIKE $table);
\copy tmp_sync FROM '$csv' WITH (FORMAT csv)
INSERT INTO $table SELECT * FROM tmp_sync ON CONFLICT DO NOTHING;
"@ | Set-Content -Path $sql -Encoding UTF8

    $result = & $PSQL -h localhost -p $dstPort -U $PgUser -d $AI_DB -f $sql 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Error "merge into $dstName $table failed: $result"; exit 1 }
    $inserted = ($result | Select-String "^INSERT" | Select-Object -Last 1) -replace "INSERT 0 ", ""
    Write-Host "  ${table}: merged $inserted new row(s) into $dstName"

    Remove-Item $csv, $sql -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Done. Rerun with no switches to verify both sides now match. ==="
