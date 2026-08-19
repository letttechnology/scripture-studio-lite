import os
import subprocess
from datetime import datetime
import platform
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv is not installed. Please run 'pip install python-dotenv'", file=sys.stderr)
    sys.exit(1)


# --- Configuration ---
PG_USER = "postgres"
DATABASES = [
    "interlinear_bible_studio_dev",
    "interlinear_bible_reader_content_dev",
    "interlinear_bible_reader_user_dev",
    "interlinear_bible_lexis_dev",
    "AI_database"
]
DUMP_BASE_DIR = r"D:\workspace\interlinear-bible-project\db_dumps"

def get_pg_dump_path():
    """Determines the path to pg_dump based on the operating system."""
    system = platform.system()
    if system == "Windows":
        # Assuming a default installation path for PostgreSQL 18. Adjust if necessary.
        return r"D:\PostgreSQL\18\bin\pg_dump.exe"
    elif system in ("Linux", "Darwin"):
        # On Linux/macOS, pg_dump is typically in the system's PATH.
        return "pg_dump"
    else:
        print(f"Unsupported operating system: {system}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main function to perform the database dumps."""
    pg_dump_path = get_pg_dump_path()

    # Load environment variables from .env file at the project root
    # The script is in scripts/db, so we go up two levels.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dotenv_path = os.path.join(project_root, '.env')
    load_dotenv(dotenv_path=dotenv_path)

    # Explicitly get the password from the loaded environment variables.
    # This is more reliable than relying on subprocess inheritance.
    pg_password = os.environ.get("DB_PASS")
    if not pg_password:
        print("Error: DB_PASS not found in .env file or environment.", file=sys.stderr)
        sys.exit(1)

    # Create the timestamped backup directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dump_dir = os.path.join(DUMP_BASE_DIR, timestamp)
    
    try:
        os.makedirs(dump_dir, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory {dump_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Dumping databases to: {dump_dir}")

    for db in DATABASES:
        dump_file = os.path.join(dump_dir, f"{db}.sql")
        print(f"Dumping database '{db}' to '{dump_file}'...")

        # Set the PGPASSWORD environment variable for the subprocess
        # This is the standard way to provide a password to pg_dump non-interactively.
        env = os.environ.copy()
        env['PGPASSWORD'] = pg_password

        # Command no longer needs --no-password, as PGPASSWORD will be used.
        command = [pg_dump_path, "-U", PG_USER, "-d", db, "-f", dump_file, "--format=plain", "--clean", "--if-exists"]

        # Run the command with the modified environment
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env)

        if result.returncode != 0:
            print(f"Error dumping database '{db}':", file=sys.stderr)
            print(f"  Exit code: {result.returncode}", file=sys.stderr)
            print(f"  Command: {' '.join(command)}", file=sys.stderr)
            print(f"  Stderr: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    print("\nAll database dumps completed successfully.")

if __name__ == "__main__":
    main()