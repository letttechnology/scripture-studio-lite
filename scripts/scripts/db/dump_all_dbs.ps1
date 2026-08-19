# Dumps all PostgreSQL databases for the Interlinear Bible project.
# Creates a timestamped folder for each run to keep versioned backups.

# --- Configuration ---
$pgUser = "postgres"
$pgDumpPath = "D:\PostgreSQL\18\bin\pg_dump.exe" # Make sure this path is correct for your system
$databases = @(
    "interlinear_bible_studio_dev",
    "interlinear_bible_reader_content_dev",
    "interlinear_bible_reader_user_dev",
    "interlinear_bible_lexis_dev",
    "AI_database"
)

$dumpBaseDir = "D:\workspace\interlinear-bible-project\db_dumps"

# --- Execution ---
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$dumpDir = Join-Path -Path $dumpBaseDir -ChildPath $timestamp

if (-not (Test-Path $dumpDir)) {
    New-Item -ItemType Directory -Path $dumpDir | Out-Null
}

Write-Host "Dumping databases to: $dumpDir"

foreach ($db in $databases) {
    $dumpFile = Join-Path -Path $dumpDir -ChildPath "$($db).sql"
    Write-Host "Dumping database '$db' to '$dumpFile'..."
    & $pgDumpPath -U $pgUser -d $db -f $dumpFile --no-password --format=plain --clean --if-exists
}

Write-Host "All database dumps completed successfully."