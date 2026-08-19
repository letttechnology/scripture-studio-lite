import os
import subprocess
import platform
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv is not installed. Please run 'pip install python-dotenv'", file=sys.stderr)
    sys.exit(1)

# --- Configuration ---
PG_USER = "postgres"
DUMP_BASE_DIR = r"D:\workspace\interlinear-bible-project\db_dumps"

def get_pg_bin_path():
    """Determines the path to the PostgreSQL bin directory."""
    system = platform.system()
    if system == "Windows":
        # Assuming a default installation path for PostgreSQL 18. Adjust if necessary.
        return Path(r"D:\PostgreSQL\18\bin")
    elif system in ("Linux", "Darwin"):
        # On Linux/macOS, pg_dump is typically in the system's PATH.
        return Path("") # An empty path will resolve executables from the system PATH
    else:
        print(f"Unsupported operating system: {system}", file=sys.stderr)
        sys.exit(1)

def find_latest_dump_dir():
    """Finds the most recent dump directory."""
    if not os.path.isdir(DUMP_BASE_DIR):
        print(f"Error: Dump directory not found at {DUMP_BASE_DIR}", file=sys.stderr)
        return None
    
    all_subdirs = [d for d in os.listdir(DUMP_BASE_DIR) if os.path.isdir(os.path.join(DUMP_BASE_DIR, d))]
    if not all_subdirs:
        print(f"Error: No backups found in {DUMP_BASE_DIR}", file=sys.stderr)
        return None
        
    latest_dump = sorted(all_subdirs)[-1]
    return os.path.join(DUMP_BASE_DIR, latest_dump)

def main():
    """Main function to restore the latest database dumps."""
    pg_bin_path = get_pg_bin_path()
    dropdb_path = pg_bin_path / "dropdb.exe" if platform.system() == "Windows" else "dropdb"
    createdb_path = pg_bin_path / "createdb.exe" if platform.system() == "Windows" else "createdb"
    psql_path = pg_bin_path / "psql.exe" if platform.system() == "Windows" else "psql"

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=project_root / '.env')

    pg_password = os.environ.get("DB_PASS")
    if not pg_password:
        print("Error: DB_PASS not found in .env file or environment.", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    env['PGPASSWORD'] = pg_password

    latest_dump_dir = find_latest_dump_dir()
    if not latest_dump_dir:
        sys.exit(1)

    print(f"Restoring databases from: {latest_dump_dir}")

    for dump_file_name in os.listdir(latest_dump_dir):
        if dump_file_name.endswith(".sql"):
            db_name = dump_file_name.replace(".sql", "")
            dump_file_path = os.path.join(latest_dump_dir, dump_file_name)
            print(f"\n--- Restoring database '{db_name}' ---")
            
            subprocess.run([str(dropdb_path), "-U", PG_USER, "--if-exists", db_name], check=True, env=env)
            subprocess.run([str(createdb_path), "-U", PG_USER, db_name], check=True, env=env)
            subprocess.run([str(psql_path), "-U", PG_USER, "-d", db_name, "-f", dump_file_path], check=True, env=env)

    print("\nAll databases restored successfully.")

if __name__ == "__main__":
    main()